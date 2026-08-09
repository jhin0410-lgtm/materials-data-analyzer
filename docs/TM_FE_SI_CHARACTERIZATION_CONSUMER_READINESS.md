# TM-Fe-Si characterization consumer readiness

## Purpose

This document defines the materials-data-analyzer side of the first real TM-Fe-Si cross-repository case. The upstream materials-characterization-analyzer source audit is complete, but a characterization handoff bundle does not yet exist. MDA therefore freezes what it is allowed to consume before seeing any producer-derived XRD features.

The public source is the six-composition TM-Fe-Si dataset associated with Data in Brief DOI `10.1016/j.dib.2022.108868` and Mendeley Data DOI `10.17632/gp8rkw2k6v.2` version 2.

## Current producer state

MCA source-audit merge commit `439aac38bec9cc6ce549550fc2a4b049fd1fb61c` established the source/workbook identities and scientific boundaries for the uploaded 13-workbook subset. That audit does **not** yet constitute a characterization handoff.

The strongest defensible cross-modal identity is nominal composition plus shared preparation/batch family. XRD was measured on powdered material while magnetometry used bulk material, so exact physical specimen identity is unresolved and must not be invented.

## Consumer use boundary

MDA requests **descriptive** use only.

Allowed after a valid MCA handoff exists:

- display of source-backed characterization features;
- descriptive comparison of XRD peak-position evidence across the six nominal compositions;
- descriptive magnetic summaries from MDA-owned dc-magnetization and M-H tables;
- cross-modal summaries joined only through frozen stable nominal-composition/preparation-family identities.

Not authorized:

- absolute XRD intensity comparison across compositions, because the public figure-data patterns contain integer plotting offsets;
- phase assignment from the uploaded XRD-only subset, because the uploaded subset omits the SEM/EDS evidence used by the publication;
- association screening, predictive modeling, causal interpretation, or engineering decisions;
- row-order, spreadsheet-row, filename-position, or unverified exact-specimen joins;
- copying raw Excel workbooks into MDA.

## Why the import is intentionally not ready

The repository already contains `mda-characterization-import` and the downstream characterization-use policy. A second integration mechanism would duplicate existing behavior and weaken the trust boundary.

This case therefore keeps `mda_characterization_import_ready=false` until MCA freezes a descriptive XRD handoff contract and emits a checksum-bound producer bundle. MDA will then build the magnetic-property consumer table independently and bind it to producer rows only through the frozen stable identities.

This is a deliberate correct-stop state, not an incomplete software workaround.

## Magnetic-data provenance requirements

The consumer table must preserve:

- dc magnetization field of 100 Oe;
- the 50–400 K VersaLab measurement segment;
- the separate high-temperature VSM segment for Zr and Hf rather than silently treating the full trajectory as one instrument series;
- temperature and field coordinates as physical join/sort keys inside trajectories rather than spreadsheet row positions;
- unresolved derivation provenance for workbook-provided `dM/dT` values.

No derived Curie temperature, coercivity, remanence, or other magnetic summary should be promoted to source truth without a separately documented extraction/validation rule.

## Scientific closeout

Current MDA readiness is **Diagnostic preparation only**:

- public source and MCA source audit: supported;
- future descriptive XRD consumption: admissible after a valid handoff;
- exact cross-modal specimen identity: inconclusive;
- absolute XRD intensity comparison: unsupported;
- current cross-modal case execution: not ready because the producer handoff is absent;
- predictive, causal, and engineering use: unsupported/not authorized.

## Next action

The next cross-repository dependency is upstream: MCA must freeze and emit a narrow descriptive XRD handoff with stable nominal-composition/preparation-family identities and the integer-offset limitation. Once that bundle exists, MDA should consume it through the existing `mda-characterization-import` path and only then construct the descriptive XRD–magnetism case.
