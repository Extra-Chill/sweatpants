#!/usr/bin/env bash
set -euo pipefail

detector=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/changed-modules.sh
tmp=$(mktemp -d)
trap 'rm -rf -- "$tmp"' EXIT
# Do not inherit repository settings from a caller (for example a git hook).
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE
cd "$tmp"
git init -q
git config user.name 'Detector Test'
git config user.email 'test@example.invalid'
git config commit.gpgsign false

assert_output() {
  local expected=$1 actual
  shift
  actual=$(cd "$tmp"; "$detector" "$@")
  if [[ $actual != "$expected" ]]; then
    printf 'FAIL (%s): expected <%s>, got <%s>\n' "$*" "$expected" "$actual" >&2
    exit 1
  fi
}
assert_failure() {
  if (cd "$tmp"; "$detector" "$@") >"$tmp/output" 2>"$tmp/error"; then
    printf 'FAIL: expected rejection of %s\n' "$*" >&2
    exit 1
  fi
}
commit() { git add -A; git commit -qm "$1"; }

mkdir modules
cd modules
mkdir -p alpha beta nested/not-a-module
printf '{}\n' > alpha/module.json
printf '{}\n' > beta/module.json
printf '{}\n' > nested/not-a-module/module.json
printf 'initial\n' > README.md
commit initial
initial=$(git rev-parse HEAD)
assert_output $'alpha\nbeta' '' HEAD
assert_output $'alpha\nbeta' 0000000000000000000000000000000000000000 HEAD
assert_output $'alpha\nbeta' not-a-commit HEAD
assert_output $'alpha\nbeta' all
assert_output $'alpha\nbeta' --explicit all
assert_output $'alpha\nbeta' --explicit $'beta alpha,beta\nalpha'
assert_failure --explicit missing
assert_failure --explicit nested
assert_failure --explicit nested/not-a-module
assert_failure --explicit ../alpha
assert_failure --explicit 'alpha missing'
assert_failure --explicit ''
assert_failure "$initial" not-a-commit
assert_output '' "$initial" "$initial"

printf 'root-only\n' >> README.md
commit root-only
root=$(git rev-parse HEAD)
assert_output '' "$initial" "$root"

printf 'changed\n' > alpha/main.py
printf 'another change\n' > alpha/requirements.txt
mkdir gamma
printf '{}\n' > gamma/module.json
rm -rf beta
commit 'add modify delete'
changed=$(git rev-parse HEAD)
assert_output $'alpha\ngamma' "$root" "$changed"
assert_output $'alpha\ngamma' 0000000000000000000000000000000000000000 "$changed"
assert_failure --explicit beta

# Detect both sides of a rename, including deletion of a module's file.
git mv alpha/main.py gamma/main.py
commit rename
renamed=$(git rev-parse HEAD)
assert_output $'alpha\ngamma' "$changed" "$renamed"

rm alpha/module.json
rm -rf gamma
commit removal
removed=$(git rev-parse HEAD)
assert_output '' "$renamed" "$removed"
assert_output '' --explicit all
assert_failure --explicit alpha
# Selection is based on the requested head tree, not the working tree.
assert_output $'alpha\ngamma' "$root" "$changed"
assert_output $'alpha\nbeta' '' "$initial"
printf 'changed-modules tests passed\n'
