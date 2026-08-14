# Epistemic Claim Graph

## Purpose

The autonomous research program needs more than a list of findings. It must preserve why a hypothesis or claim is supported, contradicted, or falsified, and it must retain negative evidence rather than allowing later stages to forget it.

The epistemic graph therefore treats the following as first-class nodes:

- research questions;
- hypotheses;
- provenance-bound evidence;
- analyses;
- simulations;
- experiments;
- claims;
- conclusions.

The following relations are explicit rather than implicit prose:

- `motivates`;
- `tests`;
- `supports`;
- `contradicts`;
- `falsifies`;
- `depends_on`;
- `produced_by`;
- `addresses`.

## Trust boundary

A reasoning model may propose graph relations, but a proposal does not change verified epistemic status.

Three assessment levels are recognized:

1. `proposal` — an unverified scientific interpretation;
2. `diagnostic` — useful for investigation but insufficient to change verified status;
3. `domain_verified` — a relation checked by a domain-specific deterministic or independently reviewed verifier.

Every `domain_verified` relation must bind an exact verifier artifact by SHA-256. If the artifact is absent or its checksum differs, graph validation fails closed.

Evidence nodes also bind exact evidence already present in the current mission program state. A graph cannot introduce an arbitrary checksum and call it evidence.

## Positive and negative inference are intentionally asymmetric

The graph does not automatically grant final scientific truth.

For a hypothesis, claim, or conclusion:

- verified falsification -> `falsified_within_verified_scope`;
- verified support plus verified contradiction -> `contested`;
- verified contradiction -> `contradicted_within_verified_scope`;
- verified support with no verified negative relation -> `provisionally_supported`;
- otherwise -> `inconclusive`.

Even `provisionally_supported` has:

```text
final_positive_support_granted = false
```

A positive scientific closeout still requires the applicable domain validation policy. This prevents an agent from converting a chain of internally consistent analyses into final truth simply because no contrary result was generated.

## Why falsification is first-class

A support-only knowledge graph creates a structural confirmation bias: every additional analysis tends to add another supporting path, while failed tests or contradictory observations disappear into prose.

Here, contradictory and falsifying paths remain in the graph. A later analysis cannot erase them; it can only add new evidence or a new verified relation that explains why a prior relation is inactive or outside the current scope.

## Analysis, simulation, and experiment nodes

Analysis, simulation, and experiment nodes have an explicit execution status:

- `planned`;
- `completed`;
- `failed`.

A completed node must bind at least one exact result artifact. Planned and failed nodes cannot masquerade as completed results by attaching output artifacts.

The graph distinguishes a completed simulation from empirical evidence. A simulation can be used in a domain-verified relation only after an appropriate domain verifier evaluates what that simulation is allowed to establish. The graph itself does not equate simulation output with physical observation.

## CLI

The graph is evaluated against the same current mission state used by `mda-research-program`:

```powershell
mda-research-program evaluate-graph `
  --mission configs/research/autonomous_materials_research_mission.v1.json `
  --repository-root . `
  --graph path/to/epistemic_graph.json
```

Relative verifier/result artifact paths are resolved from `--repository-root` by default. A separate `--artifact-root` may be supplied for controlled output directories.

The graph JSON itself is read with duplicate-key rejection and its exact SHA-256 is returned as `graph_binding`.

## Current benchmark

The tracked NIST AM-Bench planning-readiness evidence is used as the first repository-level graph benchmark. The graph can represent the current stronger-use boundary as provisionally supported by the frozen readiness artifact while still refusing to convert that result into final predictive, causal, or engineering truth.

## Next integration

The bounded multi-cycle research runner should consume graph assessments when deciding whether to:

- run another discriminating analysis;
- execute a predeclared sensitivity or simulation action;
- seek external evidence;
- design a physical experiment;
- stop after falsification;
- route a contested claim to a stronger discrimination step;
- require domain closeout before accepting a positive conclusion.

The graph is therefore the epistemic state layer between mission-level planning and repeated action execution.
