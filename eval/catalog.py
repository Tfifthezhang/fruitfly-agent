"""Data-driven registry of standardized benchmark adapters."""

from __future__ import annotations

from typing import Iterable

from .benchmarks import BenchmarkAdapter, SWEBenchAdapter, TerminalBenchAdapter


class BenchmarkCatalog:
    def __init__(self, adapters: Iterable[BenchmarkAdapter]) -> None:
        values = tuple(adapters)
        indexed = {item.descriptor.benchmark_id: item for item in values}
        if len(indexed) != len(values):
            raise ValueError("benchmark ids must be unique")
        self._adapters = indexed

    def get(self, benchmark_id: str) -> BenchmarkAdapter:
        try:
            return self._adapters[benchmark_id]
        except KeyError as exc:
            available = ", ".join(sorted(self._adapters)) or "none"
            raise ValueError(
                f"unknown benchmark {benchmark_id!r} (available: {available})"
            ) from exc

    def adapters(self) -> tuple[BenchmarkAdapter, ...]:
        return tuple(self._adapters[key] for key in sorted(self._adapters))

    def to_dict(self) -> dict[str, object]:
        benchmarks = []
        for adapter in self.adapters():
            descriptor = adapter.descriptor
            variants = []
            for variant in descriptor.variants:
                preflight = adapter.preflight(variant.variant_id)
                variants.append({**variant.to_dict(), "preflight": preflight.to_dict()})
            benchmarks.append(
                {
                    "id": descriptor.benchmark_id,
                    "label": descriptor.label,
                    "description": descriptor.description,
                    "version": descriptor.version,
                    "adapter_version": descriptor.adapter_version,
                    "metrics": list(descriptor.metric_names),
                    "network": dict(descriptor.network),
                    "isolation": descriptor.isolation,
                    "variants": variants,
                }
            )
        return {
            "schema_version": 1,
            "modes": [
                {
                    "id": "current_setup",
                    "label": "Test current setup",
                    "description": "Measure the complete active harness configuration",
                },
                {
                    "id": "mechanism_comparison",
                    "label": "Compare a mechanism",
                    "description": "Hold all conditions fixed and remove one active mechanism",
                },
            ],
            "benchmarks": benchmarks,
        }


def builtin_catalog() -> BenchmarkCatalog:
    return BenchmarkCatalog((SWEBenchAdapter(), TerminalBenchAdapter()))


__all__ = ["BenchmarkCatalog", "builtin_catalog"]
