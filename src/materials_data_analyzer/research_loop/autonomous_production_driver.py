"""Mission-level autonomous production driver over finite audited research capabilities.

The production profile advances the exact IN625 Zenodo 20503603 external-evidence gap
through standing-policy acquisition, machine-authored typed registration, row-preserving
tensile intake, observed-quality verification, quality-aware re-diagnosis, and a reviewed
physical-comparability gate.  The driver never executes arbitrary code or URLs and stops
boundedly when the newly generated next action has no audited handler in the current finite
capability set.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import urllib.parse
import urllib.request
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

from .action_registry import load_action_registry
from .authenticated_request_compiler import compile_authenticated_machine_request
from .authorized_execution import execute_authorized_action
from .in625_archive_network_acquisition import (
    build_in625_archive_network_authorization,
    execute_authorized_in625_archive_download,
)
from .in625_execution_verifier import verify_in625_execution_handoff
from .in625_network_policy import authenticate_in625_network_policy
from .in625_physical_comparability_assessment import (
    ACTION_CLASS as IN625_COMPARABILITY_ACTION,
    NEXT_ACTION_CLASS as IN625_GEOMETRY_ACQUISITION_ACTION,
    build_in625_physical_comparability_assessment,
)
from .in625_post_acquisition_rediagnosis_v2 import (
    build_in625_post_acquisition_rediagnosis_v2,
)
from .in625_tensile_quality_contract import verify_in625_tensile_observed_quality
from .in625_tensile_reviewed_intake_v2 import build_reviewed_in625_tensile_intake_v2
from .in625_zenodo_live_evidence import (
    build_verified_in625_zenodo_readme_manifest,
    inspect_verified_in625_dataset_archive,
)
from .kernel import ResearchLoopError, initialize_research_loop, load_research_state
from .planning_adapter import plan_research_next_action
from .research_program import build_research_program

AUTONOMOUS_PRODUCTION_SCHEMA_VERSION = "1.1"
AUTONOMOUS_PRODUCTION_POLICY_VERSION = "1.1"
IN625_PROFILE_ID = "in625_zenodo_20503603_first_real_closed_loop"
IN625_EXECUTION_ADAPTER = "in625-external-evidence"
IN625_NETWORK_POLICY_ID = "in625-zenodo-20503603-network-acquisition-v1"
IN625_DELEGATION_POLICY_ID = "in625-external-evidence-request-delegation-v1"
IN625_INITIAL_ACTION = "external_evidence_search"
IN625_SUCCESSOR_ACTION = IN625_COMPARABILITY_ACTION
IN625_TERTIARY_ACTION = IN625_GEOMETRY_ACQUISITION_ACTION

# Finite audited handler map.  A missing entry is a bounded stop, never dynamic execution.
_PRODUCTION_CAPABILITIES = {
    IN625_INITIAL_ACTION: "in625_zenodo_20503603_acquire_register_review",
    IN625_SUCCESSOR_ACTION: "in625_reviewed_physical_comparability_gate",
}


class AutonomousProductionDriverError(ResearchLoopError):
    """Raised when the autonomous production loop cannot preserve exact authority."""


def _canonical_sha(value: object) -> str:
    raw = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True, allow_nan=False)
        + "\n",
        encoding="utf-8",
    )


def _read_json(path: Path, field: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AutonomousProductionDriverError(f"{field} must be valid UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise AutonomousProductionDriverError(f"{field} root must be an object")
    return value


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AutonomousProductionDriverError(message)


def _repo_file(root: Path, relative: str) -> Path:
    path = (root / relative).resolve(strict=True)
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise AutonomousProductionDriverError(
            f"production configuration escapes repository: {relative}"
        ) from exc
    if not path.is_file():
        raise AutonomousProductionDriverError(
            f"production configuration is not a file: {relative}"
        )
    return path


def _repo_output(root: Path, output: Path) -> Path:
    path = output.expanduser()
    if not path.is_absolute():
        path = root / path
    path = path.resolve(strict=False)
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise AutonomousProductionDriverError(
            "autonomous production output must remain inside repository_root so "
            "machine-authored request inputs stay repository-bound"
        ) from exc
    if path.exists() and any(path.iterdir()):
        raise AutonomousProductionDriverError(
            "autonomous production output must be absent or empty"
        )
    path.mkdir(parents=True, exist_ok=True)
    return path


def _exact_zenodo_get(url: str, *, timeout: int = 60) -> bytes:
    parsed = urllib.parse.urlparse(url)
    if (
        parsed.scheme.lower() != "https"
        or (parsed.hostname or "").lower() != "zenodo.org"
        or parsed.username is not None
        or parsed.password is not None
        or parsed.port not in (None, 443)
        or parsed.fragment
    ):
        raise AutonomousProductionDriverError(
            f"network target left exact Zenodo HTTPS authority: {url}"
        )
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "materials-data-analyzer/autonomous-in625-production"},
    )
    try:
        response = urllib.request.urlopen(request, timeout=timeout)
    except Exception as exc:  # operational failure; never scientific counterevidence
        raise AutonomousProductionDriverError(
            f"exact Zenodo network request failed operationally: {exc}"
        ) from exc
    with response:
        final_url = response.geturl()
        final = urllib.parse.urlparse(final_url)
        if (
            final.scheme.lower() != "https"
            or (final.hostname or "").lower() != "zenodo.org"
            or final.username is not None
            or final.password is not None
            or final.port not in (None, 443)
            or final.fragment
        ):
            raise AutonomousProductionDriverError(
                f"Zenodo redirect left exact authorized HTTPS authority: {final_url}"
            )
        return response.read()


def _mission_metadata(program: Mapping[str, Any]) -> Mapping[str, Any]:
    mission = program.get("mission")
    if not isinstance(mission, Mapping):
        raise AutonomousProductionDriverError("research program omitted normalized mission")
    metadata = mission.get("metadata")
    if not isinstance(metadata, Mapping):
        raise AutonomousProductionDriverError(
            "autonomous production mission requires metadata"
        )
    if metadata.get("production_profile") != IN625_PROFILE_ID:
        raise AutonomousProductionDriverError(
            "unsupported autonomous production mission profile"
        )
    if metadata.get("execution_adapter") != IN625_EXECUTION_ADAPTER:
        raise AutonomousProductionDriverError("mission execution adapter drifted")
    if metadata.get("initial_expected_action_class") != IN625_INITIAL_ACTION:
        raise AutonomousProductionDriverError(
            "mission initial expected action drifted"
        )
    if metadata.get("post_acquisition_expected_action_class") != IN625_SUCCESSOR_ACTION:
        raise AutonomousProductionDriverError(
            "mission successor expected action drifted"
        )
    if metadata.get("scientific_closeout_expected_in_first_profile") is not False:
        raise AutonomousProductionDriverError(
            "first autonomous production profile may not expect scientific closeout"
        )
    return metadata


def _objective(output_root: Path) -> Path:
    path = output_root / "typed-research-objective.json"
    _write_json(
        path,
        {
            "schema_version": "1.0",
            "research_id": "autonomous-production-in625-20503603",
            "question": (
                "Can exact external IN625 evidence be autonomously acquired, typed-registered, "
                "quality-reviewed, physically compared to the tracked NIST target, and routed "
                "toward the next response-compatible evidence class without scientific over-promotion?"
            ),
            "metrics": {
                "primary": "verified_external_empirical_evidence_state",
                "secondary": [
                    "source_byte_provenance",
                    "reviewed_row_level_measurement_availability",
                    "observed_source_quality",
                    "physical_comparability_classification",
                    "bounded_successor_action_generation",
                ],
            },
            "constraints": [
                "No caller-authored typed execution request queue",
                "No unrestricted network/provider/action authority",
                "No missing-value imputation or silent row exclusion",
                "No numerical comparison across incompatible response or protocol semantics",
                "No empirical model validation, hypothesis truth, or positive scientific closeout claim",
            ],
            "budget": {"maximum_actions": 3, "maximum_cost_units": 4},
            "stop_rules": [
                "Stop when the newly generated next action is not implemented in the exact finite production capability set",
                "Stop on any authority/provenance/checksum/verifier binding mismatch",
            ],
        },
    )
    return path


def _extract_reviewed_tensile(
    *,
    repository_root: Path,
    output_root: Path,
    archive_path: Path,
    source_config: Mapping[str, Any],
) -> dict[str, Any]:
    selected_root = output_root / "selected-source-files"
    archive_manifest = inspect_verified_in625_dataset_archive(
        config=source_config,
        archive_path=archive_path,
        selected_output_dir=selected_root,
    )
    _require(
        archive_manifest["archive"]["sha256_previously_pinned"] is True,
        "archive inspection did not preserve pre-pinned SHA-256",
    )
    _write_json(output_root / "archive-manifest.json", archive_manifest)

    tensile_policy_path = _repo_file(
        repository_root,
        "configs/research/in625_tensile_reviewed_intake.v1.json",
    )
    tensile_policy = _read_json(
        tensile_policy_path,
        "IN625 tensile reviewed policy",
    )
    workbook_member = PurePosixPath(
        tensile_policy["workbook"]["archive_member_path"]
    )
    readme_member = PurePosixPath(
        tensile_policy["documentation"]["archive_member_path"]
    )
    workbook_path = selected_root.joinpath(*workbook_member.parts)
    tensile_readme_path = selected_root.joinpath(*readme_member.parts)
    _require(
        workbook_path.is_file(),
        "verified archive intake did not expose tensile workbook",
    )
    _require(
        tensile_readme_path.is_file(),
        "verified archive intake did not expose tensile README",
    )
    _require(
        _sha256_file(workbook_path) == tensile_policy["workbook"]["sha256"],
        "extracted tensile workbook differs from reviewed policy",
    )
    _require(
        _sha256_file(tensile_readme_path)
        == tensile_policy["documentation"]["sha256"],
        "extracted tensile README differs from reviewed policy",
    )
    manifest = build_reviewed_in625_tensile_intake_v2(
        workbook_path=workbook_path,
        readme_path=tensile_readme_path,
        policy_path=tensile_policy_path,
        output_dir=output_root / "reviewed-tensile",
    )
    _require(
        manifest["measurement_row_count"] == 200289,
        "real tensile row count drifted",
    )
    _require(
        manifest["parallel_test_block_count"] == 19,
        "real tensile block count drifted",
    )
    _require(
        manifest["reviewed_semantics"]["missing_values_imputed"] is False,
        "source missingness was imputed",
    )
    return manifest


def _bounded_successor_stop(state: Mapping[str, Any]) -> dict[str, Any]:
    next_action = state.get("next_action")
    if not isinstance(next_action, Mapping):
        raise AutonomousProductionDriverError(
            "autonomous research state omitted next_action"
        )
    action_class = next_action.get("action_class")
    if not isinstance(action_class, str) or not action_class:
        raise AutonomousProductionDriverError(
            "autonomous research state next action is malformed"
        )
    if action_class in _PRODUCTION_CAPABILITIES:
        raise AutonomousProductionDriverError(
            "bounded-stop helper received an action with an implemented production capability"
        )
    return {
        "status": "stopped",
        "reason_code": "registered_capability_unavailable_for_current_next_action",
        "requested_action_class": action_class,
        "available_production_action_classes": sorted(_PRODUCTION_CAPABILITIES),
        "scope": "exact_current_autonomous_production_capability_set",
        "global_evidence_unavailability_claimed": False,
        "network_failure_interpreted_as_negative_scientific_evidence": False,
        "positive_scientific_closeout": False,
        "scientific_status_changed": False,
    }


def _maximum_cycle_stop(next_action_class: object) -> dict[str, Any]:
    if not isinstance(next_action_class, str) or not next_action_class:
        raise AutonomousProductionDriverError(
            "maximum-cycle stop requires a concrete next action class"
        )
    return {
        "status": "stopped",
        "reason_code": "maximum_cycles_reached",
        "requested_action_class": next_action_class,
        "global_evidence_unavailability_claimed": False,
        "positive_scientific_closeout": False,
        "scientific_status_changed": False,
    }


def run_autonomous_production(
    *,
    repository_root: str | Path,
    mission_path: str | Path,
    expected_mission_sha256: str,
    output_root: str | Path,
    max_cycles: int = 3,
) -> dict[str, Any]:
    """Run the real one-command autonomous IN625 materials-research production profile."""
    if (
        isinstance(max_cycles, bool)
        or not isinstance(max_cycles, int)
        or max_cycles < 1
        or max_cycles > 8
    ):
        raise AutonomousProductionDriverError(
            "max_cycles must be an integer from 1 to 8"
        )
    root = Path(repository_root).expanduser().resolve(strict=True)
    mission = Path(mission_path).expanduser().resolve(strict=True)
    try:
        mission.relative_to(root)
    except ValueError as exc:
        raise AutonomousProductionDriverError(
            "mission_path must remain inside repository_root"
        ) from exc
    observed_mission_sha = _sha256_file(mission)
    _require(
        observed_mission_sha == expected_mission_sha256,
        "mission bytes do not match externally supplied expected mission SHA-256",
    )
    output = _repo_output(root, Path(output_root))

    program = build_research_program(mission, repository_root=root)
    metadata = _mission_metadata(program)
    _write_json(output / "initial-research-program.json", program)

    source_config_path = _repo_file(
        root,
        "configs/research/in625_zenodo_20503603_verified_source.v1.json",
    )
    network_policy_path = _repo_file(
        root,
        "configs/research/in625_zenodo_network_acquisition_policy.v1.json",
    )
    delegation_policy_path = _repo_file(
        root,
        "configs/research/in625_external_evidence_request_delegation_policy.v1.json",
    )
    registry_path = _repo_file(
        root,
        "configs/research/in625_external_evidence_action_registry.v1.json",
    )

    network_policy = authenticate_in625_network_policy(
        repository_root=root,
        mission_path=mission,
        expected_mission_sha256=expected_mission_sha256,
        policy_path=network_policy_path,
        source_config_path=source_config_path,
    )
    _write_json(
        output / "standing-network-policy-qualification.json",
        network_policy,
    )

    cycle_records: list[dict[str, Any]] = []

    # Cycle 1: current verified gap -> exact standing-policy acquisition -> typed registration.
    config_bytes = source_config_path.read_bytes()
    source_config = _read_json(
        source_config_path,
        "IN625 verified source config",
    )
    record_url = network_policy["record_api_url"]
    metadata_bytes = _exact_zenodo_get(record_url)
    try:
        metadata_json = json.loads(metadata_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AutonomousProductionDriverError(
            "Zenodo record response must be valid UTF-8 JSON"
        ) from exc
    if not isinstance(metadata_json, dict):
        raise AutonomousProductionDriverError(
            "Zenodo record response root is not an object"
        )
    files = {
        item["key"]: item
        for item in metadata_json.get("files", [])
        if isinstance(item, Mapping) and isinstance(item.get("key"), str)
    }
    readme_name = source_config["zenodo"]["readme_file"]
    if readme_name not in files:
        raise AutonomousProductionDriverError(
            "live Zenodo record lost exact configured README"
        )
    readme_url = files[readme_name].get("links", {}).get("self")
    if not isinstance(readme_url, str):
        raise AutonomousProductionDriverError("live Zenodo README link is missing")
    readme_bytes = _exact_zenodo_get(readme_url)
    pre_manifest = build_verified_in625_zenodo_readme_manifest(
        config=source_config,
        metadata_bytes=metadata_bytes,
        readme_bytes=readme_bytes,
    )
    _write_json(output / "source-readme-manifest.json", pre_manifest)
    (output / "record.json").write_bytes(metadata_bytes)
    (output / readme_name).write_bytes(readme_bytes)

    network_authorization = build_in625_archive_network_authorization(
        config=source_config,
        config_bytes=config_bytes,
        metadata_bytes=metadata_bytes,
        readme_bytes=readme_bytes,
    )
    _require(
        network_authorization["network_access_performed"] is False,
        "archive authorization claimed prior network execution",
    )
    _write_json(output / "network-authorization.json", network_authorization)

    archive_name = source_config["zenodo"]["archive_file"]
    archive_path = output / archive_name
    network_receipt = execute_authorized_in625_archive_download(
        authorization=network_authorization,
        config=source_config,
        config_bytes=config_bytes,
        metadata_bytes=metadata_bytes,
        readme_bytes=readme_bytes,
        output_path=archive_path,
    )
    _require(
        network_receipt["archive"]["sha256"]
        == source_config["zenodo"]["files"][archive_name]["verified_sha256"],
        "downloaded archive differs from repository-pinned SHA-256",
    )
    _write_json(output / "network-acquisition-receipt.json", network_receipt)

    tensile_manifest = _extract_reviewed_tensile(
        repository_root=root,
        output_root=output,
        archive_path=archive_path,
        source_config=source_config,
    )
    quality_contract_path = _repo_file(
        root,
        "configs/research/in625_tensile_observed_quality.v1.json",
    )
    quality = verify_in625_tensile_observed_quality(
        reviewed_tensile_manifest=tensile_manifest,
        quality_contract_path=quality_contract_path,
    )
    _write_json(output / "tensile-quality-verification.json", quality)

    objective_path = _objective(output)
    research_run = output / "typed-research-run"
    initialize_research_loop(objective_path, research_run)
    planning = plan_research_next_action(
        IN625_EXECUTION_ADAPTER,
        repository_root=root,
        research_run=research_run,
        action_registry_path=registry_path,
    )
    _require(
        planning["selection_status"] == "ready_to_execute",
        "cycle-1 planner did not select external evidence action",
    )
    selected = planning.get("selected_action")
    _require(
        isinstance(selected, Mapping)
        and selected.get("action_type") == IN625_INITIAL_ACTION,
        "cycle-1 planner selected unexpected action",
    )
    _write_json(output / "cycle-1-planning.json", planning)

    compiled = compile_authenticated_machine_request(
        IN625_EXECUTION_ADAPTER,
        repository_root=root,
        mission_path=mission,
        expected_mission_sha256=expected_mission_sha256,
        policy_id=IN625_DELEGATION_POLICY_ID,
        request_delegation_policy_path=delegation_policy_path,
        research_run=research_run,
        planning_registry_path=registry_path,
        output_dir=output / "machine-authored-request",
        action_inputs={
            "source_config": source_config_path,
            "archive_path": archive_path,
        },
    )
    request_path = Path(compiled["request_binding"]["path"]).resolve(strict=True)
    _require(
        compiled["authority_boundary"]["network_access_authorized"] is False,
        "machine request compiler improperly gained network authority",
    )
    _write_json(output / "machine-request-compilation.json", compiled)

    handoff = verify_in625_execution_handoff(
        repository_root=root,
        research_run=research_run,
        action_registry_path=registry_path,
        request_path=request_path,
    )
    execution = execute_authorized_action(
        IN625_EXECUTION_ADAPTER,
        repository_root=root,
        research_run=research_run,
        action_registry_path=registry_path,
        request_path=request_path,
        expected_action_type=handoff["action_type"],
        expected_request_sha256=handoff["request_sha256"],
        expected_research_ledger_sha256=handoff["research_ledger_sha256"],
    )
    execution_with_request = dict(execution)
    execution_with_request["request_sha256"] = handoff["request_sha256"]
    _write_json(output / "typed-execution-handoff.json", handoff)
    _write_json(output / "typed-execution-result.json", execution_with_request)
    final_state = load_research_state(research_run)
    _write_json(output / "typed-research-state.json", final_state)

    rediagnosis = build_in625_post_acquisition_rediagnosis_v2(
        network_authorization=network_authorization,
        network_receipt=network_receipt,
        typed_execution_result=execution_with_request,
        reviewed_tensile_manifest=tensile_manifest,
        quality_contract_path=quality_contract_path,
    )
    _write_json(output / "quality-aware-rediagnosis.json", rediagnosis)
    _require(
        rediagnosis["current_blocker"]["code"]
        == "cross_source_physical_comparability_not_established",
        "cycle-1 re-diagnosis did not advance to physical comparability blocker",
    )
    _require(
        rediagnosis["next_action"]["action_class"] == IN625_SUCCESSOR_ACTION,
        "cycle-1 re-diagnosis generated an unexpected successor action",
    )
    cycle1 = {
        "cycle_index": 1,
        "input_gap": "empirical_evidence_not_acquired",
        "selected_action_class": IN625_INITIAL_ACTION,
        "handler": _PRODUCTION_CAPABILITIES[IN625_INITIAL_ACTION],
        "network_policy_sha256": network_policy["policy_sha256"],
        "network_authorization_sha256": network_authorization["authorization_sha256"],
        "network_receipt_sha256": network_receipt["receipt_sha256"],
        "machine_request_manifest_sha256": compiled["manifest_binding"]["sha256"],
        "typed_request_sha256": handoff["request_sha256"],
        "pre_execution_ledger_sha256": handoff["research_ledger_sha256"],
        "post_execution_ledger_sha256": final_state["ledger_sha256"],
        "reviewed_tensile_manifest_sha256": tensile_manifest["manifest_sha256"],
        "quality_verification_sha256": quality["verification_sha256"],
        "rediagnosis_sha256": rediagnosis["rediagnosis_sha256"],
        "output_blocker": rediagnosis["current_blocker"]["code"],
        "output_next_action_class": rediagnosis["next_action"]["action_class"],
        "new_verified_information": True,
        "scientific_status_changed": False,
    }
    cycle1["cycle_sha256"] = _canonical_sha(cycle1)
    cycle_records.append(cycle1)

    comparability: dict[str, Any] | None = None
    if max_cycles < 2:
        stop = _maximum_cycle_stop(rediagnosis["next_action"]["action_class"])
    else:
        # Cycle 2: execute the generated reviewed comparability action without network/model authority.
        _require(
            IN625_SUCCESSOR_ACTION in _PRODUCTION_CAPABILITIES,
            "reviewed physical comparability capability is not registered",
        )
        comparability = build_in625_physical_comparability_assessment(
            repository_root=root,
            post_acquisition_rediagnosis=rediagnosis,
            observed_quality_verification=quality,
        )
        _write_json(
            output / "physical-comparability-assessment.json",
            comparability,
        )
        decision = comparability["gate_decision"]
        _require(
            decision["direct_nist_condition_comparability_established"] is False,
            "comparability gate improperly established direct NIST comparability",
        )
        _require(
            decision["numerical_cross_source_validation_authorized"] is False,
            "comparability gate improperly authorized numerical validation",
        )
        _require(
            comparability["scientific_boundary"][
                "numerical_cross_source_comparison_performed"
            ]
            is False,
            "comparability gate performed prohibited numerical comparison",
        )
        _require(
            comparability["next_action"]["action_class"]
            == IN625_TERTIARY_ACTION,
            "comparability gate generated an unexpected geometry evidence action",
        )
        cycle2 = {
            "cycle_index": 2,
            "predecessor_cycle_sha256": cycle1["cycle_sha256"],
            "input_blocker": rediagnosis["current_blocker"]["code"],
            "selected_action_class": IN625_SUCCESSOR_ACTION,
            "handler": _PRODUCTION_CAPABILITIES[IN625_SUCCESSOR_ACTION],
            "capability_available": True,
            "comparability_assessment_sha256": comparability["assessment_sha256"],
            "direct_nist_condition_comparability_established": False,
            "numerical_cross_source_validation_authorized": False,
            "output_blocker": "response_compatible_geometry_evidence_not_acquired",
            "output_next_action_class": comparability["next_action"]["action_class"],
            "new_verified_information": True,
            "scientific_status_changed": False,
        }
        cycle2["cycle_sha256"] = _canonical_sha(cycle2)
        cycle_records.append(cycle2)

        if max_cycles < 3:
            stop = _maximum_cycle_stop(comparability["next_action"]["action_class"])
        else:
            # Cycle 3: the gate generated an exact geometry-evidence acquisition action.
            # No handler is registered yet, so stop at the new finite capability frontier.
            stop = _bounded_successor_stop(comparability)
            cycle3 = {
                "cycle_index": 3,
                "predecessor_cycle_sha256": cycle2["cycle_sha256"],
                "input_blocker": "response_compatible_geometry_evidence_not_acquired",
                "selected_action_class": comparability["next_action"]["action_class"],
                "candidate_id": comparability["next_action"]["candidate_id"],
                "capability_available": (
                    comparability["next_action"]["action_class"]
                    in _PRODUCTION_CAPABILITIES
                ),
                "stop_reason_code": stop["reason_code"],
                "global_evidence_unavailability_claimed": False,
                "new_verified_information": False,
                "scientific_status_changed": False,
            }
            cycle3["cycle_sha256"] = _canonical_sha(cycle3)
            cycle_records.append(cycle3)

    _write_json(output / "bounded-stop.json", stop)
    archive_sha = network_receipt["archive"]["sha256"]
    archive_path.unlink(missing_ok=True)
    _require(
        not archive_path.exists(),
        "full external archive was not removed after verified execution",
    )

    final_blocker = (
        "response_compatible_geometry_evidence_not_acquired"
        if comparability is not None
        else rediagnosis["current_blocker"]["code"]
    )
    generated_next_action_class = (
        comparability["next_action"]["action_class"]
        if comparability is not None
        else rediagnosis["next_action"]["action_class"]
    )
    manifest: dict[str, Any] = {
        "schema_version": AUTONOMOUS_PRODUCTION_SCHEMA_VERSION,
        "policy_version": AUTONOMOUS_PRODUCTION_POLICY_VERSION,
        "mission_id": program["mission"]["mission_id"],
        "mission_sha256": observed_mission_sha,
        "production_profile": metadata["production_profile"],
        "cycles": cycle_records,
        "stop": stop,
        "real_external_archive_sha256": archive_sha,
        "measurement_row_count": quality["measurement_row_count"],
        "parallel_test_block_count": tensile_manifest["parallel_test_block_count"],
        "complete_numeric_measurement_row_count": quality[
            "complete_numeric_measurement_row_count"
        ],
        "incomplete_numeric_measurement_row_count": quality[
            "incomplete_numeric_measurement_row_count"
        ],
        "known_incomplete_rows": quality["known_incomplete_rows"],
        "typed_registered_outcome": execution_with_request["verified_report"][
            "registered_outcome"
        ],
        "comparability_assessment_sha256": (
            comparability["assessment_sha256"] if comparability is not None else None
        ),
        "comparability_decision_code": (
            comparability["gate_decision"]["decision_code"]
            if comparability is not None
            else None
        ),
        "preferred_geometry_candidate_id": (
            comparability["next_action"]["candidate_id"]
            if comparability is not None
            else None
        ),
        "final_blocker": final_blocker,
        "generated_next_action_class": generated_next_action_class,
        "caller_authored_request_queue_used": False,
        "machine_authored_typed_request_used": True,
        "unrestricted_network_search_performed": False,
        "arbitrary_command_execution_performed": False,
        "numerical_cross_source_comparison_performed": False,
        "missing_value_imputation_performed": False,
        "row_exclusion_performed": False,
        "direct_nist_condition_comparability_established": False,
        "numerical_cross_source_validation_authorized": False,
        "empirical_model_validation_established": False,
        "hypothesis_truth_established": False,
        "paper_evidence_promoted_to_row_level_authority": False,
        "positive_scientific_closeout_established": False,
        "global_evidence_unavailability_claimed": False,
        "scientific_status_changed": False,
    }
    manifest["manifest_sha256"] = _canonical_sha(manifest)
    _write_json(output / "autonomous-production-manifest.json", manifest)
    return manifest


__all__ = [
    "AUTONOMOUS_PRODUCTION_POLICY_VERSION",
    "AUTONOMOUS_PRODUCTION_SCHEMA_VERSION",
    "AutonomousProductionDriverError",
    "run_autonomous_production",
]
