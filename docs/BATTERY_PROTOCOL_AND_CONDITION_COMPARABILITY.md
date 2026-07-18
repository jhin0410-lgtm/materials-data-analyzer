# Battery Protocol And Condition Comparability

Status: `v2.3.3_completed`

The current source contains ambient temperature metadata and per-cycle scalar
summaries, but it does not provide a complete explicit protocol identity,
C-rate, cutoff, rest-period, or controlled-temperature protocol contract.

Protocol comparability status:

- Overall: `insufficient_protocol_metadata`
- C-rate metadata: missing
- Explicit protocol identifier: missing
- Rest-period metadata: missing
- Current/voltage summaries: available as observations, not full protocol

Temperature-condition status:

- Ambient temperature groups exist.
- Ambient metadata is not sufficient by itself as controlled Arrhenius
  temperature evidence.
- Measured operating temperature summaries are responses, not automatically
  controlled experimental conditions.

Therefore temperature/capacity correlations must not be promoted to Arrhenius
evidence or causal temperature effects.

## v2.3.5 Source Recovery Update

Nine local source protocol documents now map exactly to all 34 cells and
provide group-level charge/discharge, temperature, cutoff, and impedance-sweep
context. All 2,495 analysis-ready cycles also have observed current, voltage,
temperature, and duration summaries. This improves lineage and descriptive
context but does not establish cycle-specific commanded conditions for
variable-condition groups. The v2.3.3 comparability decision therefore remains
unchanged.
