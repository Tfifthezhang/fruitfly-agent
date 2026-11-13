# Select Representative Cases

[Up: Evidence Selection](../../README.md)

`RepresentativeSelector` reserves successful official controls, prioritizes rare
signals, and fills task rounds within a case limit and a per-task limit. Signals
include execution failure, official zero/negative reward, elapsed time, model-call
count, execution tool-start count, execution input/output token thresholds and
missing diagnostics. Turn/composite usage and reported subtotals never count as
execution token totals. Receipt completion alone never proves success.
Unknown scoring directions remain uninterpreted. All threshold defaults live in
`defaults.yaml`; Python validates integer bounds and control reservations.

This is an offline triage heuristic, not a reproduction of a published RSI
algorithm or proof of a cause. It does not rank raw tokens across incompatible
accounting scopes. Unknown facts and omitted executions remain explicit. No
Provider, mutable learning state or external service is required.
