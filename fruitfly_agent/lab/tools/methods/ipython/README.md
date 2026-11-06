# IPython Tool

[Up: Tools](../../README.md)

`ipython-tool` owns a persistent local Python process, a content-addressed Session
artifact store and a depth-one `llm_query` bridge. It can run without externalization
or reduction. The context object offers list/stat/read/search/put and explicit
JSON save/load operations. [Programmatic context](../../../context_manager/externalization/methods/programmatic_context/README.md)
uses its public artifact-writing contract.

| File | Responsibility |
|---|---|
| [algorithm.py](algorithm.py) | Native tool contract and execution |
| [runtime.py](runtime.py) | Strict configuration and Catalog installation |
| [runtime_core.py](runtime_core.py), [kernel.py](kernel.py) | Process lifecycle and namespace |
| [artifacts.py](artifacts.py) | Hash-verified artifacts and recovery |
| [query.py](query.py) | Injected model broker and per-request limits |
| [defaults.yaml](defaults.yaml) | Description, H usage/query instructions and numeric defaults |

Model aliases come from `models.roles.context_query`. Input characters, output
tokens, cell/query time and output pages are bounded; semaphore waiting is outside
the query timeout. Usage is recorded without aggregate quotas. Non-final model
responses are rejected with their usage retained. Approved Python runs with host
user permissions and can access files/network; it is not an OS sandbox.

Each kernel owns a process session. Timeout/cancellation retires its process group
and pending host requests with bounded cleanup. Unconfirmed cleanup blocks reuse;
descendants deliberately leaving the group may survive. A successful restart has
a fresh namespace. Explicit host environment injection avoids inheriting model
keys. Complete artifacts are verified before slicing; transport lines can exceed
output preview bounds.

Offline checks: `tests.lab.test_rlm` uses local subprocesses and fake Providers.
No network or real model calls are part of those checks.
