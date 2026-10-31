"""Harbor runner behavior and failure contracts."""
from __future__ import annotations
import sys
import unittest
from pathlib import Path
import tempfile
from fruitfly_eval.runner import (
    _forward_agent_events, _forward_logs, _forward_trial_results, run_harbor_job,
)
from tests.support.harbor import load_harbor_agent


FruitFlyHarborAgent = load_harbor_agent()


class HarborAdapterTests(unittest.TestCase):
    def test_harbor_job_streams_then_archives_display_transport(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            agent = root / "job" / "trial" / "agent"
            agent.mkdir(parents=True)
            stream = agent / "live-events.jsonl"
            script = (
                "from pathlib import Path; import time; "
                f"Path({str(stream)!r}).write_text(" 
                "'{\"type\":\"run_started\",\"run_id\":\"one\"}\\n'); "
                "time.sleep(0.5)"
            )
            updates = []
            code, detail = run_harbor_job(
                [sys.executable, "-c", script], environment={}, timeout=5,
                job_root=root, progress=updates.append,
                job_id="current",
            )
            self.assertEqual((code, detail), (0, ""))
            self.assertEqual(next(item for item in updates if item["type"] == "agent_event")["event"]["type"], "run_started")
            self.assertFalse(stream.exists())
            self.assertIn('"type":"run_started"', stream.with_name("events.jsonl").read_text())

    def test_quiet_harbor_job_emits_progress_before_it_exits(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            released = root / "released"
            script = (
                "from pathlib import Path; import time; "
                f"p=Path({str(released)!r}); "
                "exec('while not p.exists():\\n time.sleep(0.01)')"
            )
            updates = []

            def observe(event):
                updates.append(event)
                released.touch()  # The child cannot finish until progress arrives.

            code, detail = run_harbor_job(
                [sys.executable, "-c", script], environment={}, timeout=5,
                job_root=root, progress=observe, job_id="current",
            )
            self.assertEqual((code, detail), (0, ""))
            event = updates[0]
            self.assertEqual(event["type"], "job_progress")
            self.assertEqual(event["agent_runs_started"], 0)
            self.assertEqual(event["completed"], 0)
            self.assertGreaterEqual(event["elapsed_seconds"], 0)

    def test_runner_output_is_streamed_in_full_and_persisted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            released = root / "released"
            script = (
                "from pathlib import Path; import sys,time; "
                "print('early output',flush=True); "
                f"p=Path({str(released)!r}); "
                "exec('while not p.exists():\\n time.sleep(0.01)'); "
                "sys.stderr.write('E'*10000+'tail without newline')"
            )
            updates = []

            def observe(event):
                updates.append(event)
                if event["type"] == "log" and "early output" in event["text"]:
                    released.touch()

            code, _ = run_harbor_job(
                [sys.executable, "-u", "-c", script], environment={}, timeout=5,
                job_root=root, progress=observe, job_id="current",
            )
            self.assertEqual(code, 0)
            expected = "early output\n" + "E"*10000 + "tail without newline"
            self.assertEqual((root / "harbor.log").read_text(), expected)
            self.assertEqual("".join(e["text"] for e in updates if e["type"] == "log"), expected)

    def test_setup_and_exception_logs_forward_partial_lines_once(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            agent = root / "job" / "trial" / "agent"
            agent.mkdir(parents=True)
            setup = agent / "setup.log"
            setup.write_bytes("ＯＫ\n".encode() + b"partial")
            offsets, fragments, updates = {}, {}, []
            _forward_logs(root, "current", offsets, fragments, updates.append)
            self.assertEqual(updates[0]["text"], "ＯＫ\n")
            with setup.open("ab") as handle:
                handle.write(b" completed\n")
            (agent.parent / "exception.txt").write_text("timeout traceback")
            _forward_logs(root, "current", offsets, fragments, updates.append, final=True)
            _forward_logs(root, "current", offsets, fragments, updates.append, final=True)
            self.assertEqual([e["text"] for e in updates], ["ＯＫ\n", "partial completed\n", "timeout traceback"])

    def test_transient_registry_failure_retries_before_job_and_keeps_logs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "artifacts").mkdir()  # Staged Agent inputs are not a started Harbor job.
            count = root / "count"
            script = (
                "from pathlib import Path; import sys; "
                f"p=Path({str(count)!r}); "
                "n=int(p.read_text())+1 if p.exists() else 1; p.write_text(str(n)); "
                "print('ConnectError: Error getting dataset terminal-bench/terminal-bench-2-1' if n==1 else 'registry ready',flush=True); "
                "sys.exit(1 if n==1 else 0)"
            )
            updates = []
            code, _ = run_harbor_job([sys.executable, "-u", "-c", script], environment={}, timeout=5, job_root=root, progress=updates.append, job_id="current")
            self.assertEqual(code, 0)
            self.assertEqual(count.read_text(), "2")
            self.assertIn("ConnectError", (root / "harbor-attempt-1.log").read_text())
            self.assertEqual((root / "harbor.log").read_text(), "registry ready\n")
            text = "".join(e["text"] for e in updates if e["type"] == "log")
            self.assertEqual(text.count("ConnectError:"), 1)
            self.assertIn("retry 2/3", text)

    def test_registry_failure_after_job_creation_is_never_retried(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "job").mkdir()
            script = "print('ConnectError: Error getting dataset terminal-bench/terminal-bench-2-1'); raise SystemExit(1)"
            code, _ = run_harbor_job([sys.executable, "-c", script], environment={}, timeout=5, job_root=root, progress=None, job_id="current")
            self.assertEqual(code, 1)
            self.assertFalse((root / "harbor-attempt-1.log").exists())

    def test_live_transport_forwards_complete_events_and_trial_results(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            agent = root / "job" / "trial" / "agent"
            agent.mkdir(parents=True)
            stream = agent / "live-events.jsonl"
            updates = []
            offsets = {}
            fragments = {}
            stream.write_bytes(b'{"type":"run_started","run_id":"one"}\n{"type":')
            _forward_agent_events(root, "current", offsets, fragments, updates.append)
            self.assertEqual(len(updates), 1)
            self.assertEqual(next(item for item in updates if item["type"] == "agent_event")["event"]["type"], "run_started")
            with stream.open("ab") as handle:
                handle.write(b'"run_finished","run_id":"one"}\n')
            _forward_agent_events(root, "current", offsets, fragments, updates.append)
            self.assertEqual(updates[-1]["event"]["type"], "run_finished")
            trial_result = agent.parent / "result.json"
            trial_result.write_text('{"status":"completed"}', encoding="utf-8")
            seen = set()
            _forward_trial_results(root, "current", seen, updates.append)
            _forward_trial_results(root, "current", seen, updates.append)
            self.assertEqual([item["type"] for item in updates].count("trial_finished"), 1)
