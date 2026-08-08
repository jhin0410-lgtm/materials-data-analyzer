# Materials Project external-source search closeout

## Decision

The current high-priority search for direct source-disjoint external validation of the frozen Materials Project v1.3 Fe/Si phase-stability target is closed with **no eligible candidate identified**.

This is not a claim that no compatible dataset can exist anywhere. It is a requirement-conditioned stop decision: four high-value candidate families were audited before target acquisition, and each fails a hard requirement for a different, scientifically informative reason.

## Frozen requirement

The target remains Materials Project `energy_above_hull` in eV/atom for Fe/Si-containing 2-5 element materials under the already frozen benchmark-v1 scope. A direct external-validation source must satisfy both:

1. source/provenance independence from Materials Project; and
2. a thermodynamic target convention sufficiently compatible that the resulting values test the same scientific quantity rather than a redefined surrogate.

The locked benchmark-v1 test and exposed policy outcomes are not used to choose sources, tune transformations, or define stopping rules.

## Audited candidates

### OQMD v1.8 — `scientifically_ineligible`

OQMD is independently maintained, available, and reusable. Its `stability` concept is also a distance above a convex hull in eV/atom. The blocker is target semantics: OQMD formation energies use its own PBE/PAW, fitted elemental-phase reference, and DFT+U-related correction convention, while the frozen Materials Project target uses Materials Project thermodynamic corrections and GGA/GGA+U/r2SCAN mixing. Direct numerical equivalence is therefore not established and confirmed method/reference mismatches are preserved rather than normalized post hoc.

### NIST JARVIS-DFT — `scientifically_ineligible`

JARVIS-DFT is a distinct NIST source system. NIST documentation and the current JARVIS implementation show that the main JARVIS-DFT energetics use OptB88vdW and that formation energies are constructed from JARVIS-owned OptB88vdW elemental chemical potentials before its own convex-hull calculation. This is not the frozen Materials Project thermodynamic reference/correction convention. The functional/reference difference is a scientific method difference, not a unit conversion.

### AFLOW — `scientifically_ineligible`

AFLOW is independently maintained and provides formation-enthalpy and convex-hull tooling. The official Aflux documentation, however, restricts repository data to scientific, academic, and non-commercial purposes and states that other use is prohibited. That fails the current reusable external-evidence contract before deeper target acquisition is justified. The result does not criticize AFLOW's scientific quality or prevent a separately scoped academic diagnostic analysis.

### Alexandria PBE — `diagnostic_only`

Alexandria is an open project with current versioned PBE convex-hull data and reusable published datasets. Its relevant PBE thermodynamic lineage, however, is explicitly not source-disjoint: the published construction combined AFLOW, Materials Project, and the authors' own data, selected calculations to match Materials Project settings, and applied Materials Project workflow corrections to the energies. This makes Alexandria especially useful as evidence that target compatibility can be purchased at the cost of provenance independence, but it cannot independently validate the Materials Project benchmark.

## What the four candidates show

The limiting factor is not simply dataset size or API availability. It is the intersection of two requirements:

- **independent provenance**, and
- **compatible thermodynamic semantics**.

OQMD and JARVIS satisfy the first at the source-system level but not the second. Alexandria intentionally approaches the second but fails the first. AFLOW is additionally blocked by the current reuse boundary.

This pattern is sufficient to stop broad general-purpose database hunting for the current benchmark. Downloading more rows from these sources would not repair the identified evidence gap.

## Scientific closeout

**Evidence level: Diagnostic.**

**Result:** no eligible direct source-disjoint validation candidate was identified among the audited high-priority databases.

**Strongest evidence:** authoritative source methodology and provenance documentation establish hard incompatibilities before target acquisition.

**Primary limitation:** this is not an exhaustive proof over every materials dataset, repository, private database, or future release.

**What would change the conclusion:** restart the search only when a candidate provides credible evidence of one of the following:

- an independently generated phase-stability dataset using a thermodynamic reference/correction convention explicitly compatible with the frozen Materials Project target;
- a source-disjoint dataset accompanied by an authoritative, predeclared transformation into the frozen target convention that does not use benchmark-v1 locked outcomes for fitting or tuning;
- an experimental or reference-standard phase-stability dataset whose target can be mapped to the frozen question without silently redefining the scientific quantity;
- a new release with materially different provenance/methodology that addresses the specific blocker recorded for a rejected candidate.

A new database should not reopen the search merely because it contains more Fe/Si structures or an `energy_above_hull`-like column.

## Next research priority

Keep the Materials Project benchmark as a closed controlled acquisition benchmark and preserve the unsupported/inconclusive policy findings. Move primary Virtual Research Partner validation effort to cases where genuinely independent evidence exists or can be obtained without target redefinition, including process/characterization cases with explicit sample lineage and measurement contracts.

For characterization evidence, source compatibility and `downstream_use_policy` remain separate gates. A characterization bundle does not become predictive or engineering evidence merely because its source is independent.

## Reproduction

Run the deterministic tracked registry audit against the already generated local requirement:

```powershell
& $python `
  .\scripts\audit_materials_project_external_source_candidates.py `
  --requirement .\outputs\materials_project_external_evidence_requirement_v1\external_evidence_requirement.json `
  --output .\outputs\materials_project_external_source_candidate_audit_v1
```

Expected tracked-registry summary after this closeout:

- candidates: 4;
- eligible: 0;
- `scientifically_ineligible`: 3;
- `diagnostic_only`: 1;
- network access by the audit command: false;
- target values retrieved by the audit command: false;
- model fit: false;
- external-validation claim authorization: false.

## Authoritative references

OQMD:
- https://www.oqmd.org/download/
- https://www.oqmd.org/documentation/vasp
- https://www.oqmd.org/analysis/phase_diagram/
- https://static.oqmd.org/static/docs/restful.html

JARVIS:
- https://jarvis.nist.gov/
- https://www.nist.gov/programs-projects/advanced-materials-design-electronic-and-functional-applications
- https://pages.nist.gov/jarvis/tutorials/
- https://github.com/usnistgov/jarvis/blob/master/jarvis/analysis/thermodynamics/energetics.py

AFLOW:
- https://aflow.org/documentation/
- https://aflow.org/
- https://aflow.org/aflow-documentation/index.html

Alexandria:
- https://alexandria.icams.rub.de/
- https://alexandria.icams.rub.de/datasets.html
- https://www.nature.com/articles/s41597-022-01177-w
- https://archive.materialscloud.org/record/1755

Materials Project:
- https://docs.materialsproject.org/methodology/materials-methodology/thermodynamic-stability/thermodynamic-stability
- https://docs.materialsproject.org/methodology/materials-methodology/thermodynamic-stability/thermodynamic-stability/gga-gga%2Bu-r2scan-mixing
