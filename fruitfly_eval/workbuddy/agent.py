"""Official WorkBuddy user setup followed by ordinary frozen FruitFlyAgent execution."""
from typing import Any
from fruitfly_eval.bridges.harbor018 import NativeInstalledAgent018


class WorkBuddyFruitFlyAgent(NativeInstalledAgent018):
    async def install(self, environment: Any) -> None:
        from workbuddy_bench.agents._agent_user import ensure_agent_user  # type: ignore[import-not-found, import-untyped, unused-ignore]
        await ensure_agent_user(self, environment)
        await super().install(environment)
