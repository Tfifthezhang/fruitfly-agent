"""Task-policy registry: schema projection and scoring are independent of strategy."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
import hashlib
import json
import keyword
import math
import os
from pathlib import Path
import sys
import tempfile
from typing import Callable

from .search import TaskCase


@dataclass(frozen=True)
class ScoreResult:
    score: float
    feedback: str = ""

    def __post_init__(self):
        if isinstance(self.score, bool) or not isinstance(self.score, (float, int)) or not math.isfinite(self.score):
            raise ValueError("score must be a finite number")
        if not isinstance(self.feedback, str) or len(self.feedback) > 1000:
            raise ValueError("feedback must be bounded text")


@dataclass(frozen=True)
class TaskPolicy:
    policy_id: str
    task_schema: str
    metric: str
    execution_id: str
    required_fields: frozenset[str]
    optional_fields: frozenset[str]
    project: Callable
    score: Callable
    execution_notice: str = "No generated code execution."
    check_available: Callable = lambda: None
    acceptance_example: str = ""


def _text_case(row):
    return TaskCase(row["input"], row["expected"])


def _text_score(output, case):
    return ScoreResult(float(" ".join(output.casefold().split()) == " ".join(case.expected.casefold().split())),
                       "scored by normalized-exact-v1")


def _json_value(value, depth=0):
    if depth > 8:
        raise ValueError("test data exceeds depth 8")
    if value is None or isinstance(value, bool):
        return
    if isinstance(value, (int, float)) and abs(value) <= 1e9 and math.isfinite(value):
        return
    if isinstance(value, str) and len(value) <= 1000:
        return
    if isinstance(value, list) and len(value) <= 100:
        for item in value:
            _json_value(item, depth + 1)
        return
    if isinstance(value, dict) and len(value) <= 100 and all(isinstance(k, str) and len(k) <= 120 for k in value):
        for item in value.values():
            _json_value(item, depth + 1)
        return
    raise ValueError("tests must contain bounded JSON data")


def python_case(row):
    """Only literal call checks, never executable test code supplied by a package."""
    entry = row.get("entry_point")
    if not isinstance(entry, str) or not entry.isidentifier() or keyword.iskeyword(entry) or entry.startswith("_") or len(entry) > 80:
        raise ValueError("Python task needs a public entry_point function name")
    tests = row.get("tests")
    if not isinstance(tests, list) or not 1 <= len(tests) <= 12:
        raise ValueError("Python task needs 1–12 declared call tests")
    for test in tests:
        if not isinstance(test, dict) or test.keys() - {"args", "kwargs", "expected", "raises", "preserve_args"} or ("expected" in test) == ("raises" in test):
            raise ValueError("each Python check needs exactly one expected value or raises")
        if not isinstance(test.get("args", []), list) or not isinstance(test.get("kwargs", {}), dict):
            raise ValueError("test args/kwargs must be a list/object")
        if any(not isinstance(k, str) or not k.isidentifier() or keyword.iskeyword(k) or k.startswith("__") for k in test.get("kwargs", {})):
            raise ValueError("invalid test keyword argument")
        if "raises" in test and (not isinstance(test["raises"], str) or test["raises"] not in {"ValueError", "TypeError", "KeyError", "IndexError", "ZeroDivisionError"}):
            raise ValueError("unsupported expected exception")
        if not isinstance(test.get("preserve_args", False), bool):
            raise ValueError("preserve_args must be boolean")
        _json_value(test)
    verification = json.dumps({"entry_point": entry, "tests": tests}, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return TaskCase(row["input"], row.get("expected", "Pass all declared function tests."), verification)


def _code(output):
    source = output.strip()
    if source.startswith("```"):
        lines = source.splitlines()
        if lines[0].strip().casefold() not in {"```", "```python", "```py"} or lines[-1].strip() != "```":
            raise ValueError("return raw Python or a single Python code fence")
        source = "\n".join(lines[1:-1])
    if not source or len(source) > 20000:
        raise ValueError("code must contain 1–20000 characters")
    return source


async def score_python(output, case, *, worker=None, timeout=4.0):
    """Run the restricted subset in a short-lived process; kill/reap on cancellation."""
    if os.name != "posix":
        raise RuntimeError("restricted Python function tests currently require POSIX")
    try:
        source = _code(output)
    except ValueError as exc:
        return ScoreResult(0.0, str(exc))
    specification = json.loads(case.verification)
    if not isinstance(specification, dict) or set(specification) != {"entry_point", "tests"}:
        raise ValueError("invalid frozen Python verification")
    python_case({"input": case.input, **specification})
    payload = {"code": source, **specification}
    data = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode()
    if len(data) > 100000:
        raise ValueError("Python trial material exceeds 100 KB")
    worker = worker if worker is not None else Path(__file__).with_name("python_worker.py").read_text()
    with tempfile.TemporaryDirectory(prefix="fruitfly-function-") as directory:
        opening = asyncio.create_task(asyncio.create_subprocess_exec(sys.executable, "-I", "-S", "-c", worker,
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            cwd=directory, env={}, limit=16000))
        try:
            process = await asyncio.shield(opening)
        except asyncio.CancelledError:
            process = await opening
            if process.returncode is None:
                process.kill()
            await process.communicate()
            raise
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(data), timeout)
        except asyncio.TimeoutError:
            if process.returncode is None:
                process.kill()
            await process.communicate()
            return ScoreResult(0.0, "function execution timed out")
        except BaseException:
            if process.returncode is None:
                process.kill()
            await process.communicate()
            raise
    if process.returncode:
        if process.returncode < 0:
            return ScoreResult(0.0, f"function worker terminated by signal {-process.returncode}; tests did not complete")
        raise RuntimeError("function test worker failed: " + stderr.decode(errors="replace")[-300:])
    if len(stdout) > 16000:
        raise RuntimeError("function test worker output exceeds protocol bounds")
    result = json.loads(stdout)
    return ScoreResult(result["score"], result["feedback"][:1000])


def _python_available():
    if os.name != "posix":
        raise ValueError("restricted Python function tests currently require POSIX")


def builtin_task_policies():
    worker = Path(__file__).with_name("python_worker.py").read_text()
    implementation = hashlib.sha256(worker.encode() + Path(__file__).read_bytes()).hexdigest()
    async def python_score(output, case):
        return await score_python(output, case, worker=worker)
    return (
        TaskPolicy("normalized-exact-v1", "single-turn-text-v1", "accuracy", "normalized-exact-v1",
            frozenset({"input", "expected"}), frozenset(), _text_case, _text_score),
        TaskPolicy("python-function-tests-v1", "python-function-v1", "test_pass_rate",
            f"python-function-tests-v1:{sys.platform}:{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}:{implementation}",
            frozenset({"input", "entry_point", "tests"}), frozenset(), python_case, python_score,
            "Generated functions run locally in a restricted Python subset; no imports/files/network APIs. POSIX process, 4s timeout, CPU limits; not a general sandbox.", _python_available,
            '{"entry_point":"f","tests":[{"args":[0],"expected":1}]}'),
    )


def task_policy(policy_id, *, policies=None):
    matches = [p for p in (builtin_task_policies() if policies is None else policies) if p.policy_id == policy_id]
    if len(matches) != 1:
        raise ValueError("unknown or duplicate task policy: " + str(policy_id))
    return matches[0]
