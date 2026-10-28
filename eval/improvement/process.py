"""Cancellable invocation of the existing single-version Eval CLI."""
import asyncio
import json
from pathlib import Path
import sys


class EvalProcess:
    def __init__(self):
        self.result_root = None

    async def retire(self, process):
        if process.returncode is not None:
            return
        try:
            process.terminate()
        except ProcessLookupError:
            await process.wait()
            return
        try:
            await asyncio.wait_for(process.wait(), timeout=5)
        except TimeoutError:
            try:
                process.kill()
            except ProcessLookupError:
                pass
            try:
                await asyncio.wait_for(process.wait(), timeout=3)
            except TimeoutError as exc:
                from fruitfly_agent.improvement.contracts.failures import CleanupError
                raise CleanupError('Eval process termination was not confirmed') from exc

    async def __call__(self, request, host_path, *, directory, output_root, emit):
        directory = Path(directory)
        request_path = directory / 'request.json'
        request_path.write_text(json.dumps(request.to_dict(), indent=2) + '\n')
        opening = asyncio.create_task(asyncio.create_subprocess_exec(sys.executable, '-B', '-m', 'eval', 'run',
            '--request', str(request_path), '--host-config', str(host_path), '--output-root', str(output_root),
            '--events', 'jsonl', cwd=request.runtime.working_directory,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
            limit=4 * 1024 * 1024))
        try:
            process = await asyncio.shield(opening)
        except asyncio.CancelledError:
            process = await opening
            await self.retire(process)
            raise
        evaluation_id = None
        try:
            if process.stdout is None:
                raise RuntimeError('Eval output pipe was not created')
            with (directory / 'controller.log').open('wb') as log:
                while line := await process.stdout.readline():
                    log.write(line); log.flush()
                    try: event = json.loads(line)
                    except (ValueError, UnicodeDecodeError): continue
                    if event.get('type') == 'started':
                        evaluation_id = event['evaluation_id']
                        if not isinstance(evaluation_id, str) or evaluation_id in {'.', '..', ''} or Path(evaluation_id).name != evaluation_id:
                            raise ValueError('Eval returned an invalid evaluation identity')
                        self.result_root = Path(output_root) / evaluation_id
                    # Model text and private verifier output stay in their original logs.
                    if event.get('type') in {'started', 'preflight', 'job_started', 'job_finished', 'report_written'}:
                        emit('benchmark-progress', event_type=event['type'])
                await process.wait()
            if not evaluation_id:
                raise RuntimeError('Eval produced no evaluation identity; inspect controller.log')
            root = Path(output_root) / evaluation_id
            report = json.loads((root / 'report.json').read_text())
            return report, root
        finally:
            await self.retire(process)
