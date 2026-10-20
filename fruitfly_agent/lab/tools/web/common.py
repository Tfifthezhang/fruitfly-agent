"""Vendor-independent tool output and text helpers."""
import hashlib
from html import unescape
import json
import re

from fruitfly_agent.core.data_model import AgentToolResult, TextBlock
from .client import WebError


def source_id(url: str) -> str:
    return "web-" + hashlib.sha256(url.encode()).hexdigest()[:16]


def json_result(value: dict) -> AgentToolResult:
    return AgentToolResult(content=[TextBlock(json.dumps(value, ensure_ascii=False))], details=value)


def clean_text(value: str, maximum: int) -> str:
    return " ".join(re.sub(r"<[^>]+>", "", unescape(value)).split())[:maximum]


def text_lines(text: str) -> list[str]:
    lines = [line[i:i + 1000] for line in text.splitlines() for i in range(0, max(1, len(line)), 1000)]
    if not lines or not any(line.strip() for line in lines):
        raise WebError("empty_content", "No readable text was found. The page may need JavaScript or authentication.")
    return lines
