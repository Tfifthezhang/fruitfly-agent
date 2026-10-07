"""Explicit offline relocation of workspace model and credential files."""

import argparse
import json
import os
from pathlib import Path
import sys

import yaml

from fruitfly_agent.providers.registry import load_model_specs
from fruitfly_agent.providers.workspace import WorkspacePaths

from .configuration import load_harness_config
from .model_selection import model_catalog_path
from .model_setup import _write


def migrate_configuration(workspace: Path, *, config_path: Path | None = None,
                          apply: bool = False) -> tuple[str, ...]:
    """Preview by default; refuse conflicts and restore files on ordinary failure."""
    workspace = workspace.resolve()
    paths = WorkspacePaths(workspace)
    config_path = config_path or workspace / ".fruitfly/config.yaml"
    if not config_path.is_absolute():
        config_path = workspace / config_path
    if not config_path.resolve().is_relative_to(workspace):
        raise ValueError("Harness configuration must be inside the workspace")
    moves = [(source, target) for source, target in (
        (paths.legacy_models, paths.models), (paths.legacy_secrets, paths.secrets)
    ) if source.exists() or source.is_symlink()]
    if not moves:
        return ("No legacy workspace configuration to move.",)
    if (workspace / ".fruitfly").is_symlink() or config_path.is_symlink():
        raise ValueError("Refusing to migrate configuration through a symlink")
    for source, target in moves:
        if source.is_symlink() or not source.is_file():
            raise ValueError(f"Migration requires a regular file: {source.name}")
        if target.exists() or target.is_symlink():
            raise ValueError(f"Migration destination already exists: {target.relative_to(workspace)}")
    config_text = None
    if paths.legacy_models.is_file():
        load_model_specs(paths.legacy_models)
        if config_path.is_file():
            config = load_harness_config(config_path)
            selected = {name for name, profile in config.profiles.items()
                        if model_catalog_path(profile, config_path) == paths.legacy_models}
            if selected:
                text = config_path.read_text(encoding="utf-8")
                reference = os.path.relpath(paths.models, config_path.parent)
                # Replace only matching catalog scalars, preserving unrelated text.
                root = yaml.compose(text)
                profiles_node = next(value for key, value in root.value if key.value == "profiles")
                edits = []
                for key, profile_node in profiles_node.value:
                    if key.value not in selected:
                        continue
                    model_node = next(value for key, value in profile_node.value if key.value == "model")
                    catalog_node = next((value for key, value in model_node.value if key.value == "catalog"), None)
                    if catalog_node is not None:
                        edits.append((catalog_node.start_mark.index, catalog_node.end_mark.index, json.dumps(reference)))
                    elif model_node.flow_style:
                        index = model_node.start_mark.index + 1
                        edits.append((index, index, "catalog: " + json.dumps(reference) + (", " if model_node.value else "")))
                    else:
                        index = model_node.start_mark.index
                        edits.append((index, index, "catalog: " + json.dumps(reference) + "\n" + " " * model_node.start_mark.column))
                expected = yaml.safe_load(text)
                for name in selected:
                    expected["profiles"][name]["model"]["catalog"] = reference
                for start, end, replacement in sorted(set(edits), reverse=True):
                    text = text[:start] + replacement + text[end:]
                try:
                    valid = yaml.safe_load(text) == expected
                except yaml.YAMLError:
                    valid = False
                if not valid:
                    raise ValueError("Cannot safely update this harness YAML; set explicit catalog paths manually")
                config_text = text.encode("utf-8")
    messages = tuple(f"Move {source.relative_to(workspace)} → {target.relative_to(workspace)}"
                     for source, target in moves)
    if config_text is not None:
        messages += (f"Update matching model.catalog paths in {config_path.relative_to(workspace)}",)
    if not apply:
        return messages + ("Preview only. Add --apply to move these files; .env contents move together.",)
    originals = {source: source.read_bytes() for source, _ in moves}
    original_config = config_path.read_bytes() if config_text is not None else None
    written = []
    try:
        for source, target in moves:
            _write(target, originals[source])
            written.append(target)
        if config_text is not None:
            _write(config_path, config_text)
        for source, _ in moves:
            source.unlink()
    except BaseException:
        for source, data in originals.items():
            if not source.exists():
                _write(source, data)
        if original_config is not None:
            _write(config_path, original_config)
        for target in reversed(written):
            target.unlink(missing_ok=True)
        raise
    return messages + ("Configuration moved. Restart the CLI to reload workspace secrets.",)


def main() -> None:
    parser = argparse.ArgumentParser(description="Move legacy workspace configuration into .fruitfly")
    parser.add_argument("--cwd", type=Path, default=Path.cwd())
    parser.add_argument("--config", type=Path, help="harness configuration to update")
    parser.add_argument("--apply", action="store_true", help="perform the previewed relocation")
    args = parser.parse_args()
    try:
        for message in migrate_configuration(args.cwd, config_path=args.config, apply=args.apply):
            print(message)
    except (OSError, ValueError, TypeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2)


if __name__ == "__main__":
    main()
