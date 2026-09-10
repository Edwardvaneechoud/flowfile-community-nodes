# Contributing a node

Once a node is in this repo, anyone running Flowfile can install it with one click. So the
bar is simple: it works, it's yours to share, and the code is readable and honest about what
it does. This page explains how that works in practice.

## 1. Build and test it in the Node Designer

Build your node in Flowfile's Node Designer rather than writing `node.py` by hand. The
designer produces the file shape the validator expects.

- Fill in the Publishing metadata: `author` (your GitHub login), `version` (semver, e.g.
  `1.0.0`), and a few `tags`.
- Turn on "Save test setup with node". This stores `example_inputs` and `example_settings`
  in the file. They are required. CI uses them to actually run your `process()` in a
  sandbox, and the app uses them for the preview. Without them the node gets rejected.
- Add an `intro` and an icon. A screenshot helps a lot, since that's what people see when
  browsing.

## 2. Submit your node

The Node Designer can open the pull request for you, which is the easiest route. You can
also do it with Git yourself, or hand the node to a maintainer if you don't have a GitHub
account.

Whichever way you go, the `<id>` is the slug of your node name (`Mood Emoji` becomes
`mood_emoji`). It is permanent. Installed flows store that id, so it can't change after
publishing.

### Publish from the app (recommended)

In the designer, open Publish:

1. Pick a license and category, add at least one PNG screenshot, and optionally write the
   README and a changelog line in the form. An empty README ships as a TODO stub, and
   "Insert template" gives you the standard sections. The README is stored with the node
   and comes back when you reopen the modal. Installing a community node also brings its
   README along, so you edit it rather than retype it.
2. Click Connect GitHub and authorize with the device code at `github.com/login/device`,
   or paste a classic personal access token with the `public_repo` scope.
3. Tick the confirmation checkbox and click Create pull request.

Flowfile forks this repo, commits your `nodes/<id>/` folder, and opens the PR against
`main` with you as the author. No local Git needed. If you publish again with the same
version, the open PR is updated in place (files, title, and body), so you can keep
iterating on review feedback from the app. Bump the version if you want a fresh PR.

### By hand

If you'd rather drive Git yourself, export the bundle and submit it manually.

1. In the designer, open Publish, pick a license, fill in the form, upload your
   screenshots, and click Download bundle. You get a zip shaped like a registry folder:

   ```
   nodes/<id>/
     node.py
     manifest.json
     icon.png
     screenshots/1.png …  (the PNGs you uploaded, renumbered)
     README.md            (what you wrote in the form, or a TODO stub)
   HOW_TO_PUBLISH.md      (zip-only instructions, not part of the PR)
   ```

2. Fork this repository.
3. Copy your `nodes/<id>/` folder in and leave `HOW_TO_PUBLISH.md` out. One PR adds
   exactly one node folder. Don't touch `index.json`, `popularity.json`, `registry/`,
   `.github/`, or `scripts/`; CI's scope check rejects that in a node PR.
4. Make sure there's at least one PNG screenshot under `nodes/<id>/screenshots/` and that
   your manifest references it (`screenshots: ["screenshots/<name>.png"]`). This is already
   done if you uploaded one in the modal. Media is PNG only. No SVG (it's an XSS vector),
   and no JPEG or WebP.
5. Fill in the PR template checklist and open the PR against `main`.

### No GitHub account?

You can still contribute. Open Publish in the designer, click Download bundle, and share
the zip in the main Flowfile repo's
[Discussions](https://github.com/edwardvaneechoud/Flowfile/discussions). A maintainer will
open the PR for you and credit you as the node's `author.name`.

## 3. What CI checks

Two jobs run on your PR. They only look at the node you submitted, in a throwaway runner
with a read-only token and no repository secrets. If it's your first PR here, GitHub holds
the workflows until a maintainer clicks "Approve and run", so checks stuck on "awaiting
approval" are normal.

`validate` runs the same validator that ships with Flowfile (`community_nodes.cli validate`):

- Folder contract: exactly `node.py` and `manifest.json`, plus optional PNG `icon.png`,
  `README.md`, and `screenshots/*.png`. No SVG or other media. Size caps: `node.py` up to
  200 KiB, manifest 16 KiB, icon 256 KiB and 512 px per side, README 100 KiB, each
  screenshot 1 MiB and 2000 px per side, at most 5 screenshots, whole folder 6 MiB.
- Manifest schema: validates against `registry/manifest.schema.json`, needs a permissive
  SPDX license (MIT, Apache-2.0, BSD-2/3-Clause, MPL-2.0, Unlicense, CC0-1.0) and a
  category from `registry/categories.json`.
- Identity: folder name equals `manifest.id` equals the slug of your node's name. The id
  can't be a built-in node type or a blocklisted name. For a new node, the PR author must
  match the manifest `author.github`. For an update to an id already in the index, the PR
  author must be the node's `author.github` or one of its `maintainers`, and the version
  must strictly increase.
- Parse and examples: `node.py` parses (designer or code-only), and it has working
  `example_inputs` and `example_settings`.
- Dependencies: only a kernel-environment node may declare `dependencies`. Each spec must
  be a plain PyPI name with an optional extra and version constraint (`polars>=1.0`,
  `scikit-learn==1.5.0`). No URLs, no `git+`, no pip flags.
- Security scan: a pure AST scan, described below.
- Image checks: PNG magic bytes and dimensions, using the standard library.

`dry-run` actually executes your `process()` against `example_inputs` in a subprocess with
caps on output shape, row count, and time, to prove the node runs. For kernel nodes it
pip-installs your declared dependencies first, so a dependency that doesn't resolve fails
here too.

### The security scan, in plain language

The scanner reads your code without running it and looks for two kinds of things.

Deny families fail the PR outright. Your node may not:

- Use dynamic code execution: `eval`, `exec`, or `compile`.
- Import indirectly: `__import__`, `importlib`, or `getattr`-on-builtins chains meant to
  dodge the scanner.
- Decode then execute: feeding `base64`, `zlib`, `marshal`, or `pickle` output into `exec`,
  or shipping opaque high-entropy blobs.
- Call into native code or FFI, like `ctypes`.
- Shell out: `os.system`, `os.popen`, `subprocess(..., shell=True)`, obfuscated subprocess
  calls, or pty and reverse-shell shapes.
- Poke at the interpreter or environment wholesale: `sys._getframe`, enumerating
  `os.environ`, or installing packages at runtime with pip.

Flag families are allowed but surfaced. They show up as capability chips in the install
consent dialog so users know what they're agreeing to:

- Network access (importing `httpx`, `requests`, `socket`, and so on).
- Filesystem reads.
- Filesystem writes.
- Reading specific named environment variables.
- `subprocess` with literal, non-shell arguments.
- Deserializing data (`pickle.load` and friends).
- Building code at runtime (`setattr` with computed names and similar shapes the scanner
  can't fully inspect).
- Using a `SecretSelector`.

The scan blocks the cheap remote-code-execution tricks and makes capabilities visible. It
is not a sandbox and can't prove a node is safe. That's what the human review is for.

## 4. Review and merge

A maintainer reads the diff, mainly the actual `node.py`, what it does, and anything the
scan flagged, and then merges. On merge, a CI job rebuilds `index.json` (re-pinning every
artifact by sha256) and commits it as the registry bot, usually within a couple of minutes.
Running apps pick up the new index on their next refresh: right away when someone clicks
Refresh in the browse tab, and within about an hour otherwise, since the app caches the
index for an hour by default.

## 5. Updating your node

If your PR hasn't merged yet, just publish again from the app with the same version and the
open PR gets updated in place. On the manual path, push a new commit to your PR branch.

To ship a new version, open a PR that edits your `nodes/<id>/` folder:

- Bump `version`. Semver must strictly increase, and CI rejects anything else. The Publish
  modal shows the published version and offers one-click bumps.
- Update the `changelog` in your manifest. Installed users see it next to the update prompt.
- Only the node's `author.github` or a listed maintainer can update it.

After the merge, users who installed your node see "Update available" on its card. If the
capabilities changed between versions, they have to consent again before the update applies.

## 6. Ownership and maintainers

- The `author.github` in your manifest owns the node.
- Add co-maintainers through the `maintainers` list in the manifest. Any of them can publish
  updates.
- To transfer ownership, open a PR changing `author.github` and/or `maintainers`. The
  current owner has to approve it, and a maintainer merges once they've signed off.

## 7. The honest security model

This registry works the same way as Obsidian community plugins or Home Assistant HACS: git
is the database, GitHub Actions is the backend, the merge button is the security boundary,
and the sha256 pins in `index.json` are the root of trust the app verifies. Community nodes
are not sandboxed. An installed node runs in Flowfile's worker with the same access your own
code has. The AST scan blocks obvious attacks and exposes capabilities, and every PR is
reviewed by a person before merge, but in the end you are trusting the node's author and the
reviewer. Treat nodes like any other code from the internet: read what they do, and only
install what you need. If you ever find a bad node, see [SECURITY.md](SECURITY.md).
Takedowns are fast.

By submitting a node you agree it is yours to share under the license you declare, and that
it is licensed to users under that license.
