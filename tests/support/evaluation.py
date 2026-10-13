"""Single-configuration offline evaluation request fixture."""

def request_payload() -> dict:
    return {
        "schema_version": 2,
        "runtime": {"config_path": "/tmp/config.yaml", "profile": "test", "working_directory": "/tmp/workspace"},
        "benchmark": {"id": "swe-bench", "variant": "smoke"},
        "execution": {"attempts": 2, "concurrency": 1, "timeout_seconds": 3600},
    }
