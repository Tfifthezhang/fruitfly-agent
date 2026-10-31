"""Small explicit-material flow; experiment configuration belongs to files."""
from dataclasses import replace
import shlex

from fruitfly_agent.interactive.contracts.improvement import WorkflowRequest
from fruitfly_agent.interactive.terminal.io.menu import MenuRow, MenuHelp


class WorkflowPanel:
    def __init__(self, *, client, configuration, choose, read, confirm, report, execute, history, direction=""):
        self.client, self.configuration = client, configuration
        self.choose, self.read, self.confirm, self.report = choose, read, confirm, report
        self.execute, self.history = execute, history
        generators = tuple(c.choice_id for c in configuration.generators if c.available)
        self.request = WorkflowRequest(generator_id=generators[0] if generators else "", direction=direction,
            strategy_id="simple", retain_experience=False)

    async def run(self):
        while True:
            value = self.request
            rows = (MenuRow("Task", value.task_pack_id or value.instruction or "Choose explicit task material"),
                MenuRow("Input files", ", ".join(value.input_paths) or "No files selected"),
                MenuRow("Start improvement", help=MenuHelp("Start improvement", "One candidate comparison; preview before model calls")),
                MenuRow("Results and history"))
            selected = self.choose("Component improvement", rows,
                subtitle="For experiment settings and RSI use fruitfly-agent-lab and experiment.yaml", key="component-workflow")
            if selected is None:
                return
            try:
                if selected == 0:
                    await self.task_material()
                elif selected == 1:
                    if value.task_pack_id:
                        raise ValueError("Saved task material owns its input files")
                    text = await self.read("Workspace-relative input files; quote paths containing spaces")
                    if text is not None:
                        self.request = replace(value, input_paths=tuple(shlex.split(text)))
                elif selected == 2:
                    preview = self.client.workflow_preview(value)
                    subtitle = "\n".join(f"{k}: {v}" for k, v in preview.details) + "\n\n" + preview.cost_notice
                    if self.confirm(title="Confirm component improvement", subtitle=subtitle,
                            rows=(MenuRow("Start the frozen workflow"), MenuRow("Cancel"))):
                        if await self.execute(preview, value.direction):
                            return
                elif selected == 3:
                    await self.history()
            except (ValueError, TypeError, RuntimeError, OSError) as exc:
                self.report(str(exc) + "\n")

    async def task_material(self):
        materials = self.configuration.materials
        index = self.choose("Task material", tuple(MenuRow(c.label, help=MenuHelp(c.label, c.reason or c.detail)) for c in materials), key="workflow-material")
        if index is None:
            return
        choice = materials[index]
        if not choice.available:
            self.report(choice.reason + "\n")
            return
        if choice.choice_id:
            self.request = replace(self.request, task_pack_id=choice.choice_id, instruction="", input_paths=())
        else:
            text = await self.read("Current task instruction")
            if text is not None:
                self.request = replace(self.request, task_pack_id="", instruction=text)
