# Connect an MCP Server

[Up: Examples](../README.md) · [Client guide](../../fruitfly_agent/lab/mcp/README.md)

Install the optional client with `pip install -e '.[mcp]'` from the checkout.
This downloads dependencies; it does not install or launch any server.
Ordinary installations need no MCP SDK. Keep external server installations separate.

Copy and edit [the template](../configuration/mcp.example.yaml) as
`.fruitfly/mcp.yaml` only when absent. Enable `mcp-tools` in the selected profile:

```yaml
# Merge under profiles.<your-profile>.mechanisms in .fruitfly/config.yaml.
- id: mcp-tools
  enabled: true
  parameters:
    config: .fruitfly/mcp.yaml
```

The terminal configuration menu can enable the same mechanism under Tools.
Start or apply, authorize process startup, and inspect `/lab`. Each external
tool call requires its own approval; per-tool session grants are available.
Stdio runs locally even when the selected execution backend is SSH.

## Check the protocol without a model

```bash
# Explicitly permits launching all enabled servers in this local configuration.
# Calls no tool unless --call is supplied. No model request.
.venv/bin/python -m examples.mcp.probe --config .fruitfly/mcp.yaml --allow-start
```

The probe prints discovered names and startup time and closes every client.
It preserves selected schemas and can check one explicitly requested call using
`--service NAME --call REMOTE_TOOL --arguments '{"field":"value"}'`.
This explicitly grants that one call; the probe does not start an Agent session.
Accepted replies are retained under `.fruitfly/artifacts` in the chosen workspace.
Server startup and tools can have their own external effects and costs.

The probe resolves `secret_env` from its process environment; it does not load
the Agent CLI's secret file automatically.

See the [REA static JavaScript example](rea/README.md) for a separately installed
server and a small local target. No external server is part of default tests.
