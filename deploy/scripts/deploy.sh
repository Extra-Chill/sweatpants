#!/usr/bin/env bash
# Run as root on chubes-net from an immutable, reviewed release checkout.
set -euo pipefail
[[ $# == 3 && $1 =~ ^[0-9a-f]{40}$ && $2 =~ ^(true|false)$ && $3 =~ ^(true|false)$ ]] || exit 2
sha=$1 dry_run=$2 all_modules=$3
src=/opt/sweatpants/src
receipt=/opt/sweatpants/deployed-ref
scripts=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
exec 9>/run/lock/sweatpants-deploy.lock
flock -n 9
# A temporary mirror permits a real diff on first deploy without mutating /opt.
work=$(mktemp -d)
trap 'rm -rf -- "$work"' EXIT
git clone -q --mirror https://github.com/Extra-Chill/sweatpants.git "$work/repo"
git --git-dir="$work/repo" cat-file -e "$sha^{commit}"
base=''
[[ ! -f $receipt ]] || read -r base < "$receipt"
if [[ $all_modules == true ]]; then base=''; fi
(
  export GIT_DIR="$work/repo"
  bash "$scripts/changed-modules.sh" "$base" "$sha"
) > "$work/modules"
printf 'Deploy ref: %s; previous successful ref: %s; dry run: %s\n' "$sha" "${base:-none}" "$dry_run"
printf 'Selected modules:\n'; < "$work/modules" sort
[[ $dry_run == false ]] || exit 0
if [[ ! -d $src ]]; then
  git clone -q "$work/repo" "$src"
  git -C "$src" remote set-url origin https://github.com/Extra-Chill/sweatpants.git
fi
[[ -d $src/.git ]] || { echo 'Source path is not a git checkout' >&2; exit 1; }
[[ -z $(git -C "$src" status --porcelain) ]] || { echo 'Source checkout is dirty' >&2; exit 1; }
git -C "$src" fetch -q origin
# Fail closed if this service is not the expected existing deployment.
[[ $(systemctl show sweatpants -p User --value) == sweatpants ]]
systemctl show sweatpants -p ExecStart --value | grep -F -- '/opt/sweatpants/venv/bin/sweatpants serve --host 127.0.0.1 --port 8420' >/dev/null
systemctl show sweatpants -p EnvironmentFiles --value | grep -F '/opt/sweatpants/.env' >/dev/null
git -C "$src" checkout -q --detach "$sha"
/opt/sweatpants/venv/bin/python -m pip install "$src"
systemctl restart sweatpants
# Read credentials only inside this server-side process. Never put tokens in argv,
# environment output, response logs or runner secrets. dotenv matches engine parsing.
/opt/sweatpants/venv/bin/python "$scripts/verify-deploy.py" "$src" "$work/modules"
printf '%s\n' "$sha" > "$receipt.tmp"
mv "$receipt.tmp" "$receipt"
echo 'Deployment verified; successful-ref receipt updated.'
