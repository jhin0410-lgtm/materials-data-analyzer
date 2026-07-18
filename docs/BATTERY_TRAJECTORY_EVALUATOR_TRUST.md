# Battery Trajectory Evaluator Trust

Status: `execution_valid_interpretation_restricted`

Trust is separated into distinct boundaries rather than collapsed into a
generic confidence score.

- Representation trust: schema, Ah units, strict ordering, one-cell lineage,
  and reference policy were checked. One short trajectory was blocked and
  cycle gaps remain explicit warnings.
- Execution trust: the evaluator is bounded and deterministic. Repeated actual
  execution produced the same canonical result checksum.
- Scientific interpretation trust: findings describe observed cycle-index
  patterns only. Source measurement uncertainty is unavailable, and detection
  thresholds do not replace it.
- External validity: the evidence is limited to the current 34-cell source;
  no independent or production validation was performed.

The resulting decision is
`descriptive_evaluator_executed_with_restrictions`. Successful execution does
not promote the underlying trajectory representation to a validated physical
mechanism, and it does not unblock the v2.3.3 Arrhenius, diffusion, or
resistance-growth conclusions.

v2.3.5 preserves this decision and adds policy-stability evidence. Across nine
predeclared threshold, reference, window, and gap configurations, 211 of 489
consolidated descriptive events were stable across all eligible policies; 97
were stable with restrictions, 50 were policy-sensitive, and 131 had
insufficient support. This does not identify a mechanism. See
[Battery Evaluator Stability Audit](BATTERY_EVALUATOR_STABILITY_AUDIT.md).
