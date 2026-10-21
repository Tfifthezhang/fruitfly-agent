"""Canonical trajectories retain tools, observations and unknown usage offline."""
import json
from pathlib import Path
import tempfile
import unittest

from eval.trajectory import session_trajectory
from tests.support.harbor import load_harbor_agent
from types import SimpleNamespace


class TrajectoryTests(unittest.TestCase):
    def session(self, root, messages):
        path = root / "session.jsonl"
        rows = [{"type": "meta", "kind": "runtimeManifest",
                 "manifest": {"digest": "sha256:fixture", "models": {"main": {"model": "fake"}}}}]
        rows.extend({"type": "message", "message": m} for m in messages)
        path.write_text("".join(json.dumps(row) + "\n" for row in rows))
        return path

    def test_parallel_tools_retain_their_observations_and_explicit_zero_usage(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = self.session(root, [
                {"role": "user", "content": "inspect files"},
                {"role": "assistant", "content": [
                    {"type": "thinking", "thinking": "inspect both"},
                    {"type": "toolCall", "id": "a", "name": "read", "input": {"path": "a"}},
                    {"type": "toolCall", "id": "b", "name": "read", "input": {"path": "b"}}],
                 "usage": {"inputTokens": 0, "outputTokens": 5}},
                {"role": "toolResult", "toolCallId": "b", "content": [{"type": "text", "text": "B"}], "isError": True},
                {"role": "toolResult", "toolCallId": "a", "content": [{"type": "text", "text": "A"}]},
                {"role": "assistant", "content": [{"type": "text", "text": "finished"}]},
            ])
            trajectory = session_trajectory(path)
            self.assertEqual(len(trajectory["steps"]), 3)
            agent = trajectory["steps"][1]
            self.assertEqual(agent["reasoning_content"], "inspect both")
            observations = agent["observation"]["results"]
            self.assertEqual([(o["source_call_id"], o["content"]) for o in observations], [("b", "B"), ("a", "A")])
            self.assertTrue(observations[0]["extra"]["is_error"])
            self.assertEqual(trajectory["final_metrics"]["total_prompt_tokens"], 0)
            self.assertNotIn("metrics", trajectory["steps"][2])
            agent = load_harbor_agent().__new__(load_harbor_agent())
            agent.logs_dir = root
            context = SimpleNamespace(metadata=None)
            agent.populate_context_post_run(context)
            self.assertEqual(context.n_input_tokens, 0)
            self.assertTrue((root / "trajectory.json").is_file())

    def test_missing_usage_stays_unknown_and_orphan_observation_is_explicit(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.session(Path(directory), [
                {"role": "user", "content": "task"},
                {"role": "toolResult", "toolCallId": "orphan", "content": [{"type": "text", "text": "result"}]},
            ])
            value = session_trajectory(path)
            self.assertNotIn("total_prompt_tokens", value["final_metrics"])
            orphan = value["steps"][1]
            self.assertEqual(orphan["source"], "system")
            self.assertNotIn("source_call_id", orphan["observation"]["results"][0])

    def test_malformed_session_is_not_exported_as_a_complete_trajectory(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.session(Path(directory), [{"role": "user", "content": "task"}])
            with path.open("a") as stream:
                stream.write('{"type":')
            with self.assertRaises(ValueError):
                session_trajectory(path)
