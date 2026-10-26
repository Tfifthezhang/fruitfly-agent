# Analyze a Local JavaScript Fixture with REA

[Up: MCP examples](../README.md) · [Client guide](../../../fruitfly_agent/lab/mcp/README.md)

REA is an independent MCP server. FruitFlyAgent adds no REA code, Node dependencies,
native engines or installation hooks. This example selects one static analysis tool
and a small source fixture; it does not execute the target JavaScript.

## Prepare the external installation

Use an independently installed REA version whose catalog includes
`analyze_javascript_application`. The template follows REA 6.4.0's executable and
configuration contracts. That release declares Node `^22.19.0 || ^24.11.0 || >=26.0.0`.
For example, install that exact version into a separate prefix:

```bash
# Network download and a separate external installation; run only when desired.
npm install --prefix /absolute/path/to/rea-install rea-agents@6.4.0
```

Follow [REA's installation instructions](https://github.com/morluto/rea) for its
dependency requirements. Source checkouts need their own install/build; a checkout
without generated distribution files is insufficient. This source fixture does
not require Ghidra, IDA, Hopper, Frida or a browser. Other REA operations have their
own engines and deployment requirements; installing them is a separate decision.

## Configure only the selected operation

Copy [mcp.example.yaml](mcp.example.yaml) to `.fruitfly/mcp.yaml` only when absent,
or merge its service into the existing file. Replace both absolute executable
paths and the directory. The `node` command invokes REA's installed `scripts/rea.mjs`
with the `mcp` subcommand. No `npx` download occurs on Agent startup.
`REA_MCP_INPUT_SCHEMA_PROFILE=compact` uses REA's own compact declarations;
FruitFlyAgent preserves those schemas without removing validation constraints.

Enable `mcp-tools`, review startup and inspect `/lab`. Ask the Agent to call the
selected operation with the absolute path to `fixture/` from this example.
A direct no-model check is also available:

```bash
# Starts the independently installed service and explicitly permits one static call.
# Replace the fixture path with this checkout's absolute path.
.venv/bin/python -m examples.mcp.probe --config .fruitfly/mcp.yaml --allow-start \
  --service rea --call analyze_javascript_application \
  --arguments '{"input_path":"/absolute/path/to/fruitfly-agent/examples/mcp/rea/fixture","format":"auto","integrity_policy":"fail"}'
```

The probe reports a reply artifact and whether REA marked it as an error. Inspect
the artifact for findings and evidence. During a normal Agent session, large
responses remain complete in artifacts and have a bounded display plus a paging
tool. Tools and source paths use the local host, even with SSH execution selected.

## Verification limits

Default tests verify the client with a local protocol peer. The real REA process,
its resource usage, this selected tool's output and model endpoint schema acceptance
require the explicit external check above; they are not established by fixture
tests or by reading REA's declared contracts. REA installation and native engine
costs are independent of the optional Python client.
