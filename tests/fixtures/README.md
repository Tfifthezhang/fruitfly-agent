# Offline Process Fixtures

[Up: Tests](../README.md)

`mcp_server.py` is a standard-library JSON-RPC peer launched only by optional
MCP client tests. It supports current and legacy negotiation, pagination,
deterministic replies, cancellation, catalog change and injected failures.
It reads stdin and writes protocol messages to stdout. Optional PID files stay
inside the test's temporary directory. No network, external server or model call.

Use [tests.support.mcp](../support/mcp.py) for its path and temporary configuration.
Run the [MCP tests](../../fruitfly_agent/lab/mcp/README.md#extend-and-verify-offline)
through unittest; this fixture is not an independent test suite.
