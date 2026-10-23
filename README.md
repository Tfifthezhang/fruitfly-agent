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

Named after Thomas Hunt Morgan's fruit-fly research, the project favors small,
inspectable mechanisms and controlled comparisons. Its runtime is adapted from
[Pi](https://github.com/earendil-works/pi); attribution is retained below.

| At a glance | Details |
|---|---|
| Version | 0.1 |
| Runtime | Python 3.11+, macOS or Linux (POSIX) |
| Model APIs | Anthropic Messages and OpenAI Responses |
| License | [MIT](LICENSE) · [Third-party notices](THIRD_PARTY_NOTICES.md) |

## Quickstart

Run from the source checkout:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e .
.venv/bin/python -m fruitfly_agent
```

With no configured models, **Add model** collects service settings and a hidden
API key. Review and choose **Start new session** to save. Setup validates locally;
submitted tasks contact the service and may incur charges. Local shell tools run
with your user permissions. See [Getting started](GETTING_STARTED.md) for setup,
permissions and session recovery.

For an offline extension with a fake Provider:

```bash
.venv/bin/python -m examples.extensions.offline_guidance
```

Expected output: `Offline response: example-guidance is active.`
See the [walkthrough](examples/extensions/README.md).

## Choose your mechanisms

Use `/config` to select models, prompts, tools, context and execution environments
and apply saved choices to the current conversation while idle. `/lab` inspects the active runtime. `/resume` continues saved
conversation with current configuration after validating history and artifacts.
See [Configuration](CONFIGURATION.md) and [Terminal](fruitfly_agent/interactive/terminal/README.md).

Context mechanisms include Skill catalogs, file memory, local knowledge,
summarization and optional [programmatic context externalization](fruitfly_agent/lab/context_manager/externalization/programmatic_context/README.md).
Bash/file tools can use a local or SSH environment. These runtime choices do not
expand the isolated environment used by native improvement trials.

## Built for harness research

| Capability | Current behavior | Guide |
|---|---|---|
| H/S improvement | Propose, execute and compare registered instruction or retained-document changes; keep the baseline selectable | [Improvement](fruitfly_agent/lab/improvement/README.md) |
| I experiments | Compare editor instructions by the downstream H/S improvements they produce, then verify on separate task packages | [Editor experiments](fruitfly_agent/lab/improvement/improver/README.md) |
| Persistent adoption | Publish verified text candidates for explicit review and activation | [Improvement host](fruitfly_agent/run/improvement/README.md) |
| Experience | Stage attributed lessons; commit or reject separately while idle | [Experience](fruitfly_agent/lab/improvement/experience/README.md) |
| RSI | An explicitly invoked host repeats verified adoption and loads the adopted version for the next generation | [RSI](fruitfly_agent/lab/rsi/README.md) |
| Benchmark execution | Run the native Agent in Harbor containers and collect official results | [Eval](eval/README.md) |

`/improvement` selects execution, materials, editable components, generator,
exploration, feedback and scope. Preview is offline; confirmed execution may incur
charges. Native trials use in-memory file tools, without Bash, network tools or a
live Session. I experiments edit only declared editor fields at fixed nesting
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
