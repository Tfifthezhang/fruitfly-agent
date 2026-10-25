"""Shared sequential candidate search, independent of task count and backends."""
from ..contracts.editing import ProposalResult
from ..contracts.candidates import CandidateBundle


class SearchEngine:
    async def run(self, schedule, baseline, problem):
        current = baseline
        history = ()
        seen = {baseline.snapshot_id}
        reason = None
        for round_index in range(schedule.rounds):
            await problem.begin(round_index, current)
            pool: list[CandidateBundle] = []
            requested_stop = False
            for scope, index in schedule.missions:
                problem.record('proposal-start', scope=scope, index=index, round=round_index)
                proposal = await problem.propose(current, scope, index)
                if not isinstance(proposal, ProposalResult):
                    raise TypeError('generator must return ProposalResult')
                pool.extend(proposal.candidates)
                requested_stop = requested_stop or proposal.stop
                problem.record('proposal-finished', scope=scope, index=index,
                    candidate_ids=[c.candidate_id for c in proposal.candidates])
            repeated = bool(pool) and all(c.harness.snapshot_id in seen for c in pool)
            for candidate in pool:
                await problem.probe(candidate.harness)
                seen.add(candidate.harness.snapshot_id)
            if not pool:
                return problem.stop(round_index, 0, False, requested_stop) or 'no_candidate'
            compositions = []
            for index in range(schedule.compositions):
                candidate = await problem.compose(current, (*history, *pool), index)
                compositions.append(candidate)
                await problem.probe(candidate.harness)
            history = (*history, *pool, *compositions)
            problem.record('round-completed', index=round_index)
            await problem.select(round_index, round_index + 1 == schedule.rounds)
            reason = problem.stop(round_index, len(pool), repeated, requested_stop)
            if reason:
                break
            if round_index + 1 < schedule.rounds:
                current = await problem.advance(current)
        return reason or 'completed'
