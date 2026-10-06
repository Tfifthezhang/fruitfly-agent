"""Skill loading + catalog rendering."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fruitfly_agent.lab.context_manager.augmentation.skills import catalog

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


if __name__ == "__main__":
    unittest.main()
