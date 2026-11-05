"""Project the exact admitted Skill resource snapshot."""
from ...catalog import render_skills_xml


def render_catalog(captured, resources):
    return render_skills_xml(list(captured.skills), locations=captured.mount(resources))
