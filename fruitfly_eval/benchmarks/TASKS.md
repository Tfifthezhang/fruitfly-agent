# Select Benchmark Tasks

[Up: Benchmark Adapters](README.md)

Harbor tasks contain `instruction.md`, `task.toml` and an `environment/` definition.
Shared verifiers use `tests/test.sh`; independent verifiers own their test environment.
Multi-step tasks can override verifier settings and build contexts. Optional
`solution/` material is for task validation, not Agent input. Official verifiers
check resulting state and write rewards.

## Choose a registered dataset

These are declarations only; preparation and execution use the same public Harbor
integration for every entry. See the [server guide](../SERVER_GUIDE.md) for the
shared setup procedure.

| ID | Dataset | Exact smoke task |
|---|---|---|
| `terminal-bench` | `terminal-bench/terminal-bench-2-1` | `terminal-bench/fix-git` |
| `terminal-bench-4` | `terminal-bench/terminal-bench@4.0.0` | `terminal-bench/interleaved-vigenere` |
| `swe-bench` | `swe-bench/swe-bench-verified` | `swe-bench/psf__requests-1142` |

## Choose one of three selections

| Variant | Meaning |
|---|---|
| `smoke` | One exact declared task, preserving its original resources |
| `no_gpu` | Exclude GPU requirements in effective Agent, Verifier, step and Compose-service definitions |
| `full` | Every resolved task with its declared resources |

Use `prepare --tasks-only` before image downloads/builds to inspect selected and
excluded tasks, role/step requirements, exact local image references and build
contexts. Absence of a GPU requirement cannot be established for external Compose
includes or service inheritance; `no_gpu` excludes these conservatively and records
why. Undeclared resource needs in scripts or external services remain unverified.
No fixed task counts or benchmark-specific CPU lists drive this filtering.

Selection records identify registry versus local scope. A local directory does
not prove official dataset coverage. Only the frozen selected task set determines
required result coverage: every selected task must appear exactly once per attempt.
Missing, unexpected or duplicate attempts fail the report and suppress aggregates.
A single smoke validates its execution path, not a representative dataset score.

## Preserve task and image identity

Task images do not replace host-side instructions, configuration and verifier
material. Resolve tasks through Harbor's public dataset API or export a flat local
collection. `task_directory` accepts one task or immediate `<task>/task.toml` children.
Nested downloaded revision caches must be exported first. `@version` pins a dataset
revision; unversioned declarations resolve during preparation.

Preparation preserves content hashes, explicit setup diffs and actual image
identities. Full repository references, including digests, must resolve locally;
a short tag or matching image ID alone is insufficient. Keep instructions, scoring,
resource declarations and digests unchanged. Shared dependency setup and exact
`tests/` patches belong to the machine contract, not benchmark-specific code.

Keep preparation and job artifacts for comparisons. See
[Harbor preparation](../harbor/README.md) and [Eval results](../README.md#inspect-results).
