"""Pure projection transforms. Original messages and tool effects stay intact."""
from copy import deepcopy
from dataclasses import replace
from fruitfly_agent.core.data_model import AssistantMessage, ToolResultMessage, UserMessage, TextBlock, ImageBlock
from ....resources import public_message
from .state import digest


def groups(messages):
    result, current = [], []
    pending: set[str] = set()
    for message in messages:
        current.append(message)
        if isinstance(message, AssistantMessage):
            pending.update(call.id for call in message.tool_calls)
        elif isinstance(message, ToolResultMessage):
            pending.discard(message.tool_call_id)
        if not pending:
            result.append(tuple(current))
            current = []
    if current:
        return ()
    return tuple(result)


def references(items, prefix):
    return {digest(item.message.to_dict()): prefix + 'messages/' + item.id for item in items}


def shrink_results(messages, items, prefix, config, *, force=False):
    result = deepcopy(tuple(messages))
    complete = groups(result)
    protected = {call.id for group in complete[-config.keep_recent_groups:] for message in group
                 if isinstance(message, AssistantMessage) for call in message.tool_calls}
    originals = {item.message.tool_call_id: prefix + 'messages/' + item.id for item in items
                 if isinstance(item.message, ToolResultMessage)}
    changed = []
    for message in result:
        reference = originals.get(message.tool_call_id) if isinstance(message, ToolResultMessage) else None
        if (reference and (force or message.tool_call_id not in protected)
                and len(message.text) > max(config.tool_result_min_chars, config.preview_chars + 256)
                and not any(isinstance(block, ImageBlock) for block in message.content)
                and '[Archived tool result;' not in message.text):
            half = config.preview_chars // 2
            text = ('[Archived tool result; ' + ('failed' if message.is_error else 'succeeded') + ']\n'
                    + message.text[:half] + '\n[Middle omitted]\n' + message.text[-(config.preview_chars-half):]
                    + '\nOriginal result: ' + reference)
            changed.append(replace(message, content=[TextBlock(text)]))
        else:
            changed.append(message)
    return tuple(changed)


def split_history(messages, config, estimate, target):
    complete = groups(messages)
    if len(complete) <= config.keep_recent_groups:
        return (), tuple(messages)
    keep = config.keep_recent_groups
    budget = min(config.tail_tokens, max(1, int(target * .5)))
    tokens = sum(estimate(message) for group in complete[-keep:] for message in group)
    while keep < len(complete) - 1:
        extra = sum(estimate(message) for message in complete[-keep-1])
        if tokens + extra > budget:
            break
        keep += 1
        tokens += extra
    cut = sum(len(group) for group in complete[:-keep])
    return tuple(messages[:cut]), tuple(messages[cut:])


def anchors(items, tail):
    users = [item.message for item in items if isinstance(item.message, UserMessage)]
    present = {digest(message.to_dict()) for message in tail}
    result = []
    for message in (users[:1] + users[-1:]):
        key = digest(message.to_dict())
        if key not in present:
            present.add(key)
            result.append(deepcopy(message))
    return tuple(result)


def summary_material(earlier, items, prefix, estimate, build, limit):
    refs = references(items, prefix)
    tool_refs = {item.message.tool_call_id: prefix + 'messages/' + item.id for item in items
                 if isinstance(item.message, ToolResultMessage)}
    entries, representations = [], []
    for message in earlier:
        reference = refs.get(digest(message.to_dict()))
        if reference is None and isinstance(message, ToolResultMessage):
            reference = tool_refs.get(message.tool_call_id)
        entries.append(public_message(message))
        kind = 'preview' if isinstance(message, ToolResultMessage) and '[Archived tool result;' in message.text else 'supplied'
        representations.append({'reference': reference or prefix + 'index', 'kind': kind})
    for index in sorted(range(len(entries)), key=lambda i: len(entries[i]), reverse=True):
        if estimate(build('\n\n'.join(entries))) <= limit:
            break
        entries[index] = '[Archived source: ' + representations[index]['reference'] + ']'
        representations[index]['kind'] = 'reference'
    material = '\n\n'.join(entries)
    return material, representations, estimate(build(material)) <= limit
