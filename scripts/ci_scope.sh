#!/usr/bin/env bash
# Which checks a PR needs, from the files it changes. Prints full, copy or ci.
#   ci   — only .github/ plumbing that Test and Contrast don't run (dependabot,
#          CODEOWNERS, other workflows): every required job may skip.
#   copy — only frontend/src/locales/: frontend job + the backend tests that
#          read the catalogs + the owner copy guard.
#   full — anything else, including this script and the workflows that call it.
# On a pull_request checkout HEAD is the merge commit, so HEAD^1..HEAD is the
# PR's change against the current base. Any doubt answers full.
set -euo pipefail

files=$(git diff --name-only HEAD^1 HEAD) || { echo full; exit 0; }
[ -n "$files" ] || { echo full; exit 0; }

scope=ci
while IFS= read -r f; do
  case $f in
    .github/workflows/test.yml | .github/workflows/contrast.yml) scope=full ;;
    .github/*) ;;
    frontend/src/locales/*) scope=copy ;;
    *) scope=full ;;
  esac
  [ "$scope" = full ] && break
done <<<"$files"
echo "$scope"
