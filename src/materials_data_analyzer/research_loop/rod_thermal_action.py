"""Authorized measured-boundary rod action using the existing ledger transaction."""

import json
from pathlib import Path

from platform_core.output_safety import transactional_output_directory

from . import rod_thermal_identifiability as identifiability
from .action_output_ledger_transaction import (
    cleanup_action_output_ledger_transaction,
    mark_action_output_ledger_committed,
    prepare_action_output_ledger_transaction,
    recover_action_output_ledger_transaction_before_authorization,
)
from .kernel import ResearchLoopError, append_action, load_research_state
from .rod_thermal_comparison import compare, now, save
from .rod_thermal_contract import ACTION, VERSION, digest, read_json, require

REPORT = "action_result.json"
DESCRIPTION = "Evaluate the pinned rod forecast with an independently verified sensitivity and residual comparison."


def verify_committed(run, request_record, *, action_type=ACTION):
    """Recheck exact ledger-bound output bytes and the science boundary on resume."""
    state = load_research_state(run)
    matches = [entry for entry in state["actions"] if entry["action_id"] == action_type]
    require(len(matches) <= 1, "Rod run has a duplicate action")
    if not matches:
        return None
    action = matches[0]
    for artifact in action["artifacts"]:
        p = Path(artifact["path"])
        require(
            p.resolve().is_relative_to(run / "actions" / action_type)
            and digest(p.read_bytes()) == artifact["sha256"],
            "Rod ledger output checksum mismatch",
        )
    report_path = run / "actions" / action_type / REPORT
    require(
        str(report_path) in {x["path"] for x in action["artifacts"]},
        "Missing ledger-bound rod report",
    )
    report = json.loads(report_path.read_bytes())
    require(
        report["request"] == request_record
        and report["action_id"] == action_type
        and report["action_type"] == action_type
        and report["action_version"] == VERSION
        and report["scientific_status_upgrade_authorized"] is False,
        "Rod action result identity or scientific authority mismatch",
    )
    require(
        report["execution_status"] == action["status"], "Rod ledger status mismatch"
    )
    for artifact in report["outputs"]:
        path = Path(artifact["path"])
        require(
            path.resolve().is_relative_to(report_path.parent)
            and path.stat().st_size == artifact["bytes"]
            and digest(path.read_bytes()) == artifact["sha256"],
            "Rod report output checksum mismatch",
        )
    if (
        action_type == identifiability.ACTION
        and report["execution_status"] == "completed"
    ):
        result = report_path.parent / identifiability.RESULT
        require(
            str(result) in {item["path"] for item in action["artifacts"]},
            "Missing ledger-bound rod diagnostic",
        )
        data = read_json(result.read_bytes())
        require(
            data["bindings"] == report["input_bindings"]
            and data["evaluation_response_accessed"] is False
            and data["scientific_status_promoted"] is False,
            "Rod diagnostic evidence boundary mismatch",
        )
    return report


def execute(run, root, path, raw, request, spec, registry, plan, *, diagnosis=None):
    action_type = ACTION if diagnosis is None else identifiability.ACTION
    description = DESCRIPTION if diagnosis is None else identifiability.DESCRIPTION
    request_record = {"path": str(path), "bytes": len(raw), "sha256": digest(raw)}
    envelope = {
        "action_type": action_type,
        "action_id": action_type,
        "research_run": str(run),
        "repository_root": str(root),
        "registry": registry["registry_path"],
        "expected_registry_sha256": registry["registry_sha256"],
    }
    recovery = recover_action_output_ledger_transaction_before_authorization(
        research_run=run,
        request=envelope,
        request_path=path,
        request_record=request_record,
    )
    committed = verify_committed(run, request_record, action_type=action_type)
    if committed is not None:
        if recovery is not None:
            cleanup_action_output_ledger_transaction(
                research_run=run, action_id=action_type
            )
        return committed, False

    selected = plan.get("selected_next_action")
    require(
        selected
        and selected["action_class"] == "sensitivity_analysis"
        and selected["required_evidence"] == [description]
        and selected["automatic_execution_authorized"] is False,
        "Planner did not select the pinned rod comparison",
    )
    state = load_research_state(run)
    require(
        state["budget"]["actions_remaining"] >= 1
        and state["budget"]["cost_units_remaining"] >= 1,
        "Rod action budget is exhausted",
    )
    prepared = prepare_action_output_ledger_transaction(
        research_run=run,
        request=envelope,
        request_path=path,
        request_record=request_record,
        action_id=action_type,
        action_type=action_type,
        action_version=VERSION,
        cost_units=1,
        state=state,
    )
    if prepared["recovered"]:
        recovered = verify_committed(run, request_record, action_type=action_type)
        cleanup_action_output_ledger_transaction(
            research_run=run, action_id=action_type
        )
        return recovered, False

    destination = run / "actions" / action_type
    started = now()
    with transactional_output_directory(
        destination, protected_paths=(path,), recognized_markers=(REPORT,)
    ) as stage:
        try:
            if diagnosis is None:
                compare(path.parent, stage, request, raw, spec)
            else:
                model, bindings = diagnosis
                value = identifiability.diagnose(
                    path.parent,
                    request["partition"]["calibration"],
                    model,
                    spec,
                    bindings,
                )
                save(stage / identifiability.RESULT, value)
            status, detail = "completed", None
        except (OSError, ValueError, ResearchLoopError) as exc:
            status, detail = "failed", str(exc)
        outputs = [
            {
                "path": str(destination / p.name),
                "bytes": p.stat().st_size,
                "sha256": digest(p.read_bytes()),
            }
            for p in sorted(stage.iterdir())
        ]
        report = {
            "schema_version": VERSION,
            "action_id": action_type,
            "action_type": action_type,
            "action_version": VERSION,
            "cost_units": 1,
            "execution_status": status,
            "request": request_record,
            "started_at_utc": started,
            "completed_at_utc": now(),
            "planner_sha256": plan["plan_sha256"],
            "registered_outcome": (
                (
                    "conditional_comparison_verified"
                    if diagnosis is None
                    else "local_identifiability_verified"
                )
                if status == "completed"
                else "rod_verification_failed"
            ),
            "scientific_status_upgrade_authorized": False,
            "empirical_evidence_created": False,
            "outputs": outputs,
            "diagnostic": detail,
        }
        if diagnosis is not None:
            report["input_bindings"] = diagnosis[1]
            report["decision_actor"] = "bounded_rod_policy_and_research_planner"
            report["execution_actor"] = "mda_registered_rod_executor"
        save(stage / REPORT, report)
    after = append_action(
        run,
        action_id=action_type,
        action_type=action_type,
        status=status,
        summary=report["registered_outcome"],
        cost_units=1,
        artifact_paths=[
            destination / REPORT,
            *(o["path"] for o in outputs if status == "completed"),
        ],
    )
    mark_action_output_ledger_committed(
        research_run=run, action_id=action_type, action_type=action_type, state=after
    )
    verified = verify_committed(run, request_record, action_type=action_type)
    cleanup_action_output_ledger_transaction(research_run=run, action_id=action_type)
    return verified, True
