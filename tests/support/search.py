"""Shared offline search inputs and services."""
from dataclasses import replace
from fruitfly_agent.core.config import AgentLoopConfig
from fruitfly_agent.core.data_model import AssistantMessage, ToolCallBlock, Usage
from fruitfly_agent.lab.base_prompt.target import BasePromptTarget
from fruitfly_agent.lab.optimization.search import TaskCase, OptimizationProblem
from fruitfly_agent.lab.optimization.services import NativeSearchServices, SearchBudget, SearchJournal
from tests.support.faux_provider import FauxProvider


def problem(**changes):
    return replace(OptimizationProblem("search-1", "parent-1", BasePromptTarget("seed").snapshot(),
        "improve", (TaskCase("train", "A"),), (TaskCase("select", "B"),), "cases-1", "runtime-1",
        parameters=(("rounds", 2), ("batch_size", 2), ("history_limit", 5),
                    ("max_metric_calls", 12))), **changes)


def services(provider=None, *, p=None, model_calls=64, trials=32, **kwargs):
    p = p or problem()
    return NativeSearchServices(p, AgentLoopConfig(provider=provider or FauxProvider(), model="offline", system_prompt="production"),
        BasePromptTarget("seed"), budget=SearchBudget(model_calls, trials), journal=SearchJournal(p), **kwargs)


def tool_calls(provider, calls):
    provider.respond(AssistantMessage(content=[ToolCallBlock(id=f"call-{i}", name=name, input=args)
        for i, (name, args) in enumerate(calls)], stop_reason="toolUse", usage=Usage(input_tokens=1, output_tokens=1)))


def engineer(provider, output, *, role):
    files = ("history.json",) if role == "meta" else ("learning-context/SKILL.md", "incumbent.txt", "training.json")
    tool_calls(provider, [("read", {"path": path}) for path in files])
    tool_calls(provider, [("write", {"path": "learning-context/SKILL.md" if role == "meta" else "context.txt", "content": output})])
    provider.respond_text("Saved.")
