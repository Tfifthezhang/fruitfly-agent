# Installed Package Checks

[Up: Examples](../README.md)

[check_installed.py](check_installed.py) checks the installed runtime outside the source checkout. It uses the first-run model wizard with a placeholder key, the existing offline extension example, a fixed Python function, an IPython subprocess, a wheel source snapshot and a fake prepared Harbor environment. It makes no network or model requests and creates only temporary local files.

It also initializes native and benchmark experiment workspaces from packaged
templates and checks the native configuration offline. This guards against an
initializer that works only while `examples/` is present in the working directory.
The wizard accepts its registered SDK/protocol selections and persists the two
fields separately, without constructing a model client.

Build and install a wheel following [Contributing](../../CONTRIBUTING.md#build-and-publish). Run the script with the wheel environment's Python from a directory outside the checkout:

```bash
cd /tmp
/tmp/fruitfly-wheel/bin/python /path/to/fruitfly-agent/examples/packaging/check_installed.py /path/to/fruitfly_agent-0.1-py3-none-any.whl
```

Replace both `/path/to/` paths with actual paths. The environment must have the declared runtime dependencies installed. The script rejects imports from the checkout; it does not verify real Docker installation, benchmark downloads, or model quality. [CI](../../.github/workflows/tests.yml) runs this check after installing the wheel in a fresh environment.
