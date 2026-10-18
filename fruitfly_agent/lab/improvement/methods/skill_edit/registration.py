"""Per-job registration; no model work during discovery or construction."""
from fruitfly_agent.core.mechanisms import ParameterDescriptor as P
from fruitfly_agent.lab.improvement.registration import native_method_definition
from . import SkillEditImprover


def definition():
    return native_method_definition(SkillEditImprover, label='Skill document optimization', family='context',
        description='Improve an existing Skill body through bounded edits guided by measured task feedback.',
        implementation_path='fruitfly_agent/lab/improvement/methods/skill_edit/__init__.py',
        documentation_path='fruitfly_agent/lab/improvement/methods/skill_edit/README.md',
        target='skill-document', parameters=(
            P('rounds', 'integer', 'Update rounds', 'Maximum feedback-driven update rounds.', 2, minimum=1, maximum=20),
            P('edit_budget', 'integer', 'Edits per update', 'Maximum add/delete/replace operations per candidate.', 2, minimum=1, maximum=8),
            P('rollout_batch_size', 'integer', 'Training batch', 'Maximum frozen training tasks per update.', 4, minimum=1, maximum=12),
            P('reflection_batch_size', 'integer', 'Reflection minibatch', 'Training trajectories per reflection request.', 2, minimum=1, maximum=12)))
