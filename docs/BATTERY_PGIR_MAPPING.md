# Battery PGIR Mapping

Status: `v2.3.2_completed`

v2.3.2 maps existing processed battery cycle summaries into PGIR-compatible
representation metadata without downloading data or recomputing battery
models.

## Source

The pilot uses the tracked Kaggle NASA battery processed discharge summary:

`data/processed/kaggle_nasa_battery_cycle_summary_analysis_ready.csv`

Current audited coverage:

- cells: `34`
- cycle rows: `2,495`
- selected source status: `actual_processed_summary_available`
- uncertainty: source measurement uncertainty unavailable

## Representation Mapping

- Cycle row -> `MeasurementSeriesEntity` as PGIR Observation metadata.
- Observation -> `StateEntity` as bounded operational state summary.
- Ordered per-cell states -> `TrajectoryEntity` as cycle-index trajectory
  metadata.

Capacity, retention, and temperature values are retained as source-reported or
deterministically derived quantities with explicit units. Missing measurement
uncertainty is recorded as unavailable, not zero.

## Claim Boundary

This mapping does not create complete electrochemical State, Field,
mechanism-ready parameter, diffusion readiness, Arrhenius evidence, SOH/RUL
model input evidence, or production battery-degradation claims.

## v2.3.3 Mechanism-Audit Link

The v2.3.3 mechanism audit reuses this mapping as evidence, but it does not
promote cycle Observations or bounded operational State summaries into latent
electrochemical State or concentration Field records. Requirement gaps remain
explicit when geometry, boundary conditions, physical time, or protocol
metadata are missing.
