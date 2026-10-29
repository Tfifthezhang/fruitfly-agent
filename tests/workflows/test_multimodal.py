"""Complete offline attachment, media saving, queueing and recovery paths."""
import asyncio
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from fruitfly_agent.core.config import AgentLoopConfig
from fruitfly_agent.core.data_model import UserMessage, TextBlock, ImageBlock
from fruitfly_agent.core.session import Session
from fruitfly_agent.core.tool_runtime import ToolCallContext
from fruitfly_agent.interactive import AgentApplication, InteractiveSession, TerminalFrontend
from fruitfly_agent.lab.environment import LocalEnv
from fruitfly_agent.lab.tools.read import create_read_tool
from fruitfly_agent.lab.tools.media import create_save_media_tool
from fruitfly_agent.run import RunApplicationFactory
from fruitfly_agent.run.runtime.media import load_image
from fruitfly_agent.run.storage.artifacts import DataArtifactStore
from fruitfly_agent.run.storage.media import SessionMedia
from fruitfly_agent.run.cli import run_cli, create_parser
from tests.support.application import _Factory
from tests.support.faux_provider import FauxProvider
from tests.support.media import image, png_bytes, write_models


class MultimodalTests(unittest.IsolatedAsyncioTestCase):
    async def test_attach_send_save_and_resume_use_frozen_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_models(root)
            path = root / 'image with spaces.png'
            path.write_bytes(png_bytes())
            provider = FauxProvider()
            provider.respond_text('seen')
            registry = Mock(create=Mock(return_value=provider))
            factory = RunApplicationFactory(cwd=root, environment={}, provider_registry=registry)
            factory.configuration.set_mechanism('save-media-tool', enabled=True)
            factory.configuration.save()
            factory.reload_configuration()
            app = AgentApplication(factory)
            await app.start()
            session_path = Path(app.status.session_path)
            try:
                attached = app.load_attachment(path.name)
                path.write_text('changed after selection')
                await app.submit([TextBlock('inspect'), attached])
                message = provider.calls[-1]['messages'][0]
                self.assertEqual(message.content[1], image())
                resource = next(b.text.split('Media resource: ')[1] for b in message.content
                                if isinstance(b, TextBlock) and b.text.startswith('Media resource: '))
                provider.respond_tool_call('save_media', {'resource_id': resource, 'path': 'copy.png'})
                provider.respond_text('saved')
                await app.submit('save a copy')
                self.assertEqual((root / 'copy.png').read_bytes(), png_bytes())
                await app.close()
                await app.start(resume=True, session_path=session_path)
                provider.respond_text('continued')
                await app.submit('continue')
                self.assertTrue(any(isinstance(b, ImageBlock) for m in provider.calls[-1]['messages']
                                    if isinstance(m, UserMessage) and isinstance(m.content, list) for b in m.content))
            finally:
                await app.close()
            with Session(session_path) as session:
                self.assertTrue(any(e.payload.get('kind') == 'mediaResource' for e in session.read_all()))
            # Removing a retained resource is detected before a recovered runtime starts.
            artifact = root / '.fruitfly/artifacts' / resource.removeprefix('sha256:')
            artifact.write_bytes(b'corrupt')
            broken = AgentApplication(factory)
            with self.assertRaisesRegex(ValueError, 'hash check'):
                await broken.start(resume=True, session_path=session_path)

    async def test_nonvision_input_is_rejected_before_message_persistence(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'session.jsonl'
            provider = FauxProvider()
            provider.respond_text('text works')
            with Session(path) as durable:
                session = InteractiveSession(AgentLoopConfig(provider=provider, session=durable), vision=False)
                with self.assertRaisesRegex(ValueError, 'vision model'):
                    await session.submit([image()])
                self.assertEqual(durable.messages(), [])
                await session.submit('hello')
                self.assertEqual(provider.calls[0]['messages'][0].content, 'hello')

    async def test_queue_copies_inputs_and_steering_keeps_images(self):
        entered, release = asyncio.Event(), asyncio.Event()
        seen = []
        async def loop(config, messages, **kwargs):
            from fruitfly_agent.core.data_model import AgentLoopResult
            seen.append(list(messages))
            entered.set()
            await release.wait()
            steering = await config.get_steering_messages(None)
            seen.extend([steering] if steering else [])
            return AgentLoopResult([*messages, *steering], 'stop')
        session = InteractiveSession(AgentLoopConfig(provider=FauxProvider()), run_loop=loop)
        app = AgentApplication(_Factory([session]))
        await app.start()
        try:
            blocks = [TextBlock('original'), image()]
            app.enqueue(blocks)
            blocks.clear()
            await entered.wait()
            steering = [TextBlock('look again'), image()]
            self.assertTrue(app.steer(steering))
            steering.clear()
            release.set()
            await app.wait_until_idle()
            self.assertEqual(seen[0][0].content, [TextBlock('original'), image()])
            self.assertEqual(seen[1][0].content, [TextBlock('look again'), image()])
        finally:
            await app.close()

    async def test_terminal_attachment_commands_and_image_only_submission(self):
        provider = FauxProvider()
        provider.respond_text('seen')
        session = InteractiveSession(AgentLoopConfig(provider=provider), load_attachment=lambda _: image())
        output = io.StringIO()
        frontend = TerminalFrontend(session, input_stream=io.StringIO(
            '/attach "image with spaces.png"\n/attachments\n/detach 1\n/attach image.png\n\n/exit\n'), output_stream=output)
        await frontend.run()
        self.assertEqual(provider.calls[0]['messages'][0].content, [image()])
        self.assertIn('image with spaces.png', output.getvalue())
        self.assertIn('Attachment removed', output.getvalue())
        self.assertNotIn(image().data, output.getvalue())

    async def test_cli_image_only_uses_single_task_flow_and_current_workspace(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_models(root)
            (root / 'input.png').write_bytes(png_bytes())
            provider = FauxProvider()
            provider.respond_text('seen')
            registry = Mock(create=Mock(return_value=provider))
            with patch('fruitfly_agent.run.runtime.assembly.default_registry', return_value=registry), \
                    patch('fruitfly_agent.run.cli.TerminalConfigurationFrontend') as menu, \
                    patch('sys.stdout', new_callable=io.StringIO):
                code = await run_cli(create_parser().parse_args(['--cwd', tmp, '--image', 'input.png']))
            self.assertEqual(code, 0)
            menu.assert_not_called()
            self.assertIn(image(), provider.calls[0]['messages'][0].content)

    async def test_read_binary_rejection_and_resource_save_without_base64_arguments(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            env = LocalEnv(str(root))
            with Session(root / 'session.jsonl') as session:
                media = SessionMedia(DataArtifactStore(root / 'artifacts'), session)
                (root / 'input.png').write_bytes(png_bytes())
                result = await create_read_tool(media.put).execute(ToolCallContext('a', 'read', {'path': 'input.png'}, env))
                resource = result.content[-1].text.split('Media resource: ')[1]
                await create_save_media_tool(media.read).execute(ToolCallContext('b', 'save_media',
                    {'resource_id': resource, 'path': 'output.png'}, env))
                self.assertEqual((root / 'output.png').read_bytes(), png_bytes())
                with self.assertRaisesRegex(ValueError, 'not granted'):
                    media.read('sha256:' + '0' * 64)
                (root / 'audio.wav').write_bytes(b'RIFF\x00\x00\x00\x00WAVE')
                with self.assertRaisesRegex(ValueError, 'unsupported binary'):
                    await create_read_tool().execute(ToolCallContext('c', 'read', {'path': 'audio.wav'}, env))
                (root / 'bad.png').write_bytes(png_bytes()[:-12])
                with self.assertRaisesRegex(ValueError, 'damaged image'):
                    load_image('bad.png', workspace=root)

    async def test_save_media_h_guidance_binding_changes_the_actual_model_request(self):
        from fruitfly_agent.lab.catalog import builtin_catalog, assemble_lab, AssemblyContext, MechanismSelection
        from fruitfly_agent.core.loop import run_agent_loop
        from fruitfly_agent.core.data_model import AssistantMessage, ToolCallBlock
        from fruitfly_agent.core.model_stream import AssistantMessageEventStream, StreamDone
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = DataArtifactStore(root / 'artifacts')
            instructions = 'Save the supplied resource to the exact requested path. Preserve original bytes.'
            binding = store.put_text(instructions).artifact_id
            with Session(root / 'session.jsonl') as session:
                media = SessionMedia(store, session)
                resource = media.put(png_bytes(), 'image/png', 'fixture')
                provider = FauxProvider()
                observed = []
                def execute(view, **kwargs):
                    observed.append(next(t.description for t in view.tools if t.name == 'save_media'))
                    async def events():
                        yield StreamDone(AssistantMessage([ToolCallBlock('save', 'save_media',
                            {'resource_id': resource, 'path': 'candidate.png'})], stop_reason='toolUse'))
                    return AssistantMessageEventStream(events())
                provider.script.append(execute)
                provider.respond_text('done')
                candidate = assemble_lab(AgentLoopConfig(provider=provider), catalog=builtin_catalog(),
                    selections=(MechanismSelection('local-env'), MechanismSelection('save-media-tool')),
                    context=AssemblyContext(root, session, 'offline', lambda *args: None,
                        artifact_reader=store.read_text, artifact_bindings={'tool-guidance.save_media': binding},
                        media_reader=media.read))
                target = candidate.components['text-target:tool-guidance.save_media']
                self.assertEqual(target.snapshot().text, instructions)
                self.assertEqual(target.snapshot().binding.key, 'tool-guidance.save_media')
                result = await run_agent_loop(candidate.config, [UserMessage('save the resource')])
                self.assertFalse(result.is_error)
                self.assertEqual(observed, [instructions])
                self.assertEqual((root / 'candidate.png').read_bytes(), png_bytes())

    async def test_pending_attachment_draft_survives_rejection_and_clears_on_session_switch(self):
        from dataclasses import replace
        from fruitfly_agent.interactive.contracts.commands import CommandResult
        session = InteractiveSession(AgentLoopConfig(provider=FauxProvider()), load_attachment=lambda _: image())
        output = io.StringIO()
        frontend = TerminalFrontend(session, input_stream=io.StringIO(
            '/attach image.png\ninspect this\n/attachments\n/resume other\n/attachments\n/exit\n'), output_stream=output)
        def reject(content):
            raise ValueError('fixture input unavailable')
        frontend.bindings = replace(frontend.bindings, validate_input=reject)
        async def change(command):
            session._session_path = 'different-session.jsonl'
            return CommandResult()
        frontend.commands.register('resume', change)
        await frontend.run()
        text = output.getvalue()
        self.assertIn('Unsent text: inspect this', text)
        self.assertIn('Session changed; pending attachments and unsent draft cleared', text)
        self.assertIn('No pending attachments.', text)

    async def test_save_media_keeps_host_write_permissions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_models(root)
            provider = FauxProvider()
            registry = Mock(create=Mock(return_value=provider))
            factory = RunApplicationFactory(cwd=root, environment={}, provider_registry=registry)
            factory.configuration.set_mechanism('save-media-tool', enabled=True)
            factory.configuration.save()
            factory.reload_configuration()
            app = AgentApplication(factory)
            await app.start()
            try:
                provider.respond_text('seen')
                await app.submit([image()])
                resource = next(b.text.split('Media resource: ')[1] for b in provider.calls[0]['messages'][0].content
                                if isinstance(b, TextBlock) and b.text.startswith('Media resource: '))
                provider.respond_tool_call('save_media', {'resource_id': resource, 'path': '.env'})
                provider.respond_text('permission denied')
                await app.submit('save to protected path')
                result = next(m for m in provider.calls[-1]['messages'] if m.role == 'toolResult')
                self.assertTrue(result.is_error)
                self.assertFalse((root / '.env').exists())
            finally:
                await app.close()

    async def test_cancel_discards_queued_images_without_media_registration(self):
        from fruitfly_agent.core.data_model import AgentLoopResult
        entered = asyncio.Event()
        registered = []
        async def loop(config, messages, *, signal, **kwargs):
            entered.set()
            await signal.wait()
            return AgentLoopResult(list(messages), 'aborted')
        session = InteractiveSession(AgentLoopConfig(provider=FauxProvider()), run_loop=loop,
            register_media=lambda *args: registered.append(args))
        app = AgentApplication(_Factory([session]))
        await app.start()
        try:
            app.enqueue('active')
            await entered.wait()
            app.enqueue([image()])
            self.assertTrue(app.cancel())
            await app.wait_until_idle()
            self.assertEqual(app.pending_count, 0)
            self.assertEqual(registered, [])
            self.assertEqual(session.messages, [UserMessage('active')])
        finally:
            await app.close()

    async def test_media_save_uses_remote_binary_environment_without_network(self):
        from fruitfly_agent.lab.environment.ssh import SshConfig, SshEnv
        from tests.support.ssh import SftpFixture
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sftp = SftpFixture(root)
            sftp.path('/srv/project').mkdir(parents=True)
            env = SshEnv(SshConfig(host='server.example', cwd='/srv/project'), username='fixture', password='fixture')
            env._sftp = sftp
            try:
                tool = create_save_media_tool(lambda _: png_bytes())
                await tool.execute(ToolCallContext('remote', 'save_media',
                    {'resource_id': 'fixture-resource', 'path': 'output/image.png'}, env))
                self.assertEqual(sftp.path('/srv/project/output/image.png').read_bytes(), png_bytes())
            finally:
                await env.close()

    async def test_non_read_tool_images_receive_attributed_recoverable_resource_ids(self):
        from fruitfly_agent.core.data_model import AgentToolResult
        from fruitfly_agent.core.tool_runtime import AgentTool
        from fruitfly_agent.core.loop import run_agent_loop
        from fruitfly_agent.run.runtime.media import retain_tool_media
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with Session(root / 'session.jsonl') as session:
                media = SessionMedia(DataArtifactStore(root / 'artifacts'), session)
                async def capture(ctx):
                    return AgentToolResult([image()])
                tool = AgentTool('capture', 'Capture', 'Capture image', {'type': 'object'}, capture)
                provider = FauxProvider()
                provider.respond_tool_call('capture', {})
                provider.respond_text('seen')
                config = retain_tool_media(AgentLoopConfig(provider=provider, tools=[tool]), media)
                result = await run_agent_loop(config, [UserMessage('capture')])
                self.assertFalse(result.is_error)
                record = next(m for m in result.messages if m.role == 'toolResult')
                reference = record.content[-1].text.split('Media resource: ')[1]
                self.assertEqual(media.read(reference), png_bytes())
                self.assertEqual(session.read_all()[-1].payload['origin'], 'tool:capture')

    async def test_improvement_editor_reader_uses_the_same_media_contract(self):
        import base64
        from types import SimpleNamespace as NS
        from fruitfly_agent.lab.improvement.workspaces import WorkspaceSession
        gif = base64.b64decode('R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7')
        for data, mime in ((png_bytes(), 'image/png'), (gif, 'image/gif')):
            with self.subTest(media_type=mime):
                provider = FauxProvider()
                provider.respond_tool_call('read_file', {'path': 'input'})
                provider.respond_text('checked')
                services = NS(check=lambda: None, reserve=lambda *args: None,
                    record=lambda *args, **kwargs: None, signal=asyncio.Event())
                workspace = NS(paths=lambda: ('input',), read=lambda _: data)
                result = await WorkspaceSession(AgentLoopConfig(provider=provider), None).session(
                    'Inspect media', workspace, services)
                self.assertEqual(result, 'checked')
                tool = next(m for m in provider.calls[-1]['messages'] if m.role == 'toolResult')
                self.assertEqual(tool.content[0].media_type, mime)
