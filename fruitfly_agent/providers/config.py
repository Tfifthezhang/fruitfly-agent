"""Small, dependency-free environment-file loader shared by CLIs."""

from __future__ import annotations

from pathlib import Path


def load_env(path: str | Path | None = None) -> dict[str, str]:
    env: dict[str, str] = {}
    candidates = (
        [Path(path)]
        if path
        else [Path.cwd() / ".env", Path(__file__).resolve().parents[2] / ".env"]
    )
    for candidate in candidates:
        if not candidate.is_file():
            continue
        for line in candidate.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            env[key.strip()] = value.strip()
        break
    return env


__all__ = ["load_env"]
