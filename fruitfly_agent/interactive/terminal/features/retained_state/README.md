# Inspect retained state

[Up: Terminal Features](../README.md)

[commands.py](commands.py) registers `/memory` and `/skills` using injected public
Application callbacks. [views.py](views.py) renders retained entries and status, pending batch
IDs, source counters and maintenance errors. Inspection makes no model calls.

Use `read ID` for a retained document, or `commit UPDATE` / `reject UPDATE` for a
pending batch. Application guards writes while busy. Commit refreshes the runtime
with the same conversation. Human review expresses adoption, not independent
quality verification. These commands do not install external packages.

`/memory retry OPERATION` explicitly acknowledges an unknown call outcome and permits
another potentially paid maintenance request. New input alone cannot authorize replay.
