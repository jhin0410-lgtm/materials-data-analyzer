# Autonomous materials research — Phases B through E

This extension deliberately reuses the existing `research_loop.epistemic_graph`,
`self_directed_research`, `policy_authorized_closed_loop`, `design_simulation`, and
characterization downstream-use policy. It does not create a second reasoning graph or
a second execution framework.

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
contradiction is reported only for comparable, explicitly independent evidence whose
uncertainty intervals are confidently opposite. Measurement/model/sampling/
extrapolation/provenance uncertainty components remain separate; RSS combination is
available only when independence has explicitly been established. The analysis selector
chooses one bounded analysis contract and leaves execution to the existing typed-action
layer.

## Phase D — characterization and multimodal sample identity

`sample_identity_binding.py` binds specimen/aliquot/field-of-view identities with
provenance and rejects ambiguous parentage or cycles. XRD, SEM, TEM, Raman, EDS, and SAED
can be normalized only after the existing `CharacterizationUseEligibility` contract says
the evidence is allowed, reviewed, and Supported/Diagnostic. Feature names never imply
units, physical sample identity, or process history.

## Phase E — simulation, structural sensitivity, and design prioritization

`scientific_simulation_registry.py` is a solver-contract registry and planning bridge,
not an executor. A solver contract can be registered only when its declared callable
qualname and defining Python-module SHA-256 match the implementation. The contract pins
action type/version and explicitly routes execution to the existing independent
authorization and typed-executor chain.

The currently executable simulation remains the repository's existing response-free
`design_simulation.py`. Phase E reuses it to compare predeclared experimental-design
variants using only structural metrics such as model-matrix rank gain, residual degrees
of freedom, and new unique cells. These are explicitly labelled structural proxies:
probabilistic expected information gain remains `not_quantified`.

A planning request must cite evidence-producing nodes already present in the epistemic
graph and target an existing hypothesis/claim/conclusion. Compiling a request does not
execute it, does not grant scientific status, and does not create a second executor.
Physical experiment execution remains outside this layer and requires the separate
facility/operator authorization boundary.

Future validated physics backends such as CALPHAD, DFT, phase-field, or FEM can be added
as exact contracts and typed actions later. Their names are not treated as implemented
capabilities today.

## Scientific boundary

These phases strengthen autonomous research architecture; they do not establish a new
materials-science result by themselves. No missing dataset semantics are inferred, no
simulation replaces physical observation, and no laboratory instrument can be executed
through these modules.
