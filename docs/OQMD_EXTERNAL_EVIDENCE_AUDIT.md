# OQMD external-evidence audit

## Purpose

This note records the first real candidate evaluation under the generic external-evidence contract. The candidate is OQMD v1.8 and the requirement is the frozen Materials Project v1.3 Fe/Si source-disjoint phase-stability requirement.

This is a source-screening exercise only. It does not retrieve OQMD target rows, fit a model, compare predictions, or create external-validation evidence.

## Frozen Materials Project target

The benchmark target remains `energy_above_hull` in eV/atom for the already frozen Materials Project Fe/Si-containing, 2-5 element scope. The benchmark-v1 locked test and exposed policy results are not reused for candidate selection or retuning.

A matching property name and unit are insufficient. Direct external evidence additionally requires compatible thermodynamic reference states, correction semantics, convex-hull construction, competing-phase inventory, and structure/composition identity.

## OQMD evidence checked

Authoritative OQMD documentation establishes:

- OQMD v1.8 was updated in February 2026;
- the database is maintained by the Wolverton Research Group at Northwestern University, independently of the Materials Project source system;
- OQMD data are licensed CC BY 4.0;
- the REST API exposes persistent `entry_id` records and `stability` as distance from the convex hull in eV/atom;
- standard calculations use VASP 5.3.2, PBE-GGA, and VASP PAW-PBE potentials;
- OQMD phase-diagram formation energies use elemental reference states combining DFT elemental energies with fitted elemental-phase reference energies and corrections associated with DFT+U treatment;
- OQMD uses qhull for its convex-hull phase-diagram construction.

Authoritative Materials Project documentation establishes that current MP thermodynamic data use Materials Project-specific energy corrections and GGA/GGA+U/r2SCAN mixing logic. These conventions are not interchangeable with the OQMD fitted-reference/correction scheme.

## Disposition

For the current direct source-disjoint external-validation requirement:

- source-system independence: supported at the database/provenance level;
- availability: supported;
- reuse permission: supported;
- high-level target concept: compatible (`distance above convex hull`);
- target unit: compatible (`eV/atom`);
- thermodynamic reference-state semantics: **confirmed mismatch**;
- energy-correction semantics: **confirmed mismatch**;
- exact Fe/Si candidate inventory, competing-phase inventory, hull-input equivalence, and cross-source structure mapping: not evaluated because the confirmed semantic mismatch already blocks direct target equivalence.

Therefore the deterministic contract disposition is:

**`scientifically_ineligible` for this requirement.**

This means OQMD must not be downloaded, fitted, or reported as direct external validation for the frozen Materials Project target. It does not mean OQMD is scientifically poor or unusable. A separate cross-database diagnostic study could explicitly ask how stability rankings or qualitative conclusions change across thermodynamic conventions, but that would be a different research question and evidence claim.

## Reproduction

After generating the local Materials Project external-evidence requirement:

```powershell
& $python `
  .\scripts\audit_materials_project_external_source_candidates.py `
  --requirement .\outputs\materials_project_external_evidence_requirement_v1\external_evidence_requirement.json `
  --output .\outputs\materials_project_external_source_candidate_audit_v1
```

The tracked registry now contains multiple high-priority candidates. The OQMD-specific expectations remain:

- OQMD disposition: `scientifically_ineligible`;
- OQMD mismatches: `thermodynamic_reference_state`, `energy_correction_semantics`;
- OQMD source-system independence: satisfied;
- OQMD eligibility for this requirement: false.

For the current whole-registry expected counts and search closeout, see `MATERIALS_PROJECT_EXTERNAL_SOURCE_SEARCH_CLOSEOUT.md`.

The audit itself must continue to report:

- network access: false;
- target retrieval: false;
- model fit: false;
- external-validation authorization: false.

## Authoritative references

- https://www.oqmd.org/download/
- https://www.oqmd.org/documentation/overview
- https://www.oqmd.org/documentation/vasp
- https://www.oqmd.org/analysis/phase_diagram/
- https://static.oqmd.org/static/docs/restful.html
- https://docs.materialsproject.org/methodology/materials-methodology/thermodynamic-stability/thermodynamic-stability
- https://docs.materialsproject.org/methodology/materials-methodology/thermodynamic-stability/thermodynamic-stability/gga-gga%2Bu-r2scan-mixing

## Scientific closeout

**Evidence level: Diagnostic.**

The strongest evidence is the authoritative documentation of incompatible energy-reference/correction conventions. The primary limitation is that no cross-database row-level comparison is performed; this is intentional because the mismatch already makes direct target validation inadmissible. Evidence that would change this conclusion would require an authoritative, reproducible transformation demonstrating that the frozen MP target and OQMD stability values can be placed on the same thermodynamic reference convention without using the locked benchmark to tune that transformation.
