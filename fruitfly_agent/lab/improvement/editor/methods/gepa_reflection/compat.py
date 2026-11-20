"""Pinned admission and the two one-shot GEPA functions used by FruitFlyAgent."""
from importlib.metadata import PackageNotFoundError, version

PINNED_VERSION = '0.1.4'


def signature():
    try:
        actual = version('gepa')
    except PackageNotFoundError as exc:
        raise ValueError('GEPA reflection requires the fruitfly-agent[gepa] extra') from exc
    if actual != PINNED_VERSION:
        raise ValueError('GEPA reflection requires gepa==' + PINNED_VERSION)
    from gepa.strategies.instruction_proposal import InstructionProposalSignature
    return InstructionProposalSignature


def render(adapter, text, dataset, template):
    prompt = adapter.prompt_renderer({'current_instruction_doc': text,
        'dataset_with_feedback': dataset, 'prompt_template': template})
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError('GEPA reflection requires a nonempty text-only prompt')
    return prompt


def parse(adapter, response):
    text = adapter.output_extractor(response).get('new_instruction')
    if not isinstance(text, str) or not text.strip():
        raise ValueError('GEPA did not return a usable instruction')
    return text
