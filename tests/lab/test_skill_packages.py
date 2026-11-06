"""Portable Skill admission preserves identity and explicit dependencies."""
from copy import deepcopy
import unittest
from fruitfly_agent.lab.context_manager.augmentation.skills.library import builtin_entries
from fruitfly_agent.lab.context_manager.augmentation.skills.packages import SkillPackage, validate_skills
from fruitfly_agent.lab.context_manager.augmentation.skills.installation import prepare_installation


class SkillPackageTests(unittest.TestCase):
    def test_packaged_set_has_four_noninteractive_coding_procedures(self):
        entries = builtin_entries()
        self.assertEqual({'systematic-debugging', 'regression-testing', 'verification-before-completion', 'code-review'},
            {e['id'] for e in entries})
        for entry in entries:
            self.assertTrue(entry['description'].startswith('Use this skill when'))
            self.assertIn('## Example', entry['body'])
            self.assertFalse(entry['disabled'])

    def test_source_interface_prepares_content_without_activation(self):
        entries = builtin_entries()
        class Source:
            def load(self):
                return SkillPackage(tuple(entries), 'test', 'fixed')
        result = prepare_installation((), Source())
        self.assertEqual(4, len(result))
        entries[0]['body'] = 'Changed source after loading'
        self.assertNotEqual(entries[0]['body'], result[0]['body'])
        with self.assertRaisesRegex(ValueError, 'conflict'):
            prepare_installation(result, Source())

    def test_invalid_resources_and_undeclared_package_fields_fail(self):
        for references in ({'../escape.md': 'bad'}, {'scripts/runner.py': 'code'}, {'image.png': 'binary'}):
            entry = builtin_entries()[0]; entry['references'] = references
            with self.subTest(references=references), self.assertRaises(ValueError):
                validate_skills([entry])
        entry = builtin_entries()[0]; entry['tools'] = ['bash']
        with self.assertRaises(ValueError):
            validate_skills([entry])

    def test_dependencies_and_execution_metadata_require_a_supported_adapter(self):
        entries = builtin_entries()
        class Source:
            def load(self):
                return SkillPackage(tuple(entries), 'test', 'fixed', dependencies=('tool:bash',))
        with self.assertRaisesRegex(ValueError, 'dependencies'):
            prepare_installation((), Source())
        from fruitfly_agent.lab.context_manager.augmentation.skills.methods.indexed_documents.parser import Skill
        from fruitfly_agent.lab.context_manager.augmentation.skills.packages import package_entry
        skill = Skill('example', 'Read when relevant', 'Body', '/example', source_text=
            '---\nname: example\ndescription: Read when relevant\nallowed-tools: [bash]\n---\nBody')
        with self.assertRaisesRegex(ValueError, 'unsupported Skill metadata'):
            package_entry(skill, {}, 'test', 'fixed', 'MIT')
