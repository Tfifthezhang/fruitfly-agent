"""Present original-task events without selecting or executing jobs."""
from __future__ import annotations
from typing import Any, Mapping
from fruitfly_agent.interactive.contracts.events import event_from_dict
from fruitfly_agent.interactive.terminal.rendering.renderer import TerminalRenderer


class BenchmarkEventDisplay:
    """Render original-task events without owning input or executing a workflow."""
    def __init__(self):
        self._log_source = None

    async def show_event(
        self, renderer: TerminalRenderer, event: Mapping[str, Any]
    ) -> None:
        event_type = event.get("type")
        if event_type != "log":
            self._log_source = None
        if event_type == "agent_event":
            payload = event.get("event")
            if isinstance(payload, Mapping):
                if payload.get("type") == "run_started":
                    renderer.write_system(
                        f"\n[trial {event.get('trial_id', '?')} · "
                        f"{event.get('job_id', '?')}]\n"
                    )
                    prompt = payload.get("prompt")
                    if isinstance(prompt, str):
                        renderer.write_user_input(prompt)
                try:
                    await renderer.render(event_from_dict(payload))
                except (TypeError, ValueError):
                    pass
        elif event_type == "log":
            source = (event.get("job_id", "?"), event.get("source", "eval"))
            if self._log_source != source:
                renderer.write_system(f"[job {source[0]} · {source[1]}]\n")
                self._log_source = source
            renderer.write_log(str(event.get("text", "")))
        elif event_type == "started":
            renderer.write_system(f"[evaluation {event.get('evaluation_id', '?')}]\n")
        elif event_type == "preflight":
            renderer.write_system(
                "[preflight ready]\n" if event.get("available") else "[preflight blocked]\n"
            )
        elif event_type == "job_started":
            renderer.write_system(
                f"[job {event.get('job_id', '?')} · Harbor job running]\n"
                f"[artifacts: {event.get('artifacts_path', 'unknown')}]\n"
            )
        elif event_type == "job_progress":
            stage = (
                "Harbor preparing tasks / waiting for Agent events"
                if not event.get("agent_runs_started")
                else "Agent execution / verification"
            )
            renderer.write_system(
                f"[job {event.get('job_id', '?')} · "
                f"{event.get('elapsed_seconds', 0)}s elapsed · "
                f"{event.get('completed', 0)} trials completed · "
                f"{event.get('active_agents', 0)} Agent runs active · "
                f"{stage}]\n"
            )
        elif event_type == "job_finished":
            renderer.write_system(
                f"[job {event.get('job_id', '?')} finished · "
                f"{event.get('completed', '?')} trials collected]\n"
            )
        elif event_type == "trial_finished":
            renderer.write_system(
                f"[job {event.get('job_id', '?')} · "
                f"{event.get('completed', '?')} trials completed]\n"
            )
            error = event.get("error")
            if isinstance(error, Mapping):
                renderer.write_system(
                    f"[trial error: {error.get('exception_type', 'Error')}]\n"
                    + str(error.get("exception_message", "")) + "\n"
                )
        elif event_type == "material_preparation":
            renderer.write_system("[preparing task set] " + str(event.get("text", "")) + "\n")
        elif event_type == "report_written":
            renderer.write_system("[report written]\n")

