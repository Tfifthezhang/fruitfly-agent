"""Shared prepared mount assembly across compatible installed engine environments."""
from typing import Any, cast
from pathlib import Path
from fruitfly_eval.harbor.lifecycle import record_environment


class PreparedMounts:
    def __init__(self, *args: Any, dependency_mounts: list[dict[str, Any]],
                 mounts: list[dict[str, Any]] | None = None, **kwargs: Any) -> None:
        combined = [dict(mount) for mount in (mounts or [])]
        from fruitfly_eval.bridges.model_access import trial_relay_directory
        from fruitfly_eval.harbor.model_access import TARGET
        for mount in combined:
            if mount['target'] == TARGET:
                private = trial_relay_directory(Path(mount['source']), kwargs['trial_paths'].trial_dir)
                private.mkdir(mode=0o700, parents=True, exist_ok=True)
                mount.update(source=str(private), read_only=True)
        targets = {mount['target'] for mount in combined}
        for definition in dependency_mounts:
            target = definition['target']
            if target in targets:
                raise ValueError('prepared dependency mount conflicts with Harbor mount: ' + target)
            targets.add(target)
            combined.append(definition.copy())
        record_environment(kwargs['trial_paths'].trial_dir, kwargs['session_id'])
        # The next constructor is supplied by the selected optional SDK in the
        # cooperative MRO. Its arguments are checked by that engine's factory.
        cast(Any, super()).__init__(*args, mounts=combined, **kwargs)
