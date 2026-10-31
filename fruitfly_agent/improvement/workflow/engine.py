"""Shared transitions; schedules and all research decisions are injected."""
import asyncio
from ..contracts.editing import ProposalResult
from ..contracts.failures import StageFailure
from ..contracts.stopping import stop_reason
from .operations import run_stage, require_type
from .state import WorkflowState


def validate_schedule(schedule, plan):
    if (type(schedule.references) is not int or schedule.references < 1
            or type(schedule.rounds) is not int or not 1 <= schedule.rounds <= plan.depth
            or type(schedule.compositions) is not int or schedule.compositions < 0
            or not isinstance(schedule.missions, tuple) or not 1 <= len(schedule.missions) <= 100
            or any(not isinstance(m, tuple) or len(m) != 2 or not isinstance(m[0], str)
                or type(m[1]) is not int or m[1] < 0 for m in schedule.missions)):
        raise ValueError('search schedule exceeds the frozen execution bounds')


class SearchEngine:
    async def run(self, schedule, baseline, problem):
        validate_schedule(schedule, problem.services.plan)
        state = problem.state or WorkflowState(baseline)
        services = problem.services
        if services is None:
            raise ValueError('search operations require job services')
        services.state = state
        async def call(stage, operation, validator=None):
            state.phase = stage
            return await run_stage(services, stage, operation, validator=validator, bounded=not problem.managed)
        for index in range(schedule.rounds):
            await asyncio.sleep(0)
            state.round_index = index
            try:
                await call('begin', lambda: problem.begin(index, state.seed))
                pool, composed = [], []
                requested = False
                failed = None
                for scope, mission in schedule.missions:
                    problem.record('proposal-start', scope=scope, index=mission, round=index)
                    try:
                        proposal = await call('propose', lambda: problem.propose(state.seed, scope, mission),
                                              lambda v: require_type(v, ProposalResult))
                    except StageFailure as exc:
                        failed = exc.failure.stage
                        continue
                    pool.extend(proposal.candidates)
                    requested = requested or proposal.stop
                    problem.record('proposal-finished', scope=scope, index=mission,
                                   candidate_ids=[c.candidate_id for c in proposal.candidates])
                repeated = bool(pool) and all(c.harness.snapshot_id in state.seen for c in pool)
                for candidate in pool:
                    try:
                        await call('execute', lambda: problem.probe(candidate.harness))
                    except StageFailure as exc:
                        failed = exc.failure.stage
                    state.seen.add(candidate.harness.snapshot_id)
                if not pool:
                    if failed:
                        return 'stage_failed.' + failed
                    return stop_reason(await call('stop', lambda: problem.stop(index, 0, False, requested), stop_reason)) or 'no_candidate'
                for mission in range(schedule.compositions):
                    try:
                        from ..contracts.candidates import CandidateBundle
                        candidate = await call('compose', lambda: problem.compose(state.seed, (*state.history, *pool), mission),
                                               lambda v: require_type(v, CandidateBundle))
                        composed.append(candidate)
                        await call('execute', lambda: problem.probe(candidate.harness))
                    except StageFailure:
                        continue
                state.history = (*state.history, *pool, *composed)
                problem.record('round-completed', index=index)
                await call('select', lambda: problem.select(index, index + 1 == schedule.rounds))
                await services.emit('after_round', {'round_index': index, 'candidate_count': len(pool), 'incumbent_run_id': state.selected.run_id if state.selected else None})
                reason = stop_reason(await call('stop', lambda: problem.stop(index, len(pool), repeated, requested), stop_reason))
                if reason:
                    return reason
                if index + 1 < schedule.rounds:
                    seed = await call('advance', lambda: problem.advance(state.seed),
                                      lambda v: require_type(v, type(baseline)))
                    state.seed = seed
            except StageFailure as exc:
                return 'stage_failed.' + exc.failure.stage
        return 'completed'
