"""Explicit service policies layered over protocol adapters; no endpoint guessing."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable
import re


@dataclass(frozen=True)
class ServiceDefinition:
    id: str
    protocols: frozenset[str]
    validate: Callable[[str, str, dict[str, Any]], None]
    prefix_bound: bool = False
    responses_store: bool = True
    parallel_control: bool = True
    chat_token_field: str = 'max_tokens'
    chat_stream_usage: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.id, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', self.id):
            raise ValueError('service needs a stable ID')
        if not self.protocols or any(not isinstance(p, str) or not p for p in self.protocols) or not callable(self.validate):
            raise ValueError('service needs protocols and a pure validator')
        if any(type(v) is not bool for v in (self.prefix_bound, self.responses_store, self.parallel_control, self.chat_stream_usage)):
            raise ValueError('service control flags must be booleans')
        if self.chat_token_field not in {'max_tokens', 'max_completion_tokens'}:
            raise ValueError('unsupported Chat output-limit parameter')
        object.__setattr__(self, 'protocols', frozenset(self.protocols))


def _generic(protocol: str, model: str, options: dict[str, Any]) -> None:
    pass


def _anthropic(protocol: str, model: str, options: dict[str, Any]) -> None:
    thinking = options.get('thinking', {})
    if thinking.get('type') == 'enabled':
        budget = thinking.get('budget_tokens')
        if type(budget) is not int or budget < 1024:
            raise ValueError('Anthropic manual thinking requires budget_tokens >= 1024')
    elif 'budget_tokens' in thinking:
        raise ValueError('budget_tokens requires manual enabled thinking')
    if 'display' in thinking and thinking['display'] not in {'summarized', 'omitted', 'updates'}:
        raise ValueError('unsupported thinking.display')


def _deepseek(protocol: str, model: str, options: dict[str, Any]) -> None:
    ignored = {'include', 'service_tier', 'prompt_cache_key', 'prompt_cache_retention'} & options.keys()
    if ignored:
        raise ValueError('DeepSeek does not support: ' + ', '.join(sorted(ignored)))
    if protocol == 'responses':
        reasoning = options.get('reasoning', {})
        if reasoning.keys() - {'effort'}:
            raise ValueError('DeepSeek Responses supports only reasoning.effort')
        effort = reasoning.get('effort', 'high')
        if effort not in {'none', 'low', 'high', 'max'}:
            raise ValueError('DeepSeek reasoning.effort must be none, low, high or max')
        thinking = effort != 'none'
        if 'verbosity' in options.get('text', {}):
            raise ValueError('DeepSeek ignores text.verbosity')
    elif protocol == 'messages':
        config = options.get('thinking', {})
        if config.keys() - {'type'} or config.get('type', 'enabled') not in {'enabled', 'disabled'}:
            raise ValueError('DeepSeek thinking supports enabled/disabled without budget_tokens')
        if options.get('output_config', {}).keys() - {'effort'}:
            raise ValueError('DeepSeek output_config supports only effort')
        if options.get('output_config', {}).get('effort', 'high') not in {'low', 'high', 'max'}:
            raise ValueError('DeepSeek output_config.effort must be low, high or max')
        if 'top_k' in options:
            raise ValueError('DeepSeek ignores top_k')
        thinking = config.get('type', 'enabled') != 'disabled'
    else:
        extra = options.get('extra_body', {})
        if extra.keys() - {'thinking'}:
            raise ValueError('DeepSeek Chat extra_body supports only thinking')
        config = extra.get('thinking', {})
        if not isinstance(config, dict) or config.keys() - {'type'} or config.get('type', 'enabled') not in {'enabled', 'disabled'}:
            raise ValueError('DeepSeek Chat thinking requires enabled/disabled')
        if options.get('reasoning_effort', 'high') not in {'low', 'high', 'max'}:
            raise ValueError('DeepSeek reasoning_effort must be low, high or max')
        thinking = config.get('type', 'enabled') != 'disabled'
    if thinking and {'temperature', 'presence_penalty', 'frequency_penalty'} & options.keys():
        raise ValueError('DeepSeek ignores temperature and penalty parameters while thinking')
    if 'top_p' in options:
        value = options['top_p']
        if model == 'deepseek-flash' and ((thinking and value < .95) or (not thinking and value != 1)):
            raise ValueError('DeepSeek Flash top_p requires 0.95–1 while thinking; otherwise 1')
        if model == 'deepseek-v4-pro' and thinking:
            raise ValueError('DeepSeek Pro ignores top_p while thinking')
    if protocol != 'chat-completions' and options.get('extra_body'):
        raise ValueError('DeepSeek parameters must use the declared protocol fields')


def _qwen(protocol: str, model: str, options: dict[str, Any]) -> None:
    extra = options.get('extra_body', {})
    for name in ('enable_thinking', 'preserve_thinking', 'tool_stream'):
        if name in extra and type(extra[name]) is not bool:
            raise ValueError('Qwen ' + name + ' must be boolean')
    if 'reasoning_effort' in options:
        raise ValueError('Qwen Chat reasoning_effort belongs in extra_body')
    if 'thinking_budget' in extra:
        budget = extra['thinking_budget']
        if type(budget) is not int or budget <= 0:
            raise ValueError('Qwen thinking_budget must be a positive integer')
    if model.startswith('qwen3.8-'):
        if 'reasoning_effort' in extra and extra['reasoning_effort'] not in {'low', 'medium', 'xhigh'}:
            raise ValueError('Qwen3.8 Chat reasoning_effort must be low, medium or xhigh')
        if {'reasoning_effort', 'thinking_budget'} <= extra.keys():
            raise ValueError('Qwen3.8 cannot combine reasoning_effort and thinking_budget')
    if extra.get('enable_thinking', True) and options.get('tool_choice', 'auto') not in ('auto', 'none'):
        raise ValueError('Qwen thinking does not support forced tool_choice')


def _bigmodel(protocol: str, model: str, options: dict[str, Any]) -> None:
    extra = options.get('extra_body', {})
    thinking = extra.get('thinking', {})
    if not isinstance(thinking, dict) or thinking.keys() - {'type'} or thinking.get('type', 'enabled') not in {'enabled', 'disabled'}:
        raise ValueError('BigModel thinking supports enabled/disabled without a token budget')
    if model.startswith('glm-4.5') and ('reasoning_effort' in options or 'reasoning_effort' in extra):
        raise ValueError('GLM-4.5 does not support reasoning_effort; use extra_body.thinking.type')
    if model.startswith('glm-4.5') and 'tool_stream' in extra:
        raise ValueError('GLM-4.5 does not support tool_stream')
    if options.get('temperature', 0) > 1 or options.get('top_p', 1) < .01:
        raise ValueError('BigModel requires temperature <= 1 and top_p >= 0.01')
    if options.get('tool_choice', 'auto') != 'auto':
        raise ValueError('BigModel supports only tool_choice auto')
    if options.get('response_format', {}).get('type') == 'json_schema':
        raise ValueError('BigModel supports text or json_object response_format')


_SERVICES = {item.id: item for item in (
    ServiceDefinition('generic', frozenset({'responses', 'messages', 'chat-completions'}), _generic),
    ServiceDefinition('openai', frozenset({'responses', 'chat-completions'}), _generic, chat_token_field='max_completion_tokens'),
    ServiceDefinition('anthropic', frozenset({'messages'}), _anthropic, prefix_bound=True),
    ServiceDefinition('deepseek', frozenset({'responses', 'messages', 'chat-completions'}), _deepseek,
                      responses_store=False, parallel_control=False),
    ServiceDefinition('qwen', frozenset({'chat-completions'}), _qwen),
    ServiceDefinition('bigmodel', frozenset({'chat-completions'}), _bigmodel,
                      parallel_control=False, chat_stream_usage=False),
)}


def register_service(definition: ServiceDefinition) -> None:
    if not definition.id or definition.id in _SERVICES:
        raise ValueError('service ID must be nonempty and distinct')
    _SERVICES[definition.id] = definition


def service_definition(service: str, protocol: str) -> ServiceDefinition:
    try:
        definition = _SERVICES[service]
    except KeyError as exc:
        raise ValueError('unknown model service: ' + service) from exc
    if protocol not in definition.protocols and service != 'generic':
        raise ValueError('model service does not support protocol: ' + protocol)
    return definition


__all__ = ['ServiceDefinition', 'register_service', 'service_definition']
