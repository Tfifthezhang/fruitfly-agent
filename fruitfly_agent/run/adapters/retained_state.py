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
