"""Project the exact admitted Skill resource snapshot."""
from fruitfly_agent.lab.context_manager.augmentation.skills.methods.indexed_documents.parser import render_skills_xml


def render_catalog(captured, resources):
    locations = captured.mount(resources)
    return render_skills_xml(list(captured.skills), locations=locations), locations['__catalog__']
