"""Present candidate-backed prompt choices without coupling configuration to jobs."""
from pathlib import Path
from fruitfly_agent.lab.base_prompt import builtins
from fruitfly_agent.run.configuration.profile import HarnessProfile

def candidate_prompt_choices(profile: HarnessProfile, *, read_text, records, config_path: Path):
    options = {prompt.prompt_id: prompt.label for prompt in builtins()}
    builtin_ids = tuple(options)
    hashes = {prompt.content_hash for prompt in builtins()}
    seen = set()
    scope = (str(config_path.resolve()), profile.profile_id)
    try:
        records = records()
    except (OSError, ValueError, TypeError):
        records = ()
    for record in records:
        if (record.config_path, record.profile_id) != scope or record.target != 'base_prompt':
            continue
        task = record.task_pack_id
        if task in seen:
            continue
        seen.add(task)
        if record.status in {'rejected', 'stale'}:
            continue
        try:
            read_text(record.artifact_id)
        except (OSError, ValueError):
            continue
        if record.artifact_id in hashes:
            continue
        hashes.add(record.artifact_id)
        name = record.task_pack_name or task or 'Unattributed task'
        options[record.artifact_id] = f'{name} · {record.algorithm.upper()} improved · {record.status}'
    if profile.prompt not in options:
        label = 'Current selected prompt'
        selected = next((r for r in records if (r.config_path, r.profile_id) == scope
                         and r.target == 'base_prompt' and r.artifact_id == profile.prompt), None)
        if selected:
            label = f'{selected.task_pack_name or selected.task_pack_id or "Unattributed task"} · {selected.algorithm.upper()} improved · current'
        options[profile.prompt] = label
    adapted_ids = tuple(ref for ref in options if ref not in builtin_ids)
    groups = (("builtin", "Built-in prompts", builtin_ids, False),
              ("adapted", "Task / scenario adapted prompts", adapted_ids, True))
    return tuple(options), tuple(options.items()), groups

