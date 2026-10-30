"""Only catalog guidance is improved; referenced Skill files remain separate."""
from fruitfly_agent.improvement.contracts.optimization import OptimizationSpec
from dataclasses import replace
from fruitfly_agent.core.context import ContextFrame
from .adapter import SkillCatalogTransformer
from fruitfly_agent.improvement.contracts.optimization import TargetBinding, TargetSnapshot
from fruitfly_agent.lab.improvement.targets.text import validate_text

SKILL_CATALOG_GUIDANCE_KEY = 'skill-catalog.guidance'


class SkillGuidanceTarget:
    optimization = OptimizationSpec('H', 'text')
    label = 'Skill catalog guidance'

    def __init__(self, guidance, max_chars):
        self.guidance = guidance
        self.max_chars = max_chars

    def snapshot(self):
        return TargetSnapshot(SKILL_CATALOG_GUIDANCE_KEY, self.guidance,
                              TargetBinding('artifact', SKILL_CATALOG_GUIDANCE_KEY))

    def validate(self, text):
        validate_text(text)
        block = f'<!-- fruitfly:skill-catalog:start -->\n{text}\n<!-- fruitfly:skill-catalog:end -->'
        if len(block) > self.max_chars:
            raise ValueError('candidate guidance exceeds the projection budget')

    def prepare_trial(self, config, text):
        # An enabled empty catalog is a valid baseline, although a published
        # replacement must be nonempty and satisfy the projection budget.
        if text != self.guidance:
            self.validate(text)
        frame = ContextFrame(config.system_prompt, (), (), config.model, config.max_tokens)
        transformed = SkillCatalogTransformer(text, self.max_chars).transform(frame)
        return replace(config, system_prompt=transformed.frame.system_prompt) if transformed is not None else config
