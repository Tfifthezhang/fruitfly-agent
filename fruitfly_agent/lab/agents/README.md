# Invoke an Agent Role

[Up: Lab](../README.md)

`AgentRunner` composes one independent invocation over Core `run_agent_loop`.
Callers supply configuration, messages, tools, instructions, cancellation and
observation callbacks. It owns no editing, assessment, adoption or scheduling policy.

By default each invocation starts with supplied history/tools and no ambient
Session or steering. An explicitly supplied `PreparedAgentRuntime` retains its
host-owned Session, hooks, context pipeline and optional `run_loop`. Model and tool counts are observations; the
caller owns its stage time. Providers and injected services remain caller-owned.

| File | Responsibility |
|---|---|
| `runner.py` | Core invocation and attributed request/response observations |
| `__init__.py` | Public `AgentRunner` entry |

[Child execution contracts](subagent/README.md) separately describe host-managed
execution identity and resource ownership. The optional prepared-runtime path uses the same Core loop.

Editors and evaluators provide their own tools and result validation. No model
request occurs during construction. Explicit invocation can incur model cost.

Offline check: `tests.lab.test_agent_runner`.

Failed role invocations retain Core error details in `agent-finished` observations,
so a research report can distinguish Provider failure from submission rejection.

## Run managed child conversations

[Subagent](subagent/README.md) adds parent-scoped scheduling, explicit identities,
private Sessions, steering, bounded execution and monitoring. An explicit prepared runtime lets research roles use that scope without another
Agent loop. The caller owns startup/retirement; AgentRunner records requests and
results through the same observation callbacks.
