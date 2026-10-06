"""Execute the workflow's built-in prompt smoke check offline."""

import shlex
import subprocess
import sys
import unittest

import yaml

from tests.architecture.checks import ROOT


class WorkflowSmokeTest(unittest.TestCase):
    def test_packaged_prompt_check_matches_available_builtins(self):
        workflow = yaml.safe_load(
            (ROOT / ".github/workflows/tests.yml").read_text(encoding="utf-8")
        )
        commands = []
        for step in workflow["jobs"]["package"]["steps"]:
            for line in step.get("run", "").splitlines():
                if "from fruitfly_agent.lab.base_prompt import builtins" in line:
                    commands.append(shlex.split(line))
        self.assertEqual(1, len(commands), "Keep the installed built-in prompt smoke check")
        command = commands[0]
        self.assertEqual("-c", command[1])
        result = subprocess.run(
            [sys.executable, *command[1:]],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
