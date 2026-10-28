"""One bounded task queue, including the single-execution concurrency-one case."""
import asyncio


class TaskScheduler:
    def __init__(self, concurrency=1):
        if type(concurrency) is not int or concurrency < 1:
            raise ValueError('execution concurrency must be positive')
        self.concurrency = concurrency
        self.closed = False
        self.active = set()

    async def map(self, operations):
        if self.closed or self.active:
            raise ValueError('scheduler is closed or already running a batch')
        operations = tuple(operations)
        results = [None] * len(operations)
        iterator = iter(enumerate(operations))
        async def worker():
            for index, operation in iterator:
                results[index] = await operation()
        self.active = {asyncio.create_task(worker()) for _ in range(min(self.concurrency, len(operations)))}
        tasks = tuple(self.active)
        try:
            await asyncio.gather(*tasks)
            return tuple(results)
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            self.active.clear()

    async def aclose(self):
        self.closed = True
        tasks = tuple(self.active)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
