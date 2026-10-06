# Interactive Tests

[Up: Tests](../README.md)

Verify Application state/lifecycle, resource cleanup, events, menus, commands, and terminal I/O.

| Files | Protects |
|---|---|
| `test_terminal.py / test_menu.py` | Configuration, optimization, candidate review, confirmations, and navigation |
| `test_evaluation.py` | Generic Eval menu and complete diagnostic display |
| `test_line_editor.py` | PTY input, explicit TERM, and redirected fallback |

Local PTYs and fake models. Assembly/CLI belong to Run; complete multi-module paths belong to Workflows.

```bash
.venv/bin/python -m unittest discover -s tests/interactive -t . -v
```
