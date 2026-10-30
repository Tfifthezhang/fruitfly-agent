"""Exercise installed runtime paths outside the source checkout, offline."""

import argparse
import asyncio
import io
import json
from pathlib import Path
import runpy
import subprocess
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import AsyncMock

import fruitfly_agent
import eval
from eval.installation import resolve_installation
from eval.harbor.material import source_snapshot
from fruitfly_agent.lab.context_manager.externalization.programmatic_context import (
    IpythonRuntime, SessionArtifactStore,
)
from fruitfly_agent.lab.improvement.assessment.scorers.policies import python_case, score_python
from fruitfly_agent.interactive import TerminalConfigurationFrontend
from fruitfly_agent.run import RunApplicationFactory
from fruitfly_agent.experiments.scaffolding import initialize_workspace
from fruitfly_agent.experiments.configuration import load_configuration
from fruitfly_agent.experiments.composition import prepare_experiment
from fruitfly_agent.providers.registry import load_model_specs


def check_model_setup(root: Path) -> None:
    """Exercise the shipped model wizard against a temporary workspace."""
    factory = RunApplicationFactory(cwd=root, environment={}, allow_incomplete=True)
    lines = iter(("1", "", "wheel-check", "offline-model", "", "8192", "1024", "", "", "", "2", "1"))
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
    assert factory.environment.get("OPENAI_API_KEY") == "offline-placeholder"
    assert (root / ".fruitfly/models.yaml").is_file()
    model = load_model_specs(root / '.fruitfly/models.yaml')['wheel-check']
    assert (model.provider.sdk, model.provider.protocol) == ('openai', 'responses')
    assert 'provider' not in model.to_dict()
    assert (root / ".fruitfly/secrets.env").stat().st_mode & 0o777 == 0o600
    assert not (root / "models.yaml").exists()
    assert not (root / ".env").exists()


def check_frozen_runtime(source: Path) -> None:
    """Import only the frozen Agent and read its actual runtime resources."""
    code = '''
import sys
from pathlib import Path
source = Path(sys.argv[1])
sys.path.insert(0, str(source))
import fruitfly_agent.providers as providers
assert Path(providers.__file__).is_relative_to(source)
from fruitfly_agent.providers.services import builtin_services
assert any(service.id == 'deepseek' for service in builtin_services())
from fruitfly_agent.experiments.scaffolding import workspace_templates
assert 'default-config.yaml' in workspace_templates()
from fruitfly_agent.run import main
sys.argv = ['fruitfly-agent', '--help']
main()
'''
    result = subprocess.run([sys.executable, '-I', '-B', '-c', code, str(source)],
        cwd=source.parent, capture_output=True, text=True, timeout=30)
    if result.returncode:
        raise RuntimeError('frozen Agent check failed:\n' + result.stderr)


async def check(wheel: Path) -> None:
    from eval.harbor_agent import FruitFlyHarborAgent
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
        check_model_setup(root)
        # Resources must work from the installed wheel, without reading examples/.
        experiment = root / 'experiment'
        experiment.mkdir()
        initialize_workspace(experiment)
        prepared = prepare_experiment(load_configuration(experiment), 'improvement',
            environment={'DEEPSEEK_API_KEY': 'offline-placeholder'})
        assert prepared.model_roles['executor'] == 'deepseek-flash-openai'
        benchmark = root / 'benchmark'
        benchmark.mkdir()
        initialize_workspace(benchmark, source='task-set', benchmark='terminal-bench-4')
        assert (benchmark / '.fruitfly/eval-host.yaml').is_file()
        agent = FruitFlyHarborAgent.__new__(FruitFlyHarborAgent)
        package = resolve_installation(str(wheel), checkout=root)
        identity = source_snapshot(package, root / "source")
        assert (root / "source/eval/harbor/supervisor.py").is_file()
        check_frozen_runtime(root / 'source')
        installation = root / "prepared-installation"
        installation.mkdir()
        agent.config_path = installation / "config.yaml"
        agent.model_catalog_path = installation / "models.yaml"
        agent.config_path.write_text("offline configuration", encoding="utf-8")
        agent.model_catalog_path.write_text("offline catalog", encoding="utf-8")
        agent.exec_as_root = AsyncMock()
        agent.exec_as_agent = AsyncMock()
        (installation / "preparation.json").write_text(json.dumps({"runtime": {
            "python": "/opt/runtime/bin/python", "environment": {}, "installation": identity,
        }}), encoding="utf-8")
        environment = SimpleNamespace(
            exec=AsyncMock(return_value=SimpleNamespace(return_code=0)),
            upload_dir=AsyncMock(), upload_file=AsyncMock(),
        )
        await agent.install(environment)
        environment.upload_file.assert_any_await(installation / "config.yaml", "/installed-agent/fruitfly/runtime/config.yaml")
        environment.upload_dir.assert_not_called()
        assert "pip" not in agent.exec_as_root.call_args.kwargs["command"]
    print("Installed model wizard, experiment templates, extension, function worker, IPython, and prepared Eval checks passed.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wheel", type=Path)
    asyncio.run(check(parser.parse_args().wheel))
