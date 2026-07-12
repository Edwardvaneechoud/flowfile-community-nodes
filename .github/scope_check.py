#!/usr/bin/env python3
"""Classify a PR's changed files and enforce the one-PR-one-node contract.

Reads a newline-delimited changed-files list (produced by the workflow from
`git diff --name-only base...head`), decides whether the PR is a node / infra / docs change,
and rejects the shapes we don't allow. Emits `node_id` and `mode` to $GITHUB_OUTPUT for the
downstream validate/dry-run jobs. Stdlib only.

Rules:
- A node PR touches exactly one `nodes/<id>/` folder (never zero, never two).
- Only the maintainer may touch `index.json`, `popularity.json`, `registry/**`,
  `scripts/**`, or `.github/**` (these are CI-owned / infrastructure).
"""

import argparse
import os
import sys

MAINTAINER = "edwardvaneechoud"
# GitHub-reserved bot logins (unspoofable) allowed to update infra — Dependabot bumps
# the pinned action SHAs in .github/ and never touches node folders.
INFRA_AUTHORS = {MAINTAINER.lower(), "dependabot[bot]"}
RESTRICTED_EXACT = {"index.json", "popularity.json"}
RESTRICTED_PREFIXES = (".github/", "registry/", "scripts/")


def is_restricted(path: str) -> bool:
    return path in RESTRICTED_EXACT or path.startswith(RESTRICTED_PREFIXES)


def fail(message: str) -> None:
    print(f"scope check failed: {message}", file=sys.stderr)
    sys.exit(1)


def emit(node_id: str, mode: str) -> None:
    line = f"node_id={node_id}\nmode={mode}\n"
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as fh:
            fh.write(line)
    print(f"mode={mode} node_id={node_id or '(none)'}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("changed_files", help="file containing one changed path per line")
    parser.add_argument("--pr-author", default="", help="GitHub login of the PR author")
    args = parser.parse_args()

    with open(args.changed_files, encoding="utf-8") as fh:
        paths = [line.strip() for line in fh if line.strip()]
    if not paths:
        fail("no changed files detected")

    infra_allowed = args.pr_author.lower() in INFRA_AUTHORS
    node_ids = {p.split("/", 2)[1] for p in paths if p.startswith("nodes/") and len(p.split("/")) >= 3}
    restricted = [p for p in paths if is_restricted(p)]

    if restricted and not infra_allowed:
        fail(f"non-maintainer '{args.pr_author}' may not modify infrastructure files: {', '.join(sorted(restricted))}")

    if node_ids:
        if len(node_ids) != 1:
            fail(f"a PR must add or modify exactly one node folder; found: {', '.join(sorted(node_ids))}")
        emit(next(iter(node_ids)), "node")
    elif restricted:
        emit("", "infra")
    else:
        emit("", "docs")


if __name__ == "__main__":
    main()
