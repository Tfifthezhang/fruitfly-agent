"""Project a borrowed retained-state service into frontend contracts."""


class RetainedStateAdapter:
    def __init__(self, service):
        self.service = service

    def describe(self, kind):
        return self.service.describe(kind)

    def read_document(self, kind, identity):
        return self.service.read_document(kind, identity)

    def review(self, identity, action):
        return self.service.review(identity, action)

    async def run(self, kind, operation_id=None):
        if not self.service.workers:
            raise ValueError('manual memory maintenance is unavailable')
        result = await self.service.run(manual=True, operation_id=operation_id)
        if self.service.error:
            raise RuntimeError(self.service.error)
        if result is None:
            return 'no-work'
        return str(result)
