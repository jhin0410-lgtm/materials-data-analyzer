# Materials Structure Predictive Value

Status: `v2.2.5_complete`

v2.2.5 evaluates whether actual known-structure descriptors add incremental
predictive value beyond composition-only descriptors for the existing Materials
Project validation cohort.

## Evidence Hierarchy

Primary evidence:

- reduced-formula group split
- chemical-system group split

Secondary reference:

- random split, interpreted as optimistic only

The decision does not use test labels for feature selection, target migration,
or threshold selection. Preprocessing is fit within training folds only.

## Paired Comparisons

The tracked paired summary records positive values when the candidate feature
set improves the baseline:

- A vs D: baseline composition compared with baseline plus structure
- B vs E: composition physics compared with full combined features
- C vs D: structure-only compared with baseline plus structure
- D vs E: baseline plus structure compared with full combined features

The actual decision is `structure_predictive_value_limited`, not a broad
structure-aware success. Structure descriptors improved one primary group split
only and did not justify selecting a representative model.

## Boundary

The result is a bounded known-structure descriptor comparison. It is not:

- a pre-structure Materials screening result
- a physics-constrained model
- a hybrid physics-ML model
- a graph neural network result
- a mechanistic explanation
- a claim that current API targets replace the original target snapshot

The v2.2.1 composition-feature conclusion remains preserved as
`performance_degraded`.

## v2.2.6 Closeout

The closeout promotes no model. `structure_predictive_value_limited` remains
the canonical status, graph artifacts remain representation-only, and the
current Materials Project target remains audit-only rather than a replacement
label.
