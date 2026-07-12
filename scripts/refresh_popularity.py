#!/usr/bin/env python3
"""Bake node ratings into popularity.json — repo stars + per-node Discussion upvotes.

Runs unattended nightly (see .github/workflows/popularity.yml). Stdlib only
(urllib + json + os) so it needs no install step. For every node in index.json it reads the
matching thread in the "Node Ratings" Discussions category (title == node id), collecting
discussion upvotes and comment counts; indexed nodes without a thread get one created. The
result is written sorted by id, and the script exits without writing when nothing changed.

Auth: GITHUB_TOKEN in the environment. Repo: GITHUB_REPOSITORY (owner/name), falling back to
the constant below. It is defensive by design — a missing token or a transient API error
leaves popularity.json untouched and exits 0 rather than failing the nightly job.
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

GRAPHQL_URL = "https://api.github.com/graphql"
RATINGS_CATEGORY = "Node Ratings"
DEFAULT_REPO = "edwardvaneechoud/flowfile-community-nodes"
SCHEMA_VERSION = 1


def log(message: str) -> None:
    print(f"[refresh_popularity] {message}", file=sys.stderr)


def graphql(token: str, query: str, variables: dict) -> dict | None:
    """POST a GraphQL request; return the ``data`` object or None on any failure."""
    payload = json.dumps({"query": query, "variables": variables}).encode("utf-8")
    request = urllib.request.Request(
        GRAPHQL_URL,
        data=payload,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "flowfile-community-nodes-popularity",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        log(f"request failed: {exc}")
        return None
    if body.get("errors"):
        log(f"graphql errors: {body['errors']}")
        return None
    return body.get("data")


REPO_QUERY = """
query($owner:String!, $name:String!, $cursor:String) {
  repository(owner:$owner, name:$name) {
    id
    stargazerCount
    discussionCategories(first:25) { nodes { id name } }
    discussions(first:50, after:$cursor) {
      pageInfo { hasNextPage endCursor }
      nodes {
        number
        title
        url
        category { name }
        comments { totalCount }
        upvoteCount
      }
    }
  }
}
"""

CREATE_DISCUSSION = """
mutation($repoId:ID!, $categoryId:ID!, $title:String!, $body:String!) {
  createDiscussion(input:{repositoryId:$repoId, categoryId:$categoryId, title:$title, body:$body}) {
    discussion { number url }
  }
}
"""


def fetch_repo_state(token: str, owner: str, name: str) -> dict | None:
    """Return {repo_id, stars, category_id, threads: {title: {...}}} or None on failure."""
    repo_id = None
    stars = 0
    category_id = None
    threads: dict[str, dict] = {}
    cursor = None
    while True:
        data = graphql(token, REPO_QUERY, {"owner": owner, "name": name, "cursor": cursor})
        if data is None or data.get("repository") is None:
            return None
        repo = data["repository"]
        repo_id = repo["id"]
        stars = repo["stargazerCount"]
        if category_id is None:
            for cat in repo["discussionCategories"]["nodes"]:
                if cat["name"] == RATINGS_CATEGORY:
                    category_id = cat["id"]
        for node in repo["discussions"]["nodes"]:
            if (node.get("category") or {}).get("name") != RATINGS_CATEGORY:
                continue
            threads[node["title"]] = {
                "upvotes": node["upvoteCount"],
                "comments": node["comments"]["totalCount"],
                "discussion_number": node["number"],
                "discussion_url": node["url"],
            }
        page = repo["discussions"]["pageInfo"]
        if not page["hasNextPage"]:
            break
        cursor = page["endCursor"]
    return {"repo_id": repo_id, "stars": stars, "category_id": category_id, "threads": threads}


def create_thread(token: str, repo_id: str, category_id: str, node_id: str, node_name: str, repo: str) -> dict | None:
    folder_url = f"https://github.com/{repo}/tree/main/nodes/{node_id}"
    body = (
        f"Ratings thread for the **{node_name}** node (`{node_id}`).\n\n"
        f"Source: {folder_url}\n\n"
        "Upvote this discussion if this node works for you."
    )
    data = graphql(
        token,
        CREATE_DISCUSSION,
        {"repoId": repo_id, "categoryId": category_id, "title": node_id, "body": body},
    )
    if data is None:
        return None
    discussion = (data.get("createDiscussion") or {}).get("discussion")
    if not discussion:
        return None
    return {
        "upvotes": 0,
        "comments": 0,
        "discussion_number": discussion["number"],
        "discussion_url": discussion["url"],
    }


def load_index_nodes(index_path: str) -> list[tuple[str, str]]:
    with open(index_path, encoding="utf-8") as fh:
        index = json.load(fh)
    nodes = []
    for entry in index.get("nodes", []):
        node_id = entry.get("id")
        if node_id:
            nodes.append((node_id, entry.get("node_name") or node_id))
    return nodes


def read_existing(out_path: str) -> dict | None:
    try:
        with open(out_path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Bake node ratings into popularity.json")
    parser.add_argument("--index", default="index.json")
    parser.add_argument("--out", default="popularity.json")
    args = parser.parse_args()

    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        log("GITHUB_TOKEN not set — leaving popularity.json untouched")
        return 0

    repo = os.environ.get("GITHUB_REPOSITORY", DEFAULT_REPO)
    if "/" not in repo:
        log(f"invalid GITHUB_REPOSITORY {repo!r} — using default {DEFAULT_REPO}")
        repo = DEFAULT_REPO
    owner, name = repo.split("/", 1)

    try:
        index_nodes = load_index_nodes(args.index)
    except (OSError, ValueError) as exc:
        log(f"cannot read index {args.index!r}: {exc}")
        return 0

    state = fetch_repo_state(token, owner, name)
    if state is None:
        log("could not fetch repo state — leaving popularity.json untouched")
        return 0

    threads = state["threads"]
    if state["category_id"] is None:
        log(f"category {RATINGS_CATEGORY!r} not found — cannot create missing threads (stars still updated)")

    node_popularity: dict[str, dict] = {}
    for node_id, node_name in index_nodes:
        thread = threads.get(node_id)
        if thread is None and state["category_id"] is not None:
            thread = create_thread(token, state["repo_id"], state["category_id"], node_id, node_name, repo)
            if thread is not None:
                log(f"created ratings thread for {node_id}")
        if thread is not None:
            node_popularity[node_id] = thread

    result = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": "",  # filled below only when we actually write
        "repo_stars": state["stars"],
        "nodes": {node_id: node_popularity[node_id] for node_id in sorted(node_popularity)},
    }

    existing = read_existing(args.out) or {}
    comparable_existing = {k: v for k, v in existing.items() if k != "generated_at"}
    comparable_new = {k: v for k, v in result.items() if k != "generated_at"}
    if comparable_existing == comparable_new:
        log("no change — popularity.json is up to date")
        return 0

    import datetime

    result["generated_at"] = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=2)
        fh.write("\n")
    log(f"wrote {args.out}: {len(result['nodes'])} node(s), {result['repo_stars']} stars")
    return 0


if __name__ == "__main__":
    sys.exit(main())
