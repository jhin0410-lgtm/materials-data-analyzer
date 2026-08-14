# Epistemic-Graph-Gated Multi-Cycle Research

## Purpose

The bounded multi-cycle runner can execute second-, third-, and later-stage typed research actions, but repeated execution must also respect what the research has already established. A verified falsification must not be ignored simply because another request remains in a queue, and provisional positive support must not trigger an indefinite search for more confirming results.

This layer places the provenance-aware epistemic graph in front of every possible repeated execution.

```text
current mission state
    -> rebuild verified workstream planning state
    -> revalidate graph evidence bindings
    -> revalidate domain-verifier artifacts
    -> evaluate selected hypothesis/claim/conclusion nodes
    -> derive execution directive
    -> only if still inconclusive:
           probe current domain planner
           verify explicit checksum-bound request
           execute at most one typed action
           rebuild state
           repeat
```

## Directives

Selected target nodes are mapped conservatively:

| Verified target state | Execution directive |
|---|---|
| `inconclusive` | `continue_discriminating_research` |
| `provisionally_supported` | `domain_closeout_required` |
| `contested` | `manual_discrimination_required` |
| `contradicted_within_verified_scope` | `manual_discrimination_required` |
| `falsified_within_verified_scope` | `stop_falsified_target` |

Falsification dominates a mixed target set. A targeted line of inquiry cannot continue automatically merely because another selected node is still inconclusive.

## Why positive support also stops automatic repetition

`provisionally_supported` is intentionally not final truth. Once a selected target reaches verified positive support, the next step is the applicable domain closeout or a separately predeclared independent validation step—not open-ended confirmatory repetition. This limits confirmation-seeking and preserves the distinction between internal consistency and scientific validation.

## CLI

```powershell
mda-research-epistemic-multicycle `
  --adapter nasa-battery `
  --repository-root . `
  --mission configs/research/autonomous_materials_research_mission.v1.json `
  --context path/to/runtime_context.json `
  --graph path/to/epistemic_graph.json `
  --epistemic-workstream nasa-battery `
  --epistemic-target hypothesis-cycle-fade-mechanism `
  --run path/to/research_run `
  --registry configs/research/nasa_research_action_registry.v1.json `
  --request-queue path/to/request_queue.json
```

`--epistemic-target` may be repeated when one execution sequence is explicitly intended to discriminate several linked targets.

## Trust boundary

This command does **not**:

- generate execution requests;
- mutate the epistemic graph;
- invent hypotheses or evidence;
- turn diagnostic/proposal relations into verified relations;
- grant final scientific truth from positive graph support;
- initiate network evidence acquisition;
- execute a physical experiment;
- bypass the existing planner, registry, authorization, budget, or verifier contract.

The graph is reconstructed against the current mission state before every possible execution. If its evidence bindings or verifier artifacts no longer validate, the command fails closed rather than continuing with stale epistemic state.

## Current limitation and next step

The graph is revalidated but not automatically revised after each completed action. Therefore this layer can enforce already-recorded falsification, contradiction, conflict, and provisional support, but a newly generated result still requires a provenance-bound graph update plus domain verification before that result can change epistemic status.

The next autonomous-research integration should make **typed action result -> graph-update proposal -> domain verifier -> new graph version** an explicit, auditable transition. That is the missing bridge from repeated execution to continuously evolving scientific state.
