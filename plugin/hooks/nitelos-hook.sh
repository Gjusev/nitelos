#!/usr/bin/env bash
# Resolve the interpreter explicitly: the hook must not depend on console
# scripts being on PATH (ADR-016 ruling 5). Override with NITELOS_PYTHON.
set -eu
PY="${NITELOS_PYTHON:-}"
if [ -z "$PY" ]; then
  for candidate in python3 python py; do
    if command -v "$candidate" >/dev/null 2>&1; then
      PY="$candidate"
      break
    fi
  done
fi
if [ -z "$PY" ]; then
  echo "{\"systemMessage\":\"nitelos: no Python interpreter found; set NITELOS_PYTHON\"}"
  exit 0
fi
exec "$PY" -m nitelos.claude_code
