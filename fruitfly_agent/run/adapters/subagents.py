"""Project borrowed child execution facts without owning work or resources."""
from dataclasses import fields
from fruitfly_agent.interactive.contracts.subagents import SubagentStatus, SubagentSnapshot

class SubagentMonitorAdapter:
    def __init__(self, service):
        self.service = service

    def project(self, row):
        return SubagentStatus(**{field.name: row[field.name] for field in fields(SubagentStatus)})

    def snapshot(self):
        value = self.service.snapshot()
        return SubagentSnapshot(value['revision'], value['max_concurrent'],
            tuple(self.project(row) for row in value['executions']), value['poisoned'])

    def detail(self, agent_id, run_id=None):
        return self.project(self.service.detail(agent_id, run_id))
