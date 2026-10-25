# Experiments

[Up: Runtime Architecture](../README.md)

Start fixed-version Eval, Improvement searches and durable RSI independently of
chat. Use `fruitfly-agent-lab`, or `python -m fruitfly_agent.experiments` from a
checkout. Without arguments, an interactive terminal offers operation and action
selection. Redirected input prints help. Settings are edited in files only.

## Configure a workspace

From an existing empty workspace, generate editable files without a model request:

```bash
fruitfly-agent-lab init
# Optional benchmark task-set scaffold; catalog ID is data, not optimizer logic.
fruitfly-agent-lab --cwd /path/to/another-workspace init --source task-set --benchmark terminal-bench-4
```

`init` creates `.fruitfly/default-config.yaml`, `default-models.yaml`,
`experiment.yaml` and an empty-key `secrets.env`. Task-set initialization also
creates `eval-request.json` and `eval-host.yaml`. `--variant` selects `smoke`
(default), `no_gpu` or `full`. It validates the catalog ID without preflight,
downloads, Providers or containers. Native initialization works without Eval.
The workspace directory must already exist. Use `--json` for the created paths
and next steps.

Existing configuration destinations cause an error before writing. Existing
daily files are untouched; an existing regular `secrets.env` is preserved without
reading it. New files use mode 0600 and a new `.fruitfly` directory uses 0700.
Symlink destinations are rejected. Ordinary write failures remove files created
by this invocation; concurrent configuration writers and abrupt process failure
are not a transaction. Installed packages contain the templates, so initialization
does not depend on a source checkout. Edit model settings and credentials before
checking; host path variables also require a prepared Linux runtime.

See the [native walkthrough](../../examples/experiments/README.md#start-a-native-experiment)
and [remote benchmark walkthrough](../../examples/experiments/TB4_SERVER.md).
The files can also be created manually:

Prepare `.fruitfly/default-config.yaml`, its referenced model catalog and the
workspace secret environment using the [configuration templates](../../examples/configuration/README.md).
Defaults are editable; the chat configuration menu does not edit experiment files.
An explicit Agent configuration is also supported. Missing defaults fail without
falling back to daily chat settings.

Create `.fruitfly/experiment.yaml`:

```yaml
schema_version: 1
task:
  source: files
  instruction: Produce a concise inventory of the supplied source material.
```

For a benchmark workspace with existing request and host files:

```yaml
schema_version: 1
task:
  source: eval
  request: ../request.json
  host: ../host.yaml
```

Relative paths resolve from this YAML file. The benchmark request's runtime paths
retain Eval's workspace-relative semantics. `--cwd` selects the workspace, and
`--config` selects an experiment file, not an Agent configuration. An explicitly
missing file is an error. Without a file, built-in defaults apply, but explicit
task material or `--request` is still required. Unknown and duplicate fields fail.

```bash
fruitfly-agent-lab improvement check
# Executes models and may incur charges.
fruitfly-agent-lab improvement run
```

`check` reads local inputs and validates references, model selections, credential
presence and applicable material/budget rules. It constructs no Providers and
makes no model request. Benchmark checks inspect existing preparation and exercise
the actual runtime staging function in a temporary directory; they do not prepare
or start task containers. Connectivity and real quality remain unverified.
`run` starts explicitly without a second chat confirmation.

## Choose operation and source

| Operation | Commands | Meaning |
|---|---|---|
| `eval` | `catalog`, `prepare`, `check`, `run`, `list`, `report ID`, `stop ID` | Execute one fixed Agent configuration |
| `improvement` | `check`, `run`, `list`, `report ID`, `stop ID` | Propose and compare registered component changes |
| `rsi` | `check`, `run`, `list`, `report ID`, `stop ID`, `resume ID` | Verify, adopt and continue with the adopted version |

| Task source | Fields | Execution |
|---|---|---|
| `files` | `instruction`, optional `input_paths`; alternatively `pack` | Fresh in-memory read/write/edit workspace; no Bash or inherited chat environment |
| `editor` | Installed `material` ID, optional `parameters` | Fixed-depth downstream I comparison with private task packages |
| `eval` | `request`, `host`, optional `model_calls` | Prepared Harbor benchmark through the optional Eval adapter |
| `task-set` | `collections` of registered sources | Shared candidates, sampled common batches, bounded task parallelism and joint selection |

File inputs must remain inside the workspace. Packages own their inputs and must
not be combined with replacement instructions/files. Ordinary conversations do not
produce materials automatically. See [examples](../../examples/experiments/README.md).

Improvement is independent of RSI. RSI uses Improvement and verified adoption.
Eval optionally supplies executions and official measurements; ordinary Eval never
starts search. A single benchmark reward supports development comparison, not
independent adoption. The CLI rejects benchmark RSI without an independent
verification implementation. Native RSI requires a task package with holdout;
I RSI requires an independent editor experiment. H/S/I and future component
builders retain their existing public boundaries; arbitrary code deployment is
not implemented.

## Override only what matters

| Section | Fields and defaults |
|---|---|
| `runtime` | `config` defaults to workspace `.fruitfly/default-config.yaml`; optional harness `profile`; explicit Eval references must agree |
| `models` | Optional `editor` and `assessor`; native tasks also allow `executor`: model-catalog entry names, never credentials or duplicate endpoints |
| `improvement` | `strategy: simple`, `components: [base_prompt]`, `rounds: 1`, `feedback: auto`, `scope: task`, `retain_experience: false` |
| Search allocations | `max_model_calls: 256`, `max_executions: 16`, `operation_timeout: 1200`, `timeout_seconds: 3600` |
| Harness² settings | `strategy: harness2`, `mode: parallel` or `sequential`, `width: 1`, `rounds: 1` |
| `component_options` under `improvement` | Registered component-owned field permissions and bounds; only selected IDs |
| `process_assessment` | `assessors: []`, `max_model_calls: 16`, `timeout_seconds: 120`, `required: false`; completed executions only |
| `exploration` | `policy: incumbent`; optional `process-guided` requires a comparison-capable completed assessor |
| `rsi` | `max_generations: 3`, `max_model_calls: 768`, `max_executions: 64`, `timeout_seconds: 10800`, `phase_timeout: 3600`, `continue_on_rejection: false`, `policy: auto` |
| `stop` | Optional `improvement` and `rsi` declarative policies |
| `multi_task` | Task-set-only sampling, execution, evaluation and promotion settings; see the joint template |

The executor is selected by the default Agent profile. Editor and assessor
independently inherit it unless a role is explicitly selected; the Agent profile's
declared auxiliary choices remain available. Read-only assessment is a separate
service even with the same model. Programmatic official scoring needs no judge
model. For Eval sources, select the executor/configuration in the shared
Agent profile; conflicting explicit runtime references and executor overrides are
rejected rather than silently changing benchmark conditions. Editor/assessor
overrides apply to Improvement/RSI.
See [file responsibilities and model-role examples](../../examples/experiments/README.md#select-models-by-role)
for adding a model and selecting it without changing other roles.

Editor experiments default to `improvement-editor`, 512 model calls and 256 leaf
executions unless explicitly overridden. Their inner strategy defaults to `simple`;
`task.parameters.inner_strategy` can select Harness². Material size determines the
required budget. Defaults are allowances, not predicted usage or quality evidence.

`simple` performs one reference and one candidate execution per default search,
without a composition or reflection request. More rounds follow the official
incumbent unless an explicit exploration policy chooses another completed seed.
Harness² retains its contrastive schedule. Reflection is opt-in and
retained experience still requires separate review. Selection does not grant
independent verification. RSI uses one total ledger across generations; nested
work does not reset it. Calls count harness Provider invocations, not SDK retries
or arbitrary task-shell HTTP requests. Charges and missing usage remain distinct.

Stop conditions use existing [termination policies](../lab/improvement/termination/README.md):

```yaml
stop:
  improvement:
    any:
      - {type: iterations, limit: 3}
      - {type: no_improvement, patience: 2}
```

`resource` and `score` are also available; `all` composes conditions. Custom
policies replace default search stopping, including its repetition/generator-stop
checks. The round/generation cap, empty candidate pool, budget, deadline and
cancellation remain effective. Conditions run after a round or generation, not
before the first candidate or as an in-flight execution control. Search scores
have `selected` assurance; a score goal must explicitly select it and match the
measurement policy ID. It does not grant independent verification.

Ordinary search supports `failures` using consecutive non-completed executions
and `metric` using enabled final completed-process assessments. Zero reward is
not an execution failure. Persistent RSI rejection is not a counted failure; its
standard generation state supplies neither these process assessments nor a numeric
proof-reuse score. Native `task.parameters.assessment_interval` records separate
online assessments and does not connect them to search stopping or live replacement.

## Enable completed-process feedback

```yaml
process_assessment:
  assessors: [execution-facts-v1, completed-model-v1]
  max_model_calls: 16
  timeout_seconds: 120
  required: false
exploration:
  policy: process-guided
```

`execution-facts-v1` exposes recorded counters without a model or quality score.
`completed-model-v1` uses `models.assessor` for cited judgments and comparison of
granted evidence. `process-guided` can choose a next editing seed even when official
scores tie; the reported winner still follows official selection. Defaults keep
assessment disabled and follow the incumbent. No live changes are made.

The assessor allowance covers judgments and comparisons together per search,
inside its root budget. Optional unavailable judgments/comparisons retain the
incumbent; `required: true` stops with `assessment_unavailable`. Budget exhaustion
and cancellation still propagate. Unknown counters remain unknown, and failed
artifact collection is not treated as confirmed absence. See [assessment](../lab/improvement/assessment/README.md)
for validation, bounded full-evidence reading and extension ports.

Task tool limits belong to the executed Agent profile:
`execution.max_tool_calls_per_turn` defaults to 64 and accepts nonnegative
integers. It is separate from model allowances and the editor's 48-tool bound.
`check` prints the effective task limit. See [configuration](../../CONFIGURATION.md#bound-task-tool-calls).

The [annotated single-task reference](../../examples/experiments/benchmark.example.yaml)
and [joint task-set reference](../../examples/experiments/multi-task.example.yaml)
list fields, choices, bounds and disabled recipes. Model specifications, Agent
mechanisms and task scorers remain in their owning files.

## Prepare benchmarks

```bash
# May download/build task dependencies and start preparation containers; no model requests.
fruitfly-agent-lab eval prepare --tasks-only
fruitfly-agent-lab eval prepare
fruitfly-agent-lab eval check
# Models and official verification; may incur charges.
fruitfly-agent-lab eval run
fruitfly-agent-lab improvement run
```

The adapter defaults to 80 model calls per execution and derives a bounded host
under `.fruitfly/experiments/prepared/`. It preserves the original host. Full
preparation must match that derived host and current runtime implementation. There
is no silent download/rebuild at search startup. The benchmark Improvement adapter
requires one prepared task, one attempt and concurrency one for a single-task
source. A `task-set` source selects exact individual tasks from larger preparations
and controls parallelism in its shared scheduler. Ordinary
Eval can retain its declared multiple tasks/attempts. See [Eval](../../eval/README.md)
and its [Improvement adapter](../../eval/improvement/README.md).

## Inspect records and stop safely

```bash
fruitfly-agent-lab improvement list
fruitfly-agent-lab improvement report '<RUN_ID>' --json
fruitfly-agent-lab improvement stop '<RUN_ID>'
fruitfly-agent-lab rsi resume '<RUN_ID>'
```

Each run has a small index at `.fruitfly/experiments/runs/<id>/record.json`, including
resolved configuration, default version, source hashes, links, charged allowance
and stopping outcome. Listings scan these records; no duplicated global index is
authoritative. Full evidence remains under `.fruitfly/eval/`,
`.fruitfly/improvement/` and `.fruitfly/evolution/` respectively.

Improvement/RSI stage a separate Agent configuration and model catalog inside the
run directory. RSI adopts into that experiment copy; daily and baseline profiles
remain unchanged. The copy stays editable by the activation host while the original
file hashes remain recorded; the selected profile and exact model catalog are
staged, not a complete environment/source backup. Running jobs keep frozen inputs.
Reports/lists do not require live models or a valid current experiment file.

`stop` writes a request to the locked live owner, which interrupts only its own
process and uses existing cancellation/cleanup. Exit 1 means pending or interrupted,
not confirmed cleanup. A stale record is never permission to kill a reused PID.
RSI resume reuses the experiment copy, rejects changed conditions, restores root
usage/deadlines and delegates uncertain-phase handling to the persistent driver.
Unknown paid work is not automatically replayed. One process owns a run.

`--json` prints structured summaries/results; `--events jsonl` emits lifecycle and
search progress. Exit 0 means command completion (including rejected RSI proposals),
1 an incomplete execution/pending stop, 2 a configuration/command error, 3 blocked execution,
and 130 interruption. None is a quality certificate.

## Files and offline checks

| Files | Own |
|---|---|
| `cli.py`, `menu.py`, `presentation.py` | Arguments, selection and views |
| `scaffolding.py`, `templates/` | Offline initialization and installed public template resources; no runtime assembly |
| `configuration.py`, `sources.py`, `policies.py` | Strict file parsing, source definitions and policy construction |
| `composition.py` | Public runtime/Eval assembly and model-role resolution |
| `validation.py` | Unified offline harness, component permissions and staging checks |
| `operations/` | Independent Eval, Improvement and RSI lifecycles |
| `records.py` | Run index, ownership and scoped stop requests |

```bash
.venv/bin/python -m unittest discover -s tests/experiments -t .
```

Tests use fake Providers and task executors. They do not establish real API,
Docker or benchmark quality. No new credential environment variables are required.

## Optimize a shared task set

Use `task.source: task-set` and `collections`, with separate `multi_task` settings.
The [joint reference](../../examples/experiments/multi-task.example.yaml) declares
all defaults, alternatives and limits. Sources currently include installed native
packs and prepared Eval tasks. New material/backends use public source and runner
ports; no task-set name selects an optimizer algorithm.

`check --json` lists frozen task keys, partitions, collection coverage and minimum
allowance. Nondefault `multi_task` settings on another source are rejected. Native
packs preserve their private splits. Benchmark leaf requests share this workspace,
Agent configuration and executor profile; outer attempts/concurrency are separate
from their required one-attempt, one-concurrent leaf request.

Defaults are stratified-cycle sampling of up to eight tasks, task concurrency two,
one candidate, one attempt, equal collection-macro utility and promotion every
three rounds plus final selection. Each collection contributes its selection
split, or all its development tasks when absent. Missing results prevent promotion.
Search batch utility is distinct from full-selection utility. Next seeds can
follow a shared-batch winner or declared process comparison while formal results
retain the full common comparison requirement.

Root allowances default to twice the material-derived minimum, with floors of
256 model calls and 16 leaf executions. Explicit finite positive totals override
them and must fund initial probes and protected final selection. Batch plans can
exceed single-task allocation ceilings. Defaults are not predicted usage.
SDK retries, external grader model calls and monetary cost remain separate.

Task-set search currently requires simple/scored/task mode and disables experience
retention. Confirmation tasks stay private and unused. Persistent scope/RSI need
an independent adoption implementation and are rejected for these development-only
sources. `eval run` remains a fixed-version single-request operation; `eval prepare`
can prepare all Eval sources declared by a task set. See [Task sets](../lab/improvement/task_sets/README.md).

## Check one resolved harness

`check --json` includes `harness`: enabled normalized mechanisms, configured tools,
execution values, component owners, backend capabilities and each component's
available/selected state and reason. Text checks display the same inventory.
Enabled does not mean editable; `improvement.components` grants modification
permission. Explicit absent or unsupported selections fail. No automatic mechanism
activation or state creation repairs them.

Run and Eval share the [runtime specification](../runtime_spec/README.md). An
experiment runtime reference and an explicit Eval request reference must agree.
Omitted request references inherit the experiment baseline. Task collections share
that baseline; their backend capabilities are intersected for joint editing.

`improvement.component_options` supplies registered component-owned field
permissions and bounds. Options name selected components only, are checked offline
and frozen in each search plan. See [execution policy](../lab/execution_policy/README.md)
for a complete scalar configuration example. Models, authorizers, task sets,
grading and total experiment budgets remain outside that candidate edit scope.
