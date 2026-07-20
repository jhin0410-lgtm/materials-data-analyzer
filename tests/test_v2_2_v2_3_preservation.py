import json
from pathlib import Path

from src.platform_core.materials_pgir_reuse import (
    _canonical_csv_sha,
    validate_preserved_v2_2_v2_3_results,
)


def test_v2_2_and_v2_3_released_artifacts_remain_checksum_preserved():
    result = validate_preserved_v2_2_v2_3_results()

    mismatches = [item for item in result["checks"] if not item["preserved"]]
    assert result["status"] == "preserved", mismatches
    assert result["check_count"] == 8
    assert all(item["preserved"] for item in result["checks"])


def test_csv_preservation_checksum_is_line_ending_independent(tmp_path):
    lf = tmp_path / "lf.csv"
    crlf = tmp_path / "crlf.csv"
    lf.write_bytes(b"name,value\na,1\nb,2\n")
    crlf.write_bytes(b"name,value\r\na,1\r\nb,2\r\n")

    assert _canonical_csv_sha(lf) == _canonical_csv_sha(crlf)


def test_released_scientific_decisions_remain_unchanged():
    composition = json.loads(
        Path("data/processed/materials_physics_v2_2_predictive_value_decision.json").read_text(encoding="utf-8")
    )
    structure = json.loads(
        Path("data/processed/materials_v2_2_5_predictive_value_decision.json").read_text(encoding="utf-8")
    )
    battery = json.loads(
        Path("data/processed/battery_v2_3_5_external_data_requirement_decision.json").read_text(encoding="utf-8")
    )

    assert composition["predictive_value_status"] == "performance_degraded"
    assert composition["representative_model_selected"] is False
    assert structure["structure_predictive_value_status"] == "structure_predictive_value_limited"
    assert structure["representative_model"] == "none"
    assert battery["decision_status"] == "selective_external_source_documentation_required"
    assert battery["automatic_download_performed"] is False
