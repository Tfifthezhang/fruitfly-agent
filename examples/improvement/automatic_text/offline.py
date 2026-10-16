"""Exercise automatic material generation, confirmation and human adoption offline."""
import asyncio
from collections import deque
import json
from pathlib import Path
import tempfile

from fruitfly_agent.core import AssistantMessage, TextBlock, Usage
from fruitfly_agent.core.model_stream import AssistantMessageEventStream, StreamDone
from fruitfly_agent.interactive import AgentApplication
from fruitfly_agent.lab.catalog import MechanismSelection
from fruitfly_agent.lab.improvement.contracts.search import TaskCase
from fruitfly_agent.providers import ProviderRegistry
from fruitfly_agent.run.application import RunApplicationFactory
from fruitfly_agent.run.configuration import HarnessConfig, HarnessProfile, save_harness_config


class ScriptedProvider:
    def __init__(self):
        source = TaskCase("Return A", "A").case_id
        self.responses = deque(("wrong", "wrong", json.dumps({"tasks": [{
            "source_case_id": source, "policy_id": "normalized-exact-v1",
            "input": "Learning exercise: output exactly A", "acceptance": {"expected": "A"}}]}),
            '{"accepted": true, "reason": "The exercise retains the required label."}',
            "wrong", '["Return the requested label exactly."]', "A", "B", "A", "wrong", "C"))

    def __call__(self, view, *, signal=None):
        async def events():
            if signal is not None and signal.is_set():
                raise asyncio.CancelledError
            if not self.responses:
                raise RuntimeError("offline script exhausted")
            yield StreamDone(AssistantMessage(content=[TextBlock(self.responses.popleft())],
                                             stop_reason="stop", usage=Usage(input_tokens=1, output_tokens=1)))
        return AssistantMessageEventStream(events())


async def run_demo():
    with tempfile.TemporaryDirectory(prefix="fruitfly-automatic-") as directory:
        root = Path(directory)
        path = root / ".fruitfly/improvement/task-packs/labels"
        path.mkdir(parents=True)
        manifest = {"schema_version": 2, "id": "labels", "name": "Offline labels",
                    "description": "Control-flow demonstration with scripted responses.",
                    "task_schema": "single-turn-text-v1", "target_schema": "text-v1",
                    "compatible_targets": ["base_prompt"],
                    "objective": {"policy_id": "normalized-exact-v1", "direction": "max"},
                    "files": {"cases": "cases.json", "holdout": "holdout.json"}}
        (path / "pack.json").write_text(json.dumps(manifest), encoding="utf-8")
        (path / "cases.json").write_text(json.dumps({
            "train": [{"id": "train-a", "input": "Return A", "acceptance": {"expected": "A"}}],
            "validation": [{"id": "select-b", "input": "Return B", "acceptance": {"expected": "B"}}]}), encoding="utf-8")
        (path / "holdout.json").write_text(json.dumps({"holdout": [
            {"id": "confirm-c", "input": "Return C", "acceptance": {"expected": "C"}}]}), encoding="utf-8")
        (root / "models.yaml").write_text("models:\n  offline:\n    provider: offline\n"
            "    model: offline-example\n    api_key_env: OFFLINE_KEY\n    context_window: 8192\n", encoding="utf-8")
        config = root / ".fruitfly/config.yaml"
        save_harness_config(config, HarnessConfig(default_profile="default", profiles={"default": HarnessProfile(
            "default", model_catalog="../models.yaml", model_profile="offline", mechanisms=(
                MechanismSelection("opro", parameters={"max_metric_calls": 32}),
                MechanismSelection("failure-distillation"), MechanismSelection("automatic-text-search")))}))
        provider = ScriptedProvider()
        registry = ProviderRegistry()
        registry.register("offline", lambda spec, key: provider)
        factory = RunApplicationFactory(cwd=root, environment={"OFFLINE_KEY": "offline-placeholder"},
                                        provider_registry=registry)
        app = AgentApplication(factory)
        try:
            await app.start()
            before = app.runtime_manifest["digest"]
            preview = app.improvement_preview(pack_id="labels", direction="Improve label accuracy")
            records = await app.improve("Improve label accuracy", preview_token=preview.preview_token)
            if len(records) != 1 or app.runtime_manifest["digest"] != before:
                raise RuntimeError("a confirmed candidate must wait for review")
            print("Offline confirmed candidate: ready for human review.")
            # This explicit host action represents a user's adoption decision.
            await app.adopt_candidate(records[0].candidate_id)
            print("Explicit adoption: new session uses the candidate.")
            print("Scripted results demonstrate workflow behavior, not model quality.")
        finally:
            await app.close()


if __name__ == "__main__":
    asyncio.run(run_demo())
