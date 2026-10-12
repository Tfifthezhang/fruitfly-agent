"""Supported startup-selection composition entry point."""
class RunStartupVersions:
    def __init__(self, factory):
        self._service = factory.startup_versions()

    def versions(self, snapshot):
        return self._service.versions(snapshot)

    async def prepare(self, manifest, tokens, *, remember=()):
        return await self._service.prepare(manifest, tokens, remember=remember)
