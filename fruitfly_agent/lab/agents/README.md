# Invoke an Agent Role

[Up: Lab](../README.md)

`AgentRunner` composes one independent invocation over Core `run_agent_loop`.
Callers supply configuration, messages, tools, instructions, cancellation and
observation callbacks. It owns no editing, assessment, adoption or scheduling policy.

Each invocation starts with its supplied history and tools, without an ambient
Session or interactive steering. Model and tool counts are observations; the
caller owns its stage time. Providers and injected services remain caller-owned.

| File | Responsibility |
|---|---|
| `runner.py` | Core invocation and attributed request/response observations |
| `__init__.py` | Public `AgentRunner` entry |

Editors and evaluators provide their own tools and result validation. No model
request occurs during construction. Explicit invocation can incur model cost.

Offline check: `tests.lab.test_agent_runner`.
