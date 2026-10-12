"""Resolve built-in or content-addressed prompt text without runtime assembly."""
from fruitfly_agent.lab.base_prompt import get_builtin
from .artifacts import DataArtifactStore

def resolve_base_prompt(reference: str, store: DataArtifactStore) -> tuple[str, dict[str, str]]:
    """Resolve and verify the one immutable base prompt for a runtime."""
    if reference.startswith("sha256:"):
        content = store.read_text(reference)
        identity = {
            "reference": reference,
            "label": f"Candidate {reference[7:15]}",
            "source": "artifact",
            "content_hash": reference,
        }
    else:
        prompt = get_builtin(reference)
        content = prompt.text
        identity = {
            "reference": prompt.prompt_id,
            "label": prompt.label,
            "source": "builtin",
            "content_hash": prompt.content_hash,
        }
    if not content.strip():
        raise ValueError("base prompt must not be empty")
    return content, identity

