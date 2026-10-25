"""Operation-specific commands composed through public services."""
import asyncio
from dataclasses import asdict


async def observe(application, work, record, records, emit):
    """Forward public Application activity and retain links during long work."""
    task = asyncio.create_task(work)
    previous = None
    try:
        while not task.done():
            progress = application.improvement_progress
            activity = asdict(progress.activity) if progress.activity is not None else None
            value = (progress.status, activity)
            if value != previous:
                emit({'type': 'progress', 'id': record['id'], 'status': progress.status,
                    'activity': activity, 'usage_kind': 'charged allowance'})
                previous = value
            history = application.improvement_history()
            links = [r.run_id for r in history]
            if links and record['links'].get('improvement_runs') != links:
                record['links']['improvement_runs'] = links
                records.save(record)
            await asyncio.wait((task,), timeout=0.2)
        return await task
    finally:
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)
