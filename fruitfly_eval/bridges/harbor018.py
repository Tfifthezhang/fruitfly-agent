"""Harbor 0.18 installed-agent execution using the shared native runtime bridge."""
from __future__ import annotations

import shlex
from typing import Any
from fruitfly_eval.harbor_agent import FruitFlyHarborAgent


class NativeInstalledAgent018(FruitFlyHarborAgent):
    SUPPORTS_ATIF = True

    async def _exec(self, environment: Any, command: str, user: str | int | None = None,
                    env: dict[str, str] | None = None, cwd: str | None = None,
                    timeout_sec: int | None = None) -> Any:
        # Use the public environment port: 0.18 has no required redaction hook.
        # Commands never receive secret values as arguments. Do not echo env.
        if user == 'root':
            command = ('set -o pipefail; mkdir -p /logs/agent && { ' + command
                       + '; } 2>&1 | tee -a /logs/agent/setup.log')
        else:
            command = 'set -o pipefail; ' + command
        result = await environment.exec(command=command, user=user, env=env, cwd=cwd, timeout_sec=timeout_sec)
        if result.return_code:
            raise RuntimeError('native Agent command failed with exit ' + str(result.return_code)
                               + '; inspect retained Agent logs')
        return result
