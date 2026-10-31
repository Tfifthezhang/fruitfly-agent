# Harness² Strategy

[Up: Search Strategies](../README.md)

Adapt the contrastive Propose–Probe–Compose schedule from
[Harness²: Recursive Agent Harnessing for an Open World](https://arxiv.org/abs/2610.14224).
`strategy.py` owns invariant/domain mission pairing, reference width and composition
count. Shared services own execution, evidence, phase times, comparison and verification.

Parallel width `k` runs `k` references, `2k` proposals and `k` compositions when each
proposal supplies one candidate. Sequential depth `k` chains those contrastive
steps using the selected incumbent by default. A separately configured
[exploration policy](../README.md#choose-the-next-editing-seed) can choose another
completed seed while preserving official selection. All successful outputs remain selectable.
The parallel pool is currently awaited sequentially. Reflection is optional.

Select `improvement.strategy: harness2`, then `mode`, `width` and `rounds` in an
experiment file. These are strategy-specific settings, not required task fields.
No published scores, generalization guarantees or unrestricted code edits are
claimed. Offline tests are `tests.lab.test_improvement_pipeline` and
`tests.lab.test_search_strategies`.
