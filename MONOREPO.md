# Sweatpants monorepo

Ref #30. `sweatpants/`, `pyproject.toml` and `tests/` remain the engine package.
`modules/<id>/` contains the four public modules, imported with an unsquashed
`git subtree add --prefix=modules` from sweatpants-modules main. Original commits
are reachable through the import's second parent (use `git log --all`, or subtree
history tooling, to inspect pre-import paths). `modules/README.md` is the catalog.
Private modules remain in sweatpants-modules-private; no private code belongs here.

## CI

`.github/workflows/homeboy.yml` runs engine tests and discovers every public
module with a `tests/` directory. Each module gets an isolated job, dependencies,
and the SDK installed from this checkout. Audio transcription is explicitly
excluded because torch/whisper/pyannote are too heavy for hosted CI. No tests or
passing status are fabricated for it. Currently font-builder has module tests.
The pure Bash changed-module detector tests also run in CI.

## Release and deployment

Release publishes an immutable `checkout-<40-character SHA>` GitHub Release for
each main commit (reruns reuse it). Deploy follows a successful Release workflow
and deploys that workflow's exact head SHA, never a moving main tip. Unattended
deployment requires `DEPLOY_AUTOMATION=enabled`. Manual dispatch defaults to dry
run, accepts a ref and an `all_modules` override, and resolves refs to SHAs before
SSH. Deployment concurrency and a server flock prevent overlapping writes.

Homeboy is pinned to `0.459.0`. Checked-in server/project configuration models
chubes.net, but uses root as required by the service/venv operations (the current
chubes.net config uses deploy). SSH requires `CHUBES_DEPLOY_SSH_KEY` and trusted
`CHUBES_DEPLOY_KNOWN_HOSTS`; obtain host keys through a trusted channel, not an
unauthenticated scan. Homeboy SSH executes reviewed main-branch deployment helpers
at an immutable SHA. Component packaging cannot express this existing shared venv,
systemd service, authenticated module installation, and successful-ref receipt,
so `deploy/scripts/deploy.sh` implements the permitted script fallback.

The script fetches a temporary mirror to calculate changed modules against
`/opt/sweatpants/deployed-ref`. Missing/unknown baseline selects all modules;
root-only changes select none; additions, edits and both sides of renames are
considered; deleted modules are not uninstalled. `all_modules` forces all.
The detector and tests adapt sweatpants-modules draft PR #15 for the `modules/`
prefix. Run `bash deploy/scripts/test-changed-modules.sh` locally.

Dry run only fetches a temporary mirror and prints the ref/module plan; it does
not create/update the production checkout, install packages, restart, call APIs
or advance the receipt. The lock and temporary files are transient.

A real deploy creates/updates `/opt/sweatpants/src` as a detached git checkout,
fails on a dirty checkout, installs that exact engine into the existing
`/opt/sweatpants/venv`, and restarts sweatpants. It validates the existing service
user, command/bind and EnvironmentFile before changing the checkout. It does not
rewrite the unit. Health is authenticated `GET http://127.0.0.1:8420/status`
(the engine has no `/health` route). The server-only Python helper reads the
master token with dotenv from `/opt/sweatpants/.env`, installs selected directories
through `POST /modules/install` (the server executes as sweatpants), calls
`POST /modules/reload`, and verifies manifest IDs in `GET /modules`. Credentials
never enter runner secrets, command arguments, response logs or deploy receipts.

Only full success atomically advances the receipt. A failed deploy does not roll
back engine/module writes; rerun to heal, or manually deploy the previous SHA.
Rollback can require `all_modules=true` to restore unchanged module copies.
No automatic uninstall is performed, including private modules. Neither the old
plain source copy, `.env`, `/var/lib/sweatpants`, unit bind nor `venv-py312.bak` is
modified or removed. Normal service/API operations naturally update service data.
Existing module dependency installation requires the service user to have write
access to its venv, as with today's install API.

## Operator checklist (also include in PR body)

- [ ] Set `CHUBES_DEPLOY_SSH_KEY` (root access) and trusted `CHUBES_DEPLOY_KNOWN_HOSTS`.
- [ ] Set `DEPLOY_AUTOMATION=enabled` when ready for unattended deployments.
- [ ] Run the first deploy as a dry run and review the all-module bootstrap plan.
- [ ] Then run a real deploy and inspect health/module verification and receipt.
- [ ] Close Extra-Chill/sweatpants-modules#15 as superseded.
- [ ] Archive sweatpants-modules after adding a README pointer to this repository.
- [ ] Point sweatpants-modules-private tooling at the new layout if needed.

Production SSH/deployment is intentionally not exercised during implementation.
