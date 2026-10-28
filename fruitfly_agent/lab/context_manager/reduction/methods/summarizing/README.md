# Summarize continuity

[Up: Reduction](../../README.md)

`SummarizingCompactor` implements `ContextReducer`. `SummarizingCompactorConfig`
owns strict defaults. `registration.py` declares `compaction`; `prompts.py`
contains its default editable `summary_instructions`.

Before each main request, trigger at `trigger_ratio` of the available input
budget. Reserve the main output, measurement margin and an additional
`min(reserve_tokens, window / 4)` independently. Reactive reduction progressively
shrinks retention within Core's recovery allowance.

Prefer user boundaries. When an autonomous turn outgrows retention, allow cuts
between completed tool batches, preserving that turn's user instruction. Never
split a call/result pair. Check signed-prefix constraints before auxiliary work;
Core checks again after hooks and before commit.

Every character of public summary input is processed in sequential pages, merging
the previous page's summary. `history_char_limit` and `per_message_char_limit`
bound page size; the auxiliary model window can reduce it further. `max_pages`
defaults to 64 pages per proposal; the 120000-character page default supports
large working windows. The page allowance remains finite.
`summary_attempts` bounds transient request attempts
per page. Page exhaustion, failure, blank/truncated/non-final output or an
oversized final projection preserves the old context. There is no head/tail
omission fallback. Original serialized source and prior references remain
retrievable from immutable artifacts.

H candidates may tune instructions, thresholds, retention, paging, output and
retry limits, timeout and estimator. `enabled` and fixed `prompt_version` are protected target fields;
component selection remains a configuration decision. Exact prompts and all
effective defaults enter runtime identity. No private learning state is retained.
Auxiliary requests use the injected Provider and any root call budget it carries.

Offline tests verify behavior and limits, not summary fidelity or task quality.
See [shared checks](../../README.md#extend-a-method).
