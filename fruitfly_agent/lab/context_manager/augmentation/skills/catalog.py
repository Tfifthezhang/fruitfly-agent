"""Skill catalog loading and system-prompt rendering research mechanism.

A skill is a directory containing a SKILL.md with YAML frontmatter
(name, description, optional disable-model-invocation). The catalog (names +
descriptions, XML-escaped) is injected into the system prompt; the model
reads the full SKILL.md file itself with the read tool when needed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None  # type: ignore[assignment]

# Scan bounds are independent of the rendered catalog's max_chars budget.
_MAX_ENTRIES = 4096
_MAX_DEPTH = 32
_MAX_FILE_BYTES = 1024 * 1024
_MAX_TOTAL_BYTES = 8 * 1024 * 1024


@dataclass(frozen=True)
class Skill:
    name: str
    description: str
    content: str
    file_path: str  # absolute
    disable_model_invocation: bool = False


@dataclass
class LoadResult:
    skills: list[Skill] = field(default_factory=list)
    diagnostics: list[str] = field(default_factory=list)


def _parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    if not text.startswith("---"):
        return {}, text
    lines = text.split("\n")
    if len(lines) < 3:
        return {}, text
    # Find the closing ---
    end = 1
    while end < len(lines) and lines[end].strip() != "---":
        end += 1
    if end >= len(lines):
        return {}, text
    meta_text = "\n".join(lines[1:end])
    body = "\n".join(lines[end + 1 :])
    meta: dict[str, Any] = {}
    if yaml is not None:
        try:
            parsed = yaml.safe_load(meta_text)
            if isinstance(parsed, dict):
                meta = parsed
        except Exception:  # noqa: BLE001 — bad frontmatter degrades, not fatal
            pass
    return meta, body


def _load_skill_file(path: Path, *, parent_name: str | None, byte_budget: int) -> tuple[Skill | None, list[str], int]:
    diagnostics: list[str] = []
    consumed = 0
    try:
        limit = min(_MAX_FILE_BYTES, byte_budget)
        if path.stat().st_size > limit:
            return None, [f"scan byte limit: {path}"], 0
        with path.open("rb") as stream:
            data = stream.read(limit)
            consumed = len(data)
            # Detect growth after stat without reading beyond the total budget.
            if os.fstat(stream.fileno()).st_size > limit:
                return None, [f"scan byte limit: {path}"], consumed
        text = data.decode("utf-8")
    except (OSError, UnicodeError) as exc:
        return None, [f"read failed: {path}: {exc}"], consumed
    meta, body = _parse_frontmatter(text)
    name = str(meta.get("name") or parent_name or path.parent.name)
    description = str(meta.get("description") or "").strip()
    if not description:
        diagnostics.append(f"invalid metadata: {path}: missing description")
    return (
        Skill(
            name=name,
            description=description,
            content=body,
            file_path=str(path.resolve()),
            disable_model_invocation=bool(meta.get("disable-model-invocation")),
        ),
        diagnostics,
        consumed,
    )


def load_skills(root: str | Path) -> LoadResult:
    """Bounded scan with per-file diagnostics; skip all descendant symlinks.

    A SKILL.md wins and stops descent into its directory. Limits preserve any
    already loaded skills and diagnose omissions; this is not a filesystem sandbox.
    """
    result = LoadResult()
    root_path = Path(root)
    if not root_path.is_dir():
        return result

    entries = 0
    total_bytes = 0
    entry_limit_reported = False

    def load(path: Path, parent_name: str) -> None:
        nonlocal total_bytes
        if total_bytes >= _MAX_TOTAL_BYTES:
            result.diagnostics.append(f"scan total byte limit: {path}")
            return
        if path.is_symlink():
            result.diagnostics.append(f"symlink skipped: {path}")
            return
        skill, diagnostics, consumed = _load_skill_file(
            path, parent_name=parent_name, byte_budget=_MAX_TOTAL_BYTES - total_bytes
        )
        total_bytes += consumed
        if skill is not None:
            result.skills.append(skill)
        result.diagnostics.extend(diagnostics)

    def walk(directory: Path, depth: int) -> None:
        nonlocal entries, entry_limit_reported
        if depth > _MAX_DEPTH:
            result.diagnostics.append(f"scan depth limit: {directory}")
            return
        children = []
        try:
            with os.scandir(directory) as iterator:
                for entry in iterator:
                    if entries >= _MAX_ENTRIES:
                        if not entry_limit_reported:
                            result.diagnostics.append("scan entry limit reached")
                            entry_limit_reported = True
                        break
                    entries += 1
                    children.append(Path(entry.path))
        except OSError as exc:
            result.diagnostics.append(f"list failed: {directory}: {exc}")
            return
        for child in sorted(children, key=lambda p: p.name):
            if child.name.startswith("."):
                continue
            if child.is_symlink():
                result.diagnostics.append(f"symlink skipped: {child}")
                continue
            if child.is_dir():
                if depth + 1 > _MAX_DEPTH:
                    result.diagnostics.append(f"scan depth limit: {child}")
                    continue
                skill_file = child / "SKILL.md"
                if skill_file.is_file():
                    load(skill_file, child.name)
                    continue  # SKILL.md wins: do not descend
                walk(child, depth + 1)
            elif child.is_file() and child.name.endswith(".md") and child.parent == root_path:
                # Direct .md files at the root load as skills too.
                load(child, child.stem)

    walk(root_path, 0)
    return result


def render_skills_xml(skills: list[Skill]) -> str:
    visible = [s for s in skills if not s.disable_model_invocation]
    if not visible:
        return ""
    lines = [
        "The following skills provide specialized instructions for specific tasks.",
        "Read the full skill file when the task matches its description.",
        "When a skill file references a relative path, resolve it against the skill directory.",
        "",
        "<available_skills>",
    ]
    for skill in visible:
        lines.append("  <skill>")
        lines.append(f"    <name>{escape(skill.name)}</name>")
        lines.append(f"    <description>{escape(skill.description)}</description>")
        lines.append(f"    <location>{escape(skill.file_path)}</location>")
        lines.append("  </skill>")
    lines.append("</available_skills>")
    return "\n".join(lines)


__all__ = ["Skill", "LoadResult", "load_skills", "render_skills_xml"]
