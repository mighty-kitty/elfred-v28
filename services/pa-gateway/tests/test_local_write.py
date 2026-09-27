# -*- coding: utf-8 -*-
"""WP-03: the write-type local tool really writes, and really refuses.

These are real files in a temp directory - no mocked filesystem, because the
whole point of the tool is that it touches the user's disk.
"""
import os
import time

import app.main as main_mod
from fastapi.testclient import TestClient

from app.main import app

c = TestClient(app)


class _StubPlanner:
    name = "stub"

    def __init__(self, steps):
        self._steps = steps

    def plan(self, query, ctx, tools=None):
        return list(self._steps)


def _run(steps, boundaries, message="把结论写进报告"):
    engine = main_mod.engine
    original = engine.planner
    engine.planner = _StubPlanner(steps)
    try:
        pa = c.post("/v1/pa/profiles", json={
            "user_id": "u_write", "consent_version": 1,
            "boundaries": boundaries,
            "tool_scopes": ["local_file_write", "local_file_read"],
        }).json()["pa_id"]
        rid = c.post(f"/v1/pa/{pa}/messages", json={"message": message}).json()["run_id"]
        deadline = time.time() + 20
        while time.time() < deadline:
            if c.get(f"/v1/runs/{rid}").json()["state"] == "waiting_approval":
                break
            time.sleep(0.2)
        return c.post(f"/v1/runs/{rid}/approvals", json={"decision": "approve"}).json()
    finally:
        engine.planner = original


def _step(path, **kw):
    return {"step": 1, "goal": f"写入 {path}", "tool": "local_file_write",
            "risk": "medium", **kw}


def _failed(body):
    return [e["payload"] for e in body["events"] if e["type"] == "tool.failed"]


def _completed(body):
    return [e["payload"].get("tool") for e in body["events"] if e["type"] == "tool.completed"]


def test_write_creates_a_real_file_inside_the_allowed_root(tmp_path):
    target = os.path.join(str(tmp_path), "notes", "report.md")
    body = _run([_step(target, content="# 结论\n先给结论，再给三条要点")],
                {"allowed_roots": [str(tmp_path)]},
                message=f"内容：先给结论，再给三条要点 {target}")
    assert _completed(body) == ["local_file_write"], _failed(body)
    with open(target, encoding="utf-8") as handle:
        assert handle.read() == "# 结论\n先给结论，再给三条要点"
    artifact = [a for a in body["artifacts"] if a.get("type") == "file"][0]
    assert artifact["mode"] == "create" and artifact["bytes"] > 0
    assert artifact["run_id"] == body["run_id"]


def test_write_takes_the_body_from_an_explicit_content_marker(tmp_path):
    target = os.path.join(str(tmp_path), "summary.txt")
    body = _run([_step(target)], {"allowed_roots": [str(tmp_path)]},
                message=f"内容：三条要点在此 {target}")
    assert _completed(body) == ["local_file_write"], _failed(body)
    assert open(target, encoding="utf-8").read() == "三条要点在此 " + target


def test_write_refuses_a_path_outside_the_allowed_roots(tmp_path):
    outside = os.path.join(str(tmp_path.parent), "escaped.md")
    body = _run([_step(outside, content="nope")], {"allowed_roots": [str(tmp_path)]})
    assert _completed(body) == []
    assert _failed(body)[0]["error"] == "POLICY_DENIED"
    assert not os.path.exists(outside)


def test_write_refuses_when_the_profile_has_no_allowed_roots(tmp_path):
    body = _run([_step(os.path.join(str(tmp_path), "x.md"), content="nope")], {})
    assert _completed(body) == []
    assert "no allowed_roots" in _failed(body)[0]["detail"]


def test_write_never_silently_overwrites(tmp_path):
    target = os.path.join(str(tmp_path), "keep.md")
    with open(target, "w", encoding="utf-8") as handle:
        handle.write("original")
    body = _run([_step(target, content="replacement")], {"allowed_roots": [str(tmp_path)]})
    assert _completed(body) == []
    assert _failed(body)[0]["error"] == "CONFLICT"
    assert open(target, encoding="utf-8").read() == "original"


def test_write_overwrites_when_the_step_says_so(tmp_path):
    target = os.path.join(str(tmp_path), "replace.md")
    with open(target, "w", encoding="utf-8") as handle:
        handle.write("original")
    body = _run([_step(target, content="replacement", overwrite=True)],
                {"allowed_roots": [str(tmp_path)]})
    assert _completed(body) == ["local_file_write"], _failed(body)
    assert open(target, encoding="utf-8").read() == "replacement"
    artifact = [a for a in body["artifacts"] if a.get("type") == "file"][0]
    assert artifact["mode"] == "overwrite"


def test_write_refuses_when_there_is_no_body_to_write(tmp_path):
    target = os.path.join(str(tmp_path), "empty.md")
    body = _run([_step(target)], {"allowed_roots": [str(tmp_path)]},
                message="帮我写个文件")
    assert _completed(body) == []
    assert "no content to write" in _failed(body)[0]["detail"]
    assert not os.path.exists(target)


def test_write_refuses_an_oversized_body(tmp_path):
    target = os.path.join(str(tmp_path), "big.md")
    body = _run([_step(target, content="x" * (64 * 1024 + 1))],
                {"allowed_roots": [str(tmp_path)]})
    assert _completed(body) == []
    assert "refusing to write more than" in _failed(body)[0]["detail"]
    assert not os.path.exists(target)
