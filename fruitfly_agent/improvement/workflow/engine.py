"""One candidate per round, shared by single tasks and task sets."""
import asyncio
from ..contracts.editing import ProposalResult
from ..contracts.failures import StageFailure
from ..contracts.stopping import stop_reason
from .operations import run_stage, require_type
from .state import WorkflowState


class SearchEngine:
    async def run(self, baseline, problem):
        services = problem.services
        if services is None:
            raise ValueError('search operations require job services')
        state = problem.state or WorkflowState(baseline)
        services.state = state
        rounds = services.plan.rounds

        async def call(stage, operation, validator=None):
            state.phase = stage
            return await run_stage(services, stage, operation, validator=validator, bounded=not problem.managed)

        def validate_proposal(value):
            require_type(value, ProposalResult)
            if len(value.candidates) > 1:
                raise ValueError('a round permits at most one candidate')

        for index in range(rounds):
            await asyncio.sleep(0)
            state.round_index = index
            try:
                await call('begin', lambda: problem.begin(index, state.seed))
                problem.record('proposal-start', round=index)
                proposal = await call('propose', lambda: problem.propose(state.seed, 'propose', index),
                                      validate_proposal)
                problem.record('proposal-finished', round=index,
                               candidate_ids=[candidate.candidate_id for candidate in proposal.candidates])
                repeated = bool(proposal.candidates) and all(
                    candidate.harness.snapshot_id in state.seen for candidate in proposal.candidates)
                for candidate in proposal.candidates:
                    await call('execute', lambda: problem.probe(candidate.harness))
                    state.seen.add(candidate.harness.snapshot_id)
                if not proposal.candidates:
                    return stop_reason(await call('stop', lambda: problem.stop(
                        index, 0, False, proposal.stop), stop_reason)) or 'no_candidate'
                state.history = (*state.history, *proposal.candidates)
                problem.record('round-completed', index=index)
                await call('select', lambda: problem.select(index, index + 1 == rounds))
                await services.emit('after_round', {'round_index': index,
                    'candidate_count': len(proposal.candidates),
                    'incumbent_run_id': state.selected.run_id if state.selected else None})
                reason = stop_reason(await call('stop', lambda: problem.stop(
                    index, len(proposal.candidates), repeated, proposal.stop), stop_reason))
                if reason:
                    return reason
                if index + 1 < rounds:
                    state.seed = await call('advance', lambda: problem.advance(state.seed),
                                            lambda value: require_type(value, type(baseline)))
            except StageFailure as exc:
                return 'stage_failed.' + exc.failure.stage
        return 'completed'
