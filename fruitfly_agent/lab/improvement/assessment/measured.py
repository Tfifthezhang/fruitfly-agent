"""Stable selection over complete attributed measurements; no model judgment."""
from fruitfly_agent.improvement.contracts.assessment import SelectionDecision

def measured_selection(records, measurements, *, direction='max'):
    """Stable task-objective selection. Process judgments cannot change these scores."""
    selectable = tuple(r for r in records if r.status == 'completed')
    measured = {m.run_id: m for m in measurements}
    if not selectable or any(r.run_id not in measured for r in selectable):
        return None
    utility = -1 if direction == 'min' else 1
    best = max(selectable, key=lambda r: utility * measured[r.run_id].score)
    return SelectionDecision(best.run_id, 'Best measured development result; ties retain earlier result')



class SelectionPolicy:
    async def choose(self, plan, task, records, feedback, *, selector, measurements):
        if plan.feedback == 'scored':
            decision=measured_selection(records,feedback,direction=getattr(measurements,'direction','max'))
            if decision is None:return None
            scores={m.run_id:m.score for m in feedback}
            tied=tuple(r for r in records if r.status=='completed' and scores.get(r.run_id)==scores[decision.run_id])
            if len(tied)>1 and selector is not None:
                return await selector.select(task,tied)
            return decision
        if len(records) == 1:
            return SelectionDecision(records[0].run_id, 'Only available executed result')
        return await selector.select(task, records)
