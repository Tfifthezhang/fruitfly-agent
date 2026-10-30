"""One queue provides serial execution, bounded parallelism and cancellation cleanup."""
import asyncio
import unittest
from fruitfly_agent.improvement.execution.scheduler import TaskScheduler


class SchedulerTests(unittest.IsolatedAsyncioTestCase):
    async def test_single_and_multiple_tasks_share_the_same_queue(self):
        for concurrency, count in ((1, 1), (1, 4), (2, 7)):
            active = peak = 0
            async def operation(index):
                nonlocal active, peak
                active += 1
                peak = max(peak, active)
                try:
                    await asyncio.sleep(0)
                    return index
                finally: active -= 1
            queue = TaskScheduler(concurrency)
            self.assertEqual(await queue.map(tuple(lambda i=i: operation(i) for i in range(count))), tuple(range(count)))
            self.assertEqual(peak, min(count, concurrency))
            self.assertEqual(active, 0)
            await queue.aclose()

    async def test_cancelled_batch_closes_running_work_and_does_not_launch_queued_work(self):
        entered = asyncio.Event()
        active, cleaned = [], []
        async def operation(index):
            active.append(index)
            entered.set()
            try: await asyncio.Event().wait()
            finally: cleaned.append(index)
        queue = TaskScheduler(2)
        pending = asyncio.create_task(queue.map(tuple(lambda i=i: operation(i) for i in range(8))))
        await entered.wait()
        pending.cancel()
        with self.assertRaises(asyncio.CancelledError): await pending
        self.assertEqual(sorted(active), sorted(cleaned))
        self.assertLessEqual(len(active), 2)
        await queue.aclose()
