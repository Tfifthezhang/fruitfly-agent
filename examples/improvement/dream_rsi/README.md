# Offline DreamRSI Replay

[Up: Improvement Examples](../README.md)

Compare two bounded exploration policies on a three-node synthetic discovery tree. This demonstrates prefix-only replay and the quality/cost objective without models, external environments, files or activation.

```bash
.venv/bin/python -m examples.improvement.dream_rsi
```

The second policy scores higher on this constructed tree. That is a mechanism example, not evidence of real improvement. [__main__.py](__main__.py) contains the example; [DreamRSI](../../../fruitfly_agent/lab/improvement/methods/dream_rsi/README.md) documents real task preparation, feedback, triggering, confirmation and adoption. Real jobs can incur Provider and task-execution costs.
