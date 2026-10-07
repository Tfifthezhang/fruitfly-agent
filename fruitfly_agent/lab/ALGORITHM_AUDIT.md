# Known Limitations

[Up: Lab](README.md)

Current implementation limits. Offline tests verify covered behavior; they do not establish model quality, research gains, or every algorithm combination.

| Area | Verified behavior | Remaining limit |
|---|---|---|
| [Providers](../providers/README.md) | Request output limits, adapter retries, cancellation, and stream cleanup | Harness call budgets do not count individual HTTP retries or guarantee monetary cost. |
| [Tools](tools/README.md) | UTF-8 truncation, bounded read/bash bodies, edit span validation, and Core per-turn batch allowances | Reads load whole files; images and other errors lack a shared size budget; hints are outside body limits. |
| [Environment](environment/README.md) | Working directory, prompt process return, chunked decoding, and live callbacks | File I/O is synchronous; complete stdout/stderr remain in memory; broad exception conversion can obscure programming errors. |
| [Skills](context_manager/augmentation/skills/README.md) | Bounded scan, skipped descendant symlinks, per-file decoding diagnostics | Synchronous I/O and concurrent edits; over-limit enumeration may choose different entries across filesystems. |
| [Information](context_manager/augmentation/information/README.md) | Citations and bounded rendered retrieval blocks | Whole directory enumeration and synchronous reads; no total retrieval deadline; expiry clock is not injected. |
| [Live HTTP](context_manager/augmentation/information/live_http/README.md) | HTTPS, redirect/type/size checks, and injected fetch tests | Cancelling an await does not stop its worker thread; I/O timeout is not a whole-operation deadline. |
| [Programmatic context](context_manager/externalization/programmatic_context/README.md) | Artifact access, query budgets, process close, and explicit state restoration | Slice reads verify whole artifacts; output is transported before truncation; hard-cancel/task cleanup and queue deadlines are incomplete. |
| [Reduction](context_manager/reduction/README.md) | Reject invalid summaries; preserve complete turns, tool associations, and external references | Heuristic token estimation and unverified summary fidelity. |
| [Optimization](optimization/README.md) | Text search, candidate evidence, adoption, and recovery | No automatic holdout run, code deployment, arbitrary learning-state restoration, or cross-process adoption transaction. |

File mutation locks coordinate only this process and do not identify backend namespaces. Fuzzy matching is textual, not semantic. Information recall does not expose the complete set of source errors.

```bash
.venv/bin/python -m unittest tests.lab.test_algorithm_audit -v
.venv/bin/python -m unittest discover -s tests -t .
```
