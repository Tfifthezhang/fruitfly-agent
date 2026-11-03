"""Project a borrowed operation service into frontend contracts and facts."""
from fruitfly_agent.interactive.contracts.operations import OperationStatus
from fruitfly_agent.interactive.contracts.events import ManagedOperationChanged


class ManagedOperationAdapter:
    def __init__(self, operations, emit):
        self.operations = operations
        self.emit = emit
        operations.listener = self.changed

    def statuses(self):
        return tuple(OperationStatus(value.handle, value.state, value.elapsed_seconds, value.run_id, value.tool_call_id)
            for value in self.operations.statuses())

    async def cancel(self, handle):
        value = await self.operations.cancel(handle)
        return OperationStatus(value.handle, value.state, value.elapsed_seconds, value.run_id, value.tool_call_id)

    async def changed(self, value):
        await self.emit(ManagedOperationChanged(run_id='', handle=value.handle, state=value.state,
            elapsed_seconds=value.elapsed_seconds, initiating_run_id=value.run_id, tool_call_id=value.tool_call_id))
