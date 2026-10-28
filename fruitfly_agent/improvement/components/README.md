# Component Registry

[Up: Improvement Runtime](../README.md)

`registry.py` owns `ComponentRegistry`. Register adapters with distinct stable IDs,
validate complete snapshots and owner-granted options, and reject conflicting
publication bindings. The registry imports no concrete adapter or configuration
system. It cannot change ownership or make a declared file executable.

[Lab adapters](../../lab/improvement/components/README.md) implement legal changes.
Catalog declares available owners; runners declare capabilities; Run owns storage
and activation. Each grant is validated before work and against every candidate.

Offline checks: `tests.lab.test_harness_inventory`,
`tests.lab.test_parameter_candidates`, `tests.workflows.test_decoupling`.
