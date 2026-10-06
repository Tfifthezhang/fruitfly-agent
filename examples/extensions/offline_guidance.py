"""Register a context mechanism and run it through the Application, offline."""
from __future__ import annotations

import asyncio
from dataclasses import replace
from pathlib import Path
import tempfile

from fruitfly_agent.core import AssistantMessage, TextBlock
from fruitfly_agent.core.context import ContextStage, ContextTransform
from fruitfly_agent.core.model_stream import AssistantMessageEventStream, StreamDone
from fruitfly_agent.interactive import AgentApplication
from fruitfly_agent.lab.catalog import (
    MechanismContribution, MechanismDefinition, MechanismDescriptor,
    MechanismSelection, builtin_catalog,
)
from fruitfly_agent.providers import ProviderRegistry
from fruitfly_agent.run.application import RunApplicationFactory
from fruitfly_agent.run.configuration import HarnessConfig, HarnessProfile, save_harness_config


GUIDANCE = '<example-guidance>Answer with a short, concrete sentence.</example-guidance>'


class ExampleGuidance:
    """Transform a request projection without changing canonical messages."""

    def transform(self, frame):
        if GUIDANCE in frame.system_prompt:
            return None
        return ContextTransform(replace(
            frame, system_prompt=frame.system_prompt + '\n\n' + GUIDANCE
        ))


def install_guidance(state, context, parameters):
    return state.with_context_stage(ContextStage(
        'example-guidance.augmentation', 'augmentation', ExampleGuidance()
    ))


def example_definition():
    return MechanismDefinition(
        descriptor=MechanismDescriptor(
            mechanism_id='example-guidance',
            label='Example guidance',
            description='Add short-answer guidance before each model request.',
            contributions=(MechanismContribution('online', 'context', 'augmentation'),),
        ),
        install=install_guidance,
        implementation_id='example-guidance-v1',
    )


class OfflineProvider:
    """A deterministic Provider; it does not evaluate model quality."""

    def __call__(self, view, *, signal=None):
        async def events():
            if signal is not None and signal.is_set():
                raise asyncio.CancelledError
            if GUIDANCE not in view.system_prompt:
                raise RuntimeError('The registered mechanism did not reach the Provider.')
            yield StreamDone(AssistantMessage(content=[TextBlock(
                'Offline response: example-guidance is active.'
            )]))
        return AssistantMessageEventStream(events())


async def run_demo():
    # All configuration/session files are isolated and removed on exit.
    with tempfile.TemporaryDirectory(prefix='fruitfly-example-') as directory:
        workspace = Path(directory)
        (workspace / 'models.yaml').write_text(
            'models:\n  offline:\n    provider: offline\n    model: offline-example\n'
            '    api_key_env: OFFLINE_KEY\n    context_window: 4096\n', encoding='utf-8'
        )
        save_harness_config(workspace / '.fruitfly/config.yaml', HarnessConfig(
            default_profile='default', profiles={'default': HarnessProfile(
                'default', model_catalog='../models.yaml', model_profile='offline',
                mechanisms=(MechanismSelection('example-guidance'),),
            )},
        ))
        registry = ProviderRegistry()
        registry.register('offline', lambda spec, key: OfflineProvider())
        factory = RunApplicationFactory(
            cwd=workspace, environment={'OFFLINE_KEY': 'offline-placeholder'},
            catalog=builtin_catalog().extended((example_definition(),)),
            provider_registry=registry,
        )
        application = AgentApplication(factory)
        try:
            await application.start()
            result = await application.submit('Demonstrate the registered guidance.')
            if result.is_error:
                raise RuntimeError('Offline example failed.')
            return result.messages[-1].text
        finally:
            await application.close()


if __name__ == '__main__':
    print(asyncio.run(run_demo()))
