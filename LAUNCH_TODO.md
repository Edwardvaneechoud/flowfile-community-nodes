# Launch TODO — flowfile-community-nodes

This registry is live for testing, but its CI currently installs the validator
from the Flowfile **feature branch** (`TEST_FLOWFILE_SPEC`) rather than a pinned
PyPI release. See `MAINTAINER_SETUP.md` for the full one-time setup.

## Remaining before real launch

- [ ] **Ship the PyPI release** of Flowfile that contains
      `flowfile_core.flowfile.community_nodes` (done in the Flowfile monorepo).
- [ ] **Pin `registry/config.json`** → set `validator_flowfile_version` **and**
      `min_supported_app_version` to that released version (X.Y.Z).
- [ ] **Revert the CI to the pinned PyPI install** in both workflows
      (grep `TODO(revert before launch)`):
  - `.github/workflows/validate-pr.yml` — the two "Install validator" steps
  - `.github/workflows/build-index.yml` — the "Install validator" step

  In each, change
  `pip install "$TEST_FLOWFILE_SPEC"`
  back to
  `pip install "flowfile==$(jq -r .validator_flowfile_version registry/config.json)"`,
  and remove the workflow-level `TEST_FLOWFILE_SPEC` env blocks.

## Already done (reference)

- [x] Repo pushed; branch protection / ruleset on `main` (validate + dry-run required,
      Repository-admin bypass); Discussions "Node Ratings" (Announcement type).
- [x] OAuth App registered with Device Flow enabled; client id baked into the app.
- [x] `REGISTRY_PUSH_TOKEN` PAT set — the `build-index` / `popularity` bots push
      `index.json` / `popularity.json` to protected `main`.
- [x] `validate-pr.yml` has a `workflow_dispatch` (inputs: `node_id`, `ref`) to run the
      current workflow against any branch — handy when a PR branch carries a stale copy.

## Notes

- A PR branch runs its **own** copy of the workflow (`pull_request` semantics), so a node
  PR opened before a workflow change carries the old workflow. Fix: **Update branch** on
  the PR (merges current `main` in), then its checks re-run on the fixed workflow.
