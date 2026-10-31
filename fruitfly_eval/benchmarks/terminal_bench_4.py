"""Terminal-Bench 4.0 declaration; execution belongs to the shared Harbor layer."""
from .harbor import HarborBenchmarkAdapter, harbor_descriptor


class TerminalBench4Adapter(HarborBenchmarkAdapter):
    descriptor = harbor_descriptor(
        benchmark_id="terminal-bench-4", label="Terminal-Bench 4.0",
        description="Terminal tasks with independent official verifier environments",
        version="4.0.0", dataset="terminal-bench/terminal-bench@4.0.0",
        smoke_task="terminal-bench/interleaved-vigenere",
    )


__all__ = ["TerminalBench4Adapter"]
