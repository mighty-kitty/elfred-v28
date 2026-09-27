#!/bin/sh
# Provision the local Letta runtime for Elfred (WP-01).
#
# Usage (from the repo root, with the Letta image available):
#   docker run --rm -e HOME=/root -v elfred_letta:/root/.letta \
#     -v "$PWD/services/elfred-pa-gateway/letta:/provision:ro" \
#     --entrypoint sh docker.1ms.run/letta/letta:latest /provision/provision.sh
#
# Requires LETTA_LLM_BASE_URL / LETTA_LLM_API_KEY / LETTA_LLM_MODEL in the env.
set -eu

BASE_URL="${LETTA_LLM_BASE_URL:-https://api.deepseek.com/v1}"
API_KEY="${LETTA_LLM_API_KEY:?set LETTA_LLM_API_KEY}"
MODEL="${LETTA_LLM_MODEL:-deepseek-flash}"
AGENT_NAME="${LETTA_AGENT_NAME:-Elfred PA}"
MEM_ROOT=/root/.letta/lc-local-backend/memfs

echo "== 1/4 local backend =="
letta backend local

TOKEN_FILE=/root/.letta/ws-token
if [ ! -s "$TOKEN_FILE" ]; then
  head -c 40 /dev/urandom | od -An -tx1 | tr -d ' \n' > "$TOKEN_FILE"
  printf 'elfred-%s' "$(cat "$TOKEN_FILE")" > "$TOKEN_FILE"
  chmod 600 "$TOKEN_FILE"
  echo "generated a new capability token"
fi
echo "LETTA_API_KEY=$(cat "$TOKEN_FILE")"

echo "== 2/4 provider =="
letta connect openai-compatible --base-url "$BASE_URL" --api-key "$API_KEY"

echo "== 3/4 agent =="
AGENT_ID="$(letta agents list --name "$AGENT_NAME" | sed -n 's/.*"id": "\(agent-[^"]*\)".*/\1/p' | head -1)"
if [ -z "$AGENT_ID" ]; then
  letta agents create --name "$AGENT_NAME" --model "openai-compatible/${MODEL}" \
    --personality blank --description "Elfred Personal Agent planner" \
    --tags elfred,pa >/dev/null
  AGENT_ID="$(letta agents list --name "$AGENT_NAME" | sed -n 's/.*"id": "\(agent-[^"]*\)".*/\1/p' | head -1)"
fi
test -n "$AGENT_ID" || { echo "agent creation failed" >&2; exit 1; }
echo "agent_id=$AGENT_ID"

echo "== 4/4 persona (Elfred agent template) =="
MEM_DIR="$MEM_ROOT/$AGENT_ID/memory"
cp /provision/elfred-persona.md "$MEM_DIR/system/persona.md"
cd "$MEM_DIR"
git add system/persona.md
git -c user.name="elfred-provision" -c user.email="elfred@local" \
  commit -m "persona: install the Elfred PA planner policy" >/dev/null 2>&1 || true
echo "persona installed"

echo "AGENT_ID=$AGENT_ID"
