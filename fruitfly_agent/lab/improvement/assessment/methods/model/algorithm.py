"""One bounded read-only evaluator for execution judgments and comparisons."""
from dataclasses import asdict
import json
from fruitfly_agent.improvement.contracts.assessment import AssessmentUnavailable
from fruitfly_agent.improvement.contracts.failures import IntegrityError
from fruitfly_agent.improvement.contracts.live import DimensionJudgment, EvidenceFinding
from fruitfly_agent.improvement.contracts.components import ComponentDocument, HarnessSnapshot
from fruitfly_agent.improvement.contracts.versions import canonical_json
from ....evidence.resources import ReferenceWorkspace
from ....evidence.session import EvidenceSession
from ...instructions import EvaluatorInstructions
from ...configuration import EvaluatorSettings

class ModelEvaluator:
    implementation_id = 'model-evaluator'

    def __init__(self, config, artifacts, *, instructions=None, settings=None, reader_factory=None, context=(), runtime_factory=None, options=None):
        self.context = tuple(context)
        self.config = config
        self.artifacts=artifacts
        self.instructions=instructions or EvaluatorInstructions()
        self.options = EvaluatorSettings.from_dict(options)
        self.session=EvidenceSession(config,artifacts,settings=settings,reader_factory=reader_factory, runtime_factory=runtime_factory)

    async def evaluate(self, task, records, services, *, inputs=(), incumbent=None):
        if not records or len({r.run_id for r in records}) != len(records):
            raise ValueError('evaluation requires distinct existing executions')
        inputs = {v.record.run_id: v for v in inputs}
        supplied, references, files, rows = set(), {}, {}, []
        def observe(event, **fields):
            if event == 'evidence-page':
                supplied.add(fields['citation_id'])
            services.record(event, **fields)
        for resource in self.context:
            references['context/organized/' + resource.path] = resource.artifact_id
        for resource in task.inputs:
            references['context/inputs/' + resource.path] = resource.artifact_id
        for record in records:
            prefix = 'context/executions/' + record.run_id + '/'
            output_id = self.artifacts.put(record.output.encode())
            from fruitfly_agent.improvement.contracts.evidence import EvidenceSpan
            output_citation=EvidenceSpan(output_id,0,min(self.options.output_preview_characters,len(record.output))).citation_id
            files[prefix + 'output.txt'] = record.output.encode()
            row = {'run_id': record.run_id, 'status': record.status, 'output_id': output_id,
                   'output': record.output[:self.options.output_preview_characters], 'output_citation_id':output_citation, 'output_characters': len(record.output)}
            value = inputs.get(record.run_id)
            if value is not None:
                facts = {key: value.facts.to_dict()[key] for key in ('status', 'termination_reason', 'elapsed_seconds', 'complete', 'diagnosable')}
                facts['usage'] = {scope: {v.resource: v.used for v in value.facts.usage if v.scope == scope}
                                  for scope in sorted({v.scope for v in value.facts.usage})}
                facts['counters'] = dict(value.facts.counters)
                facts_id = self.artifacts.put(canonical_json(facts).encode())
                row.update(facts=facts, facts_id=facts_id)
            for resource in record.artifacts:
                references[prefix + resource.path] = resource.artifact_id
                if resource.path == 'evidence/coverage.json':
                    coverage = json.loads(self.artifacts.read(resource.artifact_id))
                    row.update(coverage_path=prefix + resource.path, overview_path=prefix + 'evidence/overview.json',
                               evidence_complete=coverage['evidence_complete'], evidence_dimensions=coverage['dimensions'])
            rows.append(row)
        from ....evidence.rounds import round_navigation
        files['context/rounds.json'] = canonical_json(round_navigation(services, (r.run_id for r in records))).encode()
        files['context/task.md'] = task.instruction.encode()
        files['context/executions.json'] = canonical_json(rows).encode()
        index = {'references': references, 'inline_files': sorted(files), 'executions': rows, 'incumbent': incumbent}
        files['INDEX.json'] = canonical_json(index).encode()
        placeholder = HarnessSnapshot((ComponentDocument('assessment', 'assessment', 'H', 'assessment-v1', ()),))
        workspace = ReferenceWorkspace(artifacts=self.artifacts, references=references, baseline=placeholder,
            files=files, writable_ids=(), record=observe)
        mission = self.instructions.criteria + '\n' + (self.instructions.assess if len(records) == 1 else self.instructions.compare)
        mission += '\n' + self.instructions.schema
        input_characters = max(self.options.minimum_input_characters, self.options.input_characters_per_token * (self.config.context_window - self.config.max_tokens))
        initial_value = {'task': task.instruction[:min(self.options.task_preview_characters, input_characters // self.options.task_input_divisor)],
                         'executions': rows, 'incumbent': incumbent,
                         'catalog': self.instructions.catalog}
        # Keep large task/output/fact collections behind the same paged reader.
        # This bounds initial input, not the Agent's cumulative evidence access.
        while len(canonical_json(initial_value)) > input_characters and initial_value['executions']:
            initial_value['executions'] = initial_value['executions'][:-1]
        initial_value['task_path'] = 'context/task.md'
        initial_value['execution_count'] = len(rows)
        initial_value['executions_path'] = 'context/executions.json'
        for row in initial_value['executions']:
            supplied.add(row['output_citation_id'])
            if 'facts_id' in row:
                supplied.add(row['facts_id'])
        mission += '\n' + self.instructions.coverage
        initial = canonical_json(initial_value)
        response_id = ''
        rejection_id = ''
        accepted = None
        def accept(response):
            nonlocal response_id, rejection_id, accepted
            raw = response if isinstance(response, str) else canonical_json(response)
            response_id = self.artifacts.put(raw.encode('utf-8'))
            services.record('evaluation-response', artifact_id=response_id,
                            run_ids=[r.run_id for r in records])
            def unique(pairs):
                result = {}
                for key, value in pairs:
                    if key in result:
                        raise ValueError('duplicate evaluator result field: ' + key)
                    result[key] = value
                return result
            try:
                data = json.loads(raw, object_pairs_hook=unique)
                self.validate(data, records, supplied | workspace.eligible_ids)
            except (ValueError, TypeError, KeyError) as exc:
                rejection_id = self.artifacts.put(canonical_json({
                    'reason': type(exc).__name__, 'detail': str(exc), 'response_id': response_id,
                    'run_ids': [r.run_id for r in records],
                    'supplied_citations': sorted(supplied | workspace.eligible_ids)}).encode())
                services.record('evaluation-rejected', reason=type(exc).__name__, detail=str(exc),
                    response_id=response_id, evidence=rejection_id)
                raise
            accepted = data
        from ...submission import submission_tool
        name = 'submit_assessment' if len(records) == 1 else 'submit_comparison'
        mission += '\n' + self.instructions.submit.replace('{name}', name)
        try:
            await services.operation(self.session.session(mission, workspace, services, writable=False,
                system=self.instructions.system, initial_content=initial, extra_tools=(submission_tool(name, accept, instructions=self.instructions),),
                validate_final=accept, submission_result=lambda: canonical_json(accepted) if accepted is not None else None), stage='evaluator')
            if accepted is None:
                raise ValueError('evaluation ended without an accepted judgment')
            data = accepted
        except IntegrityError:
            raise
        except (ValueError, TypeError, KeyError, TimeoutError, RuntimeError) as exc:
            services.record('evaluation-unavailable', reason=type(exc).__name__, detail=str(exc),
                response_id=response_id, evidence=rejection_id)
            raise AssessmentUnavailable('evaluator did not produce a supported final judgment') from exc
        reference = self.artifacts.put(canonical_json(data).encode())
        services.record('evaluation-result', artifact_id=reference, run_ids=[r.run_id for r in records],
                        instructions_id=self.artifacts.put(canonical_json(asdict(self.instructions)).encode()))
        return data, reference

    @staticmethod
    def validate(data, records, supplied):
        if not isinstance(data, dict) or set(data) != {'evaluations', 'choice', 'reason', 'uncertainty', 'evidence_ids'}:
            raise ValueError('invalid evaluation schema')
        ids = {r.run_id for r in records}
        if data['choice'] is not None and (len(records) == 1 or data['choice'] not in ids):
            raise ValueError('evaluation chose an unavailable execution')
        if not isinstance(data['evaluations'], list) or {v['run_id'] for v in data['evaluations']} != ids or len(data['evaluations']) != len(ids):
            raise ValueError('evaluation must cover each supplied execution')
        criteria = None
        for row in data['evaluations']:
            if set(row) != {'run_id', 'dimensions', 'findings'} or not isinstance(row['dimensions'], list) or not row['dimensions']:
                raise ValueError('evaluation requires per-dimension results')
            if not isinstance(row['findings'],list):raise ValueError('findings must be an array')
            findings=tuple(EvidenceFinding(**value) for value in row['findings'])
            if any(set(f.evidence_ids)-supplied for f in findings):raise ValueError('finding cited unread evidence')
            dimensions = tuple(DimensionJudgment(**value) for value in row['dimensions'])
            if len({d.dimension for d in dimensions}) != len(dimensions):
                raise ValueError('duplicate evaluation dimension')
            current_criteria = {d.dimension: d.criterion for d in dimensions}
            if criteria is not None and current_criteria != criteria:
                raise ValueError('comparison requires common dimensions and criteria')
            criteria = current_criteria
            for dimension in dimensions:
                if set(dimension.evidence_ids) - supplied:
                    raise ValueError('evaluation cited unread evidence')
        if any(not isinstance(data[key], str) or not 1 <= len(data[key]) <= 4000 for key in ('reason', 'uncertainty')):
            raise ValueError('evaluation requires bounded reasons and uncertainty')
        if not isinstance(data['evidence_ids'], list) or not data['evidence_ids'] or set(data['evidence_ids']) - supplied:
            raise ValueError('evaluation must cite supplied evidence')
