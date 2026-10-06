"""Important module documentation and local navigation remain available."""
import re
import tomllib
import unittest
from urllib.parse import unquote
from tests.architecture.checks import ROOT, DOCUMENTED_ROOTS

def documents():
    paths = list(ROOT.glob('*.md'))
    for root in (*DOCUMENTED_ROOTS, ROOT / 'examples'):
        paths.extend(root.rglob('*.md'))
    return sorted(set(paths))


def local_links(path):
    for target in re.findall(r'\]\(([^)]+)\)', path.read_text(encoding='utf-8')):
        if '://' not in target and not target.startswith('mailto:'):
            file, _, fragment = target.partition('#')
            yield (path.parent / unquote(file)).resolve() if file else path, unquote(fragment)


def heading_ids(path):
    ids = set()
    counts = {}
    fenced = False
    for line in path.read_text(encoding='utf-8').splitlines():
        if line.startswith('```'):
            fenced = not fenced
        if fenced:
            continue
        heading = re.match(r'^#{1,6}\s+(.+)', line)
        if heading:
            slug = re.sub(r'[^\w\- ]', '', heading[1].lower()).replace(' ', '-')
            count = counts.get(slug, 0)
            counts[slug] = count + 1
            ids.add(slug if not count else f'{slug}-{count}')
    return ids


class DocumentationTest(unittest.TestCase):
    def test_important_modules_have_readme(self) -> None:
        missing: list[str] = []
        parents = (*DOCUMENTED_ROOTS, ROOT / 'fruitfly_agent/core',
                   ROOT / 'fruitfly_agent/lab', ROOT / 'fruitfly_agent/lab/context_manager')
        for root in parents:
            directories = [root, *(path for path in root.iterdir() if path.is_dir()
                                   and path.name != '__pycache__' and not path.name.startswith('.'))]
            missing.extend(
                str(path.relative_to(ROOT))
                for path in directories
                if not (path / "README.md").is_file()
            )
        self.assertEqual([], sorted(missing))

    def test_relative_documentation_links_have_existing_files(self):
        missing = []
        for path in documents():
            for target in re.findall(r'\]\(([^)]+)\)', path.read_text(encoding='utf-8')):
                target = target.split('#', 1)[0]
                if not target or '://' in target or target.startswith('mailto:'):
                    continue
                if not (path.parent / target).exists():
                    missing.append(f'{path.relative_to(ROOT)}: {target}')
        self.assertEqual([], missing)

    def test_local_heading_links_resolve(self):
        missing = []
        for path in documents():
            for target, fragment in local_links(path):
                if fragment and target.suffix == '.md' and target.is_file():
                    if fragment not in heading_ids(target):
                        missing.append(f'{path.relative_to(ROOT)}: {target.relative_to(ROOT)}#{fragment}')
        self.assertEqual([], missing)

    def test_every_guide_is_reachable_from_root(self):
        guides = set(documents())
        reached = set()
        pending = [ROOT / 'README.md']
        while pending:
            path = pending.pop()
            if path in reached:
                continue
            reached.add(path)
            pending.extend(target for target, _ in local_links(path)
                           if target in guides and target not in reached)
        self.assertEqual([], sorted(str(path.relative_to(ROOT)) for path in guides - reached))

    def test_parent_readmes_and_backlinks_form_navigation_tree(self):
        for path in documents():
            if path == ROOT / 'README.md':
                continue
            ancestor = path.parent if path.name != 'README.md' else path.parent.parent
            while not (ancestor / 'README.md').is_file() and ancestor != ROOT:
                ancestor = ancestor.parent
            parent = ancestor / 'README.md'
            with self.subTest(path=str(path.relative_to(ROOT))):
                self.assertIn(parent, {target for target, _ in local_links(path)})
                self.assertIn(path, {target for target, _ in local_links(parent)})

    def test_documentation_is_english(self):
        non_english = [str(path.relative_to(ROOT)) for path in documents()
                       if re.search(r'[\u3400-\u4dbf\u4e00-\u9fff]', path.read_text(encoding='utf-8'))]
        self.assertEqual([], non_english)

    def test_lower_level_files_use_project_identity(self):
        upstream = re.compile(r'\bp' r'i\b', re.I)
        matches = []
        for root in (*DOCUMENTED_ROOTS, ROOT / 'examples'):
            for path in root.rglob('*'):
                if path.suffix in ('.py', '.md') and upstream.search(path.read_text(encoding='utf-8')):
                    matches.append(str(path.relative_to(ROOT)))
        self.assertEqual([], matches)

    def test_project_version_matches_documentation(self):
        metadata = tomllib.loads((ROOT / 'pyproject.toml').read_text(encoding='utf-8'))
        self.assertEqual('0.1', metadata['project']['version'])
        self.assertIn('| Version | 0.1 |', (ROOT / 'README.md').read_text(encoding='utf-8'))
