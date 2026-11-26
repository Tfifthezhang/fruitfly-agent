# Launch the native Agent from external hosts

[Up: Eval](../README.md)

A host bridge adapts its engine's public Agent interface to ordinary FruitFlyAgent
CLI execution. `native.NativeInvocation` constructs the argument vector from a
frozen system file, selected profile, instruction and retained Session path.
It does not translate model connections to generic API parameters, resolve keys,
choose a scorer or alter H/S/I components. Providers consume the complete model
configuration through the normal runtime assembly.

The host owns environment preparation, argument quoting, cancellation and
resource cleanup. Instructions remain a single literal argument after `--`.
Absolute container Python/configuration/Session paths are validated before launch.
The existing Harbor bridge consumes this same invocation contract while retaining
its supervisor, process cleanup and evidence capture responsibilities.

| File | Responsibility |
|---|---|
| `native.py` | Complete configuration and Session CLI invocation |
| `model_access.py` | Model transport grants, direct endpoint allowlists and private trial mount identity |

Offline checks: `tests.eval.test_native_bridge` and the existing
`tests.eval.test_harbor_agent` bridge tests. Native command construction does not
prove real container/model compatibility.

Unix relay mounts are read-only and contain only one trial's communication
directory. The host sets traversal/socket permissions; inference requires the
separately delivered owner-only bearer grant. Account credentials stay on the host. TLS transports
retain certificate/hostname validation and require independent network reachability.
No model name or benchmark selects request headers in this layer.
