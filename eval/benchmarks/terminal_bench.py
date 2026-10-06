"""Terminal-Bench 2.0 through Harbor's official task containers and verifier."""

from __future__ import annotations

from .base import BenchmarkDescriptor, BenchmarkVariant
from .harbor import HarborBenchmarkAdapter


class TerminalBenchAdapter(HarborBenchmarkAdapter):
    descriptor = BenchmarkDescriptor(
        benchmark_id="terminal-bench",
        label="Terminal-Bench",
        description="Terminal agent tasks scored by the official Harbor verifier",
        version="2.0",
        adapter_version="3",
        variants=(
            BenchmarkVariant(
                "smoke",
                "Low-resource smoke",
                "One deterministic task for validating the complete evaluation path",
            ),
            BenchmarkVariant(
                "no_gpu",
                "No GPU",
                "The full dataset on a CPU-only Harbor environment",
            ),
            BenchmarkVariant(
                "gpu",
                "GPU",
                "The full dataset on a GPU-capable Harbor environment",
            ),
        ),
        metric_names=(
            "success_rate",
            "official_reward",
            "error_rate",
            "timeout_rate",
            "input_tokens",
            "output_tokens",
            "cost_usd",
            "latency_ms",
        ),
        dataset="terminal-bench@2.0",
        network={
            "provider": True,
            "control_plane": True,
            "task_environment": True,
            "verifier": False,
        },
        isolation="harbor_task_container",
        smoke_task="fix-git",
    )


__all__ = ["TerminalBenchAdapter"]
