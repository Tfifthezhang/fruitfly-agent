"""Versioned offline evaluation request fixture."""

def request_payload(*, mode: str = "current_setup") -> dict[str, object]:
    return {
        "schema_version": 1,
        "mode": mode,
        "runtime": {
            "manifest": {"digest": "sha256:test", "components": []},
            "config_path": "/tmp/config.yaml",
            "profile": "test",
            "working_directory": "/tmp/workspace",
        },
        "benchmark": {"id": "swe-bench", "variant": "smoke"},
        "comparison": (
            {"mechanism_id": "compaction"}
            if mode == "mechanism_comparison"
            else None
        ),
        "execution": {
            "attempts": 2,
            "concurrency": 1,
            "seed": 7,
            "timeout_seconds": 3600,
        },
    }
