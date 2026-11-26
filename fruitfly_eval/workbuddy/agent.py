"""Official WorkBuddy user setup followed by ordinary frozen FruitFlyAgent execution."""
from typing import Any
from fruitfly_eval.harbor_agent import FruitFlyHarborAgent


class WorkBuddyFruitFlyAgent(FruitFlyHarborAgent):
    async def install(self, environment: Any) -> None:
        from workbuddy_bench.agents._agent_user import ensure_agent_user  # type: ignore[import-not-found, import-untyped, unused-ignore]
        await ensure_agent_user(self, environment)
        await super().install(environment)
        from fruitfly_eval.harbor.cache_access import configure
        await configure(environment, self.runtime_python, self.runtime_environment,
                        user=getattr(environment, 'default_user', None))
