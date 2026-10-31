"""Restore one frozen evaluator candidate into the existing inner episode."""
from dataclasses import asdict
from fruitfly_agent.lab.improvement.components import TextComponentAdapter
from fruitfly_agent.lab.improvement.assessment.instructions import EvaluatorInstructionTarget


def install_candidate(registry, candidate, settings):
    name = 'improvement-evaluator'
    if candidate is None or name not in registry.adapters:
        return
    document = candidate.component(name)
    text = document.files[0].text
    instructions = EvaluatorInstructionTarget.parse(text)
    target = EvaluatorInstructionTarget(instructions, text=text)
    registry.adapters[name] = TextComponentAdapter(target, 'evaluator-instructions')
    settings['evaluator'] = {'instructions': asdict(instructions)}
