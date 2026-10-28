# Estimate text and images

[Up: Measurement](../../README.md)

[estimator.py](estimator.py) implements `chars_div_4` and `heuristic_cjk`. It
estimates CJK text separately and charges a fixed image allowance for user and
tool-result images. It is not a tokenizer and does not decode images or opaque
continuation. The shared measurement service adds framing, schemas, calibration
and uncertainty margins.

The parent module's H target exposes `token_estimator`, `chars_per_token`, margins
and calibration bounds. Neither estimates nor calibrated ratios become exact.
See the [measurement checks](../../README.md).
