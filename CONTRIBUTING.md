# Contributing a node

Thank you for sharing a node. Publishing here means anyone running Flowfile can install
your node in one click, so the bar is: **it works, it's yours to share, and its code is
readable and honest about what it does.** This page is the full contract.

## 1. Build and test it in the Node Designer

Author your node in Flowfile's **Node Designer** (not by hand — the designer produces the
canonical `node.py` the validator expects).

- Fill in **Publishing** metadata: `author` (your GitHub login), `version` (semver, e.g.
  `1.0.0`), and a few `tags`.
- Turn **"Save test setup with node" ON**. This bakes `example_inputs` and
  `example_settings` into the file. They are **required** — CI uses them to actually run
  your `process()` in a sandbox, and the app uses them for the preview. A node with no
  saved test setup is rejected.
- Give it an `intro` and an icon. A screenshot is strongly recommended (it's what people
  see when browsing).

## 2. Submit your node

The Node Designer can open the pull request for you — that's the easy path. You can also
drive Git by hand, or hand the node to a maintainer if you don't have a GitHub account.
Whichever path you take, the `<id>` is the slug of your node name (e.g. `Mood Emoji` →
`mood_emoji`) and is **permanent** — it is what installed flows store, so it can never
change after publish.

### The easy way — publish from the app (recommended)

In the designer, open **Publish**:

1. Pick your **license** and category, and add at least one **PNG** screenshot.
2. Click **Connect GitHub** and authorize with the short **device code** at
   `github.com/login/device` (or paste a classic personal access token with the
   `public_repo` scope).
3. Tick the confirmation checkbox and click **Create pull request**.

Flowfile forks this repository, commits your `nodes/<id>/` folder, and opens the PR against
`main` with you as the author — no local Git needed. Re-running with the same version links
to the open PR instead of duplicating it; bump the version to open a fresh one.

### By hand — fork, copy, and open the PR yourself

Prefer to drive Git yourself? Export the bundle and submit it manually.

1. In the designer, open **Publish** → pick your license and fill the form → **Download
   bundle**. You get a zip shaped exactly like a registry folder:

   ```
   nodes/<id>/
     node.py
     manifest.json
     icon.png
     screenshots/         (drop your screenshot PNG here)
     README.md
   ```

2. **Fork** this repository.
3. Copy your `nodes/<id>/` folder in. **One PR adds exactly one node folder** — no edits
   to `index.json`, `popularity.json`, `registry/`, `.github/`, or `scripts/` (CI's scope
   check rejects those in a node PR).
4. Add at least one **PNG** screenshot under `nodes/<id>/screenshots/` and reference it in
   your manifest (`screenshots: ["screenshots/<name>.png"]`). Media is **PNG-only** in this
   repo — no SVG (XSS vector), no JPEG/WebP.
5. Fill in the PR template checklist and open the PR against `main`.

### No GitHub account?

You can still contribute. In the designer, open **Publish** → **Download bundle**, then
share that zip with a maintainer — post it in the main Flowfile repo's
[Discussions](https://github.com/edwardvaneechoud/Flowfile/discussions). A maintainer opens
the PR for you, crediting you as the node's `author.name`.

## 3. What CI checks

Two automated jobs run on your PR (they only run the node you submitted, in an ephemeral
runner with a read-only token and no repository secrets):

**`validate`** runs the same validator Flowfile ships (`community_nodes.cli validate`):

- **Folder contract** — exactly `node.py` + `manifest.json`, optional PNG `icon.png` /
  `README.md` / `screenshots/*.png`; size caps; no SVG or other media types.
- **Manifest schema** — validates against `registry/manifest.schema.json`; a permissive
  SPDX **license** (MIT, Apache-2.0, BSD-2/3-Clause, MPL-2.0, Unlicense, CC0-1.0); a
  **category** from `registry/categories.json`.
- **Identity** — folder name == `manifest.id` == the slug of your node's name; the id is
  globally unique (not already in the index), is not a built-in node type, and is not
  blocklisted; the **PR author must be the manifest `author.github`** (or a listed
  maintainer).
- **Parse & examples** — `node.py` parses (designer or code-only), and it carries working
  `example_inputs` + `example_settings`.
- **Security scan** — a pure-AST scan (see below).
- **Image checks** — PNG magic bytes + dimensions, via the standard library.

**`dry-run`** actually executes your `process()` against `example_inputs` in a subprocess,
with output-shape / row-count / time caps, to prove the node runs.

### The security scan, in plain language

The scanner reads your code **without running it** and looks for two things.

**Deny families — these fail the PR outright.** Your node may not:

- Use dynamic code execution — `eval`, `exec`, or `compile`.
- Reach for imports indirectly — `__import__`, `importlib`, or `getattr`-on-builtins chains
  used to dodge the scanner.
- **Decode-then-execute** — feeding `base64` / `zlib` / `marshal` / `pickle` output into
  `exec`, or shipping opaque high-entropy blobs.
- Call into native code / FFI — `ctypes`, and friends.
- Shell out — `os.system`, `os.popen`, `subprocess(..., shell=True)`, or obfuscated
  subprocess calls; pty / reverse-shell shapes.
- Poke at the interpreter or environment wholesale — `sys._getframe`, enumerating
  `os.environ`, or installing packages at runtime (`pip`).

**Flag families — these are allowed but surfaced.** They show up as capability chips in the
install consent dialog, so users know what they're agreeing to:

- Network access (importing `httpx`, `requests`, `socket`, …).
- Filesystem writes.
- Reading specific named environment variables.
- `subprocess` with literal (non-shell) arguments.
- Deserializing data (`pickle.load`, …).
- Using a `SecretSelector`.

The scan blocks the cheap remote-code-execution idioms and makes capabilities visible; it
is **not** a sandbox and cannot prove a node is safe. That is what the human review below
is for.

## 4. Review and merge = published

A maintainer reviews the diff — the actual `node.py`, what it does, and anything the scan
flagged — and merges. On merge, a CI job rebuilds `index.json` (re-pinning every artifact
by sha256) and commits it as the registry bot. Your node is **live in the app within about
ten minutes** (the index is served with a short cache so takedowns and additions propagate
quickly).

## 5. Updating your node

To ship a new version, open a PR that edits **your** `nodes/<id>/` folder:

- **Bump `version`** — semver must strictly increase; CI rejects a non-increasing version.
- Update the `changelog` in your manifest.
- Only the node's **`author.github` or a listed maintainer** may update it.

If capabilities change between versions, users who have it installed re-consent before the
update applies.

## 6. Ownership and maintainers

- The `author.github` in your manifest owns the node.
- Add co-maintainers via the `maintainers` list in the manifest — any of them can publish
  updates.
- **Transferring ownership:** open a PR changing `author.github` (and/or `maintainers`);
  the current owner must approve it. A maintainer merges once the current owner has signed
  off in the PR.

## 7. The honest security model

This registry runs on the same trust model as Obsidian community plugins or Home Assistant
HACS: **git is the database, GitHub Actions is the backend, the merge button is the
security boundary, and the sha256 pins in `index.json` are the root of trust the app
verifies.** Community nodes are **not sandboxed** — an installed node runs in Flowfile's
worker with the same access your own code has. The AST scan blocks obvious attacks and
exposes capabilities, and every PR is human-reviewed before merge, but you are ultimately
trusting the node's author and the reviewer. Install nodes the way you'd run any code from
the internet: read what it does, and only install what you need. If you ever find a bad
node, see [SECURITY.md](SECURITY.md) — takedowns are fast.

By submitting a node you agree it is yours to share under the license you declare, and that
it is licensed to users under that license.
