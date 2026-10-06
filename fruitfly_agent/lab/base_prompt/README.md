# Base Prompt

[Up: Lab](../README.md)

Own the built-in system instructions and the adapter that makes them an optimization target.

| Item | Behavior |
|---|---|
| Built-in prompt | `assistant-default`, displayed as **Assistant default** |
| `BasePrompt` | ID, label, text, and UTF-8 SHA-256 content hash |
| `builtins()` | Tuple containing `DEFAULT_PROMPT` |
| `get_builtin(id)` | Return the definition or raise `ValueError`. |
| Profile selection | `prompt` defaults to `assistant-default`; may reference a content-addressed text artifact. |

Choose **Configure → Base prompt**, preview the text, confirm, and start a new session. The menu shows built-ins, the current selection, and current configuration/profile task results. Resuming a session keeps its original manifest. Task labels do not imply general improvement or automatic prompt routing.

## Default instructions

The default identifies FruitFlyAgent as a general-purpose assistant: help the user understand, create, and solve problems; use tools when useful and keep replies concise.

## Files and integration

| File | Responsibility |
|---|---|
| [__init__.py](__init__.py) | Built-in text and lookup |
| [target.py](target.py) | `BasePromptTarget`: snapshot, validate, and prepare a trial |

Run verifies prompt contents and fixes the hash in the manifest. Skill/information augmentation is outside the base text hash. [Optimization](../optimization/README.md) searches candidates; [Run](../../run/README.md) stores them; Application manages activation. This module does not search or adopt autonomously. Loading built-ins performs no I/O and has no module-specific environment variables.

```bash
.venv/bin/python -m unittest tests.lab.test_base_prompt tests.run.test_base_prompt_flow tests.workflows.test_decoupling
```
