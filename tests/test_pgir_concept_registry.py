import json
from pathlib import Path

from src.platform_core.pgir_governance import (
    VALID_OPERATOR_ROLES,
    build_concept_registry,
    representation_maturity_levels,
)


def test_pgir_concept_registry_is_deterministic_and_unique():
    first = [record.to_dict() for record in build_concept_registry()]
    second = [record.to_dict() for record in build_concept_registry()]

    assert first == second
    assert len({item["concept_id"] for item in first}) == len(first)
    assert {item["concept_id"] for item in first} >= {
        "physical_entity",
        "observation",
        "state",
        "field",
        "relation",
        "operator",
        "context",
    }


def test_observation_state_and_field_boundaries_are_explicit():
    concepts = {record.concept_id: record.to_dict() for record in build_concept_registry()}

    assert concepts["observation"]["concept_id"] != concepts["state"]["concept_id"]
    assert "not automatically a complete state" in concepts["observation"]["definition"]
    assert any("all table rows" in item for item in concepts["state"]["prohibited_interpretations"])
    assert {"axes", "coordinate_system", "basis_or_frame", "unit"} <= set(concepts["field"]["required_metadata"])
    assert "Propagator" in concepts["field"]["allowed_operator_roles"]


def test_maturity_levels_do_not_auto_promote_scientific_claims():
    levels = representation_maturity_levels()

    assert [item["level"] for item in levels] == [f"L{index}" for index in range(9)]
    assert levels[0]["maturity_id"] == "raw_observed"
    assert levels[-1]["maturity_id"] == "production_validated"
    assert all(item["promotion_policy"] == "explicit_evidence_required_no_automatic_file_format_promotion" for item in levels)


def test_tracked_concept_registry_has_no_row_level_payload_or_credentials():
    text = Path("data/platform/pgir_concept_registry_v1.json").read_text(encoding="utf-8")
    payload = json.loads(text)

    assert payload["schema_version"] == "2.3.1"
    assert payload["status"] == "accepted_for_v2_3"
    assert {item["concept_id"] for item in payload["concepts"]} == {record.concept_id for record in build_concept_registry()}
    for forbidden in ["MP_API_KEY", "KAGGLE_KEY", "fractional_coordinates", '"sites": [', "C:/", "C:\\", "/Users/"]:
        assert forbidden not in text
    assert {"Evaluator", "Transformer", "Propagator"} <= set(VALID_OPERATOR_ROLES)
