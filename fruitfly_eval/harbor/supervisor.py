"""Linux container process ownership and bounded Agent cancellation.

Normal completion preserves task-created background services for verification.
Cancellation stops the Agent and its still-owned descendants. Final container
retirement remains Harbor's responsibility.
"""
from __future__ import annotations

import argparse
import ctypes
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import uuid

from .material import write_json


def process_identity(pid: int) -> tuple[int, int] | None:
    try:
        data = Path(f"/proc/{pid}/stat").read_text()
        values = data[data.rindex(")") + 2:].split()
        return int(values[1]), int(values[19])
    except (OSError, ValueError, IndexError):
        return None


def descendants(root: int) -> list[tuple[int, int]]:
    processes = {}
    for path in Path("/proc").iterdir():
        if path.name.isdigit():
            identity = process_identity(int(path.name))
            if identity is not None:
                processes[int(path.name)] = identity
    owned = {root}
    while True:
        added = {pid for pid, (parent, _) in processes.items() if parent in owned} - owned
        if not added:
            break
        owned.update(added)
    return [(pid, processes[pid][1]) for pid in owned if pid in processes]


def signal_owned(processes: list[tuple[int, int]], sig: int) -> None:
    for pid, start in reversed(processes):
        current = process_identity(pid)
        if current is not None and current[1] == start:
            try:
                os.kill(pid, sig)
            except ProcessLookupError:
                pass


def stop(path: Path, token: str | None = None) -> int:
    if token is not None:
        write_json(path.with_name(path.name + ".stop-" + token), {"token": token})
    if not path.is_file():
        return 0  # Startup may have been cancelled before the supervisor exists.
    record = json.loads(path.read_text())
    if token is not None and record.get("token") != token:
        return 0  # A cancelled start has not published its own record yet.
    if record.get("state") in {"finished", "cancelled"}:
        return 0
    pid = record["pid"]
    identity = process_identity(pid)
    if identity is None:
        raise RuntimeError("Agent supervisor disappeared without confirming cleanup")
    if identity[1] != record["start_ticks"]:
        raise RuntimeError("Agent supervisor PID was reused; refusing to signal it")
    os.kill(pid, signal.SIGTERM)
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        if path.is_file() and json.loads(path.read_text()).get("state") in {"finished", "cancelled"}:
            return 0
        time.sleep(.1)
    raise RuntimeError("Agent supervisor cleanup did not finish")


def supervise(command: list[str], path: Path, token: str | None = None) -> int:
    cancelled = False
    token = token or uuid.uuid4().hex
    stop_path = path.with_name(path.name + ".stop-" + token)

    def cancel(signum, frame):
        nonlocal cancelled
        cancelled = True

    signal.signal(signal.SIGTERM, cancel)
    signal.signal(signal.SIGINT, cancel)
    identity = process_identity(os.getpid())
    if identity is None:
        raise RuntimeError("Agent supervision requires Linux /proc")
    # Adopt detached grandchildren until the Agent finishes. This makes double
    # forks visible during cancellation without killing healthy task services
    # when the CLI exits normally.
    if ctypes.CDLL(None, use_errno=True).prctl(36, 1, 0, 0, 0) != 0:
        raise RuntimeError("could not enable Agent child-process supervision")
    record = {"schema_version": 1, "pid": os.getpid(), "start_ticks": identity[1],
              "token": token, "state": "running"}
    # Publish before spawning; the supervisor itself handles a stop during spawn.
    write_json(path, record)
    child = None
    code = 130
    try:
        if stop_path.exists() or cancelled:
            cancelled = True
        else:
            child = subprocess.Popen(command, start_new_session=True)
            while child.poll() is None and not cancelled and not stop_path.exists():
                time.sleep(.1)
            cancelled = cancelled or stop_path.exists()
            if cancelled:
                owned = [(p, start) for p, start in descendants(os.getpid()) if p != os.getpid()]
                signal_owned(owned, signal.SIGTERM)
                deadline = time.monotonic() + 3
                while child.poll() is None and time.monotonic() < deadline:
                    time.sleep(.1)
                signal_owned(owned, signal.SIGKILL)
            code = child.wait()
    finally:
        if cancelled or (child is not None and child.poll() is None):
            deadline = time.monotonic() + 3
            while time.monotonic() < deadline:
                owned = [(p, start) for p, start in descendants(os.getpid()) if p != os.getpid()]
                if not owned:
                    break
                signal_owned(owned, signal.SIGKILL)
                if child is not None:
                    child.poll()
                try:
                    while os.waitpid(-1, os.WNOHANG)[0]:
                        pass
                except ChildProcessError:
                    pass
                time.sleep(.02)
            else:
                raise RuntimeError("Agent descendant cleanup could not be confirmed")
        write_json(path, {**record, "state": "cancelled" if cancelled else "finished",
                          "return_code": child.returncode if child is not None else code})
    return 130 if cancelled else code


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--record", required=True, type=Path)
    parser.add_argument("--stop", action="store_true")
    parser.add_argument("--token")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if args.stop:
        return stop(args.record, args.token)
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        parser.error("an Agent command is required")
    return supervise(command, args.record, args.token)


if __name__ == "__main__":
    sys.exit(main())
