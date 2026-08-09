from __future__ import annotations

import json
from pathlib import Path

from materials_data_analyzer.characterization_use_contract import USE_LEVELS


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = (
    ROOT
    / "configs"
    / "research"
    / "tm_fe_si_characterization_consumer_readiness.v1.json"
)


def _load() -> dict:
    return json.loads(CONTRACT.read_text(encoding="utf-8"))


def test_contract_uses_existing_mda_downstream_use_vocabulary() -> None:
    data = _load()
    intent = data["consumer_intent"]
    assert intent["requested_use"] == "descriptive"
    assert intent["requested_use"] in USE_LEVELS
    assert intent["display_authorized"] is True
    assert intent["descriptive_authorized"] is True
    assert intent["association_authorized"] is False
    assert intent["predictive_authorized"] is False
    assert intent["causal_authorized"] is False
    assert intent["engineering_authorized"] is False


def test_producer_state_does_not_invent_a_handoff_or_exact_specimen_identity() -> None:
    data = _load()
    producer = data["producer"]
    assert producer["repository"] == "jhin0410-lgtm/materials-characterization-analyzer"
    assert producer["source_audit_merge_commit"] == "439aac38bec9cc6ce549550fc2a4b049fd1fb61c"
    assert producer["source_audit_supported"] is True
    assert producer["characterization_handoff_contract_ready"] is False
    assert producer["characterization_bundle_ready"] is False
    assert producer["required_future_identity_level"] == (
        "nominal_composition_and_preparation_batch_family"
    )
    assert producer["exact_cross_modality_specimen_identity_supported"] is False


def test_xrd_and_magnetic_semantics_remain_descriptive_and_fail_closed() -> None:
    data = _load()
    xrd = data["characterization_semantics"]
    magnetic = data["magnetic_consumer_data"]
    assert xrd["xrd_peak_position_descriptive_use"] == "Diagnostic"
    assert xrd["absolute_xrd_intensity_cross_composition_use"] == "Unsupported"
    assert xrd["phase_assignment_from_uploaded_xrd_only"] == "Unsupported"
    assert xrd["xrd_integer_plot_offset_preserved_as_limitation"] is True
    assert xrd["raw_workbook_transfer_to_mda_authorized"] is False
    assert magnetic["dc_magnetization_descriptive_use"] == "Diagnostic"
    assert magnetic["m_h_descriptive_use"] == "Diagnostic"
    assert magnetic["consumer_table_ready"] is False
    assert magnetic["join_authorized_before_stable_producer_identity_exists"] is False
    assert magnetic["high_temperature_instrument_split_must_be_preserved"] is True
    assert magnetic["dmdt_derivation_provenance_resolved"] is False


def test_join_policy_never_uses_row_order_filename_position_or_unverified_specimen() -> None:
    policy = _load()["join_policy"]
    assert policy["stable_producer_identity_required"] is True
    assert policy["nominal_composition_required"] is True
    assert policy["preparation_batch_family_required"] is True
    assert policy["join_by_row_order"] is False
    assert policy["join_by_spreadsheet_row"] is False
    assert policy["join_by_inferred_filename_position"] is False
    assert policy["join_by_unverified_exact_specimen_identity"] is False


def test_readiness_correctly_stops_before_mca_bundle_exists() -> None:
    readiness = _load()["readiness"]
    assert readiness["source_audit_complete"] is True
    assert readiness["consumer_contract_frozen"] is True
    assert readiness["mca_handoff_available"] is False
    assert readiness["mda_characterization_import_ready"] is False
    assert readiness["cross_modal_descriptive_case_ready"] is False
    assert readiness["predictive_case_ready"] is False
    assert readiness["causal_case_ready"] is False
    assert readiness["engineering_decision_ready"] is False
