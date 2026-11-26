"""Installed controller identity does not depend on source-tree metadata discovery."""
import unittest
from unittest.mock import patch
from fruitfly_eval.harbor.controller import environment_snapshot


class ControllerIdentityTests(unittest.TestCase):
    def test_explicit_installation_scope_is_forwarded_without_disabling_dependency_checks(self):
        with patch('fruitfly_eval.harbor.controller.metadata.distributions', return_value=[]) as distributions:
            result = environment_snapshot(distribution_paths=['/owned/site-packages'])
        distributions.assert_called_once_with(path=['/owned/site-packages'])
        self.assertEqual(result['packages'], {})
