"""Small offline model and optimization materials."""
import json
from pathlib import Path


def _write_models(root: Path) -> None:
    (root / "models.yaml").write_text(
        "models:\n  local:\n    provider: anthropic\n    model: offline-model\n"
        "    api_key_env: TEST_API_KEY\n    context_window: 4000\n"
        "    max_output_tokens: 1024\n",
        encoding="utf-8",
    )


def _write_cases(root: Path) -> None:
    path = root / ".fruitfly" / "optimization" / "cases.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "train": [{"input": "say A", "expected": "A"}],
        "validation": [{"input": "say B", "expected": "B"}],
    }), encoding="utf-8")
