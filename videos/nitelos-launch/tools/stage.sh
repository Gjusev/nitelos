#!/usr/bin/env bash
# Stage a deliverable composition as its own HyperFrames project and run a command on it.
#   tools/stage.sh <composition.html> check|snapshot|render [extra args...]
# The staged copy lives in .stage/<name>/ (git-ignored): index.html is the composition,
# assets/ is a copy of the shared assets, so root-relative /assets/... URLs resolve.
set -euo pipefail
cd "$(dirname "$0")/.."
comp="$1"; shift
cmd="$1"; shift
name="$(basename "$comp" .html)"
stage=".stage/$name"
rm -rf "$stage"
mkdir -p "$stage"
cp "$comp" "$stage/index.html"
cp -r assets "$stage/assets"
cp hyperframes.json "$stage/"
printf '{"id":"%s","name":"%s","createdAt":"2026-10-20T09:42:18.345Z"}\n' "$name" "$name" > "$stage/meta.json"
npx --yes hyperframes@0.8.181 "$cmd" "$stage" "$@"
