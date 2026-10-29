<p align="center">
  <img src="assets/logo.svg" alt="FruitFlyAgent fruit-fly logo" width="144" height="144">
</p>
<p align="center">
  <img src="https://img.shields.io/badge/version-0.1-cc9046?style=flat-square" alt="Version 0.1">
  <img src="https://img.shields.io/badge/python-3.11%2B-3776ab?style=flat-square" alt="Python 3.11 or newer">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-587f62?style=flat-square" alt="MIT license"></a>
</p>

# FruitFlyAgent

[Quickstart](#quickstart) · [Configuration](CONFIGURATION.md) · [Architecture](fruitfly_agent/README.md) · [RSI](fruitfly_agent/lab/rsi/README.md) · [Contributing](CONTRIBUTING.md)

**An interactive Python Agent harness with replaceable algorithms and explicit improvement experiments.**

FruitFlyAgent runs model/tool conversations, compares changes to registered Agent
components, and supports bounded experiments on the editor that proposes those
changes. Core owns the Agent loop; Lab owns algorithms; Application owns lifecycle;
Run assembles them. Eval is an optional external benchmark consumer.

Daily systems, experiment baselines and candidates share one H/S/I component
configuration. Start at the [configuration guide tree](CONFIGURATION.md#navigate-the-configuration-tree)
to write a config, register a component or declare bounded experiment changes.

Named after Thomas Hunt Morgan's fruit-fly research, the project favors small,
inspectable mechanisms and controlled comparisons. Its runtime is adapted from
[Pi](https://github.com/earendil-works/pi); attribution is retained below.

| At a glance | Details |
|---|---|
| Version | 0.1 |
| Runtime | Python 3.11+, macOS or Linux (POSIX) |
| Model APIs | Responses, Chat Completions and Messages; service then protocol setup with automatic SDK selection |
| Image input | Local attachments, image tool results and optional resource saving; requires a declared vision model. See [Run](fruitfly_agent/run/README.md#submit-images). |
| License | [MIT](LICENSE) · [Third-party notices](THIRD_PARTY_NOTICES.md) |

## Quickstart

Run from the source checkout:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e .
.venv/bin/python -m fruitfly_agent
```

With no configured models, **Add model** collects service settings and a hidden
API key. Review, stage, then choose **Save and start**. With complete settings,
the CLI enters the welcome and chat directly. Use `/config` during chat or
`fruitfly-agent --configure` before startup to edit settings. Setup validates locally;
submitted tasks contact the service and may incur charges. Local shell tools run
with your user permissions. See [Getting started](GETTING_STARTED.md) for setup,
permissions and session recovery.

For an offline extension with a fake Provider:

```bash
.venv/bin/python -m examples.extensions.offline_guidance
```

Expected output: `Offline response: example-guidance is active.`
See the [walkthrough](examples/extensions/README.md).

For independent experiments, generate editable defaults with
`.venv/bin/fruitfly-agent-lab init`, configure the model/key, then run
`improvement check` before `improvement run` (model charges may apply).
See [native setup](examples/experiments/README.md#start-a-native-experiment) or
the [remote Linux TB4 walkthrough](examples/experiments/TB4_SERVER.md).

## Choose your mechanisms

Use `/config` to select models, prompts, tools, context and execution environments
and apply saved choices to the current conversation while idle. `/lab` inspects the active runtime. `/resume` continues saved
conversation with current configuration after validating history and artifacts.
See [Configuration](CONFIGURATION.md) and [Terminal](fruitfly_agent/interactive/terminal/README.md).

Optional [MCP tools](fruitfly_agent/lab/mcp/README.md) connect independently
installed local stdio servers with `fruitfly-agent[mcp]`. Startup and tool calls
have separate approval. See the [REA example](examples/mcp/rea/README.md); no
external server or native analysis engine is bundled.

Context mechanisms include Skill catalogs, file memory, local knowledge,
summarization and optional [programmatic context externalization](fruitfly_agent/lab/context_manager/externalization/programmatic_context/README.md).
Bash/file tools can use a local or SSH environment. These runtime choices do not
expand the isolated environment used by native improvement trials.

Welcome, `/lab` and `/status` show the local workspace separately from the active
file/Bash environment, including the SSH server and remote directory when used.
Chat uses native terminal scrollback; temporary menus restore it on return.

## Built for harness research

| Capability | Current behavior | Guide |
|---|---|---|
| Improvement runtime | Independent stage kernel with injected algorithms, accounting, failure boundaries and evidence retention | [Runtime](fruitfly_agent/improvement/README.md) |
| H/S improvement | Propose, execute and compare registered instructions, permitted execution parameters or retained documents; keep the baseline selectable | [Improvement](fruitfly_agent/lab/improvement/README.md) |
| I experiments | Compare supported editor, feedback and search changes by downstream H/S behavior, then verify on separate task packages | [Editor experiments](fruitfly_agent/lab/improvement/improver/README.md) |
| Persistent adoption | Publish verified text candidates for explicit review and activation | [Improvement host](fruitfly_agent/run/improvement/README.md) |
| Experience | Stage attributed lessons; commit or reject separately while idle | [Experience](fruitfly_agent/lab/improvement/experience/README.md) |
| RSI | An explicitly invoked host repeats verified adoption and loads the adopted version for the next generation | [RSI](fruitfly_agent/lab/rsi/README.md) |
| Benchmark execution | Run the native Agent in Harbor containers and collect official results | [Eval](eval/README.md) |

Use the independent [experiment CLI](fruitfly_agent/experiments/README.md) for Eval,
Improvement and RSI. File settings have bounded defaults; `simple` proposes one
candidate, while Harness² remains optional. `/improvement` retains a small explicit
task/material entry and result review. Preview is offline; execution may incur
charges. Native trials use in-memory file tools, without Bash, network tools or a
live Session. I experiments edit only registered fields at fixed nesting
depth. They do not train model weights or replace arbitrary source code.

Output selection is not independent verification. Tests with fake Providers prove
covered control flow, not real model gains. Task packages are explicitly authored;
ordinary chat does not collect training material. See [task preparation](fruitfly_agent/lab/improvement/tasks/README.md).

## What you can do

| Task | Start here |
|---|---|
| Install, configure, run or resume | [Getting started](GETTING_STARTED.md) · [Configuration](CONFIGURATION.md) |
| Use remote file and shell tools | [SSH environment](fruitfly_agent/lab/environment/ssh/README.md) |
| Add or replace an algorithm | [Lab development](fruitfly_agent/lab/README.md#develop-an-algorithm) |
| Prepare an improvement experiment | [Examples](examples/improvement/README.md) · [Task packs](fruitfly_agent/lab/improvement/tasks/README.md) |
| Start Eval, Improvement or RSI | [Experiment CLI](fruitfly_agent/experiments/README.md) · [File templates](examples/experiments/README.md) |
| Run Terminal-Bench or SWE-bench | [Eval](eval/README.md) |
| Change and verify the implementation | [Contributing](CONTRIBUTING.md) · [Tests](tests/README.md) |

## Project layout

| Directory | Responsibility |
|---|---|
| [fruitfly_agent/](fruitfly_agent/README.md) | Runtime architecture and module entry points |
| [eval/](eval/README.md) | Optional benchmark execution and reports |
| [examples/](examples/README.md) | Runnable extensions and task packs |
| [tests/](tests/README.md) | Offline contracts, architecture and behavior checks |
| [AGENTS.md](AGENTS.md) | Engineering rules for AI-assisted development |

## Contribute

Read the [architecture](fruitfly_agent/README.md), the affected module guide and
[Contributing](CONTRIBUTING.md). Keep algorithm decisions in Lab and lifecycle
in Application. Update public behavior, tests and documentation together.

```bash
.venv/bin/python -m unittest discover -s tests -t .
```

## License

FruitFlyAgent is released under the [MIT License](LICENSE). See [Third-party notices](THIRD_PARTY_NOTICES.md) for attribution and upstream licenses.

## Acknowledgments

| Source | Contribution |
|---|---|
| [Pi](https://github.com/earendil-works/pi) | Runtime design and adapted Agent loop, Session, and tool infrastructure; code attribution and the upstream license are recorded in [Third-party notices](THIRD_PARTY_NOTICES.md). |
| [Harness²](https://arxiv.org/abs/2610.14224) | Evidence-driven component editing, Propose–Probe–Compose and cross-task experience; [implemented scope](fruitfly_agent/lab/improvement/README.md). |
| [Prime Agent](https://github.com/PrimeIntellect-ai/prime-agent) | Inspiration for externalizing context into a programmable Python environment; see [Programmatic context](fruitfly_agent/lab/context_manager/externalization/programmatic_context/README.md). |

Research sources and the scope of each adaptation are documented in the corresponding algorithm modules.

## Understand Improvement, RSI and Eval

| Capability | Responsibility |
|---|---|
| Improvement | Search, execute, assess and compare changes to registered H/S/I components |
| RSI | Adopt eligible changes and continue with the adopted version |
| Eval | Execute a fixed version on benchmarks; optionally supply an external runner and official assessment |

Improvement/RSI are independent of Eval. Daily and file tasks use their declared
backends. `eval run` does not implicitly improve the Agent. See
[architecture](fruitfly_agent/README.md#separate-search-evolution-and-evaluation)
and the optional [benchmark adapter](eval/improvement/README.md).

[Online assessment](fruitfly_agent/lab/improvement/assessment/README.md) can inspect
intermediate events. Explicit control policies may request supported actions;
phase judgments alone do not prove improvement or activate a version.
