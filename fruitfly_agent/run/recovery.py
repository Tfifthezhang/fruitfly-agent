"""Session discovery and verification of the exact assembled runtime."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
import uuid

from fruitfly_agent.core.errors import SessionCorruptError
from fruitfly_agent.core.session.storage import Session, SessionEntry
from fruitfly_agent.interactive import ResumableSession
from fruitfly_agent.lab.base_prompt import DEFAULT_PROMPT, DEFAULT_PROMPT_ID

from .assembly import RuntimeAssembly

_RUNTIME_MANIFEST_KIND = "runtimeManifest"


def _manifest_entries(session: Session) -> list[SessionEntry]:
    return [entry for entry in session.read_all()
            if entry.type == "meta" and entry.payload.get("kind") == _RUNTIME_MANIFEST_KIND]


def check_session_manifest(
    session: Session,
    runtime: RuntimeAssembly,
    *,
    resume: bool,
    allow_legacy_default_prompt: bool = False,
) -> None:
    entries = session.read_all()
    bindings = _manifest_entries(session)
    if not resume:
        if entries:
            raise ValueError(
                "session path already contains data; use --resume or a new session path"
            )
        return
    if not bindings:
        raise ValueError("session has no runtime manifest; start a new session")
    stored = bindings[0].payload.get("manifest")
    expected = runtime.manifest.to_dict()
    if isinstance(stored, dict) and stored.get("schema_version") in (3, 4):
        if not allow_legacy_default_prompt or not known_legacy_default():
            raise ValueError("legacy session prompt identity cannot be verified; start a new session")
        expected = runtime.manifest.legacy_dict(stored["schema_version"])
    if stored != expected or any(
        item.payload.get("manifest") != stored for item in bindings[1:]
    ):
        raise ValueError(
            "resolved runtime differs from this session; start a new session "
            "for configuration changes to take effect"
        )


def known_legacy_default() -> bool:
    """Do not infer an old session's prompt from a changed builtin definition."""
    return DEFAULT_PROMPT.content_hash == _LEGACY_DEFAULT_PROMPT_HASH


_LEGACY_DEFAULT_PROMPT_HASH = "sha256:dba2d1f5d6975a2fa0d0812defd6562d8efb9df4799332bda2cab6ddd8d25ff1"


def session_prompt_reference(session: Session) -> str | None:
    for entry in _manifest_entries(session):
        manifest = entry.payload.get("manifest")
        if not isinstance(manifest, dict):
            raise ValueError("session runtime manifest is invalid")
        if manifest.get("schema_version") in (3, 4):
            return DEFAULT_PROMPT_ID
        prompt = manifest.get("base_prompt")
        if not isinstance(prompt, dict) or not isinstance(prompt.get("reference"), str):
            raise ValueError("session runtime manifest has no base prompt identity")
        return prompt["reference"]
    return None


def session_artifact_bindings(session: Session) -> dict[str, str]:
    manifests = [entry.payload.get("manifest") for entry in _manifest_entries(session)]
    if not manifests or not isinstance(manifests[0], dict):
        return {}
    artifacts = manifests[0].get("data_artifacts", ())
    if not isinstance(artifacts, (list, tuple)):
        raise ValueError("session runtime manifest has invalid data_artifacts")
    bindings: dict[str, str] = {}
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            raise ValueError("session runtime manifest has an invalid data artifact")
        key, artifact_id = artifact.get("key"), artifact.get("id")
        if not isinstance(key, str) or not isinstance(artifact_id, str) or key in bindings:
            raise ValueError("session runtime manifest has an invalid data artifact binding")
        bindings[key] = artifact_id
    return bindings


def record_session_manifest(session: Session, runtime: RuntimeAssembly) -> None:
    if _manifest_entries(session):
        return
    session.append(
        "meta",
        {
            "kind": _RUNTIME_MANIFEST_KIND,
            "manifest": runtime.manifest.to_dict(),
        },
        sync=True,
    )


def resolve_session_path(
    *,
    cwd: Path,
    session_path: str | None,
    resume: bool,
) -> Path:
    if session_path:
        path = Path(session_path)
        return path if path.is_absolute() else (cwd / path).resolve()

    state_dir = cwd / ".fruitfly"
    if resume:
        candidates = discover_resumable_sessions(cwd)
        if candidates:
            return Path(candidates[0].path)
        legacy = state_dir / "session.jsonl"
        return legacy
    return new_session_path(cwd)


def discover_resumable_sessions(
    cwd: Path,
    *,
    current_path: Path | None = None,
    manifest_digest: str | None = None,
    manifest_digests: set[str] | None = None,
) -> tuple[ResumableSession, ...]:
    """Inspect valid non-empty sessions without leaking transcript content."""

    state_dir = cwd / ".fruitfly"
    paths = list((state_dir / "sessions").glob("*.jsonl"))
    legacy = state_dir / "session.jsonl"
    if legacy.is_file():
        paths.append(legacy)
    current = current_path.resolve() if current_path is not None else None
    candidates: list[ResumableSession] = []
    for path in paths:
        resolved = path.resolve()
        if current is not None and resolved == current:
            continue
        try:
            candidate = _inspect_resumable_session(
                resolved,
                manifest_digest=manifest_digest,
                manifest_digests=manifest_digests,
            )
        except (OSError, SessionCorruptError, TypeError, ValueError):
            continue
        if candidate is not None:
            candidates.append(candidate)
    return tuple(
        sorted(
            candidates,
            key=lambda item: (item.modified_at, item.path),
            reverse=True,
        )
    )


def _inspect_resumable_session(
    path: Path,
    *,
    manifest_digest: str | None,
    manifest_digests: set[str] | None,
) -> ResumableSession | None:
    with Session(path) as session:
        messages = session.messages()
        if not messages:
            return None
        bindings = [entry.payload.get("manifest") for entry in _manifest_entries(session)]
        if not bindings or not isinstance(bindings[0], dict):
            return None
        manifest = bindings[0]
        if any(binding != manifest for binding in bindings[1:]):
            return None
        digest = manifest.get("digest")
        if not isinstance(digest, str) or not digest:
            return None
        if manifest_digests is not None and digest not in manifest_digests:
            return None
        if manifest_digest is not None and digest != manifest_digest:
            return None
        models = manifest.get("models")
        main = models.get("main") if isinstance(models, dict) else None
        model = main.get("model") if isinstance(main, dict) else ""
        profile = manifest.get("profile")
        prompt = manifest.get("base_prompt")
        prompt_label = prompt.get("label", "") if isinstance(prompt, dict) else DEFAULT_PROMPT.label
        prompt_hash = prompt.get("content_hash", "") if isinstance(prompt, dict) else DEFAULT_PROMPT.content_hash
        return ResumableSession(
            path=str(path),
            modified_at=path.stat().st_mtime,
            message_count=len(messages),
            profile=str(profile or ""),
            model=str(model or ""),
            prompt_label=str(prompt_label),
            prompt_hash=str(prompt_hash),
        )


def new_session_path(cwd: Path) -> Path:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return cwd / ".fruitfly" / "sessions" / (
        f"{timestamp}-{uuid.uuid4().hex[:8]}.jsonl"
    )
