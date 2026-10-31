"""Stage selected Agent configuration and declared credentials for containers."""
from __future__ import annotations

from pathlib import Path
from dataclasses import replace
import hashlib
import json
import re
from typing import Any, Mapping
import yaml
from fruitfly_agent.lab.catalog import builtin_catalog, component_profile
from fruitfly_agent.lab.catalog import load_system_config as load_harness_config
from fruitfly_agent.providers.registry import load_model_specs


def prepare_runtime(
    *,
    runtime: Mapping[str, Any],
    output_dir: Path,
    environment: Mapping[str, str] | None = None,
) -> tuple[Path, Path, tuple[str, ...]]:
    workspace = Path(runtime.get("working_directory") or ".").resolve()
    original_config = (workspace / (runtime.get("config_path") or ".fruitfly/default-config.yaml")).resolve()
    config_bytes = original_config.read_bytes()
    catalog = builtin_catalog()
    system = load_harness_config(original_config, catalog=catalog)
    selected = system.select(runtime.get("profile"))
    profile_id = selected.profile_id
    prompt, bindings = selected.prompt, selected.artifact_bindings
    source_catalog = Path(selected.model_catalog)
    if not source_catalog.is_absolute():
        source_catalog = original_config.parent / source_catalog
    source_catalog = source_catalog.resolve()
    if not source_catalog.is_file():
        raise FileNotFoundError(f"model catalog not found: {source_catalog}")
    selections = selected.mechanisms
    resolved = catalog.resolve(selections)
    normalized = {item.definition.descriptor.mechanism_id: dict(item.parameters) for item in resolved}
    # A remote environment would execute outside the benchmark task container.
    if any("execution-env" in item.definition.provides and item.definition.descriptor.effects.uses_network
           for item in resolved):
        raise ValueError("evaluation requires execution inside the task container; remote environments are unsupported")
    try:
        source_models = load_model_specs(source_catalog)
    except (KeyError, TypeError, AttributeError) as exc:
        raise ValueError("invalid model catalog; verify provider, model and token limits") from exc
    selected_model = selected.model_profile
    if selected_model is None:
        if len(source_models) != 1:
            raise ValueError("select one model profile for evaluation")
        selected_model = next(iter(source_models))
    required_models = {selected_model, *catalog.required_model_profiles(selections)}
    declared_models = required_models | set(selected.model_roles.values())
    if declared_models - source_models.keys():
        raise ValueError("unknown model profiles: " + ", ".join(sorted(declared_models - source_models.keys())))
    staged_models = {}
    secret_names = set(catalog.required_credentials(selections))
    for name in sorted(declared_models):
        spec = source_models[name]
        if name in required_models:
            spec.require(tools=any(c.family == "tools" for item in resolved for c in item.definition.descriptor.contributions), streaming=True)
            secret_names.add(spec.provider.api_key_env)
        staged_models[name] = spec.to_dict()
    if any(not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name) for name in secret_names):
        raise ValueError("credential references must name environment variables")
    if environment is not None:
        missing = sorted(name for name in secret_names if not environment.get(name))
        if missing:
            raise ValueError("missing evaluation credentials: " + ", ".join(missing))
    remote_catalog = "/installed-agent/fruitfly/runtime/models.yaml"
    def read_artifact(reference):
        source = workspace / ".fruitfly/artifacts" / reference[7:]
        if source.is_symlink():
            raise ValueError("runtime artifact must not be a symlink")
        body = source.read_bytes()
        if "sha256:" + hashlib.sha256(body).hexdigest() != reference:
            raise ValueError("runtime artifact content differs from its reference")
        return body.decode("utf-8")
    from fruitfly_agent.runtime_spec import MechanismSelection
    projected = component_profile(replace(selected, model_catalog=remote_catalog,
        model_profile=selected_model, mechanisms=tuple(MechanismSelection(item.mechanism_id,
            item.enabled, normalized.get(item.mechanism_id, dict(item.parameters))) for item in selections)),
        catalog, artifact_reader=read_artifact)
    adjusted = {"default_profile": profile_id,
                "profiles": {profile_id: projected.to_dict(references=False)}}
    config_path = output_dir / "config.yaml"
    model_path = output_dir / "models.yaml"
    config_path.write_text(
        yaml.safe_dump(adjusted, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    model_path.write_text(yaml.safe_dump({"models": staged_models}, sort_keys=False), encoding="utf-8")
    references = set(bindings.values())
    if isinstance(prompt, str) and prompt.startswith("sha256:"):
        references.add(prompt)
    for reference in references:
        if not isinstance(reference, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", reference):
            raise ValueError("runtime artifacts require SHA-256 content references")
        # Consume Run's persisted content-addressed artifact format. Only
        # explicitly bound immutable content crosses into a task environment.
        source = workspace / ".fruitfly/artifacts" / reference[7:]
        if source.is_symlink():
            raise ValueError("runtime artifact must not be a symlink")
        body = (selected.artifact_contents[reference].encode('utf-8') if reference in selected.artifact_contents
                else source.read_bytes())
        if hashlib.sha256(body).hexdigest() != reference[7:]:
            raise ValueError("runtime artifact content differs from its reference")
        destination = output_dir / "artifacts" / reference[7:]
        destination.parent.mkdir(exist_ok=True)
        destination.write_bytes(body)
    receipt = {"schema_version": 1, "source": "default" if not runtime.get("config_path") else "explicit",
        "config_path": str(original_config), "profile": profile_id, "model_catalog": str(source_catalog),
        "source_config_sha256": hashlib.sha256(config_bytes).hexdigest(),
        "configuration_sources": [{"path": source.path, "sha256": source.digest}
                                  for source in selected.source_files],
        "execution_policy": "unrestricted", "isolation": "harbor_task_container",
        "files": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (config_path, model_path)}}
    (output_dir / "runtime.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    return config_path, model_path, tuple(sorted(secret_names))
