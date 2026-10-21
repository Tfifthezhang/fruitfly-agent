"""Terminal-Bench 2.1 dataset declaration for the shared Harbor runner."""
from .base import BenchmarkVariant
from .harbor import HarborBenchmarkAdapter, harbor_descriptor


class TerminalBenchAdapter(HarborBenchmarkAdapter):
    descriptor = harbor_descriptor(
        benchmark_id="terminal-bench", label="Terminal-Bench",
        description="Terminal tasks scored by the official verifier",
        version="2.1", dataset="terminal-bench/terminal-bench-2-1",
        smoke_task="terminal-bench/fix-git",
        subsets=(BenchmarkVariant(
            "starter", "Starter batch · 5 CPU tasks", "Run five fixed terminal tasks",
            task_names=tuple("terminal-bench/" + name for name in (
                "fix-git", "log-summary-date-ranges", "regex-log", "cancel-async-tasks", "fix-code-vulnerability")),
        ),),
    )


__all__ = ["TerminalBenchAdapter"]
