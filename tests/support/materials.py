"""Small offline model and improvement materials."""
from pathlib import Path


def _write_models(root: Path, *, context_window: int = 4000) -> None:
    (root / '.fruitfly').mkdir(exist_ok=True)
    (root / ".fruitfly/models.yaml").write_text(
        'models:\n  local:\n    sdk: anthropic\n    protocol: messages\n    model: offline-model\n'
        f"    api_key_env: TEST_API_KEY\n    context_window: {context_window}\n"
        "    max_output_tokens: 1024\n",
        encoding="utf-8",
    )


def _write_cases(root: Path) -> None:
    from tests.support.task_packs import install
    install(root)
