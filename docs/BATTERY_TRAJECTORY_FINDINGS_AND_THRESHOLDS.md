# Battery Trajectory Findings And Thresholds

Status: `v2.3.4_completed`

The v2.3.4 thresholds are deterministic detection rules fixed in
`configs/examples/battery_capacity_trajectory_evaluator.json` before actual
execution. They are not measurement uncertainty or confidence intervals and
were not optimized after viewing findings.

For capacity `q_i` and reference capacity `q_ref`, retention is
`r_i = q_i / q_ref`. Adjacent differences are evaluated only when the cycle
gap is one. A larger gap creates a `missing_cycle_gap` finding and is excluded
from abrupt-change and fixed-window slope interpretation. No gap is converted
to seconds or hours.

The robust scale is `1.4826 * MAD(delta r)`. The abrupt-change threshold is
the larger of the configured absolute floor `0.005` and six times that scale.
A zero-MAD trajectory therefore falls back to the absolute floor. The 5-point
plateau window uses a maximum retention range of `0.01`. Acceleration and
deceleration candidates compare fixed 5-transition median slopes with a
preconfigured shift boundary of `0.0025`; adjacent candidate windows are
merged deterministically.

Other fixed descriptive boundaries are a robust variability scale of `0.01`
and terminal observed retention of `0.8`. The latter is not an end-of-life or
failure definition.

Positive capacity changes may reflect recovery, protocol or temperature
context, measurement variability, or another unresolved influence. The
evaluator records the observation and does not choose among those causes.
Likewise, plateau and accelerated/decelerated findings do not establish stable
electrochemistry, a knee point, or a physical degradation regime.
