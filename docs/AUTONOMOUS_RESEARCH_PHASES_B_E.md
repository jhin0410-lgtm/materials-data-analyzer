# Autonomous materials research — Phases B through E

This extension deliberately reuses the existing `research_loop.epistemic_graph`,
`self_directed_research`, `policy_authorized_closed_loop`, `design_simulation`, and
characterization downstream-use policy. It does not create a second reasoning graph or
an unrestricted execution framework.

## Phase B — canonical evidence and claim graph

`scientific_evidence_normalization.py` adds strict row-level normalization for material,
sample, process context, measurement, uncertainty, and provenance. Composition always
has an explicit mass/atomic fraction/percent basis. Units and semantic roles are never
inferred. Normalized measurements emit existing epistemic `evidence` nodes; verified
program-state bindings and the existing graph remain authoritative for claim status.

## Phase C — cross-source reasoning

`cross_source_scientific_reasoning.py` adds fail-closed comparability across material,
property, process, unit, instrument, calibration, source, and independence group.
Cross-unit comparisons require caller-supplied conversion factors. Directional
contradiction is reported only for comparable, explicitly independent sources whose
uncertainty intervals are confidently opposite. Measurement/model/sampling/
extrapolation/provenance uncertainty components remain separate; RSS combination is
available only when independence has explicitly been established. The analysis selector
chooses a single bounded analysis contract and leaves execution to the existing typed
action layer.

## Phase D — characterization and multimodal sample identity

`sample_identity_binding.py` binds specimen/aliquot/field-of-view identities with
provenance and rejects ambiguous parentage or cycles. XRD, SEM, TEM, Raman, EDS, and SAED
can be normalized only after the existing `CharacterizationUseEligibility` contract says
the evidence is allowed, reviewed, and Supported/Diagnostic. Feature names never imply
units, physical sample identity, or process history.

## Phase E — simulation, sensitivity, and active learning

`scientific_simulation_registry.py` is a local in-process registry, not a generic plugin
loader. A solver is registered only when its declared Python-module SHA-256 and callable
qualname match the loaded backend. Inputs require exact units and validity bounds; every
simulation request must cite evidence-producing nodes already present in the epistemic
graph. Results are immutable checksum-bound artifacts.

A completed simulation enters the existing graph only as a `simulation` node with a
proposal-level `tests` relation. It never automatically creates a `supports` edge or
changes physical-evidence sufficiency. Finite-difference sensitivity is bounded by the
same solver contract. Candidate analysis/simulation/acquisition/physical-experiment
actions can be prioritized by expected information gain and uncertainty reduction under
a budget; physical experiments remain recommendation-only and require the separate
instrument authorization boundary.

The repository's existing response-free `design_simulation.py` remains the trusted
structural experimental-design simulator. This Phase E layer is the contract for adding
future validated physics backends (for example CALPHAD/DFT/phase-field/FEM) without
pretending those solvers exist today.

## Scientific boundary

These phases strengthen autonomous research architecture; they do not establish a new
materials-science result by themselves. No missing dataset semantics are inferred, no
simulation replaces physical observation, and no laboratory instrument can be executed
through these modules.
