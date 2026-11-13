"""Restore conversations and record the runtime used for subsequent runs."""
from __future__ import annotations
from datetime import UTC, datetime
from pathlib import Path
import re
import uuid
from fruitfly_agent.core.errors import SessionCorruptError
from fruitfly_agent.core.data_model import AgentMessage, UserMessage
from fruitfly_agent.core.session.storage import Session, SessionSnapshot
from fruitfly_agent.interactive import ResumableSession
from fruitfly_agent.run.storage.session_index import SessionIndex
from .assembly import RuntimeAssembly
from .manifest import digest_manifest

_RUNTIME_MANIFEST_KIND = "runtimeManifest"


def session_manifests(session: Session | SessionSnapshot) -> list[dict]:
    """Validate each recorded identity against its own contents, not today's config."""
    manifests = []
    for entry in session.read_all():
        if entry.type != "meta" or entry.payload.get("kind") != _RUNTIME_MANIFEST_KIND:
            continue
        manifest = entry.payload.get("manifest")
        if not isinstance(manifest, dict) or manifest.get("schema_version") not in (3, 4, 5, 6, 7, 8):
            raise ValueError(f"session entry {entry.id}: unsupported runtime manifest")
        if not isinstance(manifest.get("models"), dict) or not isinstance(manifest.get("components"), list):
            raise ValueError(f"session entry {entry.id}: malformed runtime manifest")
        if manifest.get('schema_version') == 8 and (not isinstance(manifest.get('tool_services'), list)
                or not manifest['tool_services'] or any(not isinstance(item, dict) or
                    not isinstance(item.get('name'), str) or not item['name']
                    or any(not isinstance(item.get(key), str) or not re.fullmatch(r'sha256:[0-9a-f]{64}', item[key])
                           for key in ('artifact', 'digest'))
                    or not isinstance(item.get('tools'), list)
                    or any(not isinstance(name, str) or not name for name in item['tools'])
                    for item in manifest['tool_services'])):
            raise ValueError(f'session entry {entry.id}: malformed tool service identity')
        content = {key: value for key, value in manifest.items() if key != "digest"}
        if manifest.get("digest") != digest_manifest(content):
            raise ValueError(f"session entry {entry.id}: runtime manifest digest does not match its contents")
        manifests.append(manifest)
    return manifests


def check_session_manifest(session: Session, runtime: RuntimeAssembly, *, resume: bool) -> None:
    """Validate history; a changed runtime identity is allowed when continuing chat."""
    if not resume:
        if session.read_all():
            raise ValueError("session path already contains data; use --resume or a new session path")
        return
    session_manifests(session)
    session.canonical_messages()
    session.messages()


def record_session_manifest(
    session: Session, runtime: RuntimeAssembly, *, messages: list[AgentMessage] | None = None,
) -> None:
    """Append after successful startup; the next run belongs to this snapshot."""
    manifests = session_manifests(session)
    current = runtime.manifest.to_dict()
    if manifests and manifests[-1] == current and messages is None:
        return
    payload = {"kind": _RUNTIME_MANIFEST_KIND, "manifest": current}
    if messages is not None:
        payload["contextProjection"] = {"messages": [message.to_dict() for message in messages]}
    session.append("meta", payload, sync=True)


def resolve_session_path(*, cwd: Path, session_path: str | None, resume: bool) -> Path:
    if session_path:
        path = Path(session_path)
        return path if path.is_absolute() else (cwd / path).resolve()
    if resume:
        candidates = [item for item in discover_resumable_sessions(cwd) if item.available]
        if candidates:
            return Path(candidates[0].path)
        raise ValueError("no available non-empty sessions; use --session PATH to inspect a specific session")
    return new_session_path(cwd)


def discover_resumable_sessions(cwd: Path, *, current_path: Path | None = None, on_update=None) -> tuple[ResumableSession, ...]:
    """Read history without repairing files; show unavailable sessions with reasons."""
    state_dir = cwd / ".fruitfly"
    paths = list((state_dir / "sessions").glob("*.jsonl"))
    legacy = state_dir / "session.jsonl"
    if legacy.is_file():
        paths.append(legacy)
    current = current_path.resolve() if current_path is not None else None
    candidates = []
    index = SessionIndex(state_dir / 'cache' / 'session-index')
    paths.sort(key=lambda path: path.name, reverse=True)
    for path in paths:
        resolved = path.resolve()
        if resolved == current:
            continue
        try:
            candidate = index.discover(resolved, lambda: _inspect_candidate(path, resolved))
            if candidate is not None:
                candidates.append(candidate)
        except (OSError, SessionCorruptError, TypeError, ValueError) as exc:
            if not path.exists():
                continue
            candidates.append(ResumableSession(
                path=str(resolved), modified_at=path.stat().st_mtime,
                message_count=0, profile="", model="", available=False, reason=str(exc),
            ))
        if on_update is not None:
            on_update(tuple(sorted(candidates, key=lambda item: (item.modified_at, item.path), reverse=True)))
    return tuple(sorted(candidates, key=lambda item: (item.modified_at, item.path), reverse=True))


def new_session_path(cwd: Path) -> Path:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return cwd / ".fruitfly" / "sessions" / f"{timestamp}-{uuid.uuid4().hex[:8]}.jsonl"


def _inspect_candidate(path: Path, resolved: Path) -> ResumableSession | None:
    modified = path.stat().st_mtime
    session = Session.inspect(resolved)
    messages = session.canonical_messages()
    if not messages:
        return None
    session.messages()
    users = [m for m in messages if isinstance(m, UserMessage)]
    content = users[0].content if users else ''
    title = content if isinstance(content, str) else ' '.join(getattr(b, 'text', '') for b in content)
    title = ''.join(c if c.isprintable() else ' ' for c in title)
    title = ' '.join(title.split())[:100]
    timestamps = [entry.timestamp for entry in session.read_all() if entry.type == 'message' and entry.timestamp > 0]
    modified = max(timestamps) if timestamps else modified
    manifests = session_manifests(session)
    manifest = manifests[-1] if manifests else {}
    models = manifest.get("models", {})
    main = models.get("main", {})
    prompt = manifest.get("base_prompt", {})
    if not isinstance(main, dict) or not isinstance(prompt, dict):
        raise ValueError("session runtime metadata is malformed")
    return ResumableSession(
        path=str(resolved), modified_at=modified, message_count=len(messages),
        title=title, user_turns=len(users),
        profile=str(manifest.get("profile", "")), model=str(main.get("model", "")),
        prompt_label=str(prompt.get("label", "")), prompt_hash=str(prompt.get("content_hash", "")),
        available=not session.locked,
        reason="session is locked by another process" if session.locked else "",
    )
