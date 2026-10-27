"""Export a selected system as a complete component bundle, with explicit writes."""
import argparse
from pathlib import Path
import shutil

from fruitfly_agent.lab.catalog import load_system_config, materialize_system, configuration_resources, builtin_catalog
from .inspection import inspect_configuration


def export_configuration(source, destination, *, profile_id=None, workspace=None, apply=False):
    source, destination = Path(source).resolve(), Path(destination).absolute()
    inspect_configuration(source, profile_id=profile_id)
    profile = load_system_config(source).select(profile_id)
    if destination.exists() or destination.is_symlink():
        raise ValueError('configuration destination already exists: ' + str(destination))
    if any(parent.is_symlink() for parent in destination.parents):
        raise ValueError('configuration destination must not traverse symlinks')
    catalog_path = Path(profile.model_catalog)
    catalog_path = catalog_path if catalog_path.is_absolute() else source.parent / catalog_path
    root = Path(workspace).resolve() if workspace else source.parent.parent
    resources = configuration_resources(profile, builtin_catalog(), root)
    def read(reference):
        return (root / '.fruitfly/artifacts' / reference[7:]).read_text(encoding='utf-8')
    result = {'source': str(source), 'profile': profile.profile_id, 'destination': str(destination),
              'status': 'preview',
              'resources': [{'path': entry.path, 'content_hash': entry.digest} for entry in resources]}
    if apply:
        destination.mkdir(parents=True)
        try:
            materialize_system(profile, destination / 'config.yaml', artifact_reader=read,
                model_source=catalog_path, resources=resources)
            inspect_configuration(destination / 'config.yaml')
        except BaseException:
            # The destination was exclusively created by this operation.
            shutil.rmtree(destination)
            raise
        result['status'] = 'written'
    return result


def main():
    import json
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--profile')
    parser.add_argument('--cwd', type=Path)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    try:
        print(json.dumps(export_configuration(args.config, args.output, profile_id=args.profile,
            workspace=args.cwd, apply=args.apply), indent=2))
    except (ValueError, OSError) as exc:
        parser.exit(2, 'error: ' + str(exc) + '\n')


if __name__ == '__main__':
    main()
