# Integration boundary

The core runtime MUST NOT import provider SDKs. Provider adapters implement the protocols in `base.py`.
Recommended activation order: LiteLLM model gateway → research adapter → retrieval adapter → DSPy optimizer → statistical calibration.
Every adapter is admitted only after an A/B benchmark shows a measurable gain on a named metric.
