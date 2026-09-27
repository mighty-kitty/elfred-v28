# -*- coding: utf-8 -*-
"""WP-01 smoke test for the local Letta App Server.

    services/elfred-pa-gateway/.venv/Scripts/python.exe letta/smoke.py

Checks the four things WP-01 accepts on:
  1. the App Server answers and the Elfred agent is exposed as a model
  2. the agent really plans through the configured model provider (DeepSeek)
  3. agent state and message history survive a container restart
  4. the recorded history is readable afterwards

Run it once, restart the container (`letserver restart`), run it again: the second
run must still see the same agent id with the earlier messages.
"""
from __future__ import annotations
import os
import subprocess
import sys
import time

import httpx

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass

GATEWAY_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(GATEWAY_DIR, ".env"), override=False)
except ImportError:
    pass

URL = os.environ.get("LETTA_URL", "http://127.0.0.1:4500").rstrip("/")
AGENT = os.environ.get("LETTA_AGENT_ID", "")
MODEL = os.environ.get("LETTA_MODEL", "") or AGENT
TOKEN = os.environ.get("LETTA_API_KEY", "")
CONTAINER = os.environ.get("LETTA_CONTAINER", "elfred-letta")

results: list = []


def check(name, fn):
    try:
        ok, detail = fn()
        results.append((name, bool(ok), detail))
    except Exception as e:  # noqa: BLE001
        results.append((name, False, f"EXC {type(e).__name__}: {e}"))


def headers() -> dict:
    return {"Authorization": f"Bearer {TOKEN}"} if TOKEN else {}


def _docker(args: list[str]) -> str:
    """Run the Letta CLI.

    The runtime may be a container (`LETTA_CLI_MODE=docker`) or a native npm
    install (default), which is what this machine uses because Docker Desktop is
    unusable here.
    """
    if os.environ.get("LETTA_CLI_MODE", "native") == "docker":
        command = ["docker", "exec", CONTAINER, *args]
    else:
        shim = r"C:\Users\35057\AppData\Roaming\npm\letta.cmd"
        if os.path.exists(shim):
            # npm installs a .cmd shim that IS the letta command, so it must run
            # through cmd.exe and must not be given a leading "letta" argument.
            cli_args = args[1:] if args and args[0] == "letta" else args
            command = ["cmd", "/c", shim, *cli_args]
        else:
            command = ["letta", *args]
    out = subprocess.run(command, capture_output=True, text=True, encoding="utf-8",
                         errors="replace", timeout=180, shell=False)
    return (out.stdout or "") + (out.stderr or "")


def step_models():
    r = httpx.get(f"{URL}/v1/models", headers=headers(), timeout=30)
    body = r.json()
    ids = [m.get("id") for m in body.get("data", [])]
    return r.status_code == 200 and MODEL in ids, f"models={ids}"


def step_plans_through_provider():
    prompt = (
        "Plan a personal agent. Reply with ONLY a compact JSON array, no prose. "
        'Elements: {"goal":"<short>","tool":"<allowed>","risk":"low|medium|high"}. '
        "Allowed tools: emos_recall, knowledge_search, task_create. "
        "Use at most 3 steps. Request: smoke test, create a task for tomorrow"
    )
    started = time.time()
    r = httpx.post(f"{URL}/v1/chat/completions", headers=headers(),
                   json={"model": MODEL, "messages": [{"role": "user", "content": prompt}]},
                   timeout=180)
    took = round(time.time() - started, 1)
    content = r.json()["choices"][0]["message"]["content"]
    import json as _json
    start, end = content.find("["), content.rfind("]")
    plan = _json.loads(content[start:end + 1]) if start >= 0 and end > start else []
    tools = [s.get("tool") for s in plan if isinstance(s, dict)]
    return bool(plan), f"{len(plan)} steps in {took}s tools={tools}"


def step_agent_persisted():
    import re
    out = _docker(["letta", "agents", "list", "--name", MODEL])
    found = re.search(r'"id":\s*"(agent-[^"]+)"', out)
    agent_id = found.group(1) if found else ""
    same = agent_id == AGENT
    return same, f"agent_id={agent_id or '(not found)'} expected={AGENT}"


def step_history_readable():
    """History lives in the agent's conversations (the `default` one stays empty)."""
    import base64
    if os.environ.get("LETTA_CLI_MODE", "native") == "docker":
        listed = _docker(["sh", "-c", "ls /root/.letta/lc-local-backend/conversations"])
        dirs = [line.strip() for line in listed.splitlines() if line.strip()]
    else:
        conversations = os.path.join(os.path.expanduser("~"), ".letta",
                                     "lc-local-backend", "conversations")
        try:
            dirs = os.listdir(conversations)
        except OSError as error:
            return False, f"conversation dir unreadable: {error}"
    conversations = []
    for name in dirs:
        try:
            decoded = base64.b64decode(name + "=" * (-len(name) % 4)).decode("utf-8", "replace")
        except Exception:  # noqa: BLE001
            continue
        if decoded.startswith("conversation:"):
            conversations.append(decoded.split(":", 1)[1])
    total = 0
    for conv in conversations:
        # dir names are base64("conversation:<id>"); the CLI wants the id, plus the agent
        out = _docker(["letta", "messages", "list", "--conversation", conv,
                       "--agent", AGENT])
        total += out.count('"message_type"')
    return total > 0, f"{len(conversations)} conversations, {total} messages"


def main() -> int:
    if not AGENT:
        print("LETTA_AGENT_ID is not configured (see .env)")
        return 2
    check("App Server /v1/models lists the Elfred agent", step_models)
    check("agent plans through the model provider", step_plans_through_provider)
    check("agent still exists after restart (same id)", step_agent_persisted)
    check("message history is readable", step_history_readable)

    print("=" * 76)
    passed = sum(1 for _, ok, _ in results if ok)
    for name, ok, detail in results:
        print(("PASS  " if ok else "FAIL  ") + name.ljust(46) + " | " + detail)
    print("=" * 76)
    print(f"TOTAL {passed}/{len(results)} passed")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
