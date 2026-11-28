#!/usr/bin/env bash
set -euo pipefail

usage() {
  echo 'Usage: changed-modules.sh BASE HEAD | --explicit "all|name name,name" | all' >&2
  exit 1
}

all_modules() {
  local head=$1 path
  while IFS= read -r -d '' path; do
    path=${path#modules/}
    if [[ "$path" == */module.json && "${path%/module.json}" != */* ]]; then
      printf '%s\n' "${path%/module.json}"
    fi
  done < <(git ls-tree -r --name-only -z "$head" -- modules)
}

if [[ ${1:-} == --explicit || ${1:-} == all ]]; then
  if [[ $1 == all ]]; then
    [[ $# == 1 ]] || usage
    selection=all
  else
    [[ $# == 2 ]] || usage
    selection=$2
  fi
  if [[ $selection == all ]]; then
    all_modules HEAD | LC_ALL=C sort -u
  else
    # Accept comma- or whitespace-separated top-level directory names.
    names=()
    while IFS= read -r name; do
      [[ -n $name ]] || continue
      if [[ $name == */* || $name == . || $name == .. || ! -d modules/$name || ! -f modules/$name/module.json ]]; then
        printf 'Invalid module: %s (expected a top-level directory containing module.json)\n' "$name" >&2
        exit 1
      fi
      names+=("$name")
    done < <(printf '%s\n' "$selection" | tr ',[:space:]' '\n')
    [[ ${#names[@]} -gt 0 ]] || { echo 'No explicit modules provided' >&2; exit 1; }
    printf '%s\n' "${names[@]}" | LC_ALL=C sort -u
  fi
  exit 0
fi

[[ $# == 2 ]] || usage
base=$1
head=$(git rev-parse --verify --end-of-options "$2^{commit}")
if [[ -z $base || $base == 0000000000000000000000000000000000000000 ]] ||
   ! base=$(git rev-parse --verify --end-of-options "$base^{commit}" 2>/dev/null); then
  all_modules "$head" | LC_ALL=C sort -u
  exit 0
fi

while IFS= read -r -d '' path; do
  [[ $path == */* ]] || continue
  [[ $path == modules/* ]] || continue
  path=${path#modules/}
  module=${path%%/*}
  if git cat-file -e "$head:modules/$module/module.json" 2>/dev/null; then
    printf '%s\n' "$module"
  fi
done < <(git diff --no-renames --name-only -z "$base" "$head" --) | LC_ALL=C sort -u
