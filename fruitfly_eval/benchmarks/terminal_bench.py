"""Terminal-Bench 2.1 dataset declaration for the shared Harbor runner."""
from .harbor import HarborBenchmarkAdapter, harbor_descriptor


class TerminalBenchAdapter(HarborBenchmarkAdapter):
    descriptor = harbor_descriptor(
        benchmark_id="terminal-bench", label="Terminal-Bench",
        description="Terminal tasks scored by the official verifier",
        version="2.1", dataset="terminal-bench/terminal-bench-2-1",
        smoke_task="terminal-bench/fix-git",
    )


__all__ = ["TerminalBenchAdapter"]
