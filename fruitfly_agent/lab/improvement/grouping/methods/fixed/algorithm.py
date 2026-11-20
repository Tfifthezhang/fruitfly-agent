"""Resolve researcher-declared groups in their authored order."""


def select(task_ids, members, position, batch_size, seed):
    if not isinstance(members, list) or position >= len(members):
        raise ValueError('fixed grouping requires a member list at the requested position')
    group = members[position]
    if not isinstance(group, list) or not group or len(group) > batch_size:
        raise ValueError('invalid fixed grouping members')
    selected = {}
    for member in group:
        if isinstance(member, str):
            task_id, runs = member, None
        elif isinstance(member, dict) and set(member) == {'task_id', 'run_ids'}:
            task_id, runs = member['task_id'], member['run_ids']
            if (not isinstance(runs, list) or any(not isinstance(run, str) for run in runs)
                    or len(runs) != len(set(runs))):
                raise ValueError('fixed group run IDs must be distinct')
        else:
            raise ValueError('invalid fixed grouping member')
        if not isinstance(task_id, str) or task_id not in task_ids or task_id in selected:
            raise ValueError('invalid fixed grouping task')
        selected[task_id] = runs
    return selected
