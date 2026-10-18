# Tree Search

[Up: Improvement Methods](../README.md)

Search H instruction text through parent-linked attempts and save real discovery histories for [DreamRSI](../dream_rsi/README.md). This is a bounded native text-discovery implementation, not a general code/workspace search engine.

## Use the method

Start a normal session; no improvement configuration switch is required. Prepare a [task pack](../../tasks/README.md), then use `/improvement Improve task performance.`; expand **Target**, select Base prompt and then Tree search below it, and set **Task** to the saved package. Choose **Start improvement** and confirm. Model generation and task evaluation may incur cost. Discovery alone provides selection evidence, not independent confirmation.

The default policy opens new root branches. Lightweight target preparation registers the I target `tree-search.exploration-policy`. An activated policy artifact changes subsequent tree-search decisions without changing H or S. Both H discovery and the I target are available without enabling the tree-search mechanism. The policy adapter exposes `task_target_id` for discovery of task packs compatible with its underlying H execution target; this metadata does not change scoring or adoption. Target preparation reads a bound policy artifact but starts no searches or model clients.

| Material / signal | Contract |
|---|---|
| Initial target | Active instruction snapshot, retained as root |
| Tasks | Nonempty train and selection cases with declared automatic acceptance |
| Generator | Fixed `text-discovery-v1` JSON-text proposal prompt and current model |
| Feedback | Training results and selection score; failed observations have no score |
| State | Each branch inherits its parent text/history; independent task trials reset context and have no production Session |
| History | Parent-linked text, feedback, status and score; fixed task/model/initial-target/direction/generator conditions |

Use a dedicated `history_path` for each fixed task/target/model/direction context. Do not activate an H candidate if those histories are intended for DreamRSI from the original H starting point. Automatic learning workflows can change the training material; those histories are rejected when they do not match the later DreamRSI inputs.

Search guidance is optional and uses a visible text field. Empty guidance is a valid fixed discovery condition. If histories will feed DreamRSI, keep its `discovery_direction` equal to the guidance used here, including an empty value. Guidance does not change the task scorer.

## Configure budgets and policy

| Parameter | Default | Meaning |
|---|---|---|
| `rounds` | 4 | Maximum batch decision rounds |
| `workers` | 2 | Maximum concurrent attempts |
| `discovery_calls` | 8 | Maximum candidate-generation attempts |
| `history_path` | `.fruitfly/improvement/discovery` | Workspace-relative output directory |
| Shared text parameters | See [Improvement](../../README.md#parameters) | Task source, model/trial budgets and per-operation limits |

`ExplorationPolicy` is JSON with exactly `width`, `root_every`, `ranking`, and `stop_fraction`. Width is 1–16, root frequency is 1–100, ranking is best/oldest/deepest, and stop fraction is .05–1. Decisions use observed leaves or root, within worker and discovery limits. Budget preference reduces the call ceiling by the documented factor `1 - .75 * rho`; this is the native policy family, not a paper-specified universal policy representation.

Proposals and task trials share the root model/trial budget. Parallel batches cancel and drain unfinished tasks on failure. A completed prefix can be retained after budget exhaustion; interrupted model work is not replayed automatically. Complete histories are bounded to 512 nodes and 2 MB. JSON histories use exclusive file creation; malformed or incomplete records cannot be loaded as completed worlds.

## Public entries and limits

| File | Entry |
|---|---|
| [__init__.py](__init__.py), [registration.py](registration.py) | `TreeSearchImprover`, `definition()` and native assembly |
| [improver.py](improver.py) | `discover`, fixed generator and candidate ranking |
| [policy.py](policy.py) | `ExplorationPolicy`, bounded decisions and action validation |
| [history.py](history.py) | `DiscoveryNode`, `DiscoveryWorld`, load/save contracts |
| [target.py](target.py) | Object-owned I policy artifact adapter |

No generated Python is executed. Tree histories restore text and observations, not arbitrary files, tools, process state or remote services. Task scores must be nonnegative and higher-is-better. No background scheduling or autonomous adoption is installed. Dependencies are injected; there are no method-specific environment variables.

```bash
.venv/bin/python -m unittest tests.lab.test_dream_rsi tests.workflows.test_dream_rsi
```

Offline checks establish tree/replay/activation mechanics, not improvement quality.
