"""json_repair 单元测试 — 纯函数，pytest 直接测。"""

from __future__ import annotations

import json

import pytest

from adapter.json_repair import JsonRepairError, repair_json


# ── 正常 JSON 不改 ──

def test_valid_json_passes_through():
    raw = '{"a": 1, "b": "hello"}'
    assert repair_json(raw) == raw


def test_valid_json_with_arrays():
    raw = '{"items": [1, 2, 3], "nested": {"x": true}}'
    parsed = json.loads(repair_json(raw))
    assert parsed["items"] == [1, 2, 3]
    assert parsed["nested"]["x"] is True


# ── 缺失逗号 ──

def test_missing_comma_between_fields():
    raw = '{\n  "a": 1\n  "b": 2\n}'
    repaired = repair_json(raw)
    parsed = json.loads(repaired)
    assert parsed == {"a": 1, "b": 2}


# ── 尾部逗号 ──

def test_trailing_comma_in_object():
    raw = '{"a": 1,}'
    parsed = json.loads(repair_json(raw))
    assert parsed == {"a": 1}


def test_trailing_comma_in_array():
    raw = '{"a": [1, 2,]}'
    parsed = json.loads(repair_json(raw))
    assert parsed == {"a": [1, 2]}


# ── LLM 废话前置 ──

def test_llm_preamble_removed():
    raw = '好的，这是生成的结果：\n{"a": 1}'
    parsed = json.loads(repair_json(raw))
    assert parsed == {"a": 1}


def test_llm_preamble_chinese():
    raw = '以下是日记JSON：\n```json\n{"summary_line": "今天工作顺利"}\n```'
    repaired = repair_json(raw)
    parsed = json.loads(repaired)
    assert parsed["summary_line"] == "今天工作顺利"


# ── 未引号键名 ──

def test_unquoted_key():
    raw = '{a: 1, b: "hello"}'
    parsed = json.loads(repair_json(raw))
    assert parsed == {"a": 1, "b": "hello"}


def test_unquoted_key_multiline():
    raw = '{\n  name: "test",\n  value: 42\n}'
    parsed = json.loads(repair_json(raw))
    assert parsed == {"name": "test", "value": 42}


# ── 注释 ──

def test_line_comment():
    raw = '{\n  "a": 1, // 这是注释\n  "b": 2\n}'
    parsed = json.loads(repair_json(raw))
    assert parsed == {"a": 1, "b": 2}


def test_line_comment_not_in_string():
    raw = '{"url": "https://example.com", "b": 2}'
    parsed = json.loads(repair_json(raw))
    assert parsed["url"] == "https://example.com"


# ── 不可修复 ──

def test_empty_input_raises():
    with pytest.raises(JsonRepairError):
        repair_json("")


def test_no_braces_raises():
    with pytest.raises(JsonRepairError):
        repair_json("hello world")


def test_hopelessly_broken_raises():
    with pytest.raises(JsonRepairError):
        repair_json("not json at all!!!")


def test_none_input_raises():
    with pytest.raises(JsonRepairError):
        repair_json(None)  # type: ignore


# ── 集成：模拟真实 LLM 错误场景 ──

def test_real_world_hermes_error():
    """模拟 Hermes 日报生成的典型错误：多行缺逗号。"""
    raw = """{
  "summary_line": "今天主要进行代码重构和语音管线开发"
  "main_thread": "从下午开始集中开发 Elfred 语音管线"
  "key_progress": [
    "完成 capture-utils 提取"
    "添加 knowledge 测试"
    "搭建 FunASR 语音管线"
  ]
  "decisions": "使用 JSON 修复代替重试"
}"""
    parsed = json.loads(repair_json(raw))
    assert parsed["summary_line"] == "今天主要进行代码重构和语音管线开发"
    assert len(parsed["key_progress"]) == 3
    assert parsed["decisions"] == "使用 JSON 修复代替重试"
