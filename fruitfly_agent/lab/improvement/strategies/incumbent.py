"""Default seed retention without algorithm or assessment dependencies."""
from fruitfly_agent.improvement.contracts.search import ExplorationDecision

class IncumbentExploration:
    async def choose(self, task, records, incumbent, assessment):
        return ExplorationDecision(incumbent.run_id, 'Continue from the official incumbent.')

