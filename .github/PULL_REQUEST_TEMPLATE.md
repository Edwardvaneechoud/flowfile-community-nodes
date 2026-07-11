<!-- One PR adds or updates exactly ONE node folder (nodes/<id>/). Do not edit index.json,
     popularity.json, registry/, scripts/, or .github/ in a node PR — CI generates those. -->

## Node

- **Node id:** `nodes/<id>/`
- **New node** or **update** (bump version):
- **What does it do?** (one or two sentences)

## Author checklist

- [ ] I built and **dry-ran this node in the Node Designer** with **"Save test setup with
      node" ON**, so `node.py` carries working `example_inputs` + `example_settings`.
- [ ] The manifest `author.github` is **my** GitHub login (this PR's author), or I am a
      listed maintainer of this node.
- [ ] This PR adds/edits **only** `nodes/<id>/` — no changes to `index.json`,
      `popularity.json`, `registry/`, `scripts/`, or `.github/`.
- [ ] I added at least one **PNG** screenshot under `nodes/<id>/screenshots/` (no SVG).
- [ ] The node makes **no hidden network calls** and does nothing beyond what its
      description and the flagged capabilities say.
- [ ] For an update: I **bumped the semver `version`** and updated the `changelog`.
- [ ] I understand community nodes are **not sandboxed** — installed nodes run with the same
      access as my own code — and my node is honest about what it does.

## For the reviewer

<!-- Point the reviewer at anything worth a close look: unusual imports, why a capability is
     needed (network / filesystem / subprocess / secrets), non-obvious logic. -->
