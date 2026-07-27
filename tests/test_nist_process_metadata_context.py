from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CASE_DIR = PROJECT_ROOT / "data" / "case_studies" / "nist_ambench_2018_02"
PROCESS_SOURCE = CASE_DIR / "source_process_conditions.csv"
CONTEXT_SOURCE = CASE_DIR / "process_metadata_context.json"


def _context() -> dict:
    return json.loads(CONTEXT_SOURCE.read_text(encoding="utf-8"))


def test_nist_process_metadata_context_matches_tracked_conditions() -> None:
    process = pd.read_csv(PROCESS_SOURCE)
    context = _context()

    assert context["schema_version"] == "1.0"
    assert context["case_study_id"] == (
        "nist_ambench_2018_02_process_characterization"
    )
    assert context["source"]["organization"] == (
        "National Institute of Standards and Technology"
    )
    assert context["source"]["provenance_status"] == (
        "manually_transcribed_from_official_nist_pages"
    )

    calibration = context["laser_power_calibration"]
    assert calibration["status"] == "corrected_after_experiment"
    assert calibration["analysis_power_field"] == "actual_laser_power_w"
    assert calibration["commanded_power_substituted_for_actual"] is False

    expected_commanded = {"A": 150.0, "B": 195.0, "C": 195.0}
    for case_id, mapping in calibration["case_mappings"].items():
        group = process.loc[process["case_id"].eq(case_id)]
        assert not group.empty
        assert group["actual_laser_power_w"].nunique() == 1
        assert group["scan_speed_mm_s"].nunique() == 1
        assert float(group["actual_laser_power_w"].iloc[0]) == mapping[
            "actual_laser_power_w"
        ]
        assert float(group["scan_speed_mm_s"].iloc[0]) == mapping[
            "scan_speed_mm_s"
        ]
        assert mapping["commanded_laser_power_w"] == expected_commanded[case_id]
        assert mapping["commanded_laser_power_w"] > mapping[
            "actual_laser_power_w"
        ]


def test_nist_spot_size_correction_is_preserved_without_reinterpretation() -> None:
    context = _context()
    spot = context["laser_spot_size"]

    assert spot == {
        "system": "AMMT",
        "legacy_reported_fwhm_um": 45.0,
        "corrected_fwhm_um": 100.0,
        "corrected_d4sigma_diameter_um": 170.0,
        "correction_status": "official_nist_post_experiment_correction",
        "used_in_linear_energy_descriptor": False,
        "measurement_values_revised_by_spot_size_correction": False,
    }
    assert spot["legacy_reported_fwhm_um"] != spot["corrected_fwhm_um"]
    assert spot["corrected_d4sigma_diameter_um"] > spot["corrected_fwhm_um"]

    usage = context["usage_contract"]
    assert usage[
        "tracked_process_table_remains_source_of_trace_level_actual_power_and_speed"
    ] is True
    assert usage["context_is_not_an_additional_process_condition"] is True
    assert usage["context_is_not_a_response_measurement"] is True
    assert usage["context_must_not_upgrade_evidence_level"] is True
    assert usage[
        "context_must_not_be_used_to_infer_absorptivity_or_volumetric_energy_density"
    ] is True


def test_nist_process_metadata_context_keeps_diagnostic_boundary() -> None:
    context = _context()
    boundary = context["scientific_boundary"]

    assert boundary["evidence_level"] == "Diagnostic"
    assert "predictive modeling or process optimization" in boundary["unsupported"]
    assert "volumetric energy-density calculation" in boundary["unsupported"]
    assert "retroactive remeasurement of source-reported melt-pool geometry" in (
        boundary["unsupported"]
    )
