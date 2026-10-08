"""Reviewed extension call signatures, including defaults and async semantics.

These literals are not regenerated from production. A failure is a contract
change to review, never a reason to refresh expected values automatically.
"""
import inspect
import unittest
from fruitfly_agent.core import run_agent_loop
from fruitfly_agent.core.extensions.protocols import Provider
from fruitfly_agent.core.env.protocols import Shell
from fruitfly_agent.interactive.application import RuntimeFactory, AgentApplication
from fruitfly_agent.lab.catalog import assemble_lab, LabCatalog
from fruitfly_agent.lab.optimization.text_optimizer import TextOptimizer
from fruitfly_agent.run import build_runtime


SIGNATURES = (
    (run_agent_loop, "(config: 'AgentLoopConfig', messages: 'list[AgentMessage]', *, signal: 'asyncio.Event | None' = None, context_pipeline: 'ContextPipeline | ContextReducer | None' = None) -> 'AgentLoopResult'", True),
    (Provider.__call__, "(self, view: 'ProviderView', *, signal: 'asyncio.Event | None' = None) -> 'AssistantMessageEventStream'", False),
    (Shell.exec, "(self, command: 'str', options: 'ExecOptions | None' = None) -> 'Result[ExecResult]'", True),
    (RuntimeFactory.open, "(self, *, resume: 'bool', session_path: 'Path | None') -> 'RuntimeHandle'", True),
    (LabCatalog.resolve, "(self, selections: 'Sequence[MechanismSelection]') -> 'tuple[ResolvedMechanism, ...]'", False),
    (assemble_lab, "(base_config: 'AgentLoopConfig', *, catalog: 'LabCatalog', selections: 'tuple[MechanismSelection, ...]', context: 'AssemblyContext') -> 'AssemblyResult'", False),
    (build_runtime, "(profile: 'HarnessProfile', *, config_path: 'Path', catalog: 'LabCatalog', environment: 'Mapping[str, str]', session: 'Session', cwd: 'Path', provider_registry: 'ProviderRegistry | None' = None, resource_sink: 'list[Any] | None' = None, artifact_store: 'DataArtifactStore | None' = None, artifact_bindings: 'Mapping[str, str] | None' = None, task_pack_sources: 'tuple' = (), permission_policy: 'PermissionPolicy | None' = None) -> 'RuntimeAssembly'", False),
    (AgentApplication.start, "(self, *, resume: 'bool' = False, session_path: 'Path | None' = None) -> 'None'", True),
    (AgentApplication.activate_runtime, "(self, candidate: 'RuntimeHandle', *, expected_manifest_digest: 'str') -> 'None'", True),
    (TextOptimizer.preview, "(self, *, task=None) -> fruitfly_agent.lab.optimization.text_optimizer.SearchPreview", False),
    (TextOptimizer.search, "(self, prompt: str, direction: str, *, parent_manifest: str, task=None) -> tuple[fruitfly_agent.lab.optimization.text_optimizer.TextProposal, ...]", True),
    (TextOptimizer.cancel, "(self) -> bool", False),
)


class SignatureTests(unittest.TestCase):
    def test_extension_signatures_and_async_semantics_are_fixed(self):
        for function, signature, asynchronous in SIGNATURES:
            with self.subTest(api=function.__qualname__):
                self.assertEqual(signature, str(inspect.signature(function)),
                                 'Public call contract drift: fix the implementation first; do not refresh signature baselines without explicit authorization.')
                self.assertEqual(asynchronous, inspect.iscoroutinefunction(function))
