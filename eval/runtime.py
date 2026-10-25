"""Stage selected Agent configuration and declared credentials for containers."""
from __future__ import annotations

from pathlib import Path
import hashlib
import json
import re
from typing import Any, Mapping
import yaml
from fruitfly_agent.lab.catalog import builtin_catalog
from fruitfly_agent.runtime_spec import load_harness_config
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
    selected = load_harness_config(original_config).select(runtime.get("profile"))
    profile_id = selected.profile_id
    profile = selected.to_dict()
    prompt, bindings = selected.prompt, selected.artifact_bindings
    model = profile["model"]
    raw_config = {"schema_version": 1}
    source_catalog = Path(str(model.get("catalog", "models.yaml")))
    if not source_catalog.is_absolute():
        source_catalog = original_config.parent / source_catalog
    source_catalog = source_catalog.resolve()
    if not source_catalog.is_file():
        raise FileNotFoundError(f"model catalog not found: {source_catalog}")
    selections = selected.mechanisms
    catalog = builtin_catalog()
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
    selected_model = model.get("profile")
    if selected_model is None:
        if len(source_models) != 1:
            raise ValueError("select one model profile for evaluation")
        selected_model = next(iter(source_models))
    required_models = {selected_model, *catalog.required_model_profiles(selections)}
    if required_models - source_models.keys():
        raise ValueError("unknown model profiles: " + ", ".join(sorted(required_models - source_models.keys())))
    staged_models = {}
    secret_names = set(catalog.required_credentials(selections))
    for name in sorted(required_models):
        spec = source_models[name]
        spec.require(tools=any(c.family == "tools" for item in resolved for c in item.definition.descriptor.contributions), streaming=True)
        secret_names.add(spec.provider.api_key_env)
        staged_models[name] = {"provider": spec.provider.type, "model": spec.model,
            "api_key_env": spec.provider.api_key_env, "base_url": spec.provider.base_url,
            "context_window": spec.context_window, "max_output_tokens": spec.max_output_tokens,
            "capabilities": {key: getattr(spec.capabilities, key) for key in
                             ("tools", "parallel_tool_calls", "vision", "reasoning", "streaming")},
            "parameters": dict(spec.parameters)}
    if any(not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name) for name in secret_names):
        raise ValueError("credential references must name environment variables")
    if environment is not None:
        missing = sorted(name for name in secret_names if not environment.get(name))
        if missing:
            raise ValueError("missing evaluation credentials: " + ", ".join(missing))
    remote_catalog = "/installed-agent/fruitfly/runtime/models.yaml"
    adjusted_profile = dict(profile)
    adjusted_model = dict(model)
    adjusted_model["catalog"] = remote_catalog
    adjusted_model["profile"] = selected_model
    adjusted_profile["model"] = adjusted_model
    adjusted_profile["mechanisms"] = [{**item.to_dict(), "parameters": normalized.get(item.mechanism_id, dict(item.parameters))}
                                       for item in selections]
    adjusted = {
        "schema_version": raw_config.get("schema_version", 1),
        "default_profile": profile_id,
        "profiles": {profile_id: adjusted_profile},
    }
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
        body = source.read_bytes()
        if hashlib.sha256(body).hexdigest() != reference[7:]:
            raise ValueError("runtime artifact content differs from its reference")
        destination = output_dir / "artifacts" / reference[7:]
        destination.parent.mkdir(exist_ok=True)
        destination.write_bytes(body)
    receipt = {"schema_version": 1, "source": "default" if not runtime.get("config_path") else "explicit",
        "config_path": str(original_config), "profile": profile_id, "model_catalog": str(source_catalog),
        "source_config_sha256": hashlib.sha256(config_bytes).hexdigest(),
        "execution_policy": "unrestricted", "isolation": "harbor_task_container",
        "files": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (config_path, model_path)}}
    (output_dir / "runtime.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    return config_path, model_path, tuple(sorted(secret_names))
