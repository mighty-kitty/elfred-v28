"""Repair common malformed JSON returned by configured language models.

纯函数模块，无外部依赖，可直接 pytest 测试。
设计原则：只修"确定能修"的错误，不确定的交给重试机制。
"""

from __future__ import annotations

import re


class JsonRepairError(ValueError):
    """JSON 不可修复——需要 LLM 重试或降级。"""


def repair_json(raw: str) -> str:
    """修复常见 LLM JSON 格式错误，返回可解析的 JSON 字符串。

    能修复：
      - 缺少逗号        {"a": 1  "b": 2}     →  {"a": 1, "b": 2}
      - 尾部多余逗号     {"a": 1,}            →  {"a": 1}
      - LLM 废话前/后缀  "结果是：{"a": 1}"    →  {"a": 1}
      - 未引号键名       {a: 1}               →  {"a": 1}
      - // 注释          {"a": 1 // 注释}      →  {"a": 1 }
      - 字符串含未转义内嵌引号  {"a": "he"llo"}  →  {"a": "he\"llo"}

    不能修复时报 JsonRepairError（调用方走重试/降级）。
    """
    if not raw or not isinstance(raw, str):
        raise JsonRepairError("Empty or non-string input")

    text = raw.strip()
    if not text:
        raise JsonRepairError("Empty input after strip")

    # 1. 移除 LLM 的废话前缀/后缀：找第一个 { 和最后一个 }
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        raise JsonRepairError("No JSON object boundaries found")
    text = text[start:end + 1]

    # 2. 移除行尾 // 注释
    text = _strip_line_comments(text)

    # 3. 给未引号的键名加引号
    text = _quote_unquoted_keys(text)

    # 4. 修复尾部多余逗号（对象和数组）
    text = _remove_trailing_commas(text)

    # 5. 修复缺失的逗号：两行之间如果上一行不以 ,{[ 结尾、下一行以 "} 开头
    text = _insert_missing_commas(text)

    # 6. 修复字符串值内部未转义的双引号
    text = _escape_embedded_quotes(text)

    return text


def _strip_line_comments(text: str) -> str:
    """移除 // 行尾注释（只在引号外部）。"""
    lines = text.split("\n")
    result = []
    for line in lines:
        in_string = False
        escaped = False
        for i, ch in enumerate(line):
            if escaped:
                escaped = False
                continue
            if ch == "\\":
                escaped = True
                continue
            if ch == '"':
                in_string = not in_string
                continue
            if not in_string and ch == "/" and i + 1 < len(line) and line[i + 1] == "/":
                line = line[:i].rstrip()
                break
        result.append(line)
    return "\n".join(result)


def _quote_unquoted_keys(text: str) -> str:
    """给未引号的 JSON 键名加双引号。"""
    # 匹配模式：行首空格 + 标识符 + 冒号（不在双引号内）
    pattern = re.compile(r'(^|\{|\,)\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*:')
    return pattern.sub(r'\1"\2":', text)


def _remove_trailing_commas(text: str) -> str:
    """移除对象和数组中最后一个元素后的逗号。"""
    # ,} 和 ,] 和 ,\n} 和 ,\n] 和 ,  }
    text = re.sub(r',(\s*[}\]])', r'\1', text)
    return text


def _insert_missing_commas(text: str) -> str:
    """在明显缺少逗号的地方补上。

    启发式：上一行以 " 或 } 或 ] 或数字结尾，下一行以 " 或 { 开头，
    且中间没有逗号——这是 LLM 常见错误。
    """
    lines = text.split("\n")
    result = []
    for i, line in enumerate(lines):
        stripped = line.rstrip()
        if i > 0 and stripped and result:
            prev = result[-1].rstrip()
            # 上一行结尾和当前行开头暗示应该有一个逗号
            if _needs_comma_between(prev, stripped):
                result[-1] = prev.rstrip() + ","
        result.append(line)
    return "\n".join(result)


def _needs_comma_between(prev: str, current: str) -> bool:
    """判断两行之间是否缺逗号。"""
    prev_end = prev.strip()[-1] if prev.strip() else ""
    curr_start = current.strip()[0] if current.strip() else ""

    # 上一行以值结尾（引号/数字/}/]），下一行以键开头（引号）
    prev_is_value = prev_end in ('"', "}", "]", "0", "1", "2", "3", "4", "5", "6", "7", "8", "9") or prev_end in ("e", "l")  # true/false/null
    curr_is_key = curr_start == '"'

    return prev_is_value and curr_is_key


def _escape_embedded_quotes(text: str) -> str:
    """修复字符串值内部未转义的双引号。

    启发式：在 JSON 字符串值（两个逗号/冒号之间的引号内容）中，
    查找模式 字母"字母 并转义为 字母\"字母。
    """
    # 匹配 "..." 字符串内容中，中文字符或字母后面的未转义引号
    # 模式：非\ 非" 字符 + " + 非,:}\s 字符（说明引号在字符串内部）
    text = re.sub(r'(?<=[^\\,":\[\]\{\}\s])"(?=[^,:\[\]\{\}\s])', r'\\"', text)
    return text
