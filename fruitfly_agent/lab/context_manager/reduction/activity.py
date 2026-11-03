"""Publish content-free reduction phase facts through the Core observer seam."""
from fruitfly_agent.core.data_model.context import ContextActivity


async def report_activity(snapshot, mechanism, stage, *, outcome='running', reason='', result=None):
    if snapshot.report_activity is not None:
        await snapshot.report_activity(ContextActivity(mechanism, stage, outcome,
            result.elapsed_seconds if result else 0., result.input_tokens if result else 0,
            result.output_tokens if result else 0, reason))
