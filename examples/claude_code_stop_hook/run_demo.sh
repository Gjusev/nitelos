#!/usr/bin/env bash
# Replay a Claude Code Stop event (agent claims "All tests pass.") through the
# real nitelos hook runtime. Offline: no Claude Code, no network, no LLM.
set -euo pipefail
cd "$(dirname "$0")"

# The hook requires evidence captured during the current turn (freshness rule):
# touching the report simulates the agent having just run the tests.
touch reports/junit.xml

event=$(cat <<'JSON'
{
  "session_id": "demo-session",
  "prompt_id": "demo-prompt",
  "transcript_path": "",
  "cwd": "PLACEHOLDER",
  "hook_event_name": "Stop",
  "stop_hook_active": false,
  "last_assistant_message": "All tests pass."
}
JSON
)
event=${event//PLACEHOLDER/$(pwd)}

python - "$event" <<'PY'
import json, os, sys, tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

from nitelos.claude_code import run_stop

event = json.loads(sys.argv[1])
state_dir = Path(tempfile.mkdtemp(prefix="nitelos-demo-"))
stamp = (datetime.now(UTC) - timedelta(seconds=5)).isoformat().replace("+00:00", "Z")
(state_dir / "session-demo-session.json").write_text(
    json.dumps({"turn_start_key": "demo-session:demo-prompt", "turn_start": stamp})
)
document = run_stop(json.dumps(event), state_dir=state_dir)
print(json.dumps(document, indent=2))
sys.exit(0)
PY
