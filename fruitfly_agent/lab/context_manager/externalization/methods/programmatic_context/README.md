# Programmatic Context

[Up: Externalization](../../README.md)

H `rlm-ipython` replaces large projected text with a stable content-addressed
reference. Canonical Session messages stay intact. It requires `ipython-tool` to
provide the shared [artifact writer](../../../resources/artifacts.py) capability.
The method consumes that contract rather than owning a Python process.

| File | Responsibility |
|---|---|
| [algorithm.py](algorithm.py) | Strict offload configuration and installation |
| [projection.py](projection.py) | Idempotent reference projection |
| [defaults.yaml](defaults.yaml) | H usage instructions and threshold |

The [IPython tool](../../../../tools/methods/ipython/README.md) owns the kernel,
artifact store and depth-one auxiliary query bridge. H instructions and offload
thresholds use ordinary parameter candidates; model bindings and transport
integrity remain protected. Recovery verifies stored references before activation
and starts a fresh Python namespace. Explicit JSON state can be reloaded.

The design adapts external input and symbolic inspection from Zhang et al.,
[Recursive Language Models](https://arxiv.org/abs/2512.24601v3), Section 2.
Unrestricted recursion, unlimited output and paper benchmark gains are not
implemented. Offline checks: `tests.lab.test_rlm`, `tests.lab.test_parameter_candidates`.
