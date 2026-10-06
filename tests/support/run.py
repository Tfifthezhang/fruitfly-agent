"""CLI inputs and persisted session fixtures."""
import argparse
from pathlib import Path
from fruitfly_agent.core.session import Session
from fruitfly_agent.core.data_model import UserMessage


def _write_catalog(path: Path, profiles: dict[str, str]) -> None:
    rows = ["models:"]
    for profile, model in profiles.items():
        rows.extend(
            (
                f"  {profile}:",
                "    provider: anthropic",
                f"    model: {model}",
                "    api_key_env: TEST_API_KEY",
                "    context_window: 4000",
                "    max_output_tokens: 4096",
            )
        )
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")


def _args(**values):
    defaults = dict(
        task="",
        resume=False,
        cwd=None,
        session=None,
        config=None,
        profile=None,
    )
    defaults.update(values)
    return argparse.Namespace(**defaults)


def _seed_resumable_session(
    path: Path,
    *,
    digest: str = "sha256:test",
    message: str | None = "saved",
) -> None:
    with Session(path) as session:
        session.append(
            "meta",
            {
                "kind": "runtimeManifest",
                "manifest": {
                    "schema_version": 3,
                    "profile": "default",
                    "model_profile": "offline",
                    "models": {"main": {"model": "offline-model"}},
                    "components": [],
                    "context_pipeline": None,
                    "digest": digest,
                },
            },
            sync=True,
        )
        if message is not None:
            session.append(
                "message",
                {"message": UserMessage(content=message).to_dict()},
            )
