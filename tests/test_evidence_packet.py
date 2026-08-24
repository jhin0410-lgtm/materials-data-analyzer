from __future__ import annotations

import copy
import hashlib

import pytest

from materials_data_analyzer.research_loop.evidence_packet import (
    EvidencePacketError,
    canonical_sha256,
    finalize_evidence_packet,
    normalize_evidence_packet,
    validate_evidence_packet,
)


SOURCE_BYTES = b"real-in625-row-level-source-bytes\n"
SOURCE_SHA = hashlib.sha256(SOURCE_BYTES).hexdigest()


def _unsigned_measurement_packet() -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "packet_type": "evidence_packet",
        "evidence_id": "in625-tensile-row-1",
        "evidence_kind": "measurement",
        "provider": {
            "provider_id": "in625-process-property-provider",
            "contract_version": "1.0",
            "schema_version": "1.0",
            "adapter_id": "in625-reviewed-tensile-evidence-packet-v1",
        },
        "subject": {
            "subject_type": "material_measurement",
            "identities": [
                {"namespace": "material", "value": "IN625", "role": "material"},
                {"namespace": "sample", "value": "AM-AB-H:block-1", "role": "sample"},
            ],
            "material_scope": "exact_in625_source_dataset_scope",
            "description": "One provenance-bound IN625 tensile measurement result.",
        },
        "contexts": {
            "process": {
                "status": "applicable",
                "attributes": [
                    {
                        "name": "process_family",
                        "value": "additive_manufacturing",
                        "value_type": "text",
                        "unit_state": "not_applicable",
                        "unit": None,
                        "source_binding_ids": ["source-1"],
                    }
                ],
            },
            "sample": {
                "status": "applicable",
                "attributes": [
                    {
                        "name": "sample_id",
                        "value": "AM-AB-H:block-1",
                        "value_type": "text",
                        "unit_state": "not_applicable",
                        "unit": None,
                        "source_binding_ids": ["source-1"],
                    }
                ],
            },
            "method": {
                "status": "applicable",
                "attributes": [
                    {
                        "name": "method",
                        "value": "tensile_test",
                        "value_type": "text",
                        "unit_state": "not_applicable",
                        "unit": None,
                        "source_binding_ids": ["source-1"],
                    }
                ],
            },
            "measurement": {
                "status": "applicable",
                "attributes": [
                    {
                        "name": "measurement_semantics",
                        "value": "reported_source_measurement",
                        "value_type": "text",
                        "unit_state": "not_applicable",
                        "unit": None,
                        "source_binding_ids": ["source-1"],
                    }
                ],
            },
        },
        "results": [
            {
                "result_id": "result-uts",
                "result_kind": "ultimate_tensile_strength",
                "value_state": "observed",
                "value": 950.0,
                "value_type": "number",
                "unit_state": "specified",
                "unit": "MPa",
                "source_binding_ids": ["source-1"],
                "derivation_ids": [],
                "uncertainty_ids": ["uncertainty-uts"],
                "qualifiers": ["source-reported"],
            }
        ],
        "uncertainty": [
            {
                "uncertainty_id": "uncertainty-uts",
                "status": "unknown",
                "kind": "measurement_uncertainty",
                "value": None,
                "unit": None,
                "distribution": None,
                "confidence_level": None,
                "source_binding_ids": ["source-1"],
                "notes": "The source does not quantify this uncertainty here.",
            }
        ],
        "calibration": {"status": "unknown", "records": []},
        "source_bindings": [
            {
                "binding_id": "source-1",
                "role": "measurement_source",
                "artifact_id": "in625-row-source-1",
                "locator": "artifacts/in625-row-source-1.csv",
                "sha256": SOURCE_SHA,
                "byte_size": len(SOURCE_BYTES),
                "media_type": "text/csv",
            }
        ],
        "derivation_lineage": [],
        "independence": {
            "source_family_id": "zenodo-20503603",
            "dataset_parent_id": "zenodo-20503603",
            "sample_parent_ids": ["AM-AB-H"],
            "acquisition_parent_ids": ["AM-AB-H:block-1"],
            "development_family_id": None,
            "overlap_status": "unknown",
            "overlap_with": [],
            "independence_claim_status": "not_assessed",
        },
        "scientific_validity": {
            "domain_verifier_id": "in625-tensile-quality-verifier-v1",
            "verification_status": "limited",
            "validated_scope": ["source bytes", "row identity", "reported measurement"],
            "excluded_scope": ["cross-source comparability", "causality", "calibration transfer"],
            "assumptions": [],
            "scientific_status_promoted": False,
        },
        "comparability": {
            "status": "not_assessed",
            "requirements": ["separate comparability engine assessment required"],
            "limitations": ["no cross-source comparability is claimed by this packet"],
            "comparison_performed": False,
            "comparable_claimed": False,
        },
        "limitations": [
            "Measurement uncertainty is not quantified in the bound source context.",
            "This packet does not establish cross-source comparability.",
        ],
        "authority": {
            "empirical_evidence_created": True,
            "scientific_status_promoted": False,
            "downstream_use_authorized": False,
            "planning_metadata_only": False,
            "row_level_measurement_authority": True,
            "authority_source": "domain_verifier",
        },
    }


def _packet() -> dict[str, object]:
    return finalize_evidence_packet(_unsigned_measurement_packet())


def _rehash(packet: dict[str, object]) -> dict[str, object]:
    packet = copy.deepcopy(packet)
    packet.pop("packet_sha256", None)
    packet["packet_sha256"] = canonical_sha256(packet)
    return packet


def _expectations(packet: dict[str, object]) -> dict[str, object]:
    return {
        "provider_id": "in625-process-property-provider",
        "subject_identities": copy.deepcopy(packet["subject"]["identities"]),  # type: ignore[index]
        "source_bindings": copy.deepcopy(packet["source_bindings"]),
        "result_units": {"result-uts": "MPa"},
        "calibration_status": "unknown",
        "uncertainty_status_by_id": {"uncertainty-uts": "unknown"},
        "existing_source_family_ids": [],
    }


def test_packet_is_deterministic_and_normalization_preserves_authority() -> None:
    packet = _packet()
    expected = _expectations(packet)

    first = normalize_evidence_packet(
        packet,
        artifacts={"source-1": SOURCE_BYTES},
        expected=expected,
    )
    second = normalize_evidence_packet(
        packet,
        artifacts={"source-1": SOURCE_BYTES},
        expected=expected,
    )

    assert first == second == packet
    assert first is not packet
    assert first["uncertainty"][0]["status"] == "unknown"  # type: ignore[index]
    assert first["calibration"] == {"status": "unknown", "records": []}
    assert first["authority"] == packet["authority"]
    assert first["comparability"]["comparison_performed"] is False  # type: ignore[index]


def test_packet_self_hash_tampering_fails_closed() -> None:
    packet = _packet()
    packet["packet_sha256"] = "0" * 64
    with pytest.raises(EvidencePacketError, match="self-hash mismatch"):
        validate_evidence_packet(packet)


def test_unknown_field_tampering_fails_even_when_rehashed() -> None:
    packet = _packet()
    packet["forged"] = True
    packet = _rehash(packet)
    with pytest.raises(EvidencePacketError, match="exact keys"):
        validate_evidence_packet(packet)


def test_source_sha_substitution_is_rejected_by_bound_bytes() -> None:
    packet = _packet()
    attacker = b"attacker-controlled-source\n"
    packet["source_bindings"][0]["sha256"] = hashlib.sha256(attacker).hexdigest()  # type: ignore[index]
    packet["source_bindings"][0]["byte_size"] = len(attacker)  # type: ignore[index]
    packet = _rehash(packet)

    with pytest.raises(EvidencePacketError, match="artifact byte size mismatch|artifact SHA-256 mismatch"):
        validate_evidence_packet(packet, artifacts={"source-1": SOURCE_BYTES})


def test_provider_identity_substitution_is_rejected_even_when_rehashed() -> None:
    packet = _packet()
    expected = _expectations(packet)
    packet["provider"]["provider_id"] = "forged-provider"  # type: ignore[index]
    packet = _rehash(packet)

    with pytest.raises(EvidencePacketError, match="provider identity substitution"):
        validate_evidence_packet(packet, expected=expected)


def test_material_subject_substitution_is_rejected_even_when_rehashed() -> None:
    packet = _packet()
    expected = _expectations(packet)
    packet["subject"]["identities"][0]["value"] = "IN718"  # type: ignore[index]
    packet = _rehash(packet)

    with pytest.raises(EvidencePacketError, match="material/subject identity substitution"):
        validate_evidence_packet(packet, expected=expected)


def test_source_role_and_path_substitution_is_rejected_even_when_rehashed() -> None:
    packet = _packet()
    expected = _expectations(packet)
    packet["source_bindings"][0]["role"] = "metadata_source"  # type: ignore[index]
    packet["source_bindings"][0]["locator"] = "artifacts/other.csv"  # type: ignore[index]
    packet = _rehash(packet)

    with pytest.raises(EvidencePacketError, match="source role/path/artifact substitution"):
        validate_evidence_packet(packet, expected=expected)


def test_unit_drift_is_rejected_even_when_rehashed() -> None:
    packet = _packet()
    expected = _expectations(packet)
    packet["results"][0]["unit"] = "kPa"  # type: ignore[index]
    packet = _rehash(packet)

    with pytest.raises(EvidencePacketError, match="result unit drift"):
        validate_evidence_packet(packet, expected=expected)


def test_unit_state_must_distinguish_unknown_from_not_applicable() -> None:
    packet = _packet()
    packet["results"][0]["unit_state"] = "unknown"  # type: ignore[index]
    packet = _rehash(packet)

    with pytest.raises(EvidencePacketError, match="unit must be null"):
        validate_evidence_packet(packet)


def test_calibration_status_promotion_is_rejected_by_authenticated_expectation() -> None:
    packet = _packet()
    expected = _expectations(packet)
    packet["calibration"] = {
        "status": "calibrated",
        "records": [
            {
                "calibration_id": "forged-calibration",
                "scope": "forged calibration scope",
                "source_binding_ids": ["source-1"],
                "uncertainty_ids": [],
                "notes": None,
            }
        ],
    }
    packet = _rehash(packet)

    with pytest.raises(EvidencePacketError, match="calibration status promotion/drift"):
        validate_evidence_packet(packet, expected=expected)


def test_unknown_uncertainty_cannot_be_promoted_to_numeric_by_rehashing() -> None:
    packet = _packet()
    expected = _expectations(packet)
    record = packet["uncertainty"][0]  # type: ignore[index]
    record.update(
        {
            "status": "quantified",
            "value": 5.0,
            "unit": "MPa",
            "distribution": "normal",
            "confidence_level": 0.95,
        }
    )
    packet = _rehash(packet)

    with pytest.raises(EvidencePacketError, match="uncertainty status promotion/drift"):
        validate_evidence_packet(packet, expected=expected)


def test_literature_claim_cannot_gain_row_level_measurement_authority() -> None:
    packet = _packet()
    packet["evidence_kind"] = "literature_claim"
    packet["authority"]["empirical_evidence_created"] = False  # type: ignore[index]
    packet = _rehash(packet)

    with pytest.raises(EvidencePacketError, match="literature claim may not become row-level"):
        validate_evidence_packet(packet)


def test_simulation_result_cannot_become_empirical_measurement() -> None:
    packet = _packet()
    packet["evidence_kind"] = "simulation_result"
    packet["authority"]["row_level_measurement_authority"] = False  # type: ignore[index]
    packet = _rehash(packet)

    with pytest.raises(EvidencePacketError, match="simulation evidence may not become empirical"):
        validate_evidence_packet(packet)


def test_duplicate_source_family_independence_claim_is_rejected() -> None:
    packet = _packet()
    packet["independence"].update(  # type: ignore[attr-defined]
        {
            "overlap_status": "no_known_overlap",
            "overlap_with": [],
            "independence_claim_status": "independent_within_stated_dimensions",
        }
    )
    packet = _rehash(packet)
    expected = _expectations(packet)
    expected["existing_source_family_ids"] = ["zenodo-20503603"]

    with pytest.raises(EvidencePacketError, match="duplicated source-family independence"):
        validate_evidence_packet(packet, expected=expected)


def test_independence_claim_cannot_hide_unknown_overlap() -> None:
    packet = _packet()
    packet["independence"]["independence_claim_status"] = (  # type: ignore[index]
        "independent_within_stated_dimensions"
    )
    packet = _rehash(packet)

    with pytest.raises(EvidencePacketError, match="requires no_known_overlap"):
        validate_evidence_packet(packet)


def test_comparability_cannot_be_promoted_inside_evidence_packet() -> None:
    packet = _packet()
    packet["comparability"]["status"] = "comparable"  # type: ignore[index]
    packet["comparability"]["comparison_performed"] = True  # type: ignore[index]
    packet["comparability"]["comparable_claimed"] = True  # type: ignore[index]
    packet = _rehash(packet)

    with pytest.raises(EvidencePacketError, match="comparability must remain not_assessed"):
        validate_evidence_packet(packet)


def test_derivation_lineage_cannot_promote_scientific_status() -> None:
    packet = _packet()
    result = packet["results"][0]  # type: ignore[index]
    result["value_state"] = "derived"
    result["derivation_ids"] = ["derivation-1"]
    packet["derivation_lineage"] = [
        {
            "derivation_id": "derivation-1",
            "operation": "unit-preserving deterministic transform",
            "input_binding_ids": ["source-1"],
            "input_result_ids": [],
            "output_result_ids": ["result-uts"],
            "software": {"name": "test-transform", "version": "1", "sha256": None},
            "parameters": {},
            "scientific_status_promoted": True,
        }
    ]
    packet = _rehash(packet)

    with pytest.raises(EvidencePacketError, match="derivation lineage may not promote"):
        validate_evidence_packet(packet)


def test_derived_result_requires_explicit_derivation_lineage() -> None:
    packet = _packet()
    packet["results"][0]["value_state"] = "derived"  # type: ignore[index]
    packet = _rehash(packet)

    with pytest.raises(EvidencePacketError, match="derived value requires derivation lineage"):
        validate_evidence_packet(packet)


def test_planning_metadata_cannot_gain_empirical_or_downstream_authority() -> None:
    packet = _packet()
    packet["evidence_kind"] = "planning_metadata"
    packet["authority"]["planning_metadata_only"] = True  # type: ignore[index]
    packet = _rehash(packet)

    with pytest.raises(EvidencePacketError, match="planning metadata may not gain"):
        validate_evidence_packet(packet)


def test_artifact_byte_set_must_exactly_match_bindings() -> None:
    packet = _packet()
    with pytest.raises(EvidencePacketError, match="artifact byte set must exactly match"):
        validate_evidence_packet(
            packet,
            artifacts={"source-1": SOURCE_BYTES, "extra": b"not-bound"},
        )


def test_not_applicable_context_cannot_carry_hidden_attributes() -> None:
    packet = _packet()
    packet["contexts"]["method"]["status"] = "not_applicable"  # type: ignore[index]
    packet = _rehash(packet)

    with pytest.raises(EvidencePacketError, match="not_applicable must not carry attributes"):
        validate_evidence_packet(packet)
