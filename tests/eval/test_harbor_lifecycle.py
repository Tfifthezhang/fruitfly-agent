"""Stop the owned Agent/processes without stopping healthy task services."""
import asyncio
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from fruitfly_eval.harbor.lifecycle import owned_containers, request_stop, retire_containers
from fruitfly_eval.harbor.material import write_json
from fruitfly_eval.harbor.supervisor import signal_owned, stop
from fruitfly_eval.results import load_harbor_job_result, parse_harbor_job_result
from fruitfly_eval.runner import run_harbor_job
from tests.support.harbor import installed_agent_inputs, load_harbor_agent

FruitFlyHarborAgent = load_harbor_agent()


class HarborLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory())).resolve()

    def test_timeout_stops_the_owned_process_group_and_records_cleanup(self):
        marker = self.root / "interrupted"
        script = ("import signal,time; from pathlib import Path; "
                  f"signal.signal(signal.SIGINT,lambda *a: (Path({str(marker)!r}).touch(),exit(0))); "
                  "time.sleep(30)")
        with self.assertRaisesRegex(RuntimeError, "timed out"):
            run_harbor_job([sys.executable, "-c", script], environment={}, timeout=1,
                           job_root=self.root, progress=None, job_id="owned")
        self.assertTrue(marker.exists())
        self.assertEqual(json.loads((self.root / "cleanup.json").read_text())["state"], "finished")

    def test_stop_request_is_job_scoped_and_confirmation_follows_cleanup(self):
        evaluation = self.root / "evaluation"
        harbor = evaluation / "artifacts/harbor"
        harbor.mkdir(parents=True)
        script = "import time; time.sleep(30)"
        def observe(event):
            if event["type"] == "job_progress":
                requested = request_stop(evaluation, wait_seconds=0)
                self.assertEqual(requested["state"], "stop_requested")
        with self.assertRaisesRegex(RuntimeError, "stopped by request"):
            run_harbor_job([sys.executable, "-c", script], environment={}, timeout=10,
                           job_root=harbor, progress=observe, job_id="owned")
        result = request_stop(evaluation, wait_seconds=0)
        self.assertFalse(result["requested"])
        self.assertEqual(result["state"], "finished")

    def test_timeout_retires_workers_even_when_group_leader_exits_first(self):
        ready, stopped = self.root / "worker-ready", self.root / "worker-stopped"
        worker = ("import signal,time; from pathlib import Path; "
                  "signal.signal(signal.SIGINT,signal.SIG_IGN); "
                  f"signal.signal(signal.SIGTERM,lambda *a: (Path({str(stopped)!r}).touch(),exit(0))); "
                  f"Path({str(ready)!r}).touch(); time.sleep(30)")
        script = ("import subprocess,sys,time; "
                  f"subprocess.Popen([sys.executable,'-c',{worker!r}]); time.sleep(30)")
        with self.assertRaisesRegex(RuntimeError, "timed out"):
            run_harbor_job([sys.executable, "-c", script], environment={}, timeout=1,
                           job_root=self.root, progress=None, job_id="owned")
        self.assertTrue(ready.exists())
        self.assertTrue(stopped.exists())

    def test_old_stop_token_cannot_stop_a_new_runner(self):
        (self.root / "stop-request.json").write_text(json.dumps({"token": "old"}))
        code, _ = run_harbor_job([sys.executable, "-c", "print('complete')"], environment={}, timeout=5,
                                job_root=self.root, progress=None, job_id="owned")
        self.assertEqual(code, 0)

    def test_cleanup_uses_exact_owned_compose_labels(self):
        trial = self.root / "job/Task.Name__Ab1"
        trial.mkdir(parents=True)
        (trial / "config.json").write_text(json.dumps({"trial_name": trial.name}))
        calls = []
        def run(command, **kwargs):
            calls.append(command)
            if command[1] == "ps":
                return subprocess.CompletedProcess(command, 0, "owned-id\n" if len(calls) == 1 else "", "")
            return subprocess.CompletedProcess(command, 0, "", "")
        with patch("fruitfly_eval.harbor.lifecycle.subprocess.run", side_effect=run):
            self.assertEqual(retire_containers(self.root, "docker", {}), ["owned-id"])
        self.assertEqual(calls[0][-1], "label=com.docker.compose.project=task-name__ab1__env")
        self.assertEqual(calls[1], ["docker", "rm", "-f", "-v", "owned-id"])

    def test_owned_networks_and_volumes_are_retired_without_global_pruning(self):
        trial = self.root / "job/owned"
        trial.mkdir(parents=True)
        (trial / "config.json").write_text('{"trial_name":"owned"}')
        calls = []
        def run(command, **kwargs):
            calls.append(command)
            output = ""
            if command[1:3] in (["network", "ls"], ["volume", "ls"]):
                self.assertEqual(command[-1], "label=com.docker.compose.project=owned__env")
                output = "owned-" + command[1]
            return subprocess.CompletedProcess(command, 0, output, "")
        with patch("fruitfly_eval.harbor.lifecycle.subprocess.run", side_effect=run):
            retire_containers(self.root, "docker", {})
        self.assertIn(["docker", "network", "rm", "owned-network"], calls)
        self.assertIn(["docker", "volume", "rm", "owned-volume"], calls)
        self.assertFalse(any("prune" in command for command in calls))
        self.assertEqual(json.loads((self.root / "resources.json").read_text())["volumes"], ["owned-volume"])

    def test_mismatched_trial_identity_cannot_select_unrelated_containers(self):
        trial = self.root / "job/actual"
        trial.mkdir(parents=True)
        (trial / "config.json").write_text('{"trial_name":"unrelated"}')
        with patch("fruitfly_eval.harbor.lifecycle.subprocess.run") as docker:
            self.assertEqual(owned_containers(self.root, "docker", {}), [])
        docker.assert_not_called()

    def test_cleanup_failure_keeps_events_live_and_records_unconfirmed_state(self):
        events = self.root / "job/trial/agent/live-events.jsonl"
        events.parent.mkdir(parents=True)
        events.write_text("evidence")
        with patch("fruitfly_eval.runner.retire_containers", side_effect=RuntimeError("Docker unavailable")):
            with self.assertRaisesRegex(RuntimeError, "cleanup is unconfirmed"):
                run_harbor_job([sys.executable, "-c", "pass"], environment={}, timeout=5,
                               job_root=self.root, progress=None, job_id="owned", docker="fake")
        self.assertTrue(events.exists())
        self.assertEqual(json.loads((self.root / "control.json").read_text())["state"], "cleanup_failed")

    def test_supervisor_pid_reuse_never_signals_an_unrelated_process(self):
        record = self.root / "process.json"
        write_json(record, {"state": "running", "pid": 12345, "start_ticks": 1, "token": "one"})
        with patch("fruitfly_eval.harbor.supervisor.process_identity", return_value=(1, 2)), patch("os.kill") as kill:
            with self.assertRaisesRegex(RuntimeError, "PID was reused"):
                stop(record)
            signal_owned([(12345, 1)], signal.SIGKILL)
        kill.assert_not_called()

    def test_cancel_before_spawn_publishes_a_token_specific_stop_marker(self):
        record = self.root / "process.json"
        self.assertEqual(stop(record, "starting"), 0)
        self.assertTrue(record.with_name("process.json.stop-starting").is_file())

    def test_cancelled_bridge_confirms_supervisor_stop_before_returning(self):
        agent = FruitFlyHarborAgent.__new__(FruitFlyHarborAgent)
        installed_agent_inputs(agent, self.root)
        agent.profile = "default"
        agent.exec_as_agent = AsyncMock(side_effect=[asyncio.CancelledError(), None])
        environment = SimpleNamespace(stop=AsyncMock())
        with self.assertRaises(asyncio.CancelledError):
            asyncio.run(agent.run("task", environment, SimpleNamespace()))
        self.assertIn("--stop", agent.exec_as_agent.await_args_list[1].kwargs["command"])
        environment.stop.assert_not_called()

    def test_failed_supervisor_cleanup_stops_environment_before_verification(self):
        agent = FruitFlyHarborAgent.__new__(FruitFlyHarborAgent)
        installed_agent_inputs(agent, self.root)
        agent.profile = "default"
        agent.exec_as_agent = AsyncMock(side_effect=[asyncio.CancelledError(), RuntimeError("control failure")])
        environment = SimpleNamespace(stop=AsyncMock())
        with self.assertRaisesRegex(RuntimeError, "environment stopped"):
            asyncio.run(agent.run("task", environment, SimpleNamespace()))
        environment.stop.assert_awaited_once_with(delete=False)

    def test_primary_launch_failure_survives_control_and_environment_cleanup_failures(self):
        agent = FruitFlyHarborAgent.__new__(FruitFlyHarborAgent)
        installed_agent_inputs(agent, self.root)
        agent.profile = 'default'
        primary = FileNotFoundError('runtime unavailable')
        agent.exec_as_agent = AsyncMock(side_effect=[primary, RuntimeError('control unavailable')])
        environment = SimpleNamespace(stop=AsyncMock(side_effect=TimeoutError('stop unavailable')))
        with self.assertRaisesRegex(RuntimeError, 'stop unconfirmed') as caught:
            asyncio.run(agent.run('task', environment, SimpleNamespace()))
        self.assertIs(primary, caught.exception.__cause__)
        self.assertIn('Primary failure type: FileNotFoundError', caught.exception.__notes__)
        self.assertIn('Cleanup failure type: RuntimeError', caught.exception.__notes__)
        self.assertIn('Environment stop failure type: TimeoutError', caught.exception.__notes__)

    def test_zero_reward_has_completed_execution_and_multiple_timeouts_survive(self):
        trial = self.root / "trial"
        trial.mkdir()
        (self.root / "result.json").write_text('{"n_total_trials":1}')
        (trial / "result.json").write_text(json.dumps({"task_name": "task", "verifier_result": {"rewards": {"reward": 0}}}))
        trials, _ = parse_harbor_job_result(load_harbor_job_result(self.root / "result.json"), job_id="job")
        self.assertEqual(trials[0]["status"], "failed")
        self.assertEqual(trials[0]["execution"]["state"], "completed")
        value = json.loads((trial / "result.json").read_text())
        value["exception_info"] = {"exception_type": "AgentTimeoutError", "exception_message": "agent deadline"}
        (trial / "result.json").write_text(json.dumps(value))
        (trial / "trial.log").write_text("harbor.trial.errors.VerifierTimeoutError: verifier deadline\n")
        trials, _ = parse_harbor_job_result(load_harbor_job_result(self.root / "result.json"), job_id="job")
        execution = trials[0]["execution"]
        self.assertEqual(execution["state"], "error")
        self.assertEqual(execution["official_reward"], 0.0)
        self.assertEqual(execution["phases"]["agent_execution"]["state"], "error")
        self.assertEqual(execution["phases"]["verifier"]["state"], "error")
        self.assertEqual(len(execution["exceptions"]), 2)

    @unittest.skipUnless(sys.platform == "linux", "real container supervision requires Linux /proc")
    def test_linux_normal_completion_preserves_task_background_services(self):
        record = self.root / "process.json"
        pid_file = self.root / "service-pid"
        command = [sys.executable, "-m", "fruitfly_eval.harbor.supervisor", "--record", str(record), "--",
                   sys.executable, "-c", "import subprocess,sys; "
                   f"p=subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)'],start_new_session=True); "
                   f"open({str(pid_file)!r},'w').write(str(p.pid))"]
        try:
            result = subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=8)
            self.assertEqual(result.returncode, 0)
            self.assertEqual(json.loads(record.read_text())["state"], "finished")
            os.kill(int(pid_file.read_text()), 0)
        finally:
            if pid_file.exists():
                try:
                    os.kill(int(pid_file.read_text()), signal.SIGKILL)
                except ProcessLookupError:
                    pass

    @unittest.skipUnless(sys.platform == "linux", "real container supervision requires Linux /proc")
    def test_linux_cancelled_start_never_launches_the_cli(self):
        record = self.root / "process.json"
        marker = self.root / "should-not-exist"
        stop(record, "startup")
        result = subprocess.run([sys.executable, "-m", "fruitfly_eval.harbor.supervisor", "--record", str(record),
                                 "--token", "startup", "--", sys.executable, "-c",
                                 f"open({str(marker)!r},'w').write('launched')"],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=8)
        self.assertEqual(result.returncode, 130)
        self.assertFalse(marker.exists())

    @unittest.skipUnless(sys.platform == "linux", "real container supervision requires Linux /proc")
    def test_linux_cancellation_stops_detached_descendants(self):
        record = self.root / "process.json"
        pid_file = self.root / "background-pid"
        command = [sys.executable, "-m", "fruitfly_eval.harbor.supervisor", "--record", str(record), "--",
                   sys.executable, "-c", "import subprocess,sys,time; "
                   f"p=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)'],start_new_session=True); "
                   f"open({str(pid_file)!r},'w').write(str(p.pid)); time.sleep(60)"]
        process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            deadline = time.monotonic() + 8
            while not pid_file.exists() and time.monotonic() < deadline:
                time.sleep(.02)
            self.assertTrue(pid_file.exists())
            detached_pid = int(pid_file.read_text())
            stop(record)
            process.wait(timeout=8)
            self.assertEqual(json.loads(record.read_text())["state"], "cancelled")
            with self.assertRaises(ProcessLookupError):
                os.kill(detached_pid, 0)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
