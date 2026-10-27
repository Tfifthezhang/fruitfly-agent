from __future__ import annotations

import unittest
from pathlib import Path
import tempfile

from unittest.mock import patch




from fruitfly_agent.run.application import RunApplicationFactory


class FactoryResourceTests(unittest.IsolatedAsyncioTestCase):
    async def test_factory_closes_created_resources_when_assembly_fails(self) -> None:
        class Resource:
            def __init__(self) -> None:
                self.closed = False

            async def close(self):
                self.closed = True

        resource = Resource()

        def fail(*args, resource_sink, **kwargs):
            resource_sink.append(resource)
            raise ValueError("assembly failed")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".fruitfly").mkdir()
            (root / ".fruitfly/models.yaml").write_text(
                'models:\n  offline:\n    sdk: anthropic\n    protocol: messages\n    model: offline\n    api_key_env: TEST_KEY\n    context_window: 4096\n',
                encoding="utf-8",
            )
            factory = RunApplicationFactory(cwd=root, environment={})
            with patch(
                "fruitfly_agent.run.application.build_runtime",
                side_effect=fail,
            ):
                with self.assertRaisesRegex(ValueError, "assembly failed"):
                    await factory.open(
                        resume=False,
                        session_path=root / "failed.jsonl",
                    )

        self.assertTrue(resource.closed)
