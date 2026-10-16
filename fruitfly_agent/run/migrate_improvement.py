"""Explicit offline namespace migration; immutable evidence bytes are preserved."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import tempfile
from uuid import uuid4

from .configuration.persistence import write_bytes
from fruitfly_agent.lab.catalog import migrate_legacy_improvement_config_text, migrate_legacy_improvement_candidate



def migrate_improvement(workspace: Path, *, apply=False):
    workspace = workspace.resolve()
    root = workspace / '.fruitfly'
    old, new, config = root / 'optimization', root / 'improvement', root / 'config.yaml'
    if root.is_symlink() or config.is_symlink() or old.is_symlink() or new.is_symlink():
        raise ValueError('migration paths must not be symlinks')
    if old.exists() and new.exists():
        raise ValueError('both old and new data directories exist; resolve the conflict explicitly')
    if old.exists():
        if not old.is_dir() or any(p.is_symlink() for p in old.rglob('*')):
            raise ValueError('legacy data must be a directory without symlinks')
    original = config.read_bytes() if config.exists() else None
    updated = None
    if original is not None:
        migrated = migrate_legacy_improvement_config_text(original)
        if migrated != original:
            updated = migrated
    # Validate candidate records before touching any source files.
    replacements = {}
    if old.exists():
        for path in (old / 'candidates').glob('*.json'):
            row = json.loads(path.read_text())
            row = migrate_legacy_improvement_candidate(row)
            row['evidence'] = [[label, value.replace('.fruitfly/optimization/', '.fruitfly/improvement/')
                if label in {'Task snapshot', 'Search history', 'Experiment', 'Original task source'} else value]
                for label, value in row.get('evidence', ())]
            if row.get('status') in {'proposed', 'reviewed', 'deferred', 'selected_for_next_session'}:
                row['status'] = 'stale'
            replacements[path.relative_to(old)] = json.dumps(row, ensure_ascii=False, sort_keys=True).encode()
    result: dict[str, object] = {'data_directory': old.exists(), 'configuration': updated is not None,
              'candidates': len(replacements), 'applied': False}
    if not apply or not (old.exists() or updated is not None):
        return result
    root.mkdir(parents=True, exist_ok=True)
    backup = root / 'migration-backups' / ('improvement-' + uuid4().hex)
    if (root / 'migration-backups').is_symlink():
        raise ValueError('migration backup must not be a symlink')
    stage = Path(tempfile.mkdtemp(prefix='.improvement-', dir=root))
    moved = False
    try:
        if old.exists():
            shutil.copytree(old, stage / 'data')
            for relative, payload in replacements.items():
                (stage / 'data' / relative).write_bytes(payload)
        if config.exists() and config.read_bytes() != original:
            raise ValueError('configuration changed during migration')
        backup.mkdir(parents=True, exist_ok=False)
        if original is not None:
            (backup / 'config.yaml').write_bytes(original)
        if old.exists():
            old.rename(backup / 'optimization')
            moved = True
            (stage / 'data').rename(new)
        if updated is not None:
            write_bytes(config, updated)
        result.update(applied=True, backup=str(backup.relative_to(workspace)))
        return result
    except BaseException:
        if moved:
            if new.exists():
                new.rename(stage / 'failed-data')
            (backup / 'optimization').rename(old)
        if original is not None and config.exists() and config.read_bytes() != original:
            write_bytes(config, original)
        raise
    finally:
        shutil.rmtree(stage)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', type=Path, default=Path.cwd())
    parser.add_argument('--apply', action='store_true', help='Apply after validation; default only previews changes.')
    args = parser.parse_args()
    print(json.dumps(migrate_improvement(args.workspace, apply=args.apply), ensure_ascii=False))


if __name__ == '__main__':
    main()
