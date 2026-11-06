"""Public information spaces share retrieval without dedicated model tools."""

import tempfile
from pathlib import Path
import time
import unittest

from fruitfly_agent.core.config import AgentLoopConfig
from fruitfly_agent.core.context import ContextFrame
from fruitfly_agent.core.data_model import UserMessage
from fruitfly_agent.lab.context_manager.augmentation.information import (
    InformationHub,
    InformationArtifact,
    InformationQuery,
    InformationRef,
    create_local_knowledge_space,
    create_live_http_space,
    create_static_lexical_space,
)
from fruitfly_agent.lab.catalog import (
    AssemblyContext, MechanismSelection, assemble_lab, builtin_catalog,
)

from tests.support.faux_provider import FauxProvider


class InformationSourcesTest(unittest.IsolatedAsyncioTestCase):
    async def test_file_memory_directory_is_frozen_and_body_is_read_on_demand(self) -> None:
        import json
        from tests.support.retained import memory
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            note = memory()
            runtime = assemble_lab(AgentLoopConfig(FauxProvider()), catalog=builtin_catalog(),
                selections=tuple(MechanismSelection(name) for name in ('local-env', 'read-tool', 'file-memory')),
                context=AssemblyContext(root, None, 'fake', lambda *_: self.fail('auxiliary request'),
                    component_settings={'memory-library': {'content': {'documents': json.dumps([note])}}}))
            resources = runtime.config.readable_resources
            self.addCleanup(resources.close)
            stage = next(stage for stage in runtime.context_pipeline.stages if stage.stage_id == 'file-memory')
            effect = stage.mechanism.transform(ContextFrame('base', (), (), 'fake', 32)).frame.system_prompt
            self.assertIn(note['description'], effect)
            self.assertNotIn(note['body'], effect)
            uri = f'resource://{resources.scope}/retained-memory/{note["id"]}.md'
            self.assertIn(note['body'], resources.read(uri).decode())
            note['body'] = 'New source content'
            self.assertNotIn('New source content', resources.read(uri).decode())
            self.assertFalse((root / '.fruitfly/memory').exists())

    async def test_knowledge_reindexes_current_files_and_cites_lines(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            root.mkdir(exist_ok=True)
            path = root / "guide.md"
            path.write_text("alpha\nBeta is the answer.\ngamma\n", encoding="utf-8")
            hub = InformationHub()
            hub.register(create_local_knowledge_space(root))
            first = await hub.pipeline.recall(InformationQuery("Beta"))
            self.assertIn(f"Source: {path.resolve()}:1-3", first.content)
            path.write_text("alpha\nDelta is the answer.\n", encoding="utf-8")
            self.assertIsNone(await hub.pipeline.recall(InformationQuery("Beta")))
            self.assertIn("Delta", (await hub.pipeline.recall(InformationQuery("Delta"))).content)

    def test_knowledge_keeps_the_tail_of_long_lines(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "long.txt").write_text("x" * 1_600 + "tail-marker", encoding="utf-8")
            source = create_local_knowledge_space(root).reader
            artifacts = source.artifacts()
            self.assertEqual(2, len(artifacts))
            self.assertIn("tail-marker", artifacts[1].text)
            self.assertNotEqual(artifacts[0].ref, artifacts[1].ref)

    async def test_live_source_fetches_query_on_demand_and_is_read_only(self) -> None:
        calls = []

        def fetch(url: str, timeout: float) -> str:
            calls.append((url, timeout))
            return "Current forecast: rain"

        space = create_live_http_space(
            "https://example.org/search?q={query}", fetch=fetch
        )
        hub = InformationHub()
        hub.register(space)
        self.assertFalse(space.descriptor.writable)
        self.assertTrue(space.descriptor.external)
        self.assertEqual([], calls)
        effect = await hub.pipeline.recall(InformationQuery("ＳＨ weather"))
        self.assertIn("Current forecast: rain", effect.content)
        self.assertEqual("https://example.org/search?q=%EF%BC%B3%EF%BC%A8%20weather", calls[0][0])

    async def test_one_live_source_failure_does_not_block_knowledge(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "fact.md").write_text("Jupiter is a planet.", encoding="utf-8")
            hub = InformationHub()
            hub.register(create_local_knowledge_space(root))
            hub.register(create_live_http_space(
                "https://example.org?q={query}",
                fetch=lambda _url, _timeout: (_ for _ in ()).throw(OSError("offline")),
            ))
            result = await hub.pipeline.select(InformationQuery("Jupiter"))
            self.assertEqual(1, len(result.hits))
            self.assertEqual("live-information", result.errors[0].space_id)

    def test_live_endpoint_rejects_insecure_or_credential_urls(self) -> None:
        for url in (
            "http://example.org?q={query}",
            "https://user:secret@example.org?q={query}",
            "https://example.org?q=constant",
        ):
            with self.subTest(url=url), self.assertRaises(ValueError):
                create_live_http_space(url)

    async def test_expired_information_is_not_injected(self) -> None:
        hub = InformationHub()
        hub.register(create_static_lexical_space("old", [
            InformationArtifact(
                InformationRef("old", "expired"), "obsolete answer",
                valid_until=time.time() - 1,
            )
        ]))
        self.assertIsNone(await hub.pipeline.recall(InformationQuery("obsolete")))

    def test_knowledge_does_not_require_file_memory(self) -> None:
        resolved = builtin_catalog().resolve((
            MechanismSelection("information-context"),
            MechanismSelection("knowledge-files"),
        ))
        self.assertEqual(
            {item.definition.descriptor.mechanism_id for item in resolved},
            {"information-context", "knowledge-files"},
        )

    async def test_catalog_assembly_combines_sources_without_extra_tools(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            knowledge = root / '.fruitfly/knowledge'
            knowledge.mkdir(parents=True)
            (knowledge / 'guide.md').write_text('Reports use Python unittest.', encoding='utf-8')
            result = assemble_lab(AgentLoopConfig(provider=FauxProvider()), catalog=builtin_catalog(),
                selections=tuple(MechanismSelection(name) for name in
                    ('local-env', 'read-tool', 'information-context', 'file-memory', 'knowledge-files')),
                context=AssemblyContext(root, None, 'test-model', lambda *_: self.fail('unexpected provider')))
            self.addCleanup(result.config.readable_resources.close)
            frame = ContextFrame('base', (UserMessage('Python reports'),), (), 'test', 128)
            information = next(item for item in result.context_pipeline.stages if item.stage_id == 'information-context')
            projected = (await information.mechanism.transform(frame)).frame
            self.assertIn('Reports use Python unittest.', projected.system_prompt)
            self.assertNotIn('available_memories', projected.system_prompt)
            memory = next(item for item in result.context_pipeline.stages if item.stage_id == 'file-memory')
            combined = memory.mechanism.transform(projected).frame
            self.assertIn('available_memories', combined.system_prompt)
            self.assertIn('Read a relevant memory resource', combined.system_prompt)
            self.assertEqual(('read',), tuple(tool.name for tool in result.config.tools))
