"""Developer test selection; mandatory guards precede selected behavior tests."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
GUARDS = ('architecture', 'contracts')
AREAS = (*GUARDS, 'core', 'providers', 'lab', 'interactive', 'run', 'workflows', 'eval')


def cases(suite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from cases(item)
        else:
            yield item


def select_suites(areas=(), modules=()):
    """Return guard/behavior suites with unique IDs; no online smoke selection."""
    if any(area not in AREAS for area in areas):
        raise ValueError('unknown test area; use --help')
    for name in modules:
        parts = name.split('.')
        if len(parts) < 3 or parts[0] != 'tests' or parts[1] not in AREAS or not parts[2].startswith('test_'):
            raise ValueError('module must name an offline tests.<area>.test_* module or case')
    selected = list(dict.fromkeys((*GUARDS, *(areas or (() if modules else AREAS)))))
    loader = unittest.TestLoader()
    candidates = [(area, loader.discover(str(ROOT / 'tests' / area), top_level_dir=str(ROOT))) for area in selected]
    candidates.extend((name.split('.')[1], loader.loadTestsFromName(name)) for name in modules)
    guards, behavior, seen = [], [], set()
    for area, suite in candidates:
        for case in cases(suite):
            if case.id() in seen:
                continue
            seen.add(case.id())
            target = guards if area in GUARDS else behavior
            target.append(case)
    return unittest.TestSuite(guards), unittest.TestSuite(behavior)


def main(argv=None):
    parser = argparse.ArgumentParser(description='Offline development checks; run architecture and contract guards first and stop on failure.')
    parser.add_argument('--area', choices=AREAS, action='append', default=[], help='Repeatable; defaults to the complete suite')
    parser.add_argument('--module', action='append', default=[], help='Offline test module or individual test; guard checks are always included')
    parser.add_argument('--list', action='store_true', help='List selected tests without executing test methods')
    parser.add_argument('-v', '--verbose', action='store_true')
    args = parser.parse_args(argv)
    try:
        guards, behavior = select_suites(args.area, args.module)
    except ValueError as error:
        parser.error(str(error))
    if args.list:
        for case in (*cases(guards), *cases(behavior)):
            print(case.id())
        return 0
    runner = unittest.TextTestRunner(verbosity=2 if args.verbose else 1)
    print('Architecture and contract checks: fix implementation failures; do not automatically update contract baselines.', file=sys.stderr)
    result = runner.run(guards)
    if not result.wasSuccessful():
        return 1
    if behavior.countTestCases():
        result = runner.run(behavior)
    return 0 if result.wasSuccessful() else 1
