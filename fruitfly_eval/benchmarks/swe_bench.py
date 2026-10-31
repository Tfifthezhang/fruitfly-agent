"""SWE-bench Verified dataset declaration for the shared Harbor runner."""
from .harbor import HarborBenchmarkAdapter, harbor_descriptor


class SWEBenchAdapter(HarborBenchmarkAdapter):
    descriptor = harbor_descriptor(
        benchmark_id="swe-bench", label="SWE-bench",
        description="Repository issue repair scored by the official verifier",
        version="Verified", dataset="swe-bench/swe-bench-verified",
        smoke_task="swe-bench/psf__requests-1142",
    )


__all__ = ["SWEBenchAdapter"]
