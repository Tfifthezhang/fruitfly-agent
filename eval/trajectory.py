"""Project canonical Session messages into Harbor's ATIF interchange format."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def session_trajectory(path: Path, *, version: str = "0.1") -> dict[str, Any]:
    steps: list[dict[str, Any]] = []
    calls: dict[str, dict[str, Any]] = {}
    manifest: dict[str, Any] = {}
    totals: dict[str, int] = {}

    for line in path.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        if row.get("type") == "meta" and row.get("kind") == "runtimeManifest":
            manifest = row.get("manifest", {})
        if row.get("type") != "message":
            continue
        message = row["message"]
        role = message.get("role")
        if role == "toolResult":
            call_id = message.get("toolCallId", "")
            result = {"content": _content(message.get("content", [])),
                      "extra": {"is_error": bool(message.get("isError"))}}
            owner = calls.get(call_id)
            if owner is None:
                owner = {"step_id": len(steps) + 1, "source": "system", "message": "Unmatched tool result",
                         "extra": {"native_tool_call_id": call_id}}
                steps.append(owner)
            else:
                result["source_call_id"] = call_id
            owner.setdefault("observation", {"results": []})["results"].append(result)
            continue
        if role not in {"user", "assistant", "custom"}:
            continue
        step: dict[str, Any] = {
            "step_id": len(steps) + 1,
            "source": {"user": "user", "assistant": "agent", "custom": "system"}[role],
            "message": message.get("text", "") if role == "custom" else _content(message.get("content", [])),
        }
        if role == "custom":
            step["extra"] = {"native_kind": message.get("kind", "custom")}
        if role == "assistant":
            blocks = message.get("content", [])
            thinking = "".join(b.get("thinking", "") for b in blocks if b.get("type") == "thinking")
            if thinking:
                step["reasoning_content"] = thinking
            tools = [{"tool_call_id": b["id"], "function_name": b["name"], "arguments": b["input"]}
                     for b in blocks if b.get("type") == "toolCall"]
            if tools:
                step["tool_calls"] = tools
                for tool in tools:
                    if tool["tool_call_id"] in calls:
                        raise ValueError("duplicate tool call ID in canonical Session")
                    calls[tool["tool_call_id"]] = step
            usage = message.get("usage")
            if isinstance(usage, dict):
                metrics = {}
                for native, name in (("inputTokens", "prompt_tokens"), ("outputTokens", "completion_tokens"),
                                     ("cacheReadTokens", "cached_tokens")):
                    value = usage.get(native)
                    if type(value) is int and value >= 0:
                        metrics[name] = value
                        totals[name] = totals.get(name, 0) + value
                if metrics:
                    step["metrics"] = metrics
        steps.append(step)
    if not steps:
        raise ValueError("canonical Session contains no trajectory messages")
    model = manifest.get("models", {}).get("main", {}).get("model")
    return {
        "schema_version": "ATIF-v1.7", "session_id": path.parent.name,
        "agent": {"name": "fruitfly-agent", "version": version, "model_name": model},
        "steps": steps,
        "final_metrics": {**{"total_" + key: value for key, value in totals.items()}, "total_steps": len(steps)},
        "notes": "Canonical Session projection. Native session.jsonl remains authoritative; request projections and auxiliary calls are not reconstructed.",
        "extra": {"runtime_manifest": manifest},
    }


def _content(value: Any) -> Any:
    if isinstance(value, str):
        return value
    parts = []
    for block in value:
        if block.get("type") == "text":
            parts.append({"type": "text", "text": block.get("text", "")})
        elif block.get("type") == "image":
            media = block["media_type"]
            parts.append({"type": "image", "source": {"media_type": media,
                          "path": "data:" + media + ";base64," + block["data"]}})
    if all(part["type"] == "text" for part in parts):
        return "".join(part["text"] for part in parts)
    return parts
