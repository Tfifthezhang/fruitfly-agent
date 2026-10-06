"""SWE-bench Verified through Harbor's official task containers and verifier."""

from __future__ import annotations

from .base import BenchmarkDescriptor, BenchmarkVariant
from .harbor import HarborBenchmarkAdapter


class SWEBenchAdapter(HarborBenchmarkAdapter):
    descriptor = BenchmarkDescriptor(
        benchmark_id="swe-bench",
        label="SWE-bench",
        description="Repository issue repair scored by the official SWE-bench verifier",
        version="Verified",
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
                "The full Verified dataset on a CPU-only Harbor environment",
            ),
            BenchmarkVariant(
                "gpu",
                "GPU",
                "The full Verified dataset on a GPU-capable Harbor environment",
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
        dataset="swe-bench/swe-bench-verified",
        network={
            "provider": True,
            "control_plane": True,
            "task_environment": True,
            "verifier": False,
        },
        isolation="harbor_task_container",
        smoke_task="swe-bench/psf__requests-1142",
    )


__all__ = ["SWEBenchAdapter"]
