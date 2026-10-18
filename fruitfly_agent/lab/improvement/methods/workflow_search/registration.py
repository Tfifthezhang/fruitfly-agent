"""Register workflow design independently of production execution."""
from fruitfly_agent.core.mechanisms import ParameterDescriptor as P
from fruitfly_agent.lab.improvement.registration import native_method_definition
from . import WorkflowSearchImprover


def definition():
    return native_method_definition(WorkflowSearchImprover, label='Workflow search', family='workflow',
        description='Search multi-stage execution workflows using measured designs, reflection and repair.',
        implementation_path='fruitfly_agent/lab/improvement/methods/workflow_search/__init__.py',
        documentation_path='fruitfly_agent/lab/improvement/methods/workflow_search/README.md',
        target='execution-workflow', direction_help='Optional direction for workflow design; measured task scores decide acceptance.',
        parameters=(
            P('rounds', 'integer', 'Design rounds', 'Maximum new workflow designs.', 2, minimum=1, maximum=20),
            P('archive_limit', 'integer', 'Design archive view', 'Maximum prior measured designs shown to the generator.', 5, minimum=1, maximum=12),
            P('reflection_steps', 'integer', 'Design reflections', 'Self-review requests before each trial.', 1, minimum=0, maximum=2),
            P('repair_attempts', 'integer', 'Schema repairs', 'Maximum repairs of malformed workflow declarations.', 1, minimum=0, maximum=3)))
