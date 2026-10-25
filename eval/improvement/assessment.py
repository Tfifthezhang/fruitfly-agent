"""Official development measurements; scoring does not grant verification."""
from fruitfly_agent.lab.improvement.api import Measurement


class OfficialMeasurements:
    direction = 'max'
    policy_id = 'official-benchmark-reward-v1'

    def __init__(self): self.values = {}

    async def measure(self, task, record):
        score = self.values.get(record.run_id)
        if score is None or record.status != 'completed': return None
        return Measurement(record.run_id, self.policy_id, score,
            'Official reward on declared development tasks; not independent verification.')
