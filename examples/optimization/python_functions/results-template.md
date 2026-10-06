# Python Function Results

[Up: Python Function Optimization](README.md)

No live experiment is recorded here. Enter actual observations; do not substitute reference implementation scores.

| Condition | Value |
|---|---|
| Model profile / exact ID | |
| Pack source hash | |
| Policy / executor identity | |
| Baseline prompt hash | |
| Candidate ID / hash | |
| Snapshot / search journal | |
| Repeats / seed / budgets | |
| Calls / failures / timeouts / missing usage | |

| Holdout case | Baseline passed / total | OPRO passed / total | Raw output / failure |
|---|---|---|---|
| holdout-001 run_lengths | | | |
| holdout-002 transpose | | | |
| holdout-003 rotate_left | | | |
| holdout-004 compact_dict | | | |
| holdout-005 decode_query | | | |
| holdout-006 longest_streak | | | |

| Measurement rule | Meaning |
|---|---|
| Primary metric | Mean check-pass fraction across six cases, equal weight |
| Supplemental metric | Fully passing cases / 6 |
| Missing/failed model answer | Zero in this manual comparison; record the reason and raw evidence. |
| Session setup | Same model, new empty session per case, input only |
| Selection scores | Record separately from independent holdout scores. |

Keep every repeat and failure. This small example does not establish general capability gains. See [example instructions](README.md).
