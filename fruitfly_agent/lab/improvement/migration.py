"""Validate legacy mechanism parameters and target attribution offline."""
import json
import yaml


def migrate_legacy_improvement_config_text(original):
    """Edit only affected YAML scalars; preserve comments and unrelated bytes."""
    text = original.decode('utf-8')
    expected = migrate_legacy_improvement_config(yaml.safe_load(text))
    root = yaml.compose(text)
    profiles = next(value for key, value in root.value if key.value == 'profiles')
    edits = []
    for _, profile in profiles.value:
        selections = next((value for key, value in profile.value if key.value == 'mechanisms'), None)
        if selections is None:
            continue
        for selection in selections.value:
            fields = {key.value: value for key, value in selection.value}
            if fields['id'].value != 'opro' or 'parameters' not in fields:
                continue
            for key, value in fields['parameters'].value:
                if key.value == 'optimizer_profile':
                    encoded = text[key.start_mark.index:key.end_mark.index].replace('optimizer_profile', 'improver_profile')
                    edits.append((key.start_mark.index, key.end_mark.index, encoded))
                if key.value == 'cases_path' and '.fruitfly/optimization/' in value.value:
                    encoded = json.dumps(value.value.replace('.fruitfly/optimization/', '.fruitfly/improvement/'))
                    edits.append((value.start_mark.index, value.end_mark.index, encoded))
    for start, end, value in sorted(edits, reverse=True):
        text = text[:start] + value + text[end:]
    if yaml.safe_load(text) != expected:
        raise ValueError('cannot safely preserve this configuration; update its legacy parameters explicitly')
    return text.encode('utf-8')


def migrate_legacy_improvement_config(data):
    if not isinstance(data, dict) or data.get('schema_version') != 1:
        raise ValueError('migration requires a schema-1 harness configuration')
    for profile in data.get('profiles', {}).values():
        for selection in profile.get('mechanisms', []):
            if selection['id'] == 'opro':
                parameters = selection.get('parameters', {})
                if 'optimizer_profile' in parameters:
                    if 'improver_profile' in parameters:
                        raise ValueError('both old and new model role parameters exist')
                    parameters['improver_profile'] = parameters.pop('optimizer_profile')
                path = parameters.get('cases_path')
                if isinstance(path, str):
                    parameters['cases_path'] = path.replace('.fruitfly/optimization/', '.fruitfly/improvement/')
    return data



def migrate_legacy_improvement_candidate(row):
    if 'role' not in row:
        if row.get('target') not in {'base_prompt', 'skill-catalog.guidance'}:
            raise ValueError('legacy candidate needs an explicit H/S/I classification')
        row['role'] = 'H'
    if row['role'] not in {'H', 'S', 'I'}:
        raise ValueError('invalid legacy candidate role')
    return row
