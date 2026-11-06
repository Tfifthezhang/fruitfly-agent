"""Skill loading + catalog rendering."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fruitfly_agent.lab.context_manager.augmentation.skills.methods.indexed_documents import parser as catalog

from fruitfly_agent.core.context import ContextFrame
from fruitfly_agent.lab.context_manager.augmentation.skills import (
    SkillCatalogTransformer, load_skills, render_skills_xml,
)


class TestSkills(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def write_skill(self, rel, body, name=None, description="does things", **extra):
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        frontmatter = f"name: {name or path.parent.name}\ndescription: {description}\n"
        for k, v in extra.items():
            frontmatter += f"{k}: {v}\n"
        path.write_text(f"---\n{frontmatter}---\n{body}")

    def test_load_and_parse(self):
        self.write_skill("pdf/SKILL.md", "how to pdf")
        result = load_skills(self.root)
        self.assertEqual(len(result.skills), 1)
        self.assertEqual(result.skills[0].name, "pdf")
        self.assertEqual(result.skills[0].description, "does things")
        self.assertIn("how to pdf", result.skills[0].content)

    def test_skill_md_stops_descent(self):
        self.write_skill("outer/SKILL.md", "outer wins")
        self.write_skill("outer/inner/SKILL.md", "inner hidden")
        result = load_skills(self.root)
        names = [s.name for s in result.skills]
        self.assertEqual(names, ["outer"])

    def test_root_md_files_load(self):
        (self.root / "notes.md").write_text("---\ndescription: root notes\n---\nbody")
        result = load_skills(self.root)
        self.assertEqual(len(result.skills), 1)

    def test_invalid_utf8_is_diagnosed_without_losing_other_skills(self):
        (self.root / 'bad.md').write_bytes(b'\xff')
        self.write_skill('valid/SKILL.md', 'usable')
        result = load_skills(self.root)
        self.assertEqual(['valid'], [s.name for s in result.skills])
        self.assertTrue(any('read failed' in d for d in result.diagnostics))

    def test_symlink_cycles_external_directories_and_files_are_skipped(self):
        with tempfile.TemporaryDirectory() as outside:
            external = Path(outside) / 'SKILL.md'
            external.write_text('---\ndescription: outside\n---\nbody')
            (self.root / 'cycle').symlink_to(self.root, target_is_directory=True)
            (self.root / 'outside').symlink_to(outside, target_is_directory=True)
            (self.root / 'link.md').symlink_to(external)
            (self.root / 'nested').mkdir()
            (self.root / 'nested/SKILL.md').symlink_to(external)
            self.write_skill('valid/SKILL.md', 'usable')
            result = load_skills(self.root)
        self.assertEqual(['valid'], [s.name for s in result.skills])
        self.assertEqual(4, sum('symlink skipped' in d for d in result.diagnostics))

    def test_scan_depth_entries_file_size_and_total_bytes_are_bounded(self):
        self.write_skill('nested/deep/SKILL.md', 'body')
        self.write_skill('direct/SKILL.md', 'body')
        with patch.object(catalog, '_MAX_DEPTH', 0):
            result = load_skills(self.root)
        self.assertEqual([], result.skills)
        self.assertTrue(any('depth limit' in d for d in result.diagnostics))
        with patch.object(catalog, '_MAX_ENTRIES', 0):
            result = load_skills(self.root)
        self.assertEqual([], result.skills)
        self.assertTrue(any('entry limit' in d for d in result.diagnostics))
        self.write_skill('a.md', 'small')
        self.write_skill('b.md', 'small')
        size = (self.root / 'a.md').stat().st_size
        with patch.object(catalog, '_MAX_FILE_BYTES', 1):
            result = load_skills(self.root)
        self.assertEqual([], result.skills)
        self.assertTrue(any('byte limit' in d for d in result.diagnostics))
        with patch.object(catalog, '_MAX_TOTAL_BYTES', size):
            result = load_skills(self.root)
        self.assertEqual(1, len(result.skills))
        self.assertTrue(any('total byte limit' in d for d in result.diagnostics))

    def test_entry_limit_preserves_loaded_skills_and_reports_omissions(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ('a', 'b', 'c'):
                (root / (name + '.md')).write_text('---\ndescription: usable\n---\nbody')
            with patch.object(catalog, '_MAX_ENTRIES', 2):
                result = load_skills(root)
        self.assertEqual(2, len(result.skills))
        self.assertEqual(['scan entry limit reached'], result.diagnostics)

    def test_oversized_skill_does_not_prevent_loading_a_small_one(self):
        (self.root / 'huge.md').write_text('x' * 100)
        self.write_skill('valid/SKILL.md', 'usable')
        with patch.object(catalog, '_MAX_FILE_BYTES', 80):
            result = load_skills(self.root)
        self.assertEqual(['valid'], [s.name for s in result.skills])
        self.assertTrue(any('byte limit' in d for d in result.diagnostics))

    def test_missing_description_diagnostic(self):
        self.write_skill("x/SKILL.md", "body", description="")
        result = load_skills(self.root)
        self.assertEqual(len(result.skills), 1)
        self.assertEqual(len(result.diagnostics), 1)

    def test_disable_model_invocation_filtered(self):
        self.write_skill("visible/SKILL.md", "v")
        self.write_skill("hidden/SKILL.md", "h", **{"disable-model-invocation": True})
        result = load_skills(self.root)
        xml = render_skills_xml(result.skills)
        self.assertIn("visible", xml)
        self.assertNotIn("hidden", xml)

    def test_xml_escaping(self):
        self.write_skill("evil/SKILL.md", "b", name="a<b>&c", description='d"e')
        result = load_skills(self.root)
        xml = render_skills_xml(result.skills)
        self.assertIn("a&lt;b&gt;&amp;c", xml)
        self.assertNotIn("a<b>", xml)

    def test_projection_is_owned_by_lab_and_replaces_existing_catalog(self):
        self.write_skill("first/SKILL.md", "body")
        guidance = render_skills_xml(load_skills(self.root).skills)
        transformer = SkillCatalogTransformer(guidance)
        frame = ContextFrame("base", (), (), "offline", 32)
        projected = transformer.transform(frame)
        self.assertEqual("base", frame.system_prompt)
        self.assertIsNone(transformer.transform(projected.frame))
        self.assertEqual(1, projected.frame.system_prompt.count("<available_skills>"))
        cleared = SkillCatalogTransformer("").transform(projected.frame)
        self.assertEqual("base", cleared.frame.system_prompt)

    def test_oversized_catalog_is_omitted_without_broken_xml(self):
        frame = ContextFrame("base", (), (), "offline", 32)
        projected = SkillCatalogTransformer("x" * 500, max_chars=128).transform(frame)
        self.assertTrue(projected.metadata["catalog_omitted"])
        self.assertIn("Skill catalog omitted", projected.frame.system_prompt)
        self.assertLessEqual(len(projected.frame.system_prompt) - len("base\n\n"), 128)
        self.assertIsNone(SkillCatalogTransformer("").transform(frame))
        with self.assertRaises(ValueError):
            SkillCatalogTransformer("", max_chars=True)


class SkillResourceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        from tests.support.assembly import AssemblyWorkspace
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory())).resolve()
        self.workspace = AssemblyWorkspace(self.root)
        self.path = self.root / '.skills/example/SKILL.md'
        self.path.parent.mkdir(parents=True)
        self.path.write_text('---\nname: example\ndescription: Original description\n---\nOriginal body')
        references = self.path.parent / 'references'
        references.mkdir()
        (references / 'guide.md').write_text('Original reference')

    def assemble(self, session):
        from fruitfly_agent.lab.catalog import builtin_catalog, PermissionPolicy, MechanismSelection
        from fruitfly_agent.runtime_spec import HarnessProfile
        profile = HarnessProfile('test', str(self.workspace.model_path), 'offline',
            tuple(MechanismSelection(name) for name in ('local-env', 'read-tool', 'skills')))
        return self.workspace.assemble(profile, session, catalog=builtin_catalog(),
            permission_policy=PermissionPolicy.unrestricted(self.root))

    async def test_provider_directory_body_and_relative_text_use_one_snapshot_until_reassembly(self):
        from fruitfly_agent.core.session import Session
        from fruitfly_agent.core.loop import run_agent_loop
        from fruitfly_agent.core.data_model import UserMessage
        with Session(self.root / 'first.jsonl') as session:
            runtime = self.assemble(session)
            provider = runtime.config.provider
            prefix = f'resource://{runtime.config.readable_resources.scope}/skills/.fruitfly/skill-library/example/'
            self.path.write_text('---\nname: example\ndescription: Updated description\n---\nUpdated body')
            (self.path.parent / 'references/guide.md').write_text('Updated reference')
            provider.respond_tool_call('read', {'path': prefix + 'SKILL.md'})
            provider.respond_tool_call('read', {'path': prefix + 'references/guide.md'})
            provider.respond_text('done')
            try:
                result = await run_agent_loop(runtime.config, [UserMessage('Inspect the skill')],
                                              context_pipeline=runtime.context_pipeline)
                self.assertFalse(result.is_error)
                self.assertIn('Original description', provider.calls[0]['system_prompt'])
                self.assertNotIn('Updated description', provider.calls[0]['system_prompt'])
                self.assertIn(prefix + 'SKILL.md', provider.calls[0]['system_prompt'])
                texts = [m.text for m in result.messages if m.role == 'toolResult']
                self.assertIn('Original body', texts[0])
                self.assertEqual('Original reference', texts[1])
            finally:
                runtime.config.readable_resources.close()
        with Session(self.root / 'second.jsonl') as session:
            runtime = self.assemble(session)
            try:
                snapshot = runtime.components['skill-resources']
                skill = next(skill for skill in snapshot.skills if skill.name == 'example')
                self.assertEqual('Updated description', skill.description)
                self.assertIn('Updated body', skill.content)
            finally:
                runtime.config.readable_resources.close()

    async def test_skill_read_does_not_use_the_selected_remote_filesystem_and_retired_resources_fail(self):
        from fruitfly_agent.core.session import Session
        from fruitfly_agent.core.tool_runtime import ToolCallContext
        class RemoteFilesystem:
            def __getattr__(self, name):
                raise AssertionError('Skill text must stay on the host resource path')
        with Session(self.root / 'ssh.jsonl') as session:
            runtime = self.assemble(session)
            resources = runtime.config.readable_resources
            uri = f'resource://{resources.scope}/skills/.fruitfly/skill-library/example/SKILL.md'
            read = next(t for t in runtime.config.tools if t.name == 'read')
            result = await read.execute(ToolCallContext('read-skill', 'read', {'path': uri}, RemoteFilesystem()))
            self.assertIn('Original body', result.content[0].text)
            resources.close()
            with self.assertRaisesRegex(ValueError, 'retired'):
                await read.execute(ToolCallContext('retired', 'read', {'path': uri}, RemoteFilesystem()))

    def test_diagnostics_are_retained_and_changes_during_capture_are_rejected(self):
        from fruitfly_agent.lab.context_manager.augmentation.skills.resources import capture_skills
        from fruitfly_agent.core.session import Session
        self.path.write_text('---\nname: example\n---\nbody')
        with Session(self.root / 'diagnostics.jsonl') as session:
            with self.assertRaisesRegex(ValueError, 'Skill description'):
                self.assemble(session)
        stale = load_skills(self.root / '.skills')
        self.path.write_text('Concurrent edit')
        with patch('fruitfly_agent.lab.context_manager.augmentation.skills.resources.load_skills', return_value=stale):
            with self.assertRaisesRegex(ValueError, 'changed during assembly'):
                capture_skills(self.root / '.skills', self.root)


if __name__ == "__main__":
    unittest.main()
