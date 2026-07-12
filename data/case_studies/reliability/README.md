# Reliability Case Study Planning

Status: `contract_stage` for v1.5.1, `access_gate_complete` for v1.5.2,
and `full_year_readiness_stage` for v1.5.3.

This folder defines the generic reliability/risk use-case boundary for future
asset-level case studies. It does not contain downloaded reliability raw data,
trained models, survival estimates, RUL predictions, or production maintenance
recommendations.

In short, this folder does not contain downloaded raw data.

## Primary Scope

The v1.5 primary question is:

> Can asset history and condition data available up to an observation cutoff be
> used to evaluate future failure risk or time-to-event while preserving
> censoring and temporal order?

This scope is broader than binary classification but narrower than production
maintenance decision automation. It is intended to support future readiness
audits, leakage checks, temporal and asset-disjoint validation design, and
trust-boundary reporting.

## Problem Taxonomy

- Binary failure classification: failure within a fixed horizon.
- Remaining useful life regression: remaining time or cycle target, with final
  event information separated from prediction-time features.
- Time-to-event / survival analysis: event time with right, interval, or
  administrative censoring where available.
- Recurrent event analysis: repeated failures after repair or replacement,
  requiring a clock-reset policy.
- Maintenance decision support: offline prioritization framing only, not causal
  maintenance-effect estimation.
- Degradation trajectory analysis: sensor, capacity, wear, or health-index
  trajectories using only past measurements.

Contract scaffolding was implemented in v1.5.1. v1.5.2 added a bounded
Backblaze access gate and compact readiness audit. v1.5.3 adds full-year
streaming normalization and event/censoring readiness reassessment, but still
does not train models.

## Dataset Candidate Decision

Candidate assessment lives in
[`dataset_candidates_v1_5.csv`](dataset_candidates_v1_5.csv).

Current decision:

- `backblaze_drive_stats`: `conditional_primary_candidate`
- `nasa_cmapss`: `operational_backup_candidate`
- `nasa_n_cmapss`: `secondary_fixture`
- `nasa_ims_bearing`: `secondary_fixture`
- `femto_pronostia`: `secondary_fixture`
- `uci_ai4i_2020`: `secondary_fixture`
- `battery_archive_existing`: `rejected`
- `uci_secom_existing`: `rejected_for_primary`

The Backblaze drive data is the preferred reliability candidate because it has
explicit asset identifiers, repeated observations, dates, condition variables,
and observed failures. It was not downloaded in v1.5.1. v1.5.2 verified
bounded access and file structure for the 2013 archive. v1.5.3 then processed
the full archive into a local-only analysis-ready trajectory table and compact
readiness summaries.

NASA C-MAPSS is retained as a benchmark backup for RUL methodology, but it is a
simulation benchmark rather than real-world operational evidence.

## v1.5.2 Access Gate and Readiness Result

Backblaze remains the active candidate after the v1.5.2 bounded access gate.
The script uses the official `data_2013.zip` archive, keeps the raw ZIP
local-only under `data/raw/reliability/backblaze_drive_stats/`, lists archive
members without full extraction, and reads five representative daily CSV
members for schema/readiness reconnaissance.

Compact observed results:

- bounded sample rows: 96,838
- bounded sample columns: 86
- independent assets: 28,767
- observed failure rows: 10
- selected primary task: `binary_horizon_failure`
- readiness verdict: `conditionally_ready`

Survival, RUL regression, and recurrent event analysis remain `not_ready`.
Censoring is interpreted conservatively as administrative last observation in
the bounded sample, not as a completed operational survival audit.

## v1.5.3 Full-Year Normalization Result

The v1.5.3 full-year audit streams the official 2013 Backblaze archive member
by member. It does not extract raw daily CSV files and does not commit the raw
archive or the large row-level analysis-ready table.

Compact observed results:

- valid daily CSV files: 266
- excluded archive members: 269
- date range: 2013-04-10 to 2013-12-31
- normalized rows: 5,091,501
- assets: 29,072
- multi-observation assets: 29,058
- failure rows / failed assets: 724 / 724
- post-failure anomaly assets: 7
- compatible schema signatures: 1
- SMART feature columns: 80
- selected primary task: `binary_horizon_failure`
- recommended horizon / lookback: 7 days / 7 days
- overall readiness verdict: `conditionally_ready`

The 7-day horizon has 4,892,482 eligible prediction rows and 4,797 positive
labels. Asset-disjoint, chronological, and combined asset-disjoint future
splits are `conditionally_ready`; random row split remains an optimistic or
prohibited reference, not primary evidence.

Censoring is still uncertain: non-failure asset exits may reflect administrative
end of archive, removal, retirement, or other unobserved causes. Survival
analysis is therefore only conditionally ready for a future survival-specific
censoring audit. RUL regression and recurrent event analysis remain `not_ready`.

## Contract and Leakage Map

- [`reliability_contract_v1_5.json`](reliability_contract_v1_5.json) defines
  required and preferred reliability fields, censoring/event policy, validation
  hierarchy, metrics, trust vocabulary, allowed claims, prohibited claims, and
  stop conditions.
- [`leakage_map_v1_5.csv`](leakage_map_v1_5.csv) lists common reliability
  leakage patterns such as final cycle count, future degradation windows,
  full-lifetime normalization, random row splits mixing assets, and post-event
  maintenance actions.
- [`acquisition_spec_v1_5.json`](acquisition_spec_v1_5.json) and
  [`acquisition_manifest_v1_5.json`](acquisition_manifest_v1_5.json) record
  the v1.5.2 Backblaze access gate, source metadata, SHA policy, local-only raw
  archive policy, and compact readiness result.
- [`normalization_spec_v1_5.json`](normalization_spec_v1_5.json) and
  [`full_year_manifest_v1_5.json`](full_year_manifest_v1_5.json) record the
  v1.5.3 full-year member inclusion, schema harmonization, local analysis-ready
  output policy, event/censoring treatment, and readiness conclusion.

## Relationship to Existing Case Studies

Battery Archive v1.1 already covers battery degradation trajectories and
capacity-derived threshold proxies. v1.5 should avoid simply repeating that
case study.

Smart Factory v1.4 covers process-quality classification with time-aware
validation and trust-boundary closeout, but SECOM lacks explicit asset,
maintenance, and recurrent-event structure. v1.5 should focus on asset-level
reliability data rather than another process-quality table.

## Non-Goals

v1.5.1 does not perform:

- data download or API access
- model training
- survival modeling
- Weibull fitting
- RUL regression
- hyperparameter tuning
- feature engineering from actual raw data
- SHAP or causal maintenance analysis
- dashboarding
- main merge, tag, or release

v1.5.3 also does not perform classifier training, survival modeling, RUL
regression, Weibull fitting, rolling feature generation, feature selection, or
production maintenance decision automation.

## Roadmap

- v1.5.1: generic reliability contract, candidate assessment, leakage map, and
  readiness scaffold.
- v1.5.2: dataset access gate for Backblaze, bounded schema reconnaissance,
  leakage-schema audit, and compact readiness outputs.
- v1.5.3: full-year analysis-ready normalization, event/censoring integrity,
  horizon/lookback feasibility, split feasibility, and task readiness
  reassessment.
- v1.5.4: fixed baseline validation if the data passes readiness gates.
- v1.5.5: trust-boundary closeout and conservative documentation.
