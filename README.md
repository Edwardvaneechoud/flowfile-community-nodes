# Flowfile community nodes

A community registry of custom nodes for [Flowfile](https://github.com/edwardvaneechoud/Flowfile).
Each node is a small folder — a `node.py` written in the Node Designer, a
`manifest.json`, an icon and screenshots. Publishing is a pull request; once it is
reviewed and merged, the node appears in every Flowfile install under
**Catalog → Community Nodes**, ready to install with one click.

There is no server behind any of this: **git is the database, GitHub Actions is the
backend, the merge button is the security boundary, and the sha256 pins in `index.json`
are the root of trust the app verifies.**

<!-- badges placeholder: add validate-pr / build-index / popularity workflow badges once CI has run on main -->

## The life of a node, step by step

![The life of a community node — built in the Node Designer, submitted as a one-folder pull request, validated and dry-run by CI, reviewed and merged by a maintainer (merge = published), pinned by sha256 into the CI-rebuilt index.json, then browsed, consented to, verified and re-scanned before landing in every Flowfile palette](.github/images/node-lifecycle.svg)

This is the whole pipeline, end to end. Every step is automated except two: the
maintainer's review, and your consent when you install.

1. **Someone builds a node** in Flowfile's **Node Designer** and saves a test setup
   with it (sample inputs + settings baked into the file). That test setup is what CI
   later uses to actually run the node.
2. **They publish it as a pull request** to this repo — one PR, one `nodes/<id>/`
   folder. Three ways to get there: the app opens the PR for you (connect GitHub with a
   device code or a token), you fork and open it by hand, or you download a bundle zip
   and hand it to a maintainer. Details in [CONTRIBUTING.md](CONTRIBUTING.md).
3. **CI checks the PR.** A scope check enforces the one-PR-one-node rule, the
   `validate` job runs the same validator Flowfile ships (folder contract, manifest
   schema, identity rules, a pure-AST security scan), and the `dry-run` job executes
   the node's `process()` against its saved test setup in an ephemeral runner with a
   read-only token and no secrets. First PR to this repo? GitHub holds the checks
   until a maintainer clicks **Approve and run** — that's expected, not stuck.
4. **A maintainer reads the code** — the actual `node.py`, anything the scan flagged —
   and merges. **Merge = published.** There is no separate release step.
5. **CI rebuilds `index.json`** on `main`, re-pinning every file of every node by
   **sha256**, and commits it as the registry bot. Those pins are what make a tampered
   or swapped file impossible to install.
6. **Flowfile installs pick it up.** The app fetches `index.json`, shows the node under
   **Catalog → Community Nodes**, and on install shows a consent dialog with the
   author, source link, and any capabilities the scanner found (network, file writes,
   subprocess, …). On confirm your own Flowfile backend downloads the pinned files,
   **verifies the sha256**, re-scans the bytes, and adds the node to the local palette.
   Nothing runs until the node is placed in a flow. The app caches the index for an
   hour, so a fresh merge shows up on the next refresh — immediately if you click
   **Refresh** in the browse tab.
7. **Updates repeat the loop.** The author bumps the semver `version` and opens a new
   PR; CI rejects a version that doesn't strictly increase, and only the node's author
   or its listed maintainers may update it. If the new version needs more capabilities,
   installed users re-consent before the update applies.
8. **If a node turns out to be bad**, it goes on `registry/blocklist.json` (`blocked`
   for security, `yanked` to withdraw a bad version) and the next index build delists
   it — the app then refuses to install it, full stop, and shows anyone who already
   installed it a warning with an uninstall shortcut. Reports go through
   [SECURITY.md](SECURITY.md); takedowns are fast.

Community nodes are **not sandboxed** — an installed node runs in Flowfile's worker
with the same access your own code has. The scan and the review raise the bar; your
judgment at install time is still part of the security model. The full, honest version
of this trade-off is in [CONTRIBUTING.md §7](CONTRIBUTING.md#7-the-honest-security-model).

## What do you want to do?

| I want to… | Go to |
|---|---|
| **Install** a node | In the app: **Catalog → Community Nodes**. No GitHub account needed. Walkthrough in the [Flowfile docs](https://edwardvaneechoud.github.io/Flowfile/users/visual-editor/community-nodes.html). |
| **Publish** my node | Build it in the Node Designer, then follow [CONTRIBUTING.md](CONTRIBUTING.md) — the app can open the PR for you. |
| **Update** my node | Bump the version and publish again — [CONTRIBUTING.md §5](CONTRIBUTING.md#5-updating-your-node). |
| **Report** a malicious or broken node | [SECURITY.md](SECURITY.md) — private advisory for security, the *Report a node* issue form otherwise. |
| **See a complete example** | [`nodes/mood_emoji/`](nodes/mood_emoji/) — a full node folder: `node.py`, manifest, icon, screenshot, README. |
| **Run this registry** (maintainers) | [MAINTAINER_SETUP.md](MAINTAINER_SETUP.md). |

## Repository layout

```
nodes/<id>/              one folder per node
  node.py                the node (authored in the Node Designer)
  manifest.json          distribution metadata (validated against registry/manifest.schema.json)
  icon.png               optional 1:1 icon
  screenshots/*.png      optional screenshots
  README.md              optional per-node docs
registry/
  config.json            validator + app version pins, Python version
  categories.json        the controlled browse-category vocabulary
  blocklist.json         yanked / blocked nodes (security takedowns)
  manifest.schema.json   JSON Schema generated from Flowfile's CommunityManifest model
scripts/refresh_popularity.py   nightly ratings baker (stars + Discussion upvotes)
index.json               CI-generated node index with sha256 pins  (do not hand-edit)
popularity.json          CI-generated ratings snapshot             (do not hand-edit)
```

`index.json` and `popularity.json` are **generated by CI** after each merge — do not
edit them by hand in a node PR (a PR that touches them is rejected by the scope check).

## Community

- **Questions / show-and-tell:** [Flowfile Discussions](https://github.com/edwardvaneechoud/Flowfile/discussions)
- **Node ratings:** each indexed node has a Discussion in this repo's *Node Ratings*
  category — upvote the ones that work for you; the nightly job bakes those into
  `popularity.json`.

Licensed under [Apache-2.0](LICENSE). Individual nodes carry their own SPDX license in
their manifest (permissive licenses only — see CONTRIBUTING).
