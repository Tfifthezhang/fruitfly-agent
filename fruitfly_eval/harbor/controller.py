"""Describe the actual controller environment without importing model clients."""
from __future__ import annotations

from importlib import metadata
import platform
import sys
from typing import Any


def environment_snapshot() -> dict[str, Any]:
    """Record installed versions and declared conflicts, never environment values."""
    distributions = list(metadata.distributions())
    packages = {d.metadata["Name"]: d.version for d in distributions if d.metadata["Name"]}
    issues = []
    try:
        from packaging.requirements import Requirement  # type: ignore[import-not-found, unused-ignore]
        from packaging.utils import canonicalize_name  # type: ignore[import-not-found, unused-ignore]
    except ImportError:
        dependency_check = "unverified: packaging is unavailable"
    else:
        versions = {canonicalize_name(name): version for name, version in packages.items()}
        for distribution in distributions:
            for text in distribution.requires or ():
                requirement = Requirement(text)
                if requirement.marker and not requirement.marker.evaluate({"extra": ""}):
                    continue
                installed = versions.get(canonicalize_name(requirement.name))
                if installed is None or (requirement.specifier and not requirement.specifier.contains(installed)):
                    issues.append({"package": distribution.metadata["Name"], "requirement": requirement.name + str(requirement.specifier),
                                   "installed": installed})
        dependency_check = "conflicts" if issues else "passed"
    return {"python": sys.version.split()[0], "executable": sys.executable,
            "platform": platform.system(), "architecture": platform.machine(),
            "libc": list(platform.libc_ver()), "packages": dict(sorted(packages.items())),
            "dependency_check": dependency_check,
            "dependency_issues": sorted(issues, key=lambda row: (row["package"], row["requirement"]))}
