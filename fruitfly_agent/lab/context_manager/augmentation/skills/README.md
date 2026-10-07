# Skills

[Up: Augmentation](../README.md)

Give the model task-specific instructions it can read when needed. A Skill is an instruction file, not a Python plugin or tool.

## Create a Skill

```text
<workspace>/.skills/code-review/
├── SKILL.md
└── references/checklist.md
```

```md
---
name: code-review
description: Use when asked to review code for reproducible bugs, error handling, and missing tests.
---

# Code review

1. Read the target code and relevant tests.
2. Report concrete defects with file locations and reproduction steps.
3. Read references/checklist.md when detailed criteria are needed.
```

The description helps the model decide when to read the full file. Use UTF-8, start with YAML frontmatter, and keep reference paths relative to the Skill directory.

## Enable and use

| Action | Behavior |
|---|---|
| Enable **Configure → mechanisms · context-manager → skill-catalog** | Keep **read-tool** enabled, save, and start a new session. |
| Submit a matching task | The model sees names, descriptions, and paths, then may use `read` to load instructions. |
| Modify a Skill | Start a new session to rescan. |
| Set `disable-model-invocation: true` | Hide it from the model; there is no separate manual Skill command. |

Reading and following a Skill remains model-driven; visibility does not guarantee invocation.

| Parameter | Default | Meaning |
|---|---|---|
| `root` | `.skills` | Directory within the active workspace; `--cwd` selects that workspace. |
| `max_chars` | `16000` | Complete rendered catalog budget; oversized blocks become an explicit omitted notice. |

## Loading and limits

| Rule | Behavior |
|---|---|
| Discovery | Recursive `SKILL.md`; root-level Markdown also loads, but separate Skill directories are preferred. |
| Nested Skills | Once a Skill directory is found, its nested `SKILL.md` files are not separate entries. |
| Hidden entries / symlinks | Hidden entries skipped; all descendant symlinks skipped. |
| Scan budget | 4096 enumerated entries including hidden entries; depth 32; 1 MiB/file; 8 MiB total read |
| Invalid files | Per-file I/O/UTF-8 diagnostics; malformed frontmatter may fall back to an empty description. |
| Over-limit enumeration | Retain loaded entries; selection can depend on filesystem enumeration order. |
| Rendered context | XML-escaped metadata, not full Skill text; repeated requests replace the owned block. |

Scanning is synchronous and does not isolate filesystem permissions or concurrent edits. No module-specific environment variables.

## Check offline

```bash
.venv/bin/python -c 'from fruitfly_agent.lab.context_manager.augmentation.skills import load_skills, render_skills_xml; result = load_skills(".skills"); print(render_skills_xml(result.skills)); print(result.diagnostics)'
.venv/bin/python -m unittest tests.lab.test_skill_catalog -v
```

Use the actual workspace's Skill path if running elsewhere. Resolve diagnostics before relying on the catalog.

## Files and extension points

| File | Responsibility |
|---|---|
| [catalog.py](catalog.py) | `Skill`, `LoadResult`, discovery, and XML rendering |
| [adapter.py](adapter.py) | `SkillCatalogTransformer`; bounded augmentation |
| [target.py](target.py) | `SkillGuidanceTarget`; snapshot, validation, and temporary trials |

The named target `skill-catalog.guidance` can replace rendered catalog text through an explicit artifact binding. It does not change or snapshot `SKILL.md` bodies or references. An empty catalog is a valid baseline; published replacement text must be nonempty and fit the projection budget. See [Optimization](../../../optimization/README.md) and [Run artifacts](../../../../run/README.md#text-artifacts).
