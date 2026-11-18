"""Bounded rod capability of the existing persistent research episode."""

import json
from pathlib import Path

from . import rod_thermal_identifiability as identifiability
from .action_output_ledger_transaction import shared_research_ledger_transaction_lock
from .action_registry import describe_action, load_action_registry
from .epistemic_graph import evaluate_epistemic_graph
from .evidence_packet import canonical_sha256
from .evidence_provider_contract import (
    AuthenticatedProviderStateInput,
    adapt_authenticated_planning_gaps,
)
from .evidence_provider_planning import build_provider_planner_program_state
from .hypothesis_portfolio import build_hypothesis_portfolio
from .kernel import initialize_research_loop, load_research_state, verify_research_loop
from .persistent_autonomous_episode import run_persistent_episode
from .research_agent import build_research_agent_iteration
from .research_episode import resume_episode
from .rod_thermal_action import DESCRIPTION, REPORT, execute, verify_committed
from .rod_thermal_comparison import CALIBRATION, RESULT, save
from .rod_thermal_contract import (
    ACTION,
    SHA,
    VERSION,
    digest,
    file_bytes,
    read_json,
    require,
    validate_request,
)
from .scientific_critic import build_scientific_critic_report

REGISTRY = Path("configs/research/measured_rod_thermal_action_registry.v1.json")
DIAGNOSTIC_REGISTRY = Path(
    "configs/research/rod_identifiability_action_registry.v1.json"
)
QUESTION = "Does a distributed heat-loss term improve the downstream rod temperature given the measured boundary?"
HYPOTHESES = {
    "diffusion": "The downstream time history can be explained by axial diffusion alone.",
    "distributed-loss": "A distributed effective sink is required within the bounded rod model.",
    "measurement": "Residual structure can reflect offsets, ambient conditions or instrument response.",
}


def _save_once(path, value):
    if path.exists():
        require(
            json.loads(path.read_bytes()) == value,
            "Existing rod planning artifact differs",
        )
    else:
        save(path, value)


def _plan(output, requirement, phase, result=None, prior=None, diagnostic=None):
    program = {
        "mission": {
            "mission_id": ACTION,
            "research_question": QUESTION,
            "autonomy_policy": {
                "goal_generation": "bounded_autonomous",
                "reasoning_proposals": "schema_validated",
                "typed_computational_actions": "explicit_request",
                "network_evidence_search": "explicit_authorization",
                "physical_experiment_execution": "external_only",
            },
        },
        "mission_binding": None,
        "runtime_context_binding": None,
        "workstreams": [],
        "generated_goals": [],
    }
    nodes = [
        {
            "node_id": key,
            "node_type": "hypothesis",
            "statement": value,
            "metadata": {"claim_scope": "diagnostic"},
        }
        for key, value in HYPOTHESES.items()
    ]
    graph = {
        "schema_version": VERSION,
        "graph_id": ACTION,
        "research_scope": QUESTION,
        "nodes": nodes,
        "edges": [],
    }
    if result:
        name = "analysis:conditional-comparison"
        nodes.append(
            {
                "node_id": name,
                "node_type": "analysis",
                "execution_status": "completed",
                "statement": "Frozen downstream prediction comparison and independent numerical checks.",
                "artifact_bindings": [
                    {
                        "role": "primary_result",
                        "path": str(result.relative_to(output)),
                        "sha256": digest(result.read_bytes()),
                    }
                ],
                "metadata": {
                    "claim_scope": "diagnostic",
                    "computational_evidence_is_empirical": False,
                },
            }
        )
        graph["edges"] = [
            {
                "edge_id": f"comparison:{target}",
                "source_node_id": name,
                "target_node_id": target,
                "relation": "tests",
                "assessment_level": "diagnostic",
                "rationale": "Conditional held-out calculation",
                "active": True,
            }
            for target in HYPOTHESES
        ]
    if diagnostic:
        graph["nodes"].append(
            {
                "node_id": "analysis:local-identifiability",
                "node_type": "analysis",
                "execution_status": "completed",
                "statement": "Numerically verified local parameter identifiability.",
                "artifact_bindings": [
                    {
                        "role": "primary_result",
                        "path": str(diagnostic.relative_to(output)),
                        "sha256": digest(diagnostic.read_bytes()),
                    }
                ],
                "metadata": {
                    "claim_scope": "diagnostic",
                    "computational_evidence_is_empirical": False,
                },
            }
        )
    graph_file = output / f"{phase}-graph.json"
    _save_once(graph_file, graph)
    critic = build_scientific_critic_report(
        graph_file,
        program_state=program,
        artifact_root=output,
        target_node_ids=list(HYPOTHESES),
    )
    gaps = {
        "unresolved_evidence_gaps": [
            {
                "gap_id": phase,
                "requirement": requirement,
                "action_class_hint": (
                    "physical_experiment_design"
                    if diagnostic
                    else "sensitivity_analysis"
                ),
            }
        ]
    }
    provider = adapt_authenticated_planning_gaps(
        gaps, trusted_state_sha256=canonical_sha256(gaps)
    )
    bound = build_provider_planner_program_state(
        program,
        [
            AuthenticatedProviderStateInput(
                state=provider,
                trusted_provider_state_sha256=provider["provider_state_sha256"],
            )
        ],
    )
    plan = build_research_agent_iteration(
        bound,
        scientific_critic_report=critic,
        previous_plan=prior["plan"] if prior else None,
    )
    evaluation = evaluate_epistemic_graph(
        graph, program_state=program, artifact_root=output
    )
    return {
        "critic": critic,
        "plan": plan,
        "portfolio": build_hypothesis_portfolio(
            evaluation,
            plan=plan,
            previous_portfolio=prior["portfolio"] if prior else None,
        ),
    }


def _followup(comparison):
    pairs = [r["models"] for r in comparison["runs"].values()]
    if all(p["distributed_loss"]["rmse_K"] < p["conduction"]["rmse_K"] for p in pairs):
        sign_change = any(
            (b := p["distributed_loss"]["late_bias_each_sensor_K"])
            and min(b) < 0 < max(b)
            for p in pairs
        )
        if sign_change:
            return "Design a sensitivity analysis for calibrated ambient and sensor zero offsets versus spatially varying heat removal."
        return "Acquire independent airflow and surface heat-loss measurements before interpreting the effective sink."
    return "Review measured boundary alignment and material and acquisition source records before attributing transfer failure."


def run_rod_episode(
    *,
    repository_root,
    output_root,
    request_path,
    expected_sha256,
    prior_run,
    max_cycles,
    authorize_identifiability=False,
):
    root = Path(repository_root).resolve(strict=True)
    path = Path(request_path).resolve(strict=True)
    raw = file_bytes(path, 100_000)
    require(
        isinstance(expected_sha256, str)
        and SHA.fullmatch(expected_sha256)
        and digest(raw) == expected_sha256,
        "Exact rod request SHA-256 mismatch",
    )
    request = read_json(raw)
    spec = validate_request(request)
    require(
        type(max_cycles) is int and 1 <= max_cycles <= 12,
        "Cycle bound must be within 1–12",
    )
    require(
        not authorize_identifiability or max_cycles >= 2,
        "Rod identifiability requires a budget of at least two cycles",
    )
    budget = 2 if authorize_identifiability else 1
    expected_prior = request["prior_ledger_sha256"]
    require(
        (prior_run is None) == (expected_prior is None),
        "Prior research ledger binding is required",
    )
    ancestry = verify_research_loop(prior_run) if prior_run else None
    if ancestry:
        require(
            ancestry["valid"] and ancestry["ledger_sha256"] == expected_prior,
            "Prior research ledger hash mismatch",
        )

    output = Path(output_root).resolve()
    require(
        output != path.parent
        and not path.is_relative_to(output)
        and not output.is_relative_to(root / "src"),
        "Rod output must be isolated from pinned inputs and source",
    )
    if prior_run:
        previous = Path(prior_run).resolve()
        require(
            not output.is_relative_to(previous) and not previous.is_relative_to(output),
            "Rod output must stay separate from the prior research ledger",
        )
    registry = load_action_registry(root / REGISTRY, repository_root=root)

    def check_registry(source, action_type):
        action = describe_action(source, action_type)
        require(
            action["availability"] == "available"
            and action["version"] == VERSION
            and action["cost_units"] == 1,
            "Rod execution registry contract mismatch",
        )

    check_registry(registry, ACTION)
    identity = {
        "request_sha256": expected_sha256,
        "request_path": str(path),
        "registry_sha256": registry["registry_sha256"],
        "prior_ledger_sha256": expected_prior,
    }
    if authorize_identifiability:
        diagnostic_registry = load_action_registry(
            root / DIAGNOSTIC_REGISTRY, repository_root=root
        )
        check_registry(diagnostic_registry, identifiability.ACTION)
        identity["diagnostic_registry_sha256"] = diagnostic_registry["registry_sha256"]
    output.mkdir(parents=True, exist_ok=True)
    require(
        (output / "identity.json").is_file() or not any(output.iterdir()),
        "Rod output directory is not empty",
    )
    _save_once(output / "identity.json", identity)
    run = output / "ledger"
    objective = output / "objective.json"
    _save_once(
        objective,
        {
            "schema_version": VERSION,
            "research_id": "measured-rod",
            "question": QUESTION,
            "metrics": {"primary": "downstream conditional RMSE in K", "secondary": []},
            "constraints": ["Pinned local inputs", "No scientific authority"],
            "budget": {"maximum_actions": budget, "maximum_cost_units": budget},
            "stop_rules": [
                "Stop when the diagnostic requires independent measurement."
                if authorize_identifiability
                else "Replan once after the verified comparison; no new physical experiment."
            ],
        },
    )
    if not run.exists():
        initialize_research_loop(objective, run)
    record = {"sha256": expected_sha256, "bytes": len(raw), "path": str(path)}

    comparison_dir = run / "actions" / ACTION
    comparison_path = comparison_dir / RESULT
    diagnostic_dir = run / "actions" / identifiability.ACTION
    planning_path = output / "planning-record.json"
    diagnostic_plan_path = output / "identifiability-planning-record.json"

    def bound_output(path, report):
        expected = next(
            (item for item in report["outputs"] if item["path"] == str(path)), None
        )
        raw_output = file_bytes(path, 10_000_000)
        require(
            expected
            and len(raw_output) == expected["bytes"]
            and digest(raw_output) == expected["sha256"],
            "Rod bound output checksum mismatch",
        )
        return raw_output

    def diagnosis_inputs():
        report = verify_committed(run, record)
        require(
            report and report["execution_status"] == "completed",
            "Rod comparison is not verified",
        )
        calibration_path = comparison_dir / CALIBRATION
        calibration_raw = bound_output(calibration_path, report)
        calibration = read_json(calibration_raw)
        train = request["partition"]["calibration"]
        require(calibration["id"] == train["id"], "Rod calibration identity mismatch")
        return calibration["models"]["distributed_loss"], {
            "request_sha256": expected_sha256,
            "calibration_original_sha256": train["original_sha256"],
            "calibration_projection_sha256": train["series"]["sha256"],
            "calibration_sha256": digest(calibration_raw),
            "comparison_sha256": digest(bound_output(comparison_path, report)),
            "comparison_report_sha256": digest((comparison_dir / REPORT).read_bytes()),
        }

    def step(state):
        second = bool(state["action_history"])
        if second:
            first = read_json(planning_path.read_bytes())
            require(
                canonical_sha256(first)
                == state["action_history"][0]["planner_record_sha256"],
                "Rod planning record checksum mismatch",
            )
            before = first["after"]
            inputs = diagnosis_inputs()
            report, _ = execute(
                run,
                root,
                path,
                raw,
                request,
                spec,
                diagnostic_registry,
                before["plan"],
                diagnosis=inputs,
            )
            require(
                report["input_bindings"] == inputs[1],
                "Rod diagnostic predecessor mismatch",
            )
            result = diagnostic_dir / identifiability.RESULT
            after = None
            reason = "rod_diagnostic_verification_failed"
            if report["execution_status"] == "completed":
                verdict = read_json(bound_output(result, report))["decision"]
                requirement = (
                    "Measure conductivity independently and local airflow and heat removal before attributing the fitted sink."
                    if verdict == "independent_k_and_loss_measurements_required"
                    else "Verify ambient reference and sensor zero and location before interpreting local parameter separation."
                )
                after = _plan(
                    output,
                    requirement,
                    "after-identifiability",
                    comparison_path,
                    before,
                    diagnostic=result,
                )
                reason = verdict
            plan_path, report_path, has_next = (
                diagnostic_plan_path,
                diagnostic_dir / REPORT,
                False,
            )
        else:
            before = _plan(output, DESCRIPTION, "before")
            report, _ = execute(
                run, root, path, raw, request, spec, registry, before["plan"]
            )
            result = comparison_path
            after, has_next = None, False
            reason = "rod_verification_failed"
            if report["execution_status"] == "completed":
                comparison = read_json(bound_output(result, report))
                requirement = _followup(comparison)
                if authorize_identifiability:
                    model, _ = diagnosis_inputs()
                    # Local diagnosis is valuable if the loss model improves every off-fit
                    # acquisition and the fitted k/h sensitivities are already near-collinear.
                    improved = all(
                        row["models"]["distributed_loss"]["rmse_K"]
                        < row["models"]["conduction"]["rmse_K"]
                        for row in comparison["runs"].values()
                    )
                    has_next = (
                        improved
                        and abs(model["k_h_sensitivity_cosine"]) >= 0.98
                        and identifiability.interior(model, spec)
                    )
                    if has_next:
                        requirement = identifiability.DESCRIPTION
                after = _plan(output, requirement, "after", result, before)
                selected = after["plan"]["selected_next_action"]
                has_next = (
                    has_next
                    and bool(selected)
                    and selected["action_class"] == "sensitivity_analysis"
                    and selected["required_evidence"] == [identifiability.DESCRIPTION]
                )
                reason = (
                    "verified_comparison_selected_identifiability"
                    if has_next
                    else "no_qualified_followup"
                    if authorize_identifiability
                    else "one_authorized_rod_action_limit"
                )
            plan_path, report_path = planning_path, comparison_dir / REPORT

        completed = report["execution_status"] == "completed"
        planning_record = {"before": before, "after": after, "prior_ledger": ancestry}
        _save_once(plan_path, planning_record)
        return {
            "planner_record": planning_record,
            "artifact_refs": [str(report_path), str(plan_path)],
            "evidence_refs": [digest(result.read_bytes())] if completed else [],
            "unresolved_gaps": [after["plan"]["selected_next_action"]["description"]]
            if (after and after["plan"]["selected_next_action"])
            else [],
            "review_queue": ["Independent scientific review remains external"],
            "blockers": [] if completed else [report["diagnostic"]],
            "cost_units": 1,
            "iteration_status": report["execution_status"],
            "episode_status": "active" if has_next else "stopped",
            "conclusion": None
            if has_next
            else {
                "reason": reason,
                "scientific_status_promoted": False,
            },
        }

    def validate_progress(history, *, allow_uncheckpointed):
        actions = [entry["action_id"] for entry in load_research_state(run)["actions"]]
        allowed = [ACTION, identifiability.ACTION][:budget]
        require(
            actions == allowed[: len(actions)]
            and 0 <= len(actions) - len(history) <= int(allow_uncheckpointed),
            "Rod run has an unexpected action history",
        )
        reports = []
        for action_type, entry, plan_path in zip(
            actions, history, (planning_path, diagnostic_plan_path)
        ):
            report = verify_committed(run, record, action_type=action_type)
            planning = read_json(plan_path.read_bytes())
            require(
                canonical_sha256(planning) == entry["planner_record_sha256"]
                and planning["before"]["plan"]["plan_sha256"]
                == report["planner_sha256"],
                "Rod planning record checksum mismatch",
            )
            if action_type == identifiability.ACTION:
                require(
                    report["input_bindings"] == diagnosis_inputs()[1],
                    "Rod diagnostic predecessor mismatch",
                )
            reports.append(report)
        return reports

    with shared_research_ledger_transaction_lock(run):
        checkpoint = output / "episode.json"
        if checkpoint.exists():
            existing = resume_episode(checkpoint)
            validate_progress(
                existing["action_history"],
                allow_uncheckpointed=existing["status"] == "active",
            )
        before_count = len(load_research_state(run)["actions"])
        outcome = run_persistent_episode(
            checkpoint,
            episode_id=expected_sha256,
            mission_id=ACTION,
            research_question=QUESTION,
            objectives=["Compare pinned off-fit rod runs"],
            max_iterations=budget,
            cost_budget=budget,
            step_handler=step,
        )
        reports = validate_progress(
            outcome["episode"]["action_history"], allow_uncheckpointed=False
        )
        return {
            **outcome,
            "planning_record": read_json(planning_path.read_bytes()),
            "action_report": reports[0],
            **(
                {"identifiability_action_report": reports[1]}
                if len(reports) == 2
                else {}
            ),
            "ledger_sha256": load_research_state(run)["ledger_sha256"],
            "actions_appended_this_invocation": len(reports) - before_count,
        }
