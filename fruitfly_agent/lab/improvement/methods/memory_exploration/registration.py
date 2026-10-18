"""Register explicit memory exploration with bounded authorized practice."""
from fruitfly_agent.core.mechanisms import ParameterDescriptor as P
from fruitfly_agent.lab.improvement.registration import native_method_definition
from . import MemoryExplorationImprover


def definition():
    return native_method_definition(MemoryExplorationImprover, label='Exploratory memory learning', family='context',
        description='Select verified practice tasks and consolidate reusable environment knowledge into memory.',
        implementation_path='fruitfly_agent/lab/improvement/methods/memory_exploration/__init__.py',
        documentation_path='fruitfly_agent/lab/improvement/methods/memory_exploration/README.md',
        target='learned-memory', parameters=(
            P('rounds', 'integer', 'Exploration rounds', 'Maximum curriculum/practice/consolidation rounds.', 3, minimum=1, maximum=20),
            P('broad_rounds', 'integer', 'Broad exploration rounds', 'Initial rounds for diverse practice; later rounds focus on gaps.', 1, minimum=0, maximum=20),
            P('practice_batch_size', 'integer', 'Broad practice batch', 'Maximum authorized tasks per broad round; focused rounds select one.', 3, minimum=1, maximum=12)))
