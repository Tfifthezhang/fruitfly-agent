"""edit tool — multi-block exact text replacement.

Replacement guarantees:
- all edits match against the ORIGINAL file (non-overlapping, unique);
- BOM preserved, line endings detected then restored;
- fuzzy fallback when an exact match fails (difflib, whole-line granularity);
- returns a unified diff in details.
"""

from __future__ import annotations

import difflib

from fruitfly_agent.core.data_model import AgentToolResult, TextBlock
from fruitfly_agent.core.tool_runtime import AgentTool, ToolCallContext
from .file_queue import with_file_mutation_queue
from .path_utils import normalize_tool_path

_EDIT_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "path": {"type": "string", "description": "Path to the file to edit (relative or absolute)"},
        "edits": {
            "type": "array",
            "description": (
                "One or more targeted replacements. Each edit is matched against the "
                "original file, not incrementally. Do not include overlapping or nested "
                "edits; merge nearby changes into one edit."
            ),
            "items": {
                "type": "object",
                "properties": {
                    "oldText": {
                        "type": "string",
                        "description": "Exact text for one targeted replacement, unique in the original file.",
                    },
                    "newText": {"type": "string", "description": "Replacement text."},
                },
                "required": ["oldText", "newText"],
            },
        },
    },
    "required": ["path", "edits"],
}

_BOM = "﻿"


def _apply_edits(content: str, edits: list[dict], path: str) -> tuple[str, str]:
    """Apply edits to LF-normalized content. Returns (base, new)."""
    spans: list[tuple[int, int, str]] = []
    for edit in edits:
        old = edit["oldText"]
        replacement = edit["newText"]
        if not old:
            raise RuntimeError("oldText must not be empty")
        count = content.count(old)
        if count == 0:
            fuzzy = _fuzzy_match(content, old)
            if fuzzy is not None:
                old = fuzzy
                count = content.count(old)
        if count == 0:
            raise RuntimeError(
                f"Could not find exact text to replace in {path}: {old[:120]!r}. "
                "The file may have changed; re-read it and retry."
            )
        # str.count ignores overlapping occurrences (e.g. aaa in aaaa).
        if content.find(old, content.find(old) + 1) >= 0:
            count = max(count, 2)
        if count > 1:
            raise RuntimeError(
                f"Text to replace is not unique in {path}: {old[:120]!r} appears {count} times. "
                "Include more surrounding context."
            )
        start = content.find(old)
        end = start + len(old)
        for previous_start, previous_end, _ in spans:
            if start < previous_end and previous_start < end:
                raise RuntimeError(
                    f"Edits overlap in {path}; merge overlapping replacements into one edit."
                )
        spans.append((start, end, replacement))
    new = content
    for start, end, replacement in sorted(spans, reverse=True):
        new = new[:start] + replacement + new[end:]
    return content, new


def _fuzzy_match(content: str, old: str) -> str | None:
    """Whole-line fuzzy fallback: find the most similar line span."""
    old_lines = old.splitlines()
    if not old_lines:
        return None
    lines = content.splitlines()
    if not lines:
        return None
    target = "\n".join(line.strip() for line in old_lines)
    best_ratio = 0.0
    best_span = None
    ambiguous = False
    width = len(old_lines)
    for i in range(len(lines) - width + 1):
        span = lines[i:i + width]
        normalized = "\n".join(line.strip() for line in span)
        ratio = difflib.SequenceMatcher(None, target, normalized).ratio()
        if ratio > best_ratio:
            best_ratio, best_span = ratio, "\n".join(span)
            ambiguous = False
        elif ratio == best_ratio:
            ambiguous = True
    if best_ratio < 0.6 or best_span is None or ambiguous:
        return None
    return best_span + ("\n" if old.endswith("\n") else "")


def _unified_diff(base: str, new: str, path: str) -> str:
    return "".join(
        difflib.unified_diff(
            base.splitlines(keepends=True),
            new.splitlines(keepends=True),
            fromfile=f"a/{path}",
            tofile=f"b/{path}",
        )
    )


async def _execute(ctx: ToolCallContext) -> AgentToolResult:
    if ctx.env is None:
        raise RuntimeError("edit requires an ExecutionEnv")
    path = ctx.args["path"]
    edits = ctx.args["edits"]
    if not edits:
        raise RuntimeError("Edit tool input is invalid: edits must contain at least one replacement.")
    resolved = ctx.env.absolute_path(normalize_tool_path(path))
    if not resolved.is_ok:
        raise RuntimeError(f"Could not resolve path: {path}. {resolved.error}")
    absolute = resolved.unwrap()

    async def edit() -> AgentToolResult:
        info = ctx.env.file_info(absolute)
        if not info.is_ok:
            raise RuntimeError(f"Could not edit file: {path}. {info.error}")
        if info.unwrap().kind not in ("file", "symlink"):
            raise RuntimeError(f"Could not edit file: {path}. Path is not a file.")

        read_result = ctx.env.read_binary_file(absolute)
        if not read_result.is_ok:
            raise RuntimeError(f"Could not edit file: {path}. {read_result.error}")
        raw = read_result.unwrap().decode("utf-8", errors="replace")

        bom = _BOM if raw.startswith(_BOM) else ""
        body = raw[len(bom) :]
        original_ending = "\r\n" if "\r\n" in body else "\n"
        normalized = body.replace("\r\n", "\n")

        base, new = _apply_edits(normalized, edits, path)
        final_content = bom + (new.replace("\n", original_ending) if original_ending == "\r\n" else new)

        write_result = ctx.env.write_file(absolute, final_content)
        if not write_result.is_ok:
            raise RuntimeError(f"Could not edit file: {path}. {write_result.error}")

        diff = _unified_diff(base, new, path)
        return AgentToolResult(
            content=[TextBlock(text=f"Successfully replaced {len(edits)} block(s) in {path}.")],
            details={"diff": diff, "patch": diff},
        )

    return await with_file_mutation_queue(ctx.env, absolute, edit)


def create_edit_tool() -> AgentTool:
    return AgentTool(
        name="edit",
        label="edit",
        description=(
            "Edit a single file using exact text replacement. Every edits[].oldText "
            "must match a unique, non-overlapping region of the original file. "
            "Merge nearby changes into one edit."
        ),
        parameters=_EDIT_SCHEMA,
        execute=_execute,
    )
