"""Host bounded original-task experiments through injected algorithm and execution ports."""
from __future__ import annotations

import json
import asyncio
from uuid import uuid4

from fruitfly_agent.lab.improvement.api import BenchmarkContext, ExperimentTasks, method_identity
from fruitfly_agent.lab.algorithms.targets import canonical_json, content_hash
from fruitfly_agent.run.storage.results import save_task_result


class RunExperiments:
    direction = "Improve completion of the frozen original benchmark tasks."

    def __init__(self, *, workspace, artifacts, versions, manifest, improver, target, scope, freeze_runtime,
                 candidates, compact):
        self.workspace, self.artifacts, self.versions = workspace, artifacts, versions
        self.manifest, self.improver, self.target, self.scope = manifest, improver, target, scope
        self.freeze_runtime, self.candidates, self.compact = freeze_runtime, candidates, compact
        self.receipts = {}
        self.selections = {}
        self.running_improver = None
        self._completion = None

    def completion(self):
        return self._completion

    def bind(self, improver, target):
        return RunExperiments(workspace=self.workspace, artifacts=self.artifacts, versions=self.versions,
            manifest=self.manifest, improver=lambda: improver, target=lambda: target, scope=self.scope,
            freeze_runtime=self.freeze_runtime, candidates=self.candidates, compact=self.compact)

    @property
    def available(self):
        improver = self.improver()
        return (improver is not None and callable(getattr(improver, "search_experiment", None))
                and callable(getattr(improver, "experiment_available", None)) and improver.experiment_available())

    def preview_selection(self, selection, executor, *, direction=""):
        from dataclasses import replace
        if not self.available:
            raise ValueError("configure an automatic improver before starting improvement")
        if self.target().snapshot().binding.kind != "prompt":
            raise ValueError("benchmark improvement currently supports base prompt targets")
        direction = direction.strip() or self.direction
        if len(direction) > 500:
            raise ValueError("improvement direction must contain 1–500 characters")
        preview = self.improver().preview_experiment_plan(selection["task_limit"])
        parent = self.versions.freeze()
        token = uuid4().hex
        self.selections[token] = (dict(selection), executor, direction, self.manifest()["digest"], parent, method_identity(self.improver()))
        return replace(preview, preview_token=token, details=(*preview.details,
            ("Benchmark", selection["benchmark_id"]), ("Task set", selection["variant"]),
            ("Direction", direction), ("Parent H/I/S", parent.version_id)))

    def preview_tasks(self, benchmark_id, tasks, materials, executor, *, origin="", direction=""):
        if not self.available:
            raise ValueError("configure an automatic improver before creating a benchmark experiment")
        tasks = tuple(sorted(tasks, key=lambda t: (t.dataset, t.task_id)))
        if not 3 <= len(tasks) <= 12:
            raise ValueError("initial benchmark experiments require 3–12 distinct tasks")
        partitions = ExperimentTasks(tasks[:-2], tasks[-2:-1], tasks[-1:])
        manifest = self.manifest()
        snapshot = self.target().snapshot()
        if snapshot.binding.kind != "prompt":
            raise ValueError("the initial benchmark experiment host supports base prompt targets")
        parent = self.versions.freeze()
        experiment_id = uuid4().hex
        root = self.workspace / ".fruitfly/improvement/experiments" / experiment_id
        root.mkdir(parents=True, exist_ok=False)
        runtime = self.freeze_runtime(root)
        runtime_hashes = {str(path): content_hash(path.read_text(encoding="utf-8"))
                          for path in (root / "runtime/config.yaml", root / "runtime/models.yaml")}
        harness = json.loads(self.artifacts.read_text(parent.harness))
        source_root = self.versions.snapshots.materialize(harness["source"], root / "source")
        executor.configure(runtime=runtime, benchmark_id=benchmark_id,
                           materials=materials, source_root=source_root, runtime_hashes=runtime_hashes)
        conditions_id = content_hash(canonical_json({"models": manifest["models"], "permissions": manifest.get("permissions"),
                                                     "runtime": runtime_hashes, "tasks": partitions.digest}))
        state = self.versions.snapshots.read(parent.state).to_dict()
        fixed_artifacts = {}
        for reference in (manifest["base_prompt"].get("reference", ""),
                          *(a.get("reference", a.get("id", "")) for a in manifest.get("data_artifacts", ()) )):
            if reference.startswith("sha256:"):
                fixed_artifacts[reference] = self.artifacts.read_text(reference)
        def packet_for_text(text):
            candidate = self.versions.text_candidate(parent, snapshot, text) if text != snapshot.text else None
            version = candidate.version if candidate else parent
            payload = {"schema_version": 1, "version": version.to_dict(),
                       "harness": json.loads(self.artifacts.read_text(version.harness)), "state": state,
                       "target": {"role": "H", "schema": snapshot.schema, "kind": snapshot.binding.kind,
                                  "key": snapshot.binding.key}, "text": text, "conditions_id": conditions_id,
                       "allow_local_operations": True, "expected_models": manifest["models"], "artifacts": fixed_artifacts}
            if candidate:
                payload["candidate"] = candidate.to_dict()
            return payload
        context = BenchmarkContext(partitions, parent, manifest["digest"], snapshot.text, direction or self.direction,
                                   executor, packet_for_text, self.artifacts.read_text, origin)
        preview = self.improver().preview_experiment(context)
        token = uuid4().hex
        self.receipts[token] = (context, snapshot, root, method_identity(self.improver()))
        (root / "experiment.json").write_text(canonical_json({"experiment_id": experiment_id,
            "parent": parent.to_dict(), "parent_manifest": manifest["digest"], "tasks": partitions.to_dict(),
            "task_source": origin, "benchmark_id": benchmark_id, "conditions_id": conditions_id,
            "models": manifest["models"], "permissions": manifest.get("permissions"),
            "runtime_hashes": runtime_hashes, "method_identity": method_identity(self.improver()), "status": "prepared"}), encoding="utf-8")
        from dataclasses import replace
        return replace(preview, preview_token=token)

    async def improve(self, manifest, direction, *, preview_token):
        self._completion = None
        if preview_token in self.selections:
            selection, executor, confirmed_direction, digest, parent, confirmed_method = self.selections.pop(preview_token)
            if method_identity(self.improver()) != confirmed_method:
                raise ValueError("benchmark improvement method changed; preview again")
            if (direction != confirmed_direction or manifest["digest"] != digest
                    or self.manifest()["digest"] != digest or self.versions.freeze() != parent):
                raise ValueError("benchmark improvement parent H/I/S or direction changed; preview again")
            async with asyncio.timeout(self.improver().experiment_timeout_seconds()):
                bundle = await executor.prepare_tasks(selection)
                if self.versions.freeze() != parent or method_identity(self.improver()) != confirmed_method:
                    raise ValueError("benchmark improvement parent H/I/S changed during task preparation")
                from fruitfly_agent.lab.improvement.api import TaskReference
                tasks = tuple(TaskReference.from_dict(row) for row in bundle["tasks"])
                if len(tasks) != selection["task_limit"] or bundle["benchmark_id"] != selection["benchmark_id"]:
                    raise ValueError("prepared tasks differ from the authorized selection")
                root = executor.owned_path(bundle["material_root"])
                materials = {key: executor.owned_path(root / path) for key, path in bundle["materials"].items()}
                preview = self.preview_tasks(selection["benchmark_id"], tasks, materials, executor,
                                             origin=str(root.relative_to(self.workspace)), direction=direction)
                return await self.improve(manifest, direction, preview_token=preview.preview_token)
        try:
            context, snapshot, root, confirmed_method = self.receipts.pop(preview_token)
        except KeyError as exc:
            raise ValueError("unknown or consumed benchmark experiment preview") from exc
        status = "failed"
        try:
            if method_identity(self.improver()) != confirmed_method:
                raise ValueError("benchmark improvement method changed; preview again")
            if (direction != context.direction or manifest["digest"] != context.parent_manifest
                    or self.manifest()["digest"] != context.parent_manifest or self.versions.freeze() != context.parent):
                status = "stale"
                raise ValueError("benchmark experiment parent H/I/S or direction changed")
            self.running_improver = self.improver()
            try:
                proposals = await self.running_improver.search_experiment(context)
            finally:
                completion = getattr(self.running_improver, 'completion', None)
                self._completion = completion() if callable(completion) else None
                self.running_improver = None
            if method_identity(self.improver()) != confirmed_method:
                raise ValueError("benchmark improvement method changed during search")
            if self.versions.freeze() != context.parent:
                raise ValueError("production H/I/S changed during benchmark improvement")
            records = []
            for proposal in proposals[:1]:
                record = self.candidates.create(text=proposal.text, algorithm=proposal.algorithm,
                    parent_manifest=manifest, cases_digest=proposal.cases_digest, direction=direction,
                    seed_score=proposal.seed_score, validation_score=proposal.validation_score,
                    metric_calls=proposal.metric_calls, evidence=(*proposal.evidence,
                        ("Experiment", str((root / "experiment.json").relative_to(self.workspace)))), snapshot=snapshot,
                    config_path=self.scope()[0], profile_id=self.scope()[1], report=proposal.report,
                    task_pack_id="benchmark-experiment", task_pack_name="Original benchmark experiment",
                    task_pack_hash=context.tasks.digest)
                records.append(record)
                save_task_result(self.workspace, record, proposal.text)
            if records:
                self.compact()
            status = "confirmed_improvement" if records else "no_confirmed_improvement"
            return tuple(records)
        except asyncio.CancelledError:
            status = "interrupted"
            raise
        finally:
            payload = json.loads((root / "experiment.json").read_text(encoding="utf-8"))
            payload["status"] = status
            (root / "experiment.json").write_text(canonical_json(payload), encoding="utf-8")
