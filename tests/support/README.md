# Shared Test Support

[Up: Tests](../README.md)

Reusable substitutes and temporary materials. This module contains no TestCases or discovery logic and never imports `test_*.py`.

| File | Provides |
|---|---|
| [provider_streams.py](provider_streams.py) | Offline SDK streams, requests, and patched adapter construction |
| [terminal_process.py](terminal_process.py) | Bounded real POSIX terminal child processes without network/model access |
| [faux_provider.py](faux_provider.py) | Scripted responses, errors, and request capture |
| [loop.py](loop.py) | Core configuration and counting tools |
| [materials.py](materials.py), [run.py](run.py) | Models, tasks, CLI input, and temporary sessions |
| [task_packs.py](task_packs.py) | Text/Python pack fixtures |
| [application.py](application.py) | Offline Sessions, RuntimeFactory substitutes, and Applications |
| [terminal.py](terminal.py), [configuration.py](configuration.py) | Finite input, TTY streams, fixed completion events, and configuration controller substitutes |
| [optimizers.py](optimizers.py), [search.py](search.py) | Replaceable optimizers, problems, services, and input queues |
| [evaluation.py](evaluation.py), [harbor.py](harbor.py) | Offline requests and isolated Harbor protocol |

Keep local helpers local unless multiple tests need them. Do not compute reviewed expected values from implementation helpers. Production code must not import support. Its consumers verify behavior; it has no separate execution command or key requirements.
