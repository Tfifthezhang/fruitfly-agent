"""Use public engine hooks to attribute attempts before running the Agent."""
import json
from pathlib import Path
from fruitfly_eval.harbor.evidence_hooks import EvidenceCapturePlugin
from fruitfly_eval.harbor.material import write_json
from fruitfly_eval.improvement.measurement_context import FILENAME, validate


class WorkBuddyEvidencePlugin(EvidenceCapturePlugin):
    async def on_job_start(self, job):
        await super().on_job_start(job)
        self.plan = json.loads((Path(job.job_dir).parent / 'measurement-plan.json').read_text())
        self.attempts = {}
        job.on_trial_started(self.attribute)

    async def attribute(self, event):
        task = str(event.config.task.get_local_path().resolve())
        if task not in self.plan['tasks']:
            raise ValueError('engine trial is outside the frozen execution plan')
        attempt = self.attempts.get(task, 0)
        if attempt >= self.plan['attempts']:
            raise ValueError('engine started an unplanned task attempt')
        self.attempts[task] = attempt + 1
        context = validate({**self.plan['tasks'][task], 'attempt': attempt})
        write_json(self.directory(event) / FILENAME, context)
