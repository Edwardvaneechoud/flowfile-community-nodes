# Maintainer setup (one-time)

This checklist takes the scaffold from "generated locally" to "live registry". Do it once,
after the first PyPI release that ships the `flowfile_core.flowfile.community_nodes` module.
Nothing in the Flowfile app blocks on any of this — the app works against a local fixture
registry until the real repo exists.

## 0. Prerequisite: the validator must be on PyPI

The CI workflows are meant to install the validator with `pip install flowfile==<pin>`
and run `python -m flowfile_core.flowfile.community_nodes.cli`. That module ships in a
Flowfile release. **Until that release is on PyPI, both workflows carry a
`TODO(revert before launch)`** and instead install the validator from the Flowfile
feature branch (`TEST_FLOWFILE_SPEC` in `validate-pr.yml` / `build-index.yml`) — CI runs
green off that branch today. Once the release ships:

- [ ] Edit `registry/config.json` and replace the `FLOWFILE_VERSION_PLACEHOLDER …` value
      of `validator_flowfile_version` with the real version, e.g. `"0.13.0"`
      (`min_supported_app_version` is already set). The placeholder string is
      deliberately un-parseable so a premature push fails loudly rather than silently
      pinning a nonexistent version.
- [ ] Revert the `TODO(revert before launch)` install steps in **both**
      `.github/workflows/validate-pr.yml` and `.github/workflows/build-index.yml` back to
      `pip install "flowfile==$(jq -r .validator_flowfile_version registry/config.json)"`
      and drop the `TEST_FLOWFILE_SPEC` env — otherwise CI silently keeps installing the
      feature branch.
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
      with format **Announcement** (only maintainers/bot can open threads; anyone can upvote
      and comment). `scripts/refresh_popularity.py` reads upvotes from threads in this
      category, one thread per node id.

## 3. Branch protection on `main`

- [ ] **Settings → Branches → Add rule** for `main`:
  - [ ] Require a pull request before merging, with **at least 1 approving review**.
  - [ ] Require status checks to pass; select the **`validate`** and **`dry-run`** checks
        (they appear in the list after `validate-pr.yml` has run once — open a throwaway PR
        to surface them, then add them here).
  - [ ] Require branches to be up to date before merging.
  - [ ] **Let the registry bot bypass the PR rule.** The `build-index` and `popularity`
        workflows commit `index.json` / `popularity.json` directly to `main`. GitHub rulesets
        do **not** expose the built-in `github-actions[bot]` as a bypass actor (only roles +
        installed apps), so the default `GITHUB_TOKEN` push is rejected (`GH013`). Instead:
    - [ ] Keep **Repository admin** in the ruleset **Bypass list** (default).
    - [ ] **Create a PAT** (Settings → Developer settings → Personal access tokens):
          fine-grained with **Contents: Read and write** on this repo, or classic with the
          `repo` scope. It authenticates as you (an admin), so its pushes bypass.
    - [ ] Add it as a repo secret named **`REGISTRY_PUSH_TOKEN`**
          (Settings → Secrets and variables → Actions → New repository secret).
          The two bot workflows check out with `token: ${{ secrets.REGISTRY_PUSH_TOKEN || github.token }}`
          and push as you once the secret exists (until then they fall back and the push is
          blocked, which is fine pre-launch).
    - [ ] *(Alternative, no secret)* regenerate `index.json` locally and `git push` it
          yourself after each merge — as an admin your direct push bypasses the ruleset.

## 4. Actions security settings

- [ ] **Settings → Actions → General → Fork pull request workflows from outside
      collaborators**: set to **"Require approval for first-time contributors"** (ON). This
      is the gate that stops an unknown fork's first PR from running workflows automatically
      — a maintainer clicks "Approve and run" after a glance at the diff.
- [ ] Confirm **Workflow permissions** default to read-only (each workflow already declares
      the least privilege it needs at the job level).

## 5. Register the OAuth App for in-app publishing

> **Already done for the default registry** — the client id is registered and baked into
> the app (`COMMUNITY_GITHUB_CLIENT_ID_DEFAULT` in `flowfile_core/configs/settings.py`),
> so device flow works out of the box. Keep this section as the recipe for re-registering
> or for a fork of the registry.

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

- `index.json` and `popularity.json` are **CI-generated** and machine-owned (there is no
  place for a header comment in JSON — this note is the record). `index.json` is already
  produced by the `build-index` bot on `main`; `popularity.json` is still the empty seed
  until the nightly `popularity` job first finds ratings to bake.
