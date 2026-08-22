from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path

import pytest

import materials_data_analyzer.research_loop.public_recursive_api as api

REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE_REGISTRY = REPO_ROOT / "configs/research/reference_heat_conduction_action_registry.v1.json"


def _sha_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_sha(value: object, sha_field: str | None = None) -> str:
    payload = dict(value) if isinstance(value, dict) else value
    if sha_field is not None and isinstance(payload, dict):
        payload = dict(payload)
        payload.pop(sha_field, None)
    return hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _write_json(path: Path, value: object) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = (json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
    path.write_bytes(raw)
    return hashlib.sha256(raw).hexdigest()


def _solver_request(tolerance: float) -> dict:
    return {
        "schema_version": "1.0",
        "solver_id": "heat_conduction_1d_explicit_ftcs",
        "solver_version": "1.0",
        "units": {
            "length": "m",
            "time": "s",
            "temperature": "K",
            "thermal_diffusivity": "m^2/s",
        },
        "domain": {"length_m": 1.0, "node_count": 11},
        "time": {"duration_s": 1.0, "time_step_s": 0.1},
        "material": {"thermal_diffusivity_m2_s": 0.01},
        "initial_condition": {
            "kind": "sine_mode",
            "baseline_temperature_K": 300.0,
            "amplitude_K": 10.0,
        },
        "boundary_conditions": {
            "left": {"kind": "fixed_temperature", "temperature_K": 300.0},
            "right": {"kind": "fixed_temperature", "temperature_K": 300.0},
        },
        "validation": {
            "kind": "sine_eigenmode_analytical",
            "max_abs_error_tolerance_K": tolerance,
        },
    }


def _objective(research_id: str) -> dict:
    return {
        "schema_version": "1.0",
        "research_id": research_id,
        "question": "Can the audited reference heat solver resolve a bounded numerical-validity blocker?",
        "metrics": {"primary": "numerical_validation", "secondary": []},
        "constraints": [
            "No empirical material or process validity claim",
            "No automatic scientific promotion",
        ],
        "budget": {"maximum_actions": 2, "maximum_cost_units": 2},
        "stop_rules": ["Stop when the bounded reference action is complete or unavailable"],
    }


def _execution_request(
    *,
    root: Path,
    run: Path,
    registry: Path,
    solver_request: Path,
    action_id: str,
) -> dict:
    registry_value = api.load_action_registry(registry, repository_root=root)
    contract = api.repository_heat_conduction_contract()
    return {
        "schema_version": "1.0",
        "action_id": action_id,
        "action_type": "reference_heat_conduction_simulation",
        "action_version": "1.0",
        "research_run": str(run),
        "solver_request": str(solver_request),
        "expected_solver_request_sha256": _sha_file(solver_request),
        "expected_solver_implementation_sha256": contract.implementation_module_sha256,
        "registry": str(registry),
        "repository_root": str(root),
        "expected_registry_sha256": registry_value["registry_sha256"],
    }


def _execute_heat(*, root: Path, run: Path, registry: Path, request: Path) -> dict:
    handoff = api.verify_heat_execution_handoff(
        repository_root=root,
        research_run=run,
        action_registry_path=registry,
        request_path=request,
    )
    return api.execute_authorized_action(
        "reference-heat-conduction",
        repository_root=root,
        research_run=run,
        action_registry_path=registry,
        request_path=request,
        expected_action_type=handoff["action_type"],
        expected_request_sha256=handoff["request_sha256"],
        expected_research_ledger_sha256=handoff["research_ledger_sha256"],
    )


def _base_graph(graph_id: str = "graph-heat-v1", *, extra_node: bool = False) -> dict:
    nodes = [
        {
            "node_id": "h-reference-heat-validity",
            "node_type": "hypothesis",
            "statement": api.REFERENCE_HEAT_NUMERICAL_VALIDITY_TARGET,
            "metadata": {"claim_scope": "computational"},
        }
    ]
    if extra_node:
        nodes.append(
            {
                "node_id": "unrelated-control-node",
                "node_type": "claim",
                "statement": "Unrelated control claim.",
                "metadata": {"claim_scope": "computational"},
            }
        )
    return {
        "schema_version": "1.0",
        "graph_id": graph_id,
        "research_scope": "public recursive reference-heat architecture acceptance",
        "nodes": nodes,
        "edges": [],
    }


def _transition_proposal(
    *,
    base_graph_path: Path,
    action_id: str,
    solver_result_path: Path,
    new_graph_id: str,
    transition_id: str,
) -> dict:
    return {
        "schema_version": "1.0",
        "transition_id": transition_id,
        "base_graph_id": json.loads(base_graph_path.read_text(encoding="utf-8"))["graph_id"],
        "base_graph_sha256": _sha_file(base_graph_path),
        "new_graph_id": new_graph_id,
        "target_node_id": "h-reference-heat-validity",
        "source_action": {
            "action_id": action_id,
            "action_class": "simulation",
            "action_version": "1.0",
            "execution_mode": "typed_local_action",
        },
        "result_node": {
            "node_id": f"{transition_id}-result",
            "node_type": "simulation",
            "statement": "The audited reference heat calculation passed its declared numerical benchmark.",
            "artifact_bindings": [
                {
                    "role": "primary_solver_result",
                    "path": str(solver_result_path),
                    "sha256": _sha_file(solver_result_path),
                }
            ],
            "metadata": {"result_origin": "authorized_local_simulation"},
        },
        "input_evidence_bindings": [],
        "proposed_inference": {
            "tests_edge_id": f"{transition_id}-tests",
            "inference_edge_id": f"{transition_id}-inference",
            "relation": "supports",
            "rationale": (
                "The independently verified numerical-reference result is diagnostic for "
                "the bounded computational-validity hypothesis."
            ),
        },
        "limitations": [
            "No empirical material or process validation.",
            "No automatic positive scientific closeout.",
        ],
    }


def _make_transition_bundle(
    *,
    root: Path,
    base_graph: dict,
    execution: dict,
    request_path: Path,
    action_id: str,
    name: str,
) -> Path:
    base_path = root / f"{name}-base-graph.json"
    _write_json(base_path, base_graph)
    action_report = json.loads(Path(str(execution["action_report"])).read_text(encoding="utf-8"))
    solver_result = Path(str(action_report["solver_result"]["path"])).resolve(strict=True)
    proposal_path = root / f"{name}-proposal.json"
    _write_json(
        proposal_path,
        _transition_proposal(
            base_graph_path=base_path,
            action_id=action_id,
            solver_result_path=solver_result,
            new_graph_id=f"{base_graph['graph_id']}-successor",
            transition_id=f"{name}-transition",
        ),
    )
    verification_path = root / f"{name}-verification.json"
    verification = api.publish_heat_transition_verification_decision(
        base_graph_path=base_path,
        proposal_path=proposal_path,
        action_report_path=execution["action_report"],
        execution_request_path=request_path,
        output_path=verification_path,
    )
    assert verification["pinned_heat_verification_performed"] is True
    assert verification["empirical_validation_performed"] is False
    bundle = root / f"{name}-bundle"
    api.apply_authenticated_epistemic_transition_files(
        base_graph_path=base_path,
        proposal_path=proposal_path,
        verification_decision_path=verification_path,
        program_state={"workstreams": []},
        artifact_root=root,
        output_dir=bundle,
    )
    consumed = api.authenticate_transition_bundle(bundle)
    assert consumed["current_transition_exact_provenance_authenticated"] is True
    return bundle


@pytest.fixture(scope="module")
def replay(tmp_path_factory: pytest.TempPathFactory) -> dict:
    root = tmp_path_factory.mktemp("public-recursive-replay") / "repo"
    root.mkdir()
    (root / "scripts").mkdir()
    (root / "scripts/run_reference_heat_conduction_action.py").write_text(
        "# bound test entrypoint\n",
        encoding="utf-8",
    )
    registry = root / "reference_heat_registry.json"
    registry.write_bytes(SOURCE_REGISTRY.read_bytes())

    # Run A: real immutable numerical failure. No empirical fixture is created.
    objective_a = root / "objective-a.json"
    _write_json(objective_a, _objective("public-recursive-baseline-failed"))
    run_a = root / "run-a"
    api.initialize_research_loop(objective_a, run_a)
    solver_a = root / "solver-a.json"
    _write_json(solver_a, _solver_request(1.0e-20))
    request_a = root / "request-a.json"
    _write_json(
        request_a,
        _execution_request(
            root=root,
            run=run_a,
            registry=registry,
            solver_request=solver_a,
            action_id="heat-baseline-failed-001",
        ),
    )
    failed = _execute_heat(root=root, run=run_a, registry=registry, request=request_a)
    assert failed["verified_report"]["validation_state"] == "failed"
    assert failed["verified_report"]["registered_outcome"] == "numerical_validation_failed"
    assert failed["empirical_validation_performed"] is False

    # Run B: clean live planner/authorization state for the corrected real simulation.
    objective_b = root / "objective-b.json"
    _write_json(objective_b, _objective("public-recursive-corrected"))
    run_b = root / "run-b"
    api.initialize_research_loop(objective_b, run_b)
    solver_b = root / "solver-b.json"
    _write_json(solver_b, _solver_request(0.1))
    request_b = root / "request-b.json"
    action_id_b = "heat-corrected-001"
    _write_json(
        request_b,
        _execution_request(
            root=root,
            run=run_b,
            registry=registry,
            solver_request=solver_b,
            action_id=action_id_b,
        ),
    )

    graph1_raw = _base_graph()
    graph1 = api.evaluate_epistemic_graph(
        graph1_raw,
        program_state={"workstreams": []},
        artifact_root=root,
    )
    report1 = api.build_model_evidence_discrepancy_report(
        model_adapter_id="reference-heat-conduction",
        action_report_path=failed["action_report"],
        execution_request_path=request_a,
        evaluated_graph=graph1,
        target_node_id="h-reference-heat-validity",
        empirical_evidence_path=None,
    )
    assert [item["diagnosis_type"] for item in report1["diagnoses"]] == ["numerical_invalidity"]
    assert report1["empirical_evidence"] is None
    assert report1["autonomy_boundary"]["synthetic_empirical_measurement_created"] is False

    handoff1 = api.build_discrepancy_planning_handoff(report1, evaluated_graph=graph1)
    objective1 = handoff1["research_objectives"][0]
    assert objective1["source_research_action_class"] == "numerical_validation"
    assert objective1["research_action_class"] == "simulation"

    program1 = api.build_heat_recursive_planner_program_state(
        planning_handoff=handoff1,
        discrepancy_report=report1,
        evaluated_graph=graph1,
        repository_root=root,
        research_run=run_b,
        action_registry_path=registry,
        request_path=request_b,
    )
    plan1 = api.build_autonomous_inquiry_plan(program1)
    assert plan1["selected_next_action"]["action_id"] == action_id_b
    assert plan1["selected_next_action"]["action_class"] == "simulation"
    match1 = api.build_public_candidate_match_record(
        planning_handoff=handoff1,
        fresh_plan=plan1,
    )
    limits = {
        "max_cycles": 4,
        "max_action_slots": 2,
        "max_planned_cost_units": 4.0,
    }
    planning1 = api.build_validated_recursive_planning_checkpoint(
        planning_handoff=handoff1,
        source_discrepancy_report=report1,
        source_evaluated_graph=graph1,
        fresh_plan=plan1,
        planner_program_state=program1,
        candidate_match=match1,
        recursive_limits=limits,
    )
    checkpoint1 = planning1["recursive_checkpoint"]
    assert checkpoint1["cycle_index"] == 1
    assert checkpoint1["checkpoint_status"] == "explicit_authorization_required"
    context1 = api.build_public_recursive_planning_context(
        validated_planning_artifact=planning1,
        planning_handoff=handoff1,
        source_discrepancy_report=report1,
        source_evaluated_graph=graph1,
        fresh_plan=plan1,
        planner_program_state=program1,
        candidate_match=match1,
        recursive_limits=limits,
    )

    corrected = _execute_heat(root=root, run=run_b, registry=registry, request=request_b)
    assert corrected["verified_report"]["validation_state"] == "passed"
    assert corrected["verified_report"]["registered_outcome"] == "numerically_validated_reference_solution"
    assert corrected["empirical_validation_performed"] is False
    assert corrected["scientific_evidence_upgraded_by_orchestrator"] is False

    bundle1 = _make_transition_bundle(
        root=root,
        base_graph=graph1_raw,
        execution=corrected,
        request_path=request_b,
        action_id=action_id_b,
        name="cycle1",
    )
    progression1 = api.advance_recursive_cycle_after_verified_transition(
        validated_planning_context=context1,
        recursive_limits=limits,
        execution_adapter_id="reference-heat-conduction",
        repository_root=root,
        research_run=run_b,
        action_registry_path=registry,
        request_path=request_b,
        action_report_path=corrected["action_report"],
        transition_bundle_root=bundle1,
        program_state={"workstreams": []},
    )
    assert progression1["cycle_index"] == 1
    assert progression1["progression_status"] == "re_diagnosis_required"
    science = progression1["scientific_state_comparison"]
    assert science["base"]["fingerprint_sha256"] == science["successor"]["fingerprint_sha256"]
    assert science["graph_version_bookkeeping_counts_as_new_information"] is False
    assert science["diagnostic_only_edges_count_as_verified_state_change"] is False

    graph2_raw = json.loads((bundle1 / "epistemic_graph.json").read_text(encoding="utf-8"))
    graph2 = api.evaluate_epistemic_graph(
        graph2_raw,
        program_state={"workstreams": []},
        artifact_root=bundle1,
    )
    assert graph2["graph_id"] != graph1["graph_id"]
    report2 = api.build_model_evidence_discrepancy_report(
        model_adapter_id="reference-heat-conduction",
        action_report_path=corrected["action_report"],
        execution_request_path=request_b,
        evaluated_graph=graph2,
        target_node_id="h-reference-heat-validity",
        empirical_evidence_path=None,
        previous_report=report1,
    )
    assert report2["iteration_index"] == 2
    assert [item["diagnosis_type"] for item in report2["diagnoses"]] == ["empirical_evidence_not_acquired"]
    assert report2["gates"]["numerical_validity"]["passed"] is True
    assert report2["gates"]["empirical_evidence_acquired"]["passed"] is False

    completion1 = api.complete_recursive_cycle_with_rediagnosis(
        validated_planning_context=context1,
        progression=progression1,
        current_discrepancy_report=report2,
        previous_discrepancy_report=report1,
        evaluated_graph=graph2,
        recursive_limits=limits,
    )
    handoff2 = completion1["next_planning_handoff"]
    assert handoff2["research_objectives"][0]["research_action_class"] == "external_evidence_search"
    program2 = api.build_external_evidence_waiting_program_state(
        planning_handoff=handoff2,
        discrepancy_report=report2,
        evaluated_graph=graph2,
        previous_discrepancy_report=report1,
    )
    plan2 = api.build_autonomous_inquiry_plan(program2)
    assert plan2["plan_sha256"] != plan1["plan_sha256"]
    assert plan2["selected_next_action"] is None
    assert plan2["stop_decision"]["stop"] is True
    assert plan2["stop_decision"]["reason"] == "no_affordable_informative_action"

    planning2 = api.build_validated_recursive_planning_checkpoint(
        planning_handoff=handoff2,
        source_discrepancy_report=report2,
        source_evaluated_graph=graph2,
        fresh_plan=plan2,
        planner_program_state=program2,
        previous_discrepancy_report=report1,
        previous_validated_planning_context=context1,
        recursive_limits=limits,
    )
    checkpoint2 = planning2["recursive_checkpoint"]
    assert checkpoint2["cycle_index"] == 2
    assert checkpoint2["checkpoint_status"] == "bounded_stop_fresh_planner_decision"
    assert checkpoint2["ancestry"]["previous_checkpoint_sha256"] == checkpoint1["checkpoint_sha256"]
    assert planning2["predecessor_validation"]["deterministically_reconstructed"] is True
    context2 = api.build_public_recursive_planning_context(
        validated_planning_artifact=planning2,
        planning_handoff=handoff2,
        source_discrepancy_report=report2,
        source_evaluated_graph=graph2,
        fresh_plan=plan2,
        planner_program_state=program2,
        previous_discrepancy_report=report1,
        previous_validated_planning_context=context1,
        recursive_limits=limits,
    )

    manifest = api.build_public_recursive_replay_manifest(
        cycle1_planning_context=context1,
        cycle1_progression=progression1,
        cycle1_completion=completion1,
        cycle2_planning_context=context2,
        recursive_limits=limits,
    )
    assert manifest["scientific_boundary"]["synthetic_empirical_measurement_used"] is False
    assert manifest["scientific_boundary"]["caller_authored_execution_record_used"] is False
    assert manifest["scientific_boundary"]["hypothesis_truth_established"] is False
    assert manifest["cycle2"]["checkpoint_status"] == "bounded_stop_fresh_planner_decision"
    assert manifest["manifest_sha256"] == _canonical_sha(manifest, "manifest_sha256")
    _write_json(root / "public_recursive_replay_manifest.json", manifest)
    if os.environ.get("PUBLIC_RECURSIVE_REPLAY_MANIFEST_OUT"):
        _write_json(Path(os.environ["PUBLIC_RECURSIVE_REPLAY_MANIFEST_OUT"]), manifest)

    return {
        "root": root,
        "registry": registry,
        "run_b": run_b,
        "request_b": request_b,
        "corrected": corrected,
        "graph1": graph1,
        "graph2": graph2,
        "report1": report1,
        "report2": report2,
        "handoff1": handoff1,
        "handoff2": handoff2,
        "program1": program1,
        "program2": program2,
        "plan1": plan1,
        "plan2": plan2,
        "match1": match1,
        "planning1": planning1,
        "planning2": planning2,
        "context1": context1,
        "context2": context2,
        "progression1": progression1,
        "completion1": completion1,
        "bundle1": bundle1,
        "limits": limits,
        "manifest": manifest,
        "action_id_b": action_id_b,
    }


def test_public_api_real_evidence_replay_reaches_two_cycles_and_bounded_stop(replay: dict) -> None:
    assert replay["planning1"]["recursive_checkpoint"]["cycle_index"] == 1
    assert replay["planning2"]["recursive_checkpoint"]["cycle_index"] == 2
    assert replay["planning2"]["recursive_checkpoint"]["checkpoint_status"] == "bounded_stop_fresh_planner_decision"
    assert replay["manifest"]["scientific_boundary"] == {
        "repository_owned_audited_heat_solver_used": True,
        "immutable_heat_execution_ledger_replayed": True,
        "pinned_heat_domain_verifier_used": True,
        "synthetic_empirical_measurement_used": False,
        "caller_authored_execution_record_used": False,
        "empirical_material_or_process_validation_established": False,
        "hypothesis_truth_established": False,
        "positive_scientific_closeout_granted": False,
        "physical_experiment_executed": False,
    }


def test_public_progression_rejects_recursive_limit_substitution(replay: dict) -> None:
    changed = dict(replay["limits"])
    changed["max_cycles"] = 5
    with pytest.raises(api.PublicRecursiveProgressionError, match="recursive_limits"):
        api.advance_recursive_cycle_after_verified_transition(
            validated_planning_context=replay["context1"],
            recursive_limits=changed,
            execution_adapter_id="reference-heat-conduction",
            repository_root=replay["root"],
            research_run=replay["run_b"],
            action_registry_path=replay["registry"],
            request_path=replay["request_b"],
            action_report_path=replay["corrected"]["action_report"],
            transition_bundle_root=replay["bundle1"],
            program_state={"workstreams": []},
        )


def test_candidate_match_rejects_source_discrepancy_sha_substitution(replay: dict) -> None:
    tampered = copy.deepcopy(replay["match1"])
    tampered["source_discrepancy_report_sha256"] = "0" * 64
    with pytest.raises(api.PublicRecursivePlanningError, match="candidate match"):
        api.build_validated_recursive_planning_checkpoint(
            planning_handoff=replay["handoff1"],
            source_discrepancy_report=replay["report1"],
            source_evaluated_graph=replay["graph1"],
            fresh_plan=replay["plan1"],
            planner_program_state=replay["program1"],
            candidate_match=tampered,
            recursive_limits=replay["limits"],
        )


def test_predecessor_context_substitution_fails_even_if_resigned(replay: dict) -> None:
    tampered = copy.deepcopy(replay["context1"])
    tampered["validation_inputs"]["source_evaluated_graph"]["graph_id"] = "substituted-predecessor-graph"
    tampered["context_sha256"] = _canonical_sha(tampered, "context_sha256")
    with pytest.raises(api.PublicRecursivePlanningError, match="reconstruct|planning|discrepancy"):
        api.build_validated_recursive_planning_checkpoint(
            planning_handoff=replay["handoff2"],
            source_discrepancy_report=replay["report2"],
            source_evaluated_graph=replay["graph2"],
            fresh_plan=replay["plan2"],
            planner_program_state=replay["program2"],
            previous_discrepancy_report=replay["report1"],
            previous_validated_planning_context=tampered,
            recursive_limits=replay["limits"],
        )


def test_second_cycle_stale_plan_reuse_fails_closed(replay: dict) -> None:
    with pytest.raises(api.PublicRecursivePlanningError, match="fresh|handoff|planner|candidate"):
        api.build_validated_recursive_planning_checkpoint(
            planning_handoff=replay["handoff2"],
            source_discrepancy_report=replay["report2"],
            source_evaluated_graph=replay["graph2"],
            fresh_plan=replay["plan1"],
            planner_program_state=replay["program1"],
            previous_discrepancy_report=replay["report1"],
            candidate_match=replay["match1"],
            previous_validated_planning_context=replay["context1"],
            recursive_limits=replay["limits"],
        )


def test_authenticated_base_graph_substitution_is_rejected(replay: dict) -> None:
    bundle = _make_transition_bundle(
        root=replay["root"],
        base_graph=_base_graph("graph-heat-substituted", extra_node=True),
        execution=replay["corrected"],
        request_path=replay["request_b"],
        action_id=replay["action_id_b"],
        name="substituted-base",
    )
    with pytest.raises(api.PublicRecursiveProgressionError, match="ancestry|base graph|planning source"):
        api.advance_recursive_cycle_after_verified_transition(
            validated_planning_context=replay["context1"],
            recursive_limits=replay["limits"],
            execution_adapter_id="reference-heat-conduction",
            repository_root=replay["root"],
            research_run=replay["run_b"],
            action_registry_path=replay["registry"],
            request_path=replay["request_b"],
            action_report_path=replay["corrected"]["action_report"],
            transition_bundle_root=bundle,
            program_state={"workstreams": []},
        )


def test_public_signature_rejects_self_certified_execution_record(replay: dict) -> None:
    with pytest.raises(TypeError, match="verified_execution_record"):
        api.advance_recursive_cycle_after_verified_transition(
            validated_planning_context=replay["context1"],
            recursive_limits=replay["limits"],
            execution_adapter_id="reference-heat-conduction",
            repository_root=replay["root"],
            research_run=replay["run_b"],
            action_registry_path=replay["registry"],
            request_path=replay["request_b"],
            action_report_path=replay["corrected"]["action_report"],
            transition_bundle_root=replay["bundle1"],
            program_state={"workstreams": []},
            verified_execution_record={"self_certified": True},  # type: ignore[call-arg]
        )
