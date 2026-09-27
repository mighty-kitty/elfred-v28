# -*- coding: utf-8 -*-
from app.policy import Policy
from app.manifest import build_manifest


def test_policy_deny_unscoped_tool():
    p = Policy(tool_scopes=["emos_recall", "knowledge_search"])
    assert not p.allow("local_file_write")
    assert p.allow("emos_recall")


def test_policy_allow_all_when_no_scopes():
    p = Policy()
    assert p.allow("anything")


def test_policy_risk_requires_approval():
    p = Policy()
    assert p.requires_approval({"risk": "high"})
    assert not p.requires_approval({"risk": "low"})


def test_policy_caps_steps():
    p = Policy()
    steps = [{"step": i} for i in range(30)]
    assert len(p.cap_steps(steps)) == p.MAX_STEPS


class _P:
    profile_version = 2
    consent_version = 1


def test_manifest_shape():
    m = build_manifest("r1", "query", _P(), {"memory_refs": ["m1"], "knowledge_refs": ["k1"]},
                       ["redacted"])
    assert m["run_id"] == "r1"
    assert m["memory_refs"] == ["m1"]
    assert m["knowledge_refs"] == ["k1"]
    assert "redaction_log" in m and m["redaction_log"] == ["redacted"]
    assert m["token_budget"] > 0 and m["profile_version"] == 2
