from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest

from materials_data_analyzer.research_loop.comparability_engine import (
    COMPARABLE,
    CONDITIONALLY_COMPARABLE,
    NOT_COMPARABLE,
    UNKNOWN,
    AuthenticatedEvidenceInput,
    ComparabilityEngineError,
    DEFAULT_RULE_REGISTRY,
    assess_comparability as _raw_assess_comparability,
    verify_comparability_assessment,
)
from materials_data_analyzer.research_loop.evidence_packet import (
    EvidencePacketError,
    canonical_sha256,
    finalize_evidence_packet,
)


ROOT = Path(__file__).resolve().parents[1]


def _attribute(
    name: str,
    value: object,
    *,
    unit: str | None = None,
) -> dict[str, object]:
    if isinstance(value, bool):
        value_type = "boolean"
    elif isinstance(value, int):
        value_type = "integer"
    elif isinstance(value, float):
        value_type = "number"
    else:
        value_type = "text"
    return {
        "name": name,
        "value": value,
        "value_type": value_type,
        "unit_state": "specified" if unit is not None else "not_applicable",
        "unit": unit,
        "source_binding_ids": ["source-1"],
    }


def _packet(
    *,
    evidence_id: str,
    artifact: bytes,
    locator: str,
    material: str = "IN625",
    sample: str = "sample-1",
    result_kind: str = "ultimate_tensile_strength",
    unit: str = "MPa",
    process_route: str | None = "LPBF",
    geometry: str | None = None,
    protocol: str | None = None,
    instrument: str | None = None,
    calibration_status: str = "unknown",
    source_family_id: str = "source-family-1",
    dataset_parent_id: str = "dataset-1",
    sample_parent_ids: list[str] | None = None,
    acquisition_parent_ids: list[str] | None = None,
    independence_claim_status: str = "not_assessed",
    overlap_status: str = "unknown",
    reference_convention: str | None = "declared_scalar_quantity_convention",
) -> dict[str, Any]:
    process_attributes = []
    if process_route is not None:
        process_attributes.append(_attribute("process_route", process_route))
    sample_attributes = []
    if geometry is not None:
        sample_attributes.append(_attribute("specimen_geometry", geometry))
    method_attributes = []
    if protocol is not None:
        method_attributes.append(_attribute("protocol", protocol))
    if instrument is not None:
        method_attributes.append(_attribute("instrument", instrument))
    measurement_attributes = []
    if reference_convention is not None:
        measurement_attributes.append(
            _attribute("reference_convention", reference_convention)
        )

    unsigned: dict[str, Any] = {
        "schema_version": "1.0",
        "packet_type": "evidence_packet",
        "evidence_id": evidence_id,
        "evidence_kind": "measurement",
        "provider": {
            "provider_id": "benchmark-provider",
            "contract_version": "1.0",
            "schema_version": "1.0",
            "adapter_id": "benchmark-adapter",
        },
        "subject": {
            "subject_type": "material_measurement",
            "identities": [
                {"namespace": "material", "value": material, "role": "material"},
                {"namespace": "sample", "value": sample, "role": "sample"},
            ],
            "material_scope": "test_scope",
            "description": "Provenance-bound comparability benchmark packet.",
        },
        "contexts": {
            "process": {"status": "applicable", "attributes": process_attributes},
            "sample": {"status": "applicable", "attributes": sample_attributes},
            "method": {"status": "applicable", "attributes": method_attributes},
            "measurement": {
                "status": "applicable",
                "attributes": measurement_attributes,
            },
        },
        "results": [
            {
                "result_id": "result-1",
                "result_kind": result_kind,
                "value_state": "observed",
                "value": 1.0,
                "value_type": "number",
                "unit_state": "specified",
                "unit": unit,
                "source_binding_ids": ["source-1"],
                "derivation_ids": [],
                "uncertainty_ids": ["uncertainty-1"],
                "qualifiers": ["benchmark"],
            }
        ],
        "uncertainty": [
            {
                "uncertainty_id": "uncertainty-1",
                "status": "unknown",
                "kind": "measurement_uncertainty",
                "value": None,
                "unit": None,
                "distribution": None,
                "confidence_level": None,
                "source_binding_ids": ["source-1"],
                "notes": "No transferable uncertainty is asserted by this benchmark.",
            }
        ],
        "calibration": {"status": calibration_status, "records": []},
        "source_bindings": [
            {
                "binding_id": "source-1",
                "role": "measurement_source",
                "artifact_id": evidence_id + "-artifact",
                "locator": locator,
                "sha256": __import__("hashlib").sha256(artifact).hexdigest(),
                "byte_size": len(artifact),
                "media_type": "application/octet-stream",
            }
        ],
        "derivation_lineage": [],
        "independence": {
            "source_family_id": source_family_id,
            "dataset_parent_id": dataset_parent_id,
            "sample_parent_ids": (
                [sample] if sample_parent_ids is None else sample_parent_ids
            ),
            "acquisition_parent_ids": (
                [sample + "-acq"]
                if acquisition_parent_ids is None
                else acquisition_parent_ids
            ),
            "development_family_id": None,
            "overlap_status": overlap_status,
            "overlap_with": [],
            "independence_claim_status": independence_claim_status,
        },
        "scientific_validity": {
            "domain_verifier_id": "benchmark-domain-verifier",
            "verification_status": "limited",
            "validated_scope": ["source bytes", "declared benchmark context"],
            "excluded_scope": ["causality", "predictive validation", "engineering use"],
            "assumptions": [],
            "scientific_status_promoted": False,
        },
        "comparability": {
            "status": "not_assessed",
            "requirements": ["separate Comparability Engine assessment required"],
            "limitations": ["packet itself grants no cross-source comparability"],
            "comparison_performed": False,
            "comparable_claimed": False,
        },
        "limitations": ["Benchmark packet does not authorize predictive or engineering use."],
        "authority": {
            "empirical_evidence_created": True,
            "scientific_status_promoted": False,
            "downstream_use_authorized": False,
            "planning_metadata_only": False,
            "row_level_measurement_authority": True,
            "authority_source": "domain_verifier",
        },
    }
    return finalize_evidence_packet(unsigned)


def _expectations(packet: dict[str, Any]) -> dict[str, Any]:
    return {
        "provider_id": packet["provider"]["provider_id"],
        "subject_identities": copy.deepcopy(packet["subject"]["identities"]),
        "source_bindings": copy.deepcopy(packet["source_bindings"]),
        "result_units": {
            result["result_id"]: result["unit"]
            for result in packet["results"]
        },
        "calibration_status": packet["calibration"]["status"],
        "uncertainty_status_by_id": {
            record["uncertainty_id"]: record["status"]
            for record in packet["uncertainty"]
        },
        "existing_source_family_ids": [],
        "packet_sha256": packet["packet_sha256"],
    }


def _rehash_packet(packet: dict[str, Any]) -> dict[str, Any]:
    value = copy.deepcopy(packet)
    value.pop("packet_sha256", None)
    value["packet_sha256"] = canonical_sha256(value)
    return value


def _input(packet: dict[str, Any], artifact: bytes) -> AuthenticatedEvidenceInput:
    expected = _expectations(packet)
    return AuthenticatedEvidenceInput(
        packet=packet,
        artifacts={"source-1": artifact},
        expected=expected,
        trusted_expectation_sha256=canonical_sha256(expected),
    )


def _claim(
    *required: str,
    allowed_transformations: tuple[str, ...] = (),
    independent: bool = False,
) -> dict[str, Any]:
    dimensions = [rule.dimension for rule in DEFAULT_RULE_REGISTRY]
    required_set = set(required)
    return {
        "claim_id": "benchmark-claim",
        "claim_type": "declared_cross_source_comparison",
        "required_dimensions": [d for d in dimensions if d in required_set],
        "irrelevant_dimensions": [d for d in dimensions if d not in required_set],
        "allowed_transformations": list(allowed_transformations),
        "requires_independent_replication": independent,
        "maximum_downstream_use_requested": "comparative",
    }


def _assess(
    left: AuthenticatedEvidenceInput,
    right: AuthenticatedEvidenceInput,
    *,
    claim_scope: dict[str, Any],
    rule_registry=DEFAULT_RULE_REGISTRY,
) -> dict[str, Any]:
    return _raw_assess_comparability(
        left,
        right,
        claim_scope=claim_scope,
        trusted_claim_scope_sha256=canonical_sha256(claim_scope),
        rule_registry=rule_registry,
    )


def test_exact_context_can_be_comparable_without_granting_predictive_authority() -> None:
    left_raw = b"left-real-source\n"
    right_raw = b"right-real-source\n"
    left = _packet(evidence_id="left", artifact=left_raw, locator="artifacts/left.bin")
    right = _packet(
        evidence_id="right",
        artifact=right_raw,
        locator="artifacts/right.bin",
        source_family_id="source-family-2",
        dataset_parent_id="dataset-2",
        sample="sample-2",
    )
    claim = _claim(
        "material_identity",
        "process_route",
        "target_response_semantics",
        "units_reference_conventions",
    )

    result = _assess(
        _input(left, left_raw),
        _input(right, right_raw),
        claim_scope=claim,
    )

    assert result["assessment_status"] == COMPARABLE
    assert result["left_packet"]["source_bindings"][0]["sha256"] == left["source_bindings"][0]["sha256"]
    assert result["right_packet"]["source_bindings"][0]["byte_size"] == len(right_raw)
    assert result["conflicting_dimensions"] == []
    assert result["missing_context"] == []
    assert result["maximum_allowed_downstream_use"] == "descriptive_comparison_only"
    assert set(result["authority_boundary"].values()) == {False}


def test_declared_unit_normalization_yields_conditional_not_unqualified_comparability() -> None:
    left_raw = b"left\n"
    right_raw = b"right\n"
    left = _packet(evidence_id="left", artifact=left_raw, locator="a/left.bin", unit="MPa")
    right = _packet(
        evidence_id="right",
        artifact=right_raw,
        locator="a/right.bin",
        unit="kPa",
        source_family_id="family-2",
        dataset_parent_id="dataset-2",
        sample="sample-2",
    )
    claim = _claim(
        "material_identity",
        "target_response_semantics",
        "units_reference_conventions",
        allowed_transformations=("units_reference_conventions",),
    )
    result = _assess(
        _input(left, left_raw),
        _input(right, right_raw),
        claim_scope=claim,
    )
    assert result["assessment_status"] == CONDITIONALLY_COMPARABLE
    assert result["required_normalization"] == ["units_reference_conventions"]
    assert result["authority_boundary"]["calibration_transfer_performed"] is False


def test_declared_unit_transformation_rejects_dimensionally_incompatible_units() -> None:
    left_raw = b"left\n"
    right_raw = b"right\n"
    left = _packet(evidence_id="left", artifact=left_raw, locator="a/left.bin", unit="MPa")
    right = _packet(
        evidence_id="right",
        artifact=right_raw,
        locator="a/right.bin",
        unit="um",
        source_family_id="family-2",
        dataset_parent_id="dataset-2",
        sample="sample-2",
    )
    result = _assess(
        _input(left, left_raw),
        _input(right, right_raw),
        claim_scope=_claim(
            "material_identity",
            "target_response_semantics",
            "units_reference_conventions",
            allowed_transformations=("units_reference_conventions",),
        ),
    )
    assert result["assessment_status"] == NOT_COMPARABLE
    assert result["required_normalization"] == []
    assert result["conflicting_dimensions"] == ["units_reference_conventions"]


def test_missing_required_protocol_stays_unknown() -> None:
    left_raw = b"left\n"
    right_raw = b"right\n"
    left = _packet(evidence_id="left", artifact=left_raw, locator="a/left.bin")
    right = _packet(
        evidence_id="right",
        artifact=right_raw,
        locator="a/right.bin",
        source_family_id="family-2",
        dataset_parent_id="dataset-2",
        sample="sample-2",
    )
    result = _assess(
        _input(left, left_raw),
        _input(right, right_raw),
        claim_scope=_claim("protocol_reference_version"),
    )
    assert result["assessment_status"] == UNKNOWN
    assert result["missing_context"] == ["protocol_reference_version"]
    assert result["planner_evidence_gaps"] == [
        {
            "requirement_id": "comparability-context:protocol_reference_version",
            "dimension": "protocol_reference_version",
            "requirement_status": "missing_context",
            "action_class": "evidence_acquisition",
            "scientific_status_promoted": False,
        }
    ]
    assert result["authority_boundary"]["missing_context_inferred"] is False


def test_missing_sample_or_acquisition_lineage_stays_unknown() -> None:
    left_raw = b"left\n"
    right_raw = b"right\n"
    left = _packet(
        evidence_id="left",
        artifact=left_raw,
        locator="a/left.bin",
        sample_parent_ids=[],
        acquisition_parent_ids=[],
    )
    right = _packet(
        evidence_id="right",
        artifact=right_raw,
        locator="a/right.bin",
        sample_parent_ids=[],
        acquisition_parent_ids=[],
        source_family_id="family-2",
        dataset_parent_id="dataset-2",
        sample="sample-2",
    )
    result = _assess(
        _input(left, left_raw),
        _input(right, right_raw),
        claim_scope=_claim("sample_acquisition_identity"),
    )
    assert result["assessment_status"] == UNKNOWN
    assert result["missing_context"] == ["sample_acquisition_identity"]


def test_absent_preprocessing_history_does_not_imply_same_processing() -> None:
    left_raw = b"left\n"
    right_raw = b"right\n"
    left = _packet(evidence_id="left", artifact=left_raw, locator="a/left.bin")
    right = _packet(
        evidence_id="right",
        artifact=right_raw,
        locator="a/right.bin",
        source_family_id="family-2",
        dataset_parent_id="dataset-2",
        sample="sample-2",
    )
    result = _assess(
        _input(left, left_raw),
        _input(right, right_raw),
        claim_scope=_claim("preprocessing_transformation_history"),
    )
    assert result["assessment_status"] == UNKNOWN
    assert result["missing_context"] == ["preprocessing_transformation_history"]


def test_missing_reference_convention_keeps_unit_comparability_unknown() -> None:
    left_raw = b"left\n"
    right_raw = b"right\n"
    left = _packet(
        evidence_id="left",
        artifact=left_raw,
        locator="a/left.bin",
        reference_convention=None,
    )
    right = _packet(
        evidence_id="right",
        artifact=right_raw,
        locator="a/right.bin",
        source_family_id="family-2",
        dataset_parent_id="dataset-2",
        sample="sample-2",
        reference_convention=None,
    )
    result = _assess(
        _input(left, left_raw),
        _input(right, right_raw),
        claim_scope=_claim("units_reference_conventions"),
    )
    assert result["assessment_status"] == UNKNOWN
    assert result["missing_context"] == ["units_reference_conventions"]


def test_unknown_calibration_on_both_packets_does_not_become_comparable() -> None:
    left_raw = b"left\n"
    right_raw = b"right\n"
    left = _packet(evidence_id="left", artifact=left_raw, locator="a/left.bin")
    right = _packet(
        evidence_id="right",
        artifact=right_raw,
        locator="a/right.bin",
        source_family_id="family-2",
        dataset_parent_id="dataset-2",
        sample="sample-2",
    )
    result = _assess(
        _input(left, left_raw),
        _input(right, right_raw),
        claim_scope=_claim("instrument_state_calibration"),
    )
    assert result["assessment_status"] == UNKNOWN
    assert result["missing_context"] == ["instrument_state_calibration"]


def test_same_source_family_blocks_independent_replication_claim() -> None:
    left_raw = b"left\n"
    right_raw = b"right\n"
    left = _packet(
        evidence_id="left",
        artifact=left_raw,
        locator="a/left.bin",
        independence_claim_status="independent_within_stated_dimensions",
        overlap_status="no_known_overlap",
    )
    right = _packet(
        evidence_id="right",
        artifact=right_raw,
        locator="a/right.bin",
        sample="sample-2",
        independence_claim_status="independent_within_stated_dimensions",
        overlap_status="no_known_overlap",
    )
    result = _assess(
        _input(left, left_raw),
        _input(right, right_raw),
        claim_scope=_claim("independence_lineage", independent=True),
    )
    assert result["assessment_status"] == NOT_COMPARABLE
    assert result["conflicting_dimensions"] == ["independence_lineage"]
    assert result["independence_relationships"]["same_source_family_id"] is True


def test_real_in625_nist_vs_zenodo_chain_remains_not_comparable_for_direct_numerical_claim() -> None:
    nist_path = ROOT / "data/case_studies/nist_ambench_2018_02/README.md"
    zenodo_path = ROOT / "configs/research/in625_tensile_reviewed_intake.v1.json"
    nist_raw = nist_path.read_bytes()
    zenodo_raw = zenodo_path.read_bytes()

    nist = _packet(
        evidence_id="nist-ambench-2018-02-melt-pool",
        artifact=nist_raw,
        locator="data/case_studies/nist_ambench_2018_02/README.md",
        result_kind="melt_pool_width",
        unit="um",
        process_route="bare_plate_single_track",
        geometry="individual laser scan track on bare substrate without powder",
        protocol="polished transverse cross-section optical metrology",
        instrument="NIST AMMT",
        source_family_id="nist-ambench-2018-02",
        dataset_parent_id="nist-ambench-2018-02",
    )
    tensile = _packet(
        evidence_id="zenodo-20503603-tensile",
        artifact=zenodo_raw,
        locator="configs/research/in625_tensile_reviewed_intake.v1.json",
        result_kind="tensile_stress",
        unit="MPa",
        process_route="LPBF manufactured material",
        geometry="DIN50125 Type E tensile specimen",
        protocol="DIN50125 Type E room-temperature uniaxial tensile test",
        instrument=None,
        source_family_id="zenodo-20503603",
        dataset_parent_id="zenodo-20503603",
        sample="AM-AB-H",
    )
    claim = _claim(
        "material_identity",
        "process_route",
        "geometry",
        "target_response_semantics",
        "units_reference_conventions",
        "protocol_reference_version",
    )
    result = _assess(
        _input(nist, nist_raw),
        _input(tensile, zenodo_raw),
        claim_scope=claim,
    )

    assert result["assessment_status"] == NOT_COMPARABLE
    assert "material_identity" in result["satisfied_dimensions"]
    assert {
        "process_route",
        "geometry",
        "target_response_semantics",
        "units_reference_conventions",
        "protocol_reference_version",
    } <= set(result["conflicting_dimensions"])
    assert result["maximum_allowed_downstream_use"] == "none"
    assert result["authority_boundary"]["scientific_status_promoted"] is False


def test_characterization_software_example_is_not_material_phase_validation() -> None:
    example_raw = b"lossy FINDS SAED software example\n"
    material_raw = b"raw calibrated material-aware diffraction evidence\n"
    example = _packet(
        evidence_id="saed-software-example",
        artifact=example_raw,
        locator="characterization/saed-example.bin",
        material="software_example_unspecified",
        result_kind="algorithm_example_diffraction_pattern",
        unit="1/nm",
        process_route=None,
        geometry=None,
        protocol="lossy software demonstration",
        instrument=None,
        source_family_id="software-example",
        dataset_parent_id="software-example",
    )
    material = _packet(
        evidence_id="material-aware-saed",
        artifact=material_raw,
        locator="characterization/raw-saed.bin",
        material="IN625",
        result_kind="phase_indexing_observation",
        unit="1/nm",
        process_route=None,
        geometry=None,
        protocol="raw calibrated material-aware SAED",
        instrument="TEM diffraction detector",
        calibration_status="unknown",
        source_family_id="material-validation",
        dataset_parent_id="material-validation",
        sample="foil-1",
    )
    result = _assess(
        _input(example, example_raw),
        _input(material, material_raw),
        claim_scope=_claim(
            "material_identity",
            "target_response_semantics",
            "protocol_reference_version",
        ),
    )
    assert result["assessment_status"] == NOT_COMPARABLE
    assert "material_identity" in result["conflicting_dimensions"]
    assert "target_response_semantics" in result["conflicting_dimensions"]


def test_rehashed_assessment_tamper_fails_authenticated_recomputation() -> None:
    left_raw = b"left\n"
    right_raw = b"right\n"
    left = _packet(evidence_id="left", artifact=left_raw, locator="a/left.bin")
    right = _packet(
        evidence_id="right",
        artifact=right_raw,
        locator="a/right.bin",
        source_family_id="family-2",
        dataset_parent_id="dataset-2",
        sample="sample-2",
    )
    left_input = _input(left, left_raw)
    right_input = _input(right, right_raw)
    claim = _claim("material_identity")
    result = _assess(left_input, right_input, claim_scope=claim)
    forged = copy.deepcopy(result)
    forged["assessment_status"] = NOT_COMPARABLE
    forged.pop("assessment_sha256")
    forged["assessment_sha256"] = canonical_sha256(forged)

    with pytest.raises(
        ComparabilityEngineError,
        match="authenticated recomputation",
    ):
        verify_comparability_assessment(
            forged,
            left_input,
            right_input,
            claim_scope=claim,
            trusted_claim_scope_sha256=canonical_sha256(claim),
        )


def test_packet_source_substitution_cannot_be_hidden_by_rehashing_packet() -> None:
    raw = b"original-source\n"
    packet = _packet(evidence_id="left", artifact=raw, locator="a/left.bin")
    expected = _expectations(packet)
    trusted = canonical_sha256(expected)

    forged = copy.deepcopy(packet)
    attacker = b"attacker-source\n"
    forged["source_bindings"][0]["sha256"] = __import__("hashlib").sha256(attacker).hexdigest()
    forged["source_bindings"][0]["byte_size"] = len(attacker)
    forged.pop("packet_sha256")
    forged["packet_sha256"] = canonical_sha256(forged)

    other_raw = b"other\n"
    other = _packet(
        evidence_id="other",
        artifact=other_raw,
        locator="a/other.bin",
        source_family_id="family-2",
        dataset_parent_id="dataset-2",
        sample="sample-2",
    )
    forged_input = AuthenticatedEvidenceInput(
        packet=forged,
        artifacts={"source-1": attacker},
        expected=expected,
        trusted_expectation_sha256=trusted,
    )

    with pytest.raises(
        EvidencePacketError,
        match="source role/path/artifact substitution|packet SHA-256 expectation",
    ):
        _assess(
            forged_input,
            _input(other, other_raw),
            claim_scope=_claim("material_identity"),
        )


def test_claim_scope_cannot_be_weakened_under_original_external_trust_root() -> None:
    raw = b"source\n"
    packet = _packet(evidence_id="one", artifact=raw, locator="a/one.bin")
    original = _claim("material_identity", "material_composition")
    trusted = canonical_sha256(original)
    weakened = copy.deepcopy(original)
    weakened["required_dimensions"].remove("material_composition")
    weakened["irrelevant_dimensions"].append("material_composition")
    weakened["irrelevant_dimensions"].sort(
        key=[rule.dimension for rule in DEFAULT_RULE_REGISTRY].index
    )

    with pytest.raises(
        ComparabilityEngineError,
        match="external trust-root",
    ):
        _raw_assess_comparability(
            _input(packet, raw),
            _input(packet, raw),
            claim_scope=weakened,
            trusted_claim_scope_sha256=trusted,
        )


def test_v1_rule_registry_cannot_be_narrowed_by_caller() -> None:
    raw = b"source\n"
    packet = _packet(evidence_id="one", artifact=raw, locator="a/one.bin")
    claim = _claim("material_identity")
    with pytest.raises(
        ComparabilityEngineError,
        match="rule registry is immutable",
    ):
        _raw_assess_comparability(
            _input(packet, raw),
            _input(packet, raw),
            claim_scope=claim,
            trusted_claim_scope_sha256=canonical_sha256(claim),
            rule_registry=DEFAULT_RULE_REGISTRY[:-1],
        )


def test_claim_must_explicitly_classify_every_registered_dimension() -> None:
    raw = b"source\n"
    packet = _packet(evidence_id="one", artifact=raw, locator="a/one.bin")
    malformed = _claim("material_identity")
    malformed["irrelevant_dimensions"].remove("protocol_reference_version")
    with pytest.raises(
        ComparabilityEngineError,
        match="every registered comparability dimension",
    ):
        _assess(
            _input(packet, raw),
            _input(packet, raw),
            claim_scope=malformed,
        )



def test_independent_replication_claim_cannot_waive_lineage_dimension() -> None:
    raw = b"source\n"
    packet = _packet(evidence_id="one", artifact=raw, locator="a/one.bin")
    claim = _claim("material_identity", independent=True)

    with pytest.raises(
        ComparabilityEngineError,
        match="must require independence_lineage",
    ):
        _assess(
            _input(packet, raw),
            _input(packet, raw),
            claim_scope=claim,
        )


def test_material_identity_namespace_is_part_of_identity() -> None:
    left_raw = b"left\n"
    right_raw = b"right\n"
    left = _packet(evidence_id="left", artifact=left_raw, locator="a/left.bin")
    right = _packet(
        evidence_id="right",
        artifact=right_raw,
        locator="a/right.bin",
        source_family_id="family-2",
        dataset_parent_id="dataset-2",
        sample="sample-2",
    )
    right["subject"]["identities"][0]["namespace"] = "supplier-code"
    right = _rehash_packet(right)

    result = _assess(
        _input(left, left_raw),
        _input(right, right_raw),
        claim_scope=_claim("material_identity"),
    )
    assert result["assessment_status"] == NOT_COMPARABLE
    assert result["conflicting_dimensions"] == ["material_identity"]


def test_unknown_quantitative_context_unit_stays_missing() -> None:
    left_raw = b"left\n"
    right_raw = b"right\n"
    left = _packet(evidence_id="left", artifact=left_raw, locator="a/left.bin")
    right = _packet(
        evidence_id="right",
        artifact=right_raw,
        locator="a/right.bin",
        source_family_id="family-2",
        dataset_parent_id="dataset-2",
        sample="sample-2",
    )
    unknown_power = {
        "name": "laser_power",
        "value": 100,
        "value_type": "integer",
        "unit_state": "unknown",
        "unit": None,
        "source_binding_ids": ["source-1"],
    }
    left["contexts"]["measurement"]["attributes"].append(copy.deepcopy(unknown_power))
    right["contexts"]["measurement"]["attributes"].append(copy.deepcopy(unknown_power))
    left = _rehash_packet(left)
    right = _rehash_packet(right)

    result = _assess(
        _input(left, left_raw),
        _input(right, right_raw),
        claim_scope=_claim("acquisition_parameters"),
    )
    assert result["assessment_status"] == UNKNOWN
    assert result["missing_context"] == ["acquisition_parameters"]


def test_all_duplicate_result_kind_units_are_compared() -> None:
    left_raw = b"left\n"
    right_raw = b"right\n"
    left = _packet(evidence_id="left", artifact=left_raw, locator="a/left.bin")
    right = _packet(
        evidence_id="right",
        artifact=right_raw,
        locator="a/right.bin",
        source_family_id="family-2",
        dataset_parent_id="dataset-2",
        sample="sample-2",
    )

    def second_result(result_id: str, unit: str) -> dict[str, Any]:
        return {
            "result_id": result_id,
            "result_kind": "ultimate_tensile_strength",
            "value_state": "observed",
            "value": 2.0,
            "value_type": "number",
            "unit_state": "specified",
            "unit": unit,
            "source_binding_ids": ["source-1"],
            "derivation_ids": [],
            "uncertainty_ids": [],
            "qualifiers": ["second-measurement"],
        }

    left["results"].append(second_result("result-2", "GPa"))
    right["results"].append(second_result("result-2", "MPa"))
    left = _rehash_packet(left)
    right = _rehash_packet(right)

    result = _assess(
        _input(left, left_raw),
        _input(right, right_raw),
        claim_scope=_claim("units_reference_conventions"),
    )
    assert result["assessment_status"] == NOT_COMPARABLE
    assert result["conflicting_dimensions"] == ["units_reference_conventions"]


def test_one_sided_unknown_result_unit_is_missing_not_conflict() -> None:
    left_raw = b"left\n"
    right_raw = b"right\n"
    left = _packet(evidence_id="left", artifact=left_raw, locator="a/left.bin")
    right = _packet(
        evidence_id="right",
        artifact=right_raw,
        locator="a/right.bin",
        source_family_id="family-2",
        dataset_parent_id="dataset-2",
        sample="sample-2",
    )
    right["results"][0]["unit_state"] = "unknown"
    right["results"][0]["unit"] = None
    right = _rehash_packet(right)

    result = _assess(
        _input(left, left_raw),
        _input(right, right_raw),
        claim_scope=_claim("units_reference_conventions"),
    )
    assert result["assessment_status"] == UNKNOWN
    assert result["missing_context"] == ["units_reference_conventions"]
    assert result["conflicting_dimensions"] == []


def test_commanded_and_actual_laser_power_do_not_alias() -> None:
    left_raw = b"left\n"
    right_raw = b"right\n"
    left = _packet(evidence_id="left", artifact=left_raw, locator="a/left.bin")
    right = _packet(
        evidence_id="right",
        artifact=right_raw,
        locator="a/right.bin",
        source_family_id="family-2",
        dataset_parent_id="dataset-2",
        sample="sample-2",
    )
    left["contexts"]["measurement"]["attributes"].append(
        _attribute("actual_laser_power_w", 200, unit="W")
    )
    right["contexts"]["measurement"]["attributes"].append(
        _attribute("commanded_laser_power_w", 200, unit="W")
    )
    left = _rehash_packet(left)
    right = _rehash_packet(right)

    result = _assess(
        _input(left, left_raw),
        _input(right, right_raw),
        claim_scope=_claim("acquisition_parameters"),
    )
    assert result["assessment_status"] == NOT_COMPARABLE
    assert result["conflicting_dimensions"] == ["acquisition_parameters"]


def test_preprocessing_history_preserves_software_sha() -> None:
    left_raw = b"left\n"
    right_raw = b"right\n"
    left = _packet(evidence_id="left", artifact=left_raw, locator="a/left.bin")
    right = _packet(
        evidence_id="right",
        artifact=right_raw,
        locator="a/right.bin",
        source_family_id="family-2",
        dataset_parent_id="dataset-2",
        sample="sample-2",
    )

    def make_derived(packet: dict[str, Any], software_sha: str) -> dict[str, Any]:
        value = copy.deepcopy(packet)
        value["results"][0]["value_state"] = "derived"
        value["results"][0]["derivation_ids"] = ["derive-1"]
        value["derivation_lineage"] = [
            {
                "derivation_id": "derive-1",
                "operation": "deterministic preprocessing",
                "input_binding_ids": ["source-1"],
                "input_result_ids": [],
                "output_result_ids": ["result-1"],
                "software": {
                    "name": "processor",
                    "version": "1.0",
                    "sha256": software_sha,
                },
                "parameters": {"window": 5},
                "scientific_status_promoted": False,
            }
        ]
        return _rehash_packet(value)

    left = make_derived(left, "a" * 64)
    right = make_derived(right, "b" * 64)

    result = _assess(
        _input(left, left_raw),
        _input(right, right_raw),
        claim_scope=_claim("preprocessing_transformation_history"),
    )
    assert result["assessment_status"] == NOT_COMPARABLE
    assert result["conflicting_dimensions"] == [
        "preprocessing_transformation_history"
    ]


def test_explicit_known_overlap_is_independence_conflict() -> None:
    left_raw = b"left\n"
    right_raw = b"right\n"
    left = _packet(
        evidence_id="left",
        artifact=left_raw,
        locator="a/left.bin",
        source_family_id="family-1",
        dataset_parent_id="dataset-1",
        sample="sample-1",
    )
    right = _packet(
        evidence_id="right",
        artifact=right_raw,
        locator="a/right.bin",
        source_family_id="family-2",
        dataset_parent_id="dataset-2",
        sample="sample-2",
    )
    left["independence"]["overlap_status"] = "known_overlap"
    left["independence"]["overlap_with"] = ["right"]
    left["independence"]["independence_claim_status"] = "not_independent"
    right["independence"]["overlap_status"] = "no_known_overlap"
    right["independence"]["independence_claim_status"] = (
        "independent_within_stated_dimensions"
    )
    left = _rehash_packet(left)
    right = _rehash_packet(right)

    result = _assess(
        _input(left, left_raw),
        _input(right, right_raw),
        claim_scope=_claim("independence_lineage", independent=True),
    )
    assert result["assessment_status"] == NOT_COMPARABLE
    assert result["conflicting_dimensions"] == ["independence_lineage"]


def test_calibration_identity_and_bound_source_provenance_are_compared() -> None:
    left_raw = b"left-calibration-source\n"
    right_raw = b"right-calibration-source\n"
    left = _packet(evidence_id="left", artifact=left_raw, locator="a/left.bin")
    right = _packet(
        evidence_id="right",
        artifact=right_raw,
        locator="a/right.bin",
        source_family_id="family-2",
        dataset_parent_id="dataset-2",
        sample="sample-2",
    )
    left["calibration"] = {
        "status": "calibrated",
        "records": [
            {
                "calibration_id": "cal-A",
                "scope": "laser power calibration",
                "source_binding_ids": ["source-1"],
                "uncertainty_ids": [],
                "notes": None,
            }
        ],
    }
    right["calibration"] = {
        "status": "calibrated",
        "records": [
            {
                "calibration_id": "cal-B",
                "scope": "laser power calibration",
                "source_binding_ids": ["source-1"],
                "uncertainty_ids": [],
                "notes": None,
            }
        ],
    }
    left = _rehash_packet(left)
    right = _rehash_packet(right)

    result = _assess(
        _input(left, left_raw),
        _input(right, right_raw),
        claim_scope=_claim("instrument_state_calibration"),
    )
    assert result["assessment_status"] == NOT_COMPARABLE
    assert result["conflicting_dimensions"] == ["instrument_state_calibration"]


def test_unknown_target_response_state_stays_missing() -> None:
    left_raw = b"left\n"
    right_raw = b"right\n"
    left = _packet(evidence_id="left", artifact=left_raw, locator="a/left.bin")
    right = _packet(
        evidence_id="right",
        artifact=right_raw,
        locator="a/right.bin",
        source_family_id="family-2",
        dataset_parent_id="dataset-2",
        sample="sample-2",
    )
    right["results"][0]["value_state"] = "unknown"
    right["results"][0]["value"] = None
    right["results"][0]["value_type"] = "null"
    right["authority"]["empirical_evidence_created"] = False
    right["authority"]["row_level_measurement_authority"] = False
    right["authority"]["authority_source"] = "none"
    right = _rehash_packet(right)

    result = _assess(
        _input(left, left_raw),
        _input(right, right_raw),
        claim_scope=_claim("target_response_semantics"),
    )
    assert result["assessment_status"] == UNKNOWN
    assert result["missing_context"] == ["target_response_semantics"]


def test_parent_identifier_order_does_not_create_false_conflict() -> None:
    left_raw = b"left\n"
    right_raw = b"right\n"
    left = _packet(
        evidence_id="left",
        artifact=left_raw,
        locator="a/left.bin",
        sample="sample-shared",
        sample_parent_ids=["parent-a", "parent-b"],
        acquisition_parent_ids=["acq-a", "acq-b"],
    )
    right = _packet(
        evidence_id="right",
        artifact=right_raw,
        locator="a/right.bin",
        source_family_id="family-2",
        dataset_parent_id="dataset-2",
        sample="sample-shared",
        sample_parent_ids=["parent-b", "parent-a"],
        acquisition_parent_ids=["acq-b", "acq-a"],
    )

    result = _assess(
        _input(left, left_raw),
        _input(right, right_raw),
        claim_scope=_claim("sample_acquisition_identity"),
    )
    assert result["assessment_status"] == COMPARABLE
    assert result["satisfied_dimensions"] == ["sample_acquisition_identity"]
