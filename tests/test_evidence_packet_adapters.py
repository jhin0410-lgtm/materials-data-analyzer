from __future__ import annotations

import copy
import shutil
from pathlib import Path
from typing import Any

import pytest

import materials_data_analyzer.research_loop.evidence_packet_adapters as packet_adapters
from src.loaders.characterization_evidence_ladder import LEVELS, evaluate_evidence_ladder
from materials_data_analyzer.research_loop.characterization_evidence_bridge import (
    CharacterizationEvidenceBridgeError,
)
from materials_data_analyzer.research_loop.evidence_expectation_trust import (
    validate_authenticated_evidence_packet,
)
from materials_data_analyzer.research_loop.evidence_packet import (
    EvidencePacketError,
    canonical_json_bytes,
    canonical_sha256,
    validate_evidence_packet,
)
from materials_data_analyzer.research_loop.evidence_packet_adapters import (
    CHARACTERIZATION_ADAPTER_ID,
    NIST_AMBENCH_ADAPTER_ID,
    EvidencePacketAdapterError,
    build_characterization_planning_evidence_packet,
    build_heat_conduction_reference_evidence_packet,
    build_nist_ambench_trace_evidence_packets,
    build_nist_ambench_trace_validation_material,
)


ROOT = Path(__file__).resolve().parents[1]
NIST_PATHS = (
    "data/case_studies/nist_ambench_2018_02/source_process_conditions.csv",
    "data/case_studies/nist_ambench_2018_02/source_melt_pool_measurements.csv",
    "data/case_studies/nist_ambench_2018_02/README.md",
    "configs/research/nist_ambench_2018_02_planning_readiness.v1.json",
)


def _rehash_packet(packet: dict[str, Any]) -> dict[str, Any]:
    value = copy.deepcopy(packet)
    value.pop("packet_sha256", None)
    value["packet_sha256"] = canonical_sha256(value)
    return value


def _copy_nist_sources(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    for relative in NIST_PATHS:
        source = ROOT / relative
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    return root


def _characterization_assessment() -> dict[str, Any]:
    levels: dict[str, dict[str, Any]] = {}
    for index, level in enumerate(LEVELS):
        supported = index <= 4
        levels[level] = {
            "assessment": "Supported" if supported else "Inconclusive",
            "evidence": [f"verified-{level}"] if supported else [],
            "limitations": [] if supported else [f"blocked-at-{level}"],
        }
    declaration = {
        "schema_version": "1.0",
        "declaration_id": "real-system-characterization-handoff-fixture",
        "subject": {
            "modality": "tem",
            "source_material_domain": "public_reference_material",
            "target_material_domain": "IN625",
            "claim_scope": "method_and_material_domain_validation",
        },
        "source_bindings": [
            {"role": "source_manifest", "sha256": "1" * 64},
            {"role": "analysis_manifest", "sha256": "2" * 64},
            {"role": "comparability_matrix", "sha256": "3" * 64},
        ],
        "levels": levels,
        "limitations": [
            "Producer/consumer contract fixture; does not create new empirical measurement truth."
        ],
    }
    return evaluate_evidence_ladder(declaration)


def test_real_nist_sources_produce_ten_distinct_empirical_trace_packets_without_direct_row_authority() -> None:
    packets = build_nist_ambench_trace_evidence_packets(ROOT)

    assert len(packets) == 10
    assert len({packet["packet_sha256"] for packet in packets}) == 10
    assert [packet["evidence_id"] for packet in packets] == [
        f"nist-ambench-2018-02:amb2018_02_ammt_trace_{index:02d}"
        for index in range(1, 11)
    ]

    first = packets[0]
    assert first["provider"]["adapter_id"] == NIST_AMBENCH_ADAPTER_ID
    assert first["subject"]["identities"][0] == {
        "namespace": "material",
        "value": "IN625",
        "role": "material",
    }
    process = {
        item["name"]: item["value"] for item in first["contexts"]["process"]["attributes"]
    }
    assert process["actual_laser_power_w"] == 179.2
    assert process["scan_speed_mm_s"] == 1200.0
    results = {item["result_id"]: item for item in first["results"]}
    assert results["melt-pool-width-mean"]["value"] == 104.4
    assert results["melt-pool-depth-mean"]["value"] == 29.0
    assert first["calibration"] == {"status": "unknown", "records": []}
    assert first["authority"] == {
        "empirical_evidence_created": True,
        "scientific_status_promoted": False,
        "downstream_use_authorized": False,
        "planning_metadata_only": False,
        "row_level_measurement_authority": False,
        "authority_source": "preexisting_authenticated_scientific_record",
    }
    assert "predictive validation" in first["scientific_validity"]["excluded_scope"]


def test_nist_validation_material_exercises_authenticated_validator_without_self_issuing_trust_root() -> None:
    material = build_nist_ambench_trace_validation_material(ROOT)
    assert len(material) == 10

    for item in material:
        assert "trusted_expectation_sha256" not in item
        expected = item["expected"]
        packet = item["packet"]
        # This local digest exercises the authenticated-validator path only. It is
        # deliberately not returned by the production adapter and is not a production
        # Governance trust root.
        replayed = validate_authenticated_evidence_packet(
            packet,
            artifacts=item["artifacts"],
            expected=expected,
            trusted_expectation_sha256=canonical_sha256(expected),
        )
        assert replayed == packet
        assert expected["packet_sha256"] == packet["packet_sha256"]
        assert expected["calibration_status"] == "unknown"


def test_nist_authority_bearing_packet_cannot_self_validate_without_external_expectation() -> None:
    item = build_nist_ambench_trace_validation_material(ROOT)[0]

    with pytest.raises(
        EvidencePacketError,
        match="requires authenticated external expectations",
    ):
        validate_evidence_packet(
            item["packet"],
            artifacts=item["artifacts"],
        )


def test_nist_source_byte_substitution_fails_before_packet_creation(tmp_path: Path) -> None:
    root = _copy_nist_sources(tmp_path)
    path = root / NIST_PATHS[1]
    path.write_text(
        path.read_text(encoding="utf-8").replace(",104.4,", ",999.9,", 1),
        encoding="utf-8",
    )

    with pytest.raises(
        EvidencePacketAdapterError,
        match="source bytes drifted from reviewed Git-blob authority",
    ):
        build_nist_ambench_trace_evidence_packets(root)


def test_nist_raw_sha256_pin_survives_git_blob_pin_substitution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _copy_nist_sources(tmp_path)
    path = root / NIST_PATHS[1]
    path.write_text(
        path.read_text(encoding="utf-8").replace(",104.4,", ",999.9,", 1),
        encoding="utf-8",
    )
    tampered = path.read_bytes()
    forged_blob_roots = dict(packet_adapters._NIST_BLOB_SHA1)
    forged_blob_roots["measurement"] = packet_adapters._git_blob_sha1(tampered)
    monkeypatch.setattr(packet_adapters, "_NIST_BLOB_SHA1", forged_blob_roots)

    with pytest.raises(
        EvidencePacketAdapterError,
        match="reviewed SHA-256 authority",
    ):
        build_nist_ambench_trace_evidence_packets(root)


def test_rehashed_nist_measurement_substitution_fails_external_expectation() -> None:
    item = build_nist_ambench_trace_validation_material(ROOT)[0]
    packet = copy.deepcopy(item["packet"])
    packet["results"][0]["value"] = 999.9
    packet = _rehash_packet(packet)

    with pytest.raises(
        EvidencePacketError,
        match="authenticated packet SHA-256 expectation drifted",
    ):
        validate_authenticated_evidence_packet(
            packet,
            artifacts=item["artifacts"],
            expected=item["expected"],
            trusted_expectation_sha256=canonical_sha256(item["expected"]),
        )


def test_characterization_ladder_becomes_planning_metadata_not_empirical_evidence() -> None:
    assessment = _characterization_assessment()
    packet = build_characterization_planning_evidence_packet(assessment)

    assert packet["provider"]["adapter_id"] == CHARACTERIZATION_ADAPTER_ID
    assert packet["evidence_kind"] == "planning_metadata"
    assert packet["authority"] == {
        "empirical_evidence_created": False,
        "scientific_status_promoted": False,
        "downstream_use_authorized": False,
        "planning_metadata_only": True,
        "row_level_measurement_authority": False,
        "authority_source": "none",
    }
    assert packet["results"][0]["value"] == 4
    assert (
        "highest_supported_level=L4_method_algorithm_validation"
        in packet["results"][0]["qualifiers"]
    )
    assert (
        "first_blocking_level=L5_material_domain_validation"
        in packet["results"][0]["qualifiers"]
    )

    assessment_bytes = canonical_json_bytes(assessment)
    replayed = validate_evidence_packet(
        packet,
        artifacts={"characterization-assessment": assessment_bytes},
    )
    assert replayed == packet


def test_characterization_assessment_rehash_cannot_promote_ladder_state() -> None:
    assessment = _characterization_assessment()
    forged = copy.deepcopy(assessment)
    forged["handoff"]["scientific_status_promoted"] = True
    forged_without_hash = copy.deepcopy(forged)
    forged_without_hash.pop("assessment_sha256", None)
    forged["assessment_sha256"] = canonical_sha256(forged_without_hash)

    with pytest.raises(
        CharacterizationEvidenceBridgeError,
        match="must not promote scientific status",
    ):
        build_characterization_planning_evidence_packet(forged)


def test_planning_metadata_packet_cannot_be_rehashed_into_empirical_authority() -> None:
    packet = build_characterization_planning_evidence_packet(_characterization_assessment())
    forged = copy.deepcopy(packet)
    forged["authority"]["empirical_evidence_created"] = True
    forged["authority"]["row_level_measurement_authority"] = True
    forged["authority"]["planning_metadata_only"] = False
    forged["authority"]["authority_source"] = "domain_verifier"
    forged = _rehash_packet(forged)

    with pytest.raises(EvidencePacketError, match="planning_metadata_only"):
        validate_evidence_packet(
            forged,
            artifacts={
                "characterization-assessment": canonical_json_bytes(
                    _characterization_assessment()
                )
            },
        )


def _heat_request() -> dict[str, Any]:
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
            "max_abs_error_tolerance_K": 0.1,
        },
    }


def test_heat_reference_fixture_is_non_empirical_and_replayable() -> None:
    request = _heat_request()
    packet = build_heat_conduction_reference_evidence_packet(request)

    assert packet["evidence_kind"] == "simulation_result"
    assert packet["authority"] == {
        "empirical_evidence_created": False,
        "scientific_status_promoted": False,
        "downstream_use_authorized": False,
        "planning_metadata_only": False,
        "row_level_measurement_authority": False,
        "authority_source": "none",
    }
    assert "LPBF melt-pool physics" in packet["scientific_validity"]["excluded_scope"]
    assert packet["comparability"]["comparison_performed"] is False

    request_bytes = canonical_json_bytes(request)
    result_binding = next(
        item for item in packet["source_bindings"] if item["binding_id"] == "heat-result"
    )
    request_binding = next(
        item for item in packet["source_bindings"] if item["binding_id"] == "heat-request"
    )
    assert request_binding["sha256"] == canonical_sha256(request)

    # Recompute the deterministic solver result through the adapter and verify the packet
    # against the exact canonical request/result artifacts it declares.
    packet_again = build_heat_conduction_reference_evidence_packet(request)
    assert packet_again == packet
    from materials_data_analyzer.research_loop.heat_conduction_solver import (
        run_reference_heat_conduction_request,
    )

    result_bytes = canonical_json_bytes(run_reference_heat_conduction_request(request))
    assert result_binding["sha256"] == canonical_sha256(
        run_reference_heat_conduction_request(request)
    )
    replayed = validate_evidence_packet(
        packet,
        artifacts={
            "heat-request": request_bytes,
            "heat-result": result_bytes,
        },
    )
    assert replayed == packet


def test_heat_reference_fixture_cannot_be_rehashed_into_empirical_evidence() -> None:
    request = _heat_request()
    packet = build_heat_conduction_reference_evidence_packet(request)
    forged = copy.deepcopy(packet)
    forged["authority"]["empirical_evidence_created"] = True
    forged["authority"]["row_level_measurement_authority"] = True
    forged["authority"]["authority_source"] = "domain_verifier"
    forged = _rehash_packet(forged)

    with pytest.raises(EvidencePacketError, match="simulation evidence may not become empirical"):
        validate_evidence_packet(forged)
