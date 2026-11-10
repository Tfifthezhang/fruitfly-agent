"""Prepare owner component documents for ordinary saves without writing sources."""
from dataclasses import replace
from pathlib import Path
import yaml
from fruitfly_agent.lab.catalog import component_profile


def prepare_component_files(path, config, catalog, artifact_reader=None):
    """Return a referenced config and payloads; frozen exporters do not use this."""
    path = Path(path).resolve()
    payloads, profiles = {}, {}
    for key, profile in config.profiles.items():
        effective = component_profile(profile, catalog, artifact_reader=artifact_reader)
        authored = {d.id: d for d in profile.component_documents}
        documents = []
        for document in effective.component_documents:
            if document.reference.get('default') is True or 'file' in document.reference:
                documents.append(document)
                continue
            relative = Path('components') / path.stem / key / document.role / (document.id + '.yaml')
            previous = authored.get(document.id)
            if previous is not None and 'file' in previous.reference:
                relative = Path(previous.reference['file'])
            target = (path.parent / relative).resolve()
            text = yaml.safe_dump(document.to_dict(), sort_keys=False, allow_unicode=True).encode()
            # A pre-existing managed destination must belong to this input snapshot.
            known = {source.path for source in profile.source_files}
            if target.exists() and str(target) not in known and target.read_bytes() != text:
                raise ValueError('component destination already exists: ' + str(target))
            if target in payloads and payloads[target] != text:
                raise ValueError('conflicting component writers: ' + str(target))
            payloads[target] = text
            documents.append(replace(document, source=str(target), reference={'file': relative.as_posix()}))
        profiles[key] = replace(effective, component_documents=tuple(documents))
    return replace(config, profiles=profiles), payloads
