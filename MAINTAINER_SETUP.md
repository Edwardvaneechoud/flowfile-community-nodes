# Maintainer setup (one-time)

This checklist takes the scaffold from "generated locally" to "live registry". Do it once,
after the first PyPI release that ships the `flowfile_core.flowfile.community_nodes` module.
Nothing in the Flowfile app blocks on any of this — the app works against a local fixture
registry until the real repo exists.

## 0. Prerequisite: the validator must be on PyPI

The CI workflows install the validator with `pip install flowfile==<pin>` and run
`python -m flowfile_core.flowfile.community_nodes.cli`. That module ships in a Flowfile
release. **Until that release is on PyPI, CI cannot go green** — this is expected, not a
bug. Once it ships:

- [ ] Edit `registry/config.json` and replace **both** `FLOWFILE_VERSION_PLACEHOLDER …`
      values (`validator_flowfile_version` and `min_supported_app_version`) with the real
      version, e.g. `"0.4.0"`. The placeholder strings are deliberately un-parseable so a
      premature push fails loudly rather than silently pinning a nonexistent version.
- [ ] Regenerate `registry/manifest.schema.json` from the shipped model so it can never
      drift from the validator:
      ```bash
      pip install "flowfile==<version>"
      TESTING=True FLOWFILE_SKIP_STARTUP_MIGRATION=1 FLOWFILE_DB_PATH=/tmp/ff.db \
        python -c "import json; from flowfile_core.flowfile.community_nodes.models import manifest_json_schema; \
        print(json.dumps(manifest_json_schema(), indent=2))" > registry/manifest.schema.json
      ```
      (The committed schema was generated from the model with one field pattern omitted as a
      pre-release shim — regenerate from the released model to get the authoritative copy.)

## 1. Create the GitHub repo and push

- [ ] Create `edwardvaneechoud/flowfile-community-nodes` on GitHub (public, no auto-README —
      this scaffold has one).
- [ ] Push this directory to `main`.

## 2. Enable Discussions + the ratings category

- [ ] **Settings → General → Features → Discussions**: enable.
- [ ] In **Discussions → categories**, create a category named exactly **`Node Ratings`**
      with format **Announcement** (only maintainers/bot can open threads; anyone can react
      and comment). `scripts/refresh_popularity.py` reads 👍 reactions from threads in this
      category, one thread per node id.

## 3. Branch protection on `main`

- [ ] **Settings → Branches → Add rule** for `main`:
  - [ ] Require a pull request before merging, with **at least 1 approving review**.
  - [ ] Require status checks to pass; select the **`validate`** and **`dry-run`** checks
        (they appear in the list after `validate-pr.yml` has run once — open a throwaway PR
        to surface them, then add them here).
  - [ ] Require branches to be up to date before merging.
  - [ ] **Allow the GitHub Actions app to bypass** the PR requirement (or use a targeted
        bypass / ruleset exception). The `build-index` and `popularity` workflows commit
        `index.json` / `popularity.json` directly to `main` as the registry bot — they must
        not be blocked by the PR rule. Keep the bypass scoped to the Actions app only.

## 4. Actions security settings

- [ ] **Settings → Actions → General → Fork pull request workflows from outside
      collaborators**: set to **"Require approval for first-time contributors"** (ON). This
      is the gate that stops an unknown fork's first PR from running workflows automatically
      — a maintainer clicks "Approve and run" after a glance at the diff.
- [ ] Confirm **Workflow permissions** default to read-only (each workflow already declares
      the least privilege it needs at the job level).

## 5. Register the OAuth App for in-app publishing

The designer's **Publish → Connect GitHub** flow uses GitHub's device flow, which needs an
OAuth App client id. This is optional — without it, contributors can still publish by pasting
a personal access token or by downloading the bundle — but registering it enables the
one-click path.

- [ ] GitHub → **Settings → Developer settings → OAuth Apps → New OAuth App**.
- [ ] **Application name:** e.g. `Flowfile Community Publishing`.
- [ ] **Homepage URL:** the repo URL.
- [ ] **Authorization callback URL:** the repo URL — this field is **required** by GitHub but
      is **unused** by the device flow (any valid URL works).
- [ ] Tick **Enable Device Flow**.
- [ ] Register. **No client secret is needed or ever shipped** — the device flow uses only the
      public client id.
- [ ] Copy the **Client ID** and wire it in:
  - **Local testing:** set `FLOWFILE_COMMUNITY_GITHUB_CLIENT_ID=<client_id>` in the app's env.
  - **For a release:** set `COMMUNITY_GITHUB_CLIENT_ID_DEFAULT` in
    `flowfile_core/configs/settings.py` so it ships baked into the build.

## 6. Dependabot / action pinning

- [ ] `.github/dependabot.yml` is configured for weekly `github-actions` updates. The
      workflows pin every action to a **full commit SHA** with a `# vX.Y.Z` comment; let
      Dependabot bump those SHAs so pins stay fresh without hand-editing.

## 7. Polish

- [ ] Add repo **topics**: `flowfile`, `etl`, `data-engineering`, `polars`, `custom-nodes`,
      `community`.
- [ ] Add a link to this registry from the Flowfile docs (the community-nodes page) and from
      the Flowfile README.
- [ ] Update the badges placeholder in `README.md` with the three workflow badges once CI
      has run.

## Notes

- `index.json` and `popularity.json` are **CI-generated**. The versions committed in this
  scaffold are seed/placeholder copies (all-zeros commit hash, empty popularity); the first
  `build-index` / `popularity` run replaces them. There is no place for a header comment in
  JSON — this note is the record that they are machine-owned.
