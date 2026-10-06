"""Text task-pack materials and temporary installation."""
import json
from fruitfly_agent.lab.optimization.task_packs import package_documents, validate_pack


def package():
    return dict(schema_version=2, id="project", name="Project regression", description="Regression tasks", files={"cases":"cases.json", "holdout":"holdout.json"},
        task_schema="single-turn-text-v1", target_schema="text-v1",
        compatible_targets=["base_prompt", "skill-catalog.guidance"],
        objective=dict(policy_id="normalized-exact-v1", direction="max"),
        train=[dict(id="train-1", input="say A", expected="A", reason="METADATA_ONLY")],
        validation=[dict(id="validation-1", input="say B", expected="B")],
        holdout=[dict(id="holdout-1", input="UNSEEN_INPUT", expected="SECRET_ANSWER")])


def validate_material(payload):
    manifest, cases, holdout = package_documents(payload)
    return validate_pack(manifest, cases=cases, holdout=holdout)


def install(root, payload=None):
    payload = payload or package()
    path = root / ".fruitfly/optimization/task-packs" / payload["id"] / "pack.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    manifest, cases, holdout = package_documents(payload)
    path.write_text(json.dumps(manifest), encoding="utf-8")
    (path.parent / manifest["files"]["cases"]).write_text(json.dumps(cases), encoding="utf-8")
    if holdout is not None:
        (path.parent / manifest["files"]["holdout"]).write_text(json.dumps(holdout), encoding="utf-8")
    return path

def coding_pack():
    return dict(schema_version=2, id="coding", name="Coding regression", description="Coding tasks", files={"cases":"cases.json", "holdout":"holdout.json"},
        task_schema="python-function-v1", target_schema="text-v1", compatible_targets=["base_prompt"],
        objective=dict(policy_id="python-function-tests-v1", direction="max"),
        train=[dict(id="train-add", input="Implement add_one(value), returning value + 1.", entry_point="add_one",
            tests=[dict(args=[0], expected=1), dict(args=[-2], expected=-1)])],
        validation=[dict(id="validation-double", input="Implement double(value), returning value * 2.", entry_point="double",
            tests=[dict(args=[2], expected=4), dict(args=[-3], expected=-6)])],
        holdout=[dict(id="holdout-unseen", input="UNSEEN_CODING_TASK", entry_point="UNSEEN_FUNCTION",
            tests=[dict(args=[7], expected="SECRET_CODING_ANSWER")])])
