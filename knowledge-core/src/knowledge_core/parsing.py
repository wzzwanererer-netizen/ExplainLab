"""模型输出 JSON 的健壮解析（共享工具）。

兼容代码围栏、前后多余文本；解析失败返回 None，调用方据此如实返回空结果，不造假。
"""

from __future__ import annotations

import json
import re


def strip_fence(text: str) -> str:
    """去除 Markdown 代码围栏，返回围栏内内容（无围栏则原样.strip）。"""
    cleaned = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", cleaned, re.DOTALL)
    if fence:
        return fence.group(1).strip()
    return cleaned


def extract_json(text: str) -> object:
    """尽力从模型输出中解析出一个 JSON 对象/数组；失败返回 None。"""
    cleaned = strip_fence(text)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    start = cleaned.find("{")
    if start == -1:
        return None
    depth = 0
    for i in range(start, len(cleaned)):
        if cleaned[i] == "{":
            depth += 1
        elif cleaned[i] == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(cleaned[start : i + 1])
                except json.JSONDecodeError:
                    return None
    return None