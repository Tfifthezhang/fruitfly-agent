# Threshold Maintenance

[Up: Methods](../README.md)

Generate explicit memory changes after original user characters or completed turns reach thresholds. No time gate is used. The host supplies evidence, model bindings and persistence. `algorithm.py` proposes; it cannot commit. `config.py` validates bounds; `registration.py` exposes H policy and I prompts. `defaults.yaml`, `extraction.yaml` and `consolidation.yaml` own their values.

The input window is bounded. Long user messages are paged without changing their
source identity; all pages succeed before processing advances. Consolidation
visits bounded groups of notes and protects notes outside each group. An individual
note or complete extraction catalog exceeding the input budget fails explicitly. When both triggers are due, existing content is consolidated first.
No-change output is valid; malformed output never clears notes. Cancellation and unknown outcomes retain evidence. Calls may incur charges.
