"""Exercise installed runtime paths outside the source checkout, offline."""

import argparse
import asyncio
import io
from pathlib import Path
import runpy
import tempfile
from types import SimpleNamespace
from unittest.mock import AsyncMock

import fruitfly_agent
import eval
from eval.harbor_agent import FruitFlyHarborAgent
from eval.installation import resolve_installation
from fruitfly_agent.lab.context_manager.externalization.programmatic_context import (
    IpythonRuntime, SessionArtifactStore,
)
from fruitfly_agent.lab.optimization.scoring import python_case, score_python
from fruitfly_agent.interactive import TerminalConfigurationFrontend
from fruitfly_agent.run import RunApplicationFactory


async def check(wheel: Path) -> None:
    checkout = Path(__file__).resolve().parents[2]
    for module in (fruitfly_agent, eval):
        if Path(module.__file__).resolve().is_relative_to(checkout):
            raise RuntimeError("check must import the installed wheel outside the checkout")
    example = runpy.run_path(str(checkout / "examples/extensions/offline_guidance.py"))
    assert await example["run_demo"]() == "Offline response: example-guidance is active."
    case = python_case({"input": "Increment", "entry_point": "f", "tests": [
        {"args": [2], "expected": 3},
    ]})
    assert (await score_python("def f(x):\n    return x + 1", case)).score == 1.0
    with tempfile.TemporaryDirectory(prefix="fruitfly-wheel-check-") as directory:
        root = Path(directory)

        async def host_handler(*args):
            raise AssertionError("no model queries in installed checks")

        runtime = IpythonRuntime(
            cwd=root, artifact_store=SessionArtifactStore(root / "artifacts", max_artifact_bytes=10000),
            host_handler=host_handler, max_output_chars=1000, timeout_seconds=10,
        )
        try:
            assert (await runtime.execute("value = 40")).status == "ok"
            assert (await runtime.execute("value + 2")).result == "42"
        finally:
            await runtime.close()
        factory = RunApplicationFactory(cwd=root, environment={}, allow_incomplete=True)
        lines = iter(("1", "wheel-check", "offline-model", "", "8192", "1024", "", "", "2", "1"))
        output = io.StringIO()
        frontend = TerminalConfigurationFrontend(
            factory.configuration, input_stream=io.StringIO("offline-placeholder\n"),
            output_stream=output, line_editor=SimpleNamespace(read_line=lambda: next(lines)),
        )
        launch = frontend.run()
        assert launch.start and launch.saved
        assert "offline-placeholder" not in output.getvalue()
        factory.reload_configuration()
        assert factory.selection.profile.model_profile == "wheel-check"
        assert factory.environment.get("FRUITFLY_MODEL_WHEEL_CHECK_API_KEY") == "offline-placeholder"
        assert (root / ".fruitfly/models.yaml").is_file()
        assert (root / ".fruitfly/secrets.env").stat().st_mode & 0o777 == 0o600
        assert not (root / "models.yaml").exists()
        assert not (root / ".env").exists()
        agent = FruitFlyHarborAgent.__new__(FruitFlyHarborAgent)
        agent.source_root = resolve_installation(str(wheel), checkout=root)
        agent.config_path = root / "config.yaml"
        agent.model_catalog_path = root / "models.yaml"
        agent.config_path.write_text("offline configuration", encoding="utf-8")
        agent.model_catalog_path.write_text("offline catalog", encoding="utf-8")
        agent.exec_as_root = AsyncMock()
        environment = SimpleNamespace(
            exec=AsyncMock(return_value=SimpleNamespace(return_code=0)),
            upload_dir=AsyncMock(), upload_file=AsyncMock(),
        )
        await agent.install(environment)
        environment.upload_file.assert_any_await(
            wheel.resolve(), "/installed-agent/fruitfly/source/" + wheel.name,
        )
        assert wheel.name in agent.exec_as_root.call_args.kwargs["command"]
    print("Installed model wizard, extension, function worker, IPython, and Eval installation checks passed.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wheel", type=Path)
    asyncio.run(check(parser.parse_args().wheel))
