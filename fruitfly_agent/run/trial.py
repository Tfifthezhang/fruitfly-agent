"""Run an explicitly authorized isolated task through the normal Application factory."""
from __future__ import annotations

import argparse
import asyncio
from dataclasses import replace
import json
import os
import sys
from importlib.metadata import distributions
from pathlib import Path

from fruitfly_agent.core.data_model import AssistantMessage
from fruitfly_agent.interactive import AgentApplication
from fruitfly_agent.lab.algorithms.targets import SystemVersion, StateSnapshot, TargetSnapshot, target_edits, content_hash, canonical_json
from fruitfly_agent.providers.registry import default_registry
from fruitfly_agent.run.application import RunApplicationFactory
from fruitfly_agent.run.configuration.profile import HarnessConfig, save_harness_config
from fruitfly_agent.run.runtime.trial_budget import TrialInvocationBudget, BudgetedRegistry
from fruitfly_agent.run.runtime.manifest import execution_version_payload
from fruitfly_agent.run.storage.artifacts import DataArtifactStore
from fruitfly_agent.run.storage.snapshots import capture_source_tree


async def execute_trial(packet: dict, *, workspace: Path, config_path: Path, profile: str,
                        source_root: Path, output_directory: Path, provider_registry=None,
                        environment=None) -> dict:
    expected = {"schema_version", "lease_id", "version", "harness", "state", "target", "text",
                "conditions_id", "max_model_calls", "max_output_tokens", "instruction", "allow_local_operations", "expected_models", "artifacts"}
    if not isinstance(packet, dict) or set(packet) != expected or packet["schema_version"] != 1:
        raise ValueError("invalid isolated runtime request")
    if type(packet["allow_local_operations"]) is not bool:
        raise ValueError("trial permissions must be explicitly declared")
    version = SystemVersion.from_dict(packet["version"])
    state = StateSnapshot.from_dict(packet["state"])
    harness = packet["harness"]
    if (state.snapshot_id != version.state or content_hash(canonical_json(harness)) != version.harness
            or harness["source"] != capture_source_tree(source_root).snapshot_id):
        raise ValueError("trial source, H or S material does not match its frozen version")
    target = packet["target"]
    if target.get("role") not in {'H', 'S'} or target.get("kind") not in {"prompt", "artifact", "components"}:
        raise ValueError("this runtime trial host supports registered execution and state components")
    from fruitfly_agent.lab.algorithms.targets import validate_text
    if target.get('kind') != 'components':
        validate_text(packet["text"])
    snapshot = TargetSnapshot.from_dict(target['snapshot']) if 'snapshot' in target else None
    if snapshot is not None and (snapshot.role != target['role'] or snapshot.schema != target['schema']
                                 or snapshot.binding.kind != target['kind'] or snapshot.binding.key != target['key']):
        raise ValueError('trial target metadata differs from its snapshot')
    if target['kind'] == 'components' and snapshot is None:
        raise ValueError('component trials require their frozen target snapshot')
    if target["kind"] == "prompt" and harness["base_prompt"]["content_hash"] != content_hash(packet["text"]):
        raise ValueError("trial prompt differs from its H version")
    if target['kind'] == 'artifact' and (snapshot is None or packet['text'] != snapshot.text):
        reference = next((a['id'] for a in harness.get('data_artifacts', ()) if a['key'] == target['key']), None)
        if reference != content_hash(packet['text']):
            raise ValueError('trial guidance differs from its H version')
    workspace = workspace.resolve()
    expected_paths = {entry.path for entry in state.files}
    for root in state.roots:
        directory = workspace / root
        if not directory.resolve().is_relative_to(workspace) or directory.is_symlink():
            raise ValueError("trial state root escapes its isolated workspace")
        if directory.exists():
            for path in directory.rglob("*"):
                if path.is_symlink() or path.is_file() and path.relative_to(workspace).as_posix() not in expected_paths:
                    raise ValueError("trial initial state contains undeclared files")
    for entry in state.files:
        path = workspace / entry.path
        if not path.resolve().is_relative_to(workspace) or any(p.is_symlink() for p in (path, *path.parents)):
            raise ValueError("trial state cannot escape its isolated workspace")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(entry.content, encoding="utf-8")
    output_directory.mkdir(parents=True, exist_ok=True)
    budget = TrialInvocationBudget(packet["max_model_calls"], packet["max_output_tokens"])
    registry = BudgetedRegistry(provider_registry or default_registry(), budget)
    environment = dict(os.environ if environment is None else environment)
    artifacts = DataArtifactStore(workspace / ".fruitfly/artifacts")
    for reference, body in packet["artifacts"].items():
        if artifacts.put_text(body).artifact_id != reference:
            raise ValueError("trial artifact content differs from its declared identity")
    factory = RunApplicationFactory(cwd=workspace, config_path=str(config_path), profile_id=profile,
                                    environment=environment, provider_registry=registry)
    selected = factory.selection.profile
    if snapshot is not None:
        for part, value in target_edits(snapshot, packet['text']):
            if part.role not in {'H', 'S'} or part.binding.kind not in {'prompt', 'artifact'}:
                raise ValueError('trial component needs an execution/state binding')
            binding = factory.artifact_store.put_text(value).artifact_id
            selected = (replace(selected, prompt=binding) if part.binding.kind == 'prompt' else
                        replace(selected, artifact_bindings={**selected.artifact_bindings, part.binding.key: binding}))
    else:
        binding = factory.artifact_store.put_text(packet["text"]).artifact_id
        selected = (replace(selected, prompt=binding) if target['kind'] == 'prompt' else
                    replace(selected, artifact_bindings={**selected.artifact_bindings, target['key']: binding}))
    # Preserve absolute catalog resolution before writing an isolated profile.
    catalog = Path(selected.model_catalog)
    if not catalog.is_absolute():
        catalog = factory.selection.config_path.parent / catalog
    selected = replace(selected, model_catalog=str(catalog.resolve()))
    trial_config = output_directory / "runtime.yaml"
    save_harness_config(trial_config, HarnessConfig(selected.profile_id, {selected.profile_id: selected}))
    factory = RunApplicationFactory(cwd=workspace, config_path=str(trial_config), profile_id=profile,
                                    environment=environment, provider_registry=registry)
    app = AgentApplication(factory)
    event_path = output_directory / "live-events.jsonl"
    stream = event_path.open("x", encoding="utf-8")
    async def emit(event):
        stream.write(json.dumps(event.to_dict(), ensure_ascii=False) + "\n")
        stream.flush()
    app.set_event_sink(emit)
    if packet["allow_local_operations"]:
        async def authorize(prompt):
            return "once"  # Explicit trial scope; protected paths still fail in the normal authorizer.
        app.set_authorization_handler(authorize)
    receipt = {"schema_version": 1, "lease_id": packet["lease_id"], "version": version.to_dict(),
               "conditions_id": packet["conditions_id"], "model_calls": 0,
               "instruction_hash": content_hash(packet["instruction"]),
               "status": "error", "output": "", "runtime": None,
               "execution_environment": {"python": sys.version, "platform": sys.platform,
                   "packages": sorted((d.metadata["Name"] or "", d.version) for d in distributions())}}
    try:
        await app.start(session_path=output_directory / "session.jsonl")
        receipt["runtime"] = app.runtime_manifest
        if content_hash(canonical_json(
                execution_version_payload(app.runtime_manifest, harness["source"]))) != version.harness:
            raise ValueError("trial assembled different execution mechanisms or artifacts")
        actual_models = {key: {k: v for k, v in value.items() if k != "transport"}
                         for key, value in app.runtime_manifest["models"].items()}
        expected_models = {key: {k: v for k, v in value.items() if k != "transport"}
                           for key, value in packet["expected_models"].items()}
        if actual_models != expected_models:
            raise ValueError("trial resolved different model conditions")
        result = await app.submit(packet["instruction"])
        receipt["output"] = "\n".join(m.text for m in result.messages if isinstance(m, AssistantMessage))
        receipt["status"] = "budget_exhausted" if budget.exhausted else "error" if result.is_error else "completed"
        return receipt
    except asyncio.CancelledError:
        receipt["status"] = "cancelled"
        raise
    finally:
        receipt["model_calls"] = budget.used
        if capture_source_tree(source_root).snapshot_id != harness["source"]:
            receipt["status"] = "error"
        try:
            await app.close()
        finally:
            stream.close()
            (output_directory / "trial-receipt.json").write_text(canonical_json(receipt), encoding="utf-8")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Execute one authorized isolated runtime trial")
    for name in ("request", "config", "profile", "source", "output"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--cwd", default=".")
    args = parser.parse_args(argv)
    packet = json.loads(Path(args.request).read_text(encoding="utf-8"))
    receipt = asyncio.run(execute_trial(packet, workspace=Path(args.cwd), config_path=Path(args.config),
        profile=args.profile, source_root=Path(args.source), output_directory=Path(args.output)))
    return 0 if receipt["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
