from __future__ import annotations

import json
import urllib.request


BASE_URL = "http://127.0.0.1:8000"


def post_json(path: str, payload: dict) -> dict:
    request = urllib.request.Request(
        url=f"{BASE_URL}{path}",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def get_json(path: str) -> dict:
    with urllib.request.urlopen(f"{BASE_URL}{path}", timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> None:
    manifest = get_json("/system/agent-api-manifest")
    print("manifest:", manifest["contract_version"])

    write_plan = post_json(
        "/memory/write-plan",
        {
            "user_id": "demo-user",
            "session_id": "demo-session",
            "text": "The user prefers black coffee with no sugar.",
            "task_type": "chat",
            "memory_scope": "auto",
            "source": "agent",
            "task_goal": "capture durable preference",
            "context_summary": "personalization update",
            "working_memory": ["coffee preference surfaced during chat"],
        },
    )
    print("write-plan action:", write_plan["payload"]["action_surface"]["recommended_action"])

    write_result = post_json(
        "/memory/write",
        {
            "user_id": "demo-user",
            "session_id": "demo-session",
            "text": "The user prefers black coffee with no sugar.",
            "task_type": "chat",
            "memory_scope": "auto",
            "source": "agent",
            "task_goal": "capture durable preference",
            "context_summary": "personalization update",
            "working_memory": ["coffee preference surfaced during chat"],
        },
    )
    print("write mode:", write_result["payload"]["agent_handoff"]["mode"])

    recall_result = post_json(
        "/memory/recall",
        {
            "user_id": "demo-user",
            "session_id": "demo-session",
            "query_text": "What coffee preference should I remember?",
            "top_k": 5,
            "include_profile": True,
            "task_goal": "answer from long-term memory",
            "context_summary": "agent wants a grounded answer",
            "working_memory": ["answer briefly"],
            "response_mode": "execution_surface",
        },
    )
    execution_surface = recall_result["payload"]["execution_surface"]
    print("recall next action:", execution_surface["action_surface"]["recommended_action"])
    print("recall can execute now:", execution_surface["policy_input"]["can_execute_now"])


if __name__ == "__main__":
    main()
