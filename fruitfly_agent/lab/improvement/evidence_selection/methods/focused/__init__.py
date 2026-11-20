"""Material-only selection for an already composed feedback group."""
from fruitfly_agent.improvement.contracts.versions import canonical_json, content_hash
from ...configuration import MATERIAL_POLICIES, OPTIONAL_CATEGORIES


def trajectory_material(resource):
    return not resource.path.startswith('originals/') and (
        resource.kind == 'trajectory' or '/interaction-bodies/' in resource.path
        or resource.path in {'evidence/events.json', 'evidence/sources.json'})


class FocusedGroupSelector:
    implementation_id = 'focused-group-material-v1'
    _diagnostics = frozenset({'execution-facts.json', 'operations.json', 'termination.json',
        'final-answer.json', 'task.json', 'model-usage.json', 'process.json', 'trajectory-status.json',
        'overview.json', 'coverage.json', 'sources.json', 'events.json', 'history.json', 'outcome.json',
        'capture-manifest.json', 'reading-scope.json'})

    _categories = {
        'outputs': {'final-answer.json'},
        'termination': {'termination.json', 'outcome.json', 'process.json'},
        'usage': {'model-usage.json', 'execution-facts.json'},
        'capture': {'capture-manifest.json', 'reading-scope.json', 'coverage.json'},
    }

    def __init__(self, material_policy, optional_categories=(), *, bounded=True):
        if material_policy not in MATERIAL_POLICIES:
            raise ValueError('unknown group material policy')
        if any(category not in OPTIONAL_CATEGORIES for category in optional_categories):
            raise ValueError('unknown optional evidence category')
        self.bounded = bounded
        self.material_policy = material_policy
        self.optional_categories = tuple(sorted(set(optional_categories)))

    @property
    def identity(self):
        return content_hash(canonical_json([self.implementation_id, self.material_policy, self.optional_categories, self.bounded]))

    def select(self, summaries, *, resources):
        selected = []
        for row in summaries:
            run_id = row['run_id']
            granted = resources[run_id]
            reasons = {}
            for item in granted:
                name = item.path.rsplit('/', 1)[-1]
                categories = [category for category in self.optional_categories
                              if name in self._categories[category]
                              or category == 'outputs' and item.kind == 'deliverable']
                if trajectory_material(item):
                    categories.append('trajectory')
                elif self.material_policy == 'all-granted':
                    categories.append('all-granted')
                elif self.material_policy == 'focused' and (item.kind == 'deliverable' or name in self._diagnostics):
                    categories.append('focused')
                if categories:
                    reasons[item.path] = categories
            selected.append({'run_id': run_id, 'task_id': row['task_id'],
                             'reasons': ['member_material_policy'], 'material_paths': list(reasons), 'material_reasons': reasons,
                             'omitted_materials': len(granted) - len(reasons)})
        return {'selector_id': self.identity, 'implementation_id': self.implementation_id,
                'settings': {'material_policy': self.material_policy, 'optional_categories': self.optional_categories}, 'selected': selected,
                'bounded': self.bounded, 'total_executions': len(summaries), 'omitted_executions': 0}
