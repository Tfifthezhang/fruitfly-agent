# Base Prompt

[Up: Lab](../README.md)

Own the built-in system instructions and the adapter that makes them an improvement target.

| Item | Behavior |
|---|---|
| Built-in prompt | `assistant-default`, displayed as **Assistant default** |
| `BasePrompt` | ID, label, text, and UTF-8 SHA-256 content hash |
| `builtins()` | Current default derived from the owner parameter document |
| `get_builtin(id)` | Return the definition or raise `ValueError`. |
| Profile selection | `prompt` defaults to `assistant-default`; may reference a content-addressed text artifact. |

Choose **/config → prompt**, preview the text, confirm, then save and apply. The menu shows built-ins, the current selection, and current configuration/profile task results. Recovery validates saved history and records the current runtime environment. Task labels do not imply general improvement or automatic prompt routing.

## Default instructions

The concise default asks for a brief goal/scope/evidence/deliverable statement
before substantial work, respects planning-only or analysis-only scope, and asks
for material findings and remaining uncertainty during execution. It discourages
repetitive progress and premature completion claims, directs independent long
commands through managed handles, and closes with results, checks and limits.
These are model instructions, not an enforced planner or a task-completion detector.
Prompt candidates use the ordinary H target and retain exact text/hash identity.

## Files and integration

| File | Responsibility |
|---|---|
| [defaults.yaml](defaults.yaml) | Single default H parameter document |
| [__init__.py](__init__.py) | Derived built-in value and current lookup |
| [target.py](target.py) | `BasePromptTarget`: snapshot, validate, and prepare a trial |

Run verifies prompt contents and fixes the hash in the manifest. Tool/Skill catalog and information augmentation is outside the base text hash. [Improvement](../improvement/README.md) searches candidates; [Run](../../run/README.md) stores them; Application manages activation. This module does not search or adopt autonomously. Lookup reads the installed owner resource, without network or model requests. There are no module-specific environment variables.

```bash
.venv/bin/python -m unittest tests.lab.test_base_prompt tests.run.test_base_prompt_flow tests.workflows.test_decoupling
```
