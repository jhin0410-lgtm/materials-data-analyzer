"""Verify either 14-cycle Weaver success or the reviewed typed NIST transport stop.

This verifier extends, rather than replaces, the 12-cycle autonomous-production verifier. A
transport stop is delegated to the reviewed transport verifier. A successful 14-cycle run is
accepted only when the exact Weaver source/evidence lineage and the unchanged scientific gates
are independently replayable from persisted artifacts.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from . import autonomous_production_live_verifier as base_verifier
from . import autonomous_production_live_verifier_impl as base_impl
from .autonomous_production_transport_recovery import TRANSPORT_STOP_REASON_CODE
from .weaver_2021_full_text_acquisition import NEXT_ACTION_CLASS
from .weaver_2021_full_text_capability import ACTION_CLASS as WEAVER_ACTION_CLASS
from .weaver_2021_full_text_policy import (
    AUTHORITY_EXTENSION_ID,
    POLICY_ID,
    SOURCE_DOI,
    SOURCE_PMCID,
    SOURCE_PMID,
)


class AutonomousProductionWeaverLiveVerificationError(AssertionError):
    """Raised when the Weaver live production outcome violates its bounded contract."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AutonomousProductionWeaverLiveVerificationError(message)


def _load(root: Path, name: str) -> dict[str, Any]:
    try:
        return base_impl._load(root, name)
    except base_impl.AutonomousProductionLiveVerificationError as exc:
        raise AutonomousProductionWeaverLiveVerificationError(str(exc)) from exc


def _verify_self_hash(value: dict[str, Any], field: str, *, label: str) -> str:
    try:
        return base_impl._verify_self_hash(value, field, label=label)
    except base_impl.AutonomousProductionLiveVerificationError as exc:
        raise AutonomousProductionWeaverLiveVerificationError(str(exc)) from exc


def _verify_cycle_chain(cycles: object) -> list[dict[str, Any]]:
    _require(isinstance(cycles, list) and len(cycles) == 14, "Weaver cycle history must contain 14 cycles")
    result: list[dict[str, Any]] = []
    predecessor: str | None = None
    for index, raw_cycle in enumerate(cycles, start=1):
        _require(isinstance(raw_cycle, dict), f"Weaver cycle {index} must be an object")
        cycle = dict(raw_cycle)
        digest = _verify_self_hash(cycle, "cycle_sha256", label=f"Weaver cycle {index}")
        _require(cycle.get("cycle_index") == index, f"Weaver cycle {index} index drifted")
        if predecessor is not None:
            _require(
                cycle.get("predecessor_cycle_sha256") == predecessor,
                f"Weaver cycle {index} predecessor binding drifted",
            )
        predecessor = digest
        result.append(cycle)
    return result


def _claim_map(evidence: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    raw = evidence.get("claim_receipts")
    _require(isinstance(raw, list), "Weaver claim receipts are missing")
    result: dict[str, Mapping[str, Any]] = {}
    for item in raw:
        _require(isinstance(item, Mapping), "Weaver claim receipt must be an object")
        claim_id = item.get("claim_id")
        _require(isinstance(claim_id, str) and claim_id, "Weaver claim id is missing")
        _require(claim_id not in result, "Weaver claim ids are not unique")
        result[claim_id] = item
    return result


def _verify_weaver_success(root: Path, manifest: dict[str, Any], stop: dict[str, Any]) -> str:
    manifest_sha = _verify_self_hash(manifest, "manifest_sha256", label="Weaver manifest")
    _require(manifest.get("schema_version") == "1.9", "Weaver manifest schema drifted")
    _require(manifest.get("policy_version") == "1.9", "Weaver manifest policy drifted")
    cycles = _verify_cycle_chain(manifest.get("cycles"))

    reference_graph = _load(root, "mds2-2923-experiment-identity-reference-chain.json")
    reference_sha = _verify_self_hash(
        reference_graph,
        "report_sha256_without_self_field",
        label="mds2 reference graph",
    )
    _require(
        manifest.get("reference_chain_assessment_sha256") == reference_sha,
        "Weaver manifest/reference-graph binding drifted",
    )

    candidate = _load(root, "capability-candidate-5.json")
    candidate_sha = _verify_self_hash(
        candidate,
        "capability_candidate_sha256_without_self_field",
        label="Weaver capability candidate",
    )
    verification = _load(root, "capability-verification-5.json")
    verification_sha = _verify_self_hash(
        verification,
        "capability_verification_sha256_without_self_field",
        label="Weaver capability verification",
    )
    _require(candidate.get("action_class") == WEAVER_ACTION_CLASS, "Weaver candidate action drifted")
    _require(candidate.get("network_authority_granted") is False, "Weaver candidate gained network authority")
    _require(candidate.get("execution_authority_granted") is False, "Weaver candidate gained execution authority")
    _require(candidate.get("scientific_status_change_authorized") is False, "Weaver candidate gained scientific authority")
    _require(verification.get("promotion_eligible") is True, "Weaver capability was not independently verified")
    _require(verification.get("all_required_checks_passed") is True, "Weaver capability verification checks failed")

    qualification = _load(root, "weaver-full-text-policy-qualification.json")
    _require(
        qualification.get("qualification_status") == "exact_weaver_2021_full_text_policy_authenticated",
        "Weaver source policy is not authenticated",
    )
    _require(qualification.get("policy_id") == POLICY_ID, "Weaver policy id drifted")
    _require(qualification.get("authority_extension_id") == AUTHORITY_EXTENSION_ID, "Weaver authority extension drifted")
    _require(qualification.get("source_doi") == SOURCE_DOI, "Weaver DOI drifted")
    _require(qualification.get("source_pmcid") == SOURCE_PMCID, "Weaver PMCID drifted")
    _require(qualification.get("source_pmid") == SOURCE_PMID, "Weaver PMID drifted")
    _require(qualification.get("network_access_performed") is False, "policy authentication performed network access")
    _require(qualification.get("caller_authored_url_used") is False, "caller-authored Weaver URL gained authority")

    authorization = _load(root, "weaver-derived-full-text-authorization.json")
    authorization_sha = _verify_self_hash(
        authorization,
        "authorization_sha256",
        label="Weaver derived authorization",
    )
    _require(authorization.get("doi") == SOURCE_DOI, "Weaver authorization DOI drifted")
    _require(authorization.get("pmcid") == SOURCE_PMCID, "Weaver authorization PMCID drifted")
    _require(authorization.get("doi_derived_from_reference_graph") is True, "Weaver DOI was not reference-derived")
    _require(authorization.get("pmcid_derived_from_separately_pinned_policy") is True, "Weaver PMCID was not policy-pinned")
    _require(authorization.get("caller_authored_url_used") is False, "caller-authored URL used")
    _require(authorization.get("caller_authored_pmcid_used") is False, "caller-authored PMCID used")
    _require(authorization.get("scientific_status_change_authorized") is False, "Weaver authorization promoted science")

    evidence = _load(root, "weaver-2021-full-text-acquisition.json")
    evidence_sha = _verify_self_hash(
        evidence,
        "report_sha256_without_self_field",
        label="Weaver full-text evidence",
    )
    source = evidence.get("source")
    _require(isinstance(source, Mapping), "Weaver source binding is missing")
    source_sha = source.get("source_sha256")
    _require(isinstance(source_sha, str) and len(source_sha) == 64, "Weaver source SHA is missing")
    _require(evidence.get("authorization_sha256") == authorization_sha, "Weaver evidence/authorization binding drifted")
    _require(evidence.get("acquisition_status") == "exact_weaver_primary_full_text_acquired_and_identity_verified", "Weaver acquisition status drifted")
    _require(evidence.get("network_requests_performed") == 1, "Weaver execution request budget drifted")
    _require(evidence.get("core_claims_matched") is True, "Weaver core claims are incomplete")
    _require(evidence.get("caller_authored_url_used") is False, "Weaver execution used caller URL")
    _require(evidence.get("caller_authored_pmcid_used") is False, "Weaver execution used caller PMCID")
    _require(evidence.get("unrestricted_search_performed") is False, "Weaver execution performed unrestricted search")
    _require(evidence.get("literature_promoted_to_row_level_measurement_authority") is False, "literature gained row authority")
    _require(evidence.get("acquisition_success_establishes_scientific_bridge") is False, "acquisition self-promoted bridge")
    _require(evidence.get("scientific_status_changed") is False, "Weaver acquisition changed scientific status")

    identity = evidence.get("article_identity")
    _require(isinstance(identity, Mapping) and identity.get("article_identity_established") is True, "Weaver article identity is not established")
    claims = _claim_map(evidence)
    for claim_id in (
        "weaver-primary-condition",
        "weaver-ammt-machine-condition",
        "weaver-d4sigma-definition",
        "weaver-cross-section-protocol",
        "weaver-dataset-size",
    ):
        _require(claims.get(claim_id, {}).get("matched") is True, f"required Weaver claim failed: {claim_id}")
    ammt_fragments = claims["weaver-ammt-machine-condition"].get("required_fragments")
    _require(isinstance(ammt_fragments, list), "Weaver AMMT claim fragments are missing")
    _require("50" not in ammt_fragments and "256" not in ammt_fragments, "Naderi/mds2 numeric spot range leaked into Weaver authority")
    _require(claims.get("weaver-explicit-mds2-id", {}).get("matched") is False, "Weaver unexpectedly established explicit mds2 id")
    _require(claims.get("weaver-explicit-power-conversion", {}).get("matched") is False, "Weaver unexpectedly established power conversion")

    gate = evidence.get("gate_assessment")
    _require(isinstance(gate, Mapping), "Weaver gate assessment is missing")
    _require(gate.get("exact_mds2_rows_to_weaver_experiment_established") is False, "row identity was promoted")
    _require(gate.get("exact_mds2_experiment_identity_established") is False, "experiment identity was promoted")
    _require(gate.get("machine_setting_to_calibrated_power_relation_established") is False, "power calibration was transferred")
    _require(gate.get("spot_size_transfer_authorized") is False, "spot-size transfer was authorized")
    _require(gate.get("protocol_equivalence_established") is False, "protocol equivalence was promoted")
    _require(gate.get("directly_comparable_mds2_rows") == 0, "directly comparable mds2 rows changed")
    _require(gate.get("direct_numerical_cross_source_validation_authorized") is False, "direct numerical validation was authorized")
    _require(gate.get("issue_76_exact_target_cells_satisfied") == 0, "Issue #76 gate changed")

    cycle13 = cycles[12]
    cycle14 = cycles[13]
    _require(cycle13.get("selected_action_class") == WEAVER_ACTION_CLASS, "cycle 13 action drifted")
    _require(cycle13.get("predecessor_candidate_reauthenticated") is True, "cycle 13 did not reauthenticate candidate")
    _require(cycle13.get("candidate_rediscovery_performed") is False, "cycle 13 rediscovered candidate")
    _require(cycle14.get("selected_action_class") == WEAVER_ACTION_CLASS, "cycle 14 action drifted")
    _require(cycle14.get("research_action_resumed") is True, "cycle 14 did not resume Weaver action")
    _require(cycle14.get("capability_verification_sha256") == verification_sha, "cycle 14 verification binding drifted")
    _require(cycle14.get("weaver_evidence_sha256") == evidence_sha, "cycle 14 evidence binding drifted")
    _require(cycle14.get("weaver_source_sha256") == source_sha, "cycle 14 source binding drifted")
    _require(cycle14.get("exact_mds2_experiment_identity_established") is False, "cycle 14 promoted identity")
    _require(cycle14.get("bridge_established") is False, "cycle 14 promoted bridge")
    _require(cycle14.get("directly_comparable_mds2_rows") == 0, "cycle 14 comparable rows changed")
    _require(cycle14.get("issue_76_exact_target_cells_satisfied") == 0, "cycle 14 Issue #76 gate changed")
    _require(cycle14.get("output_next_action_class") == NEXT_ACTION_CLASS, "cycle 14 next action drifted")

    _require(manifest.get("manifest_sha256") == manifest_sha, "Weaver manifest SHA drifted")
    _require(manifest.get("weaver_authorization_sha256") == authorization_sha, "manifest/Weaver authorization binding drifted")
    _require(manifest.get("weaver_full_text_acquisition_sha256") == evidence_sha, "manifest/Weaver evidence binding drifted")
    _require(manifest.get("weaver_source_sha256") == source_sha, "manifest/Weaver source binding drifted")
    _require(manifest.get("weaver_full_text_acquired") is True, "manifest omitted Weaver acquisition")
    _require(manifest.get("weaver_article_identity_established") is True, "manifest omitted Weaver identity")
    _require(manifest.get("exact_mds2_experiment_identity_established") is False, "manifest promoted experiment identity")
    _require(manifest.get("exact_machine_setting_to_calibrated_power_relation_established") is False, "manifest promoted calibration transfer")
    _require(manifest.get("bridge_established") is False, "manifest promoted bridge")
    _require(manifest.get("directly_comparable_mds2_rows") == 0, "manifest comparable rows changed")
    _require(manifest.get("direct_numerical_cross_source_validation_authorized") is False, "manifest authorized numerical validation")
    _require(manifest.get("issue_76_exact_target_cells_satisfied") == 0, "manifest Issue #76 gate changed")
    _require(manifest.get("generated_next_action_class") == NEXT_ACTION_CLASS, "manifest next action drifted")
    _require(manifest.get("scientific_status_changed") is False, "manifest changed scientific status")
    _require(manifest.get("positive_scientific_closeout_established") is False, "manifest claimed scientific closeout")

    _require(stop.get("reason_code") == "capability_expansion_required", "Weaver final stop reason drifted")
    _require(stop.get("requested_action_class") == NEXT_ACTION_CLASS, "Weaver final stop action drifted")
    _require(stop.get("bounded_candidate_discovered") is False, "unaudited row-identity capability appeared")
    _require(stop.get("scientific_status_changed") is False, "Weaver final stop changed science")
    return "weaver_14_cycle_success_verified"


def verify_live_autonomous_output(output_root: str | Path) -> str:
    root = Path(output_root).expanduser().resolve(strict=True)
    manifest = _load(root, "autonomous-production-manifest.json")
    stop = _load(root, "bounded-stop.json")
    if stop.get("reason_code") == TRANSPORT_STOP_REASON_CODE:
        try:
            return base_verifier.verify_live_autonomous_output(root)
        except base_impl.AutonomousProductionLiveVerificationError as exc:
            raise AutonomousProductionWeaverLiveVerificationError(str(exc)) from exc
    return _verify_weaver_success(root, manifest, stop)


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Verify Weaver-capable autonomous production output.")
    parser.add_argument("output_root", type=Path)
    args = parser.parse_args(argv)
    print(verify_live_autonomous_output(args.output_root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "AutonomousProductionWeaverLiveVerificationError",
    "verify_live_autonomous_output",
]
