from src.platform_core.scientific_applicability import (
    check_scientific_applicability,
    validate_scientific_config_safety,
    validate_scientific_input,
)


def test_applicability_reports_missing_variable_and_missing_unit_without_violation():
    missing_variable = {
        "schema_version": "2.1",
        "constraint_ids": ["xrd.bragg.geometry"],
        "variables": {"two_theta": {"value": 45, "unit": "degree"}},
        "credential_policy": {"store_credentials": False},
    }
    missing_unit = {
        "schema_version": "2.1",
        "constraint_ids": ["xrd.bragg.geometry"],
        "variables": {"two_theta": {"value": 45, "unit": "degree"}, "wavelength": {"value": 1.54}},
        "credential_policy": {"store_credentials": False},
    }

    result_missing_variable = check_scientific_applicability(missing_variable)
    result_missing_unit = check_scientific_applicability(missing_unit)

    assert result_missing_variable.applicability[0].status == "unavailable_missing_variable"
    assert result_missing_unit.applicability[0].status == "unavailable_missing_unit"
    assert result_missing_unit.findings == ()


def test_applicability_unknown_semantics_and_invalid_assumption():
    config = {
        "schema_version": "2.1",
        "constraint_ids": ["manufacturing.flow.non_negative"],
        "variables": {"flow_rate": {"value": 1.0}},
        "metadata": {"semantic_availability": {"flow_rate": "unknown"}},
        "credential_policy": {"store_credentials": False},
    }
    invalid = {
        "schema_version": "2.1",
        "constraint_ids": ["battery.temperature.arrhenius_domain"],
        "variables": {"temperature": {"value": 25, "unit": "degC"}},
        "metadata": {"invalid_assumptions": ["battery.temperature.arrhenius_domain"]},
        "credential_policy": {"store_credentials": False},
    }

    assert check_scientific_applicability(config).applicability[0].status == "unavailable_unknown_semantics"
    assert check_scientific_applicability(invalid).applicability[0].status == "invalid_assumption"


def test_scientific_config_safety_blocks_paths_credentials_and_code_text():
    errors = validate_scientific_config_safety(
        {
            "schema_version": "2.1",
            "constraint_ids": ["materials.composition_fraction.sum_to_one"],
            "input_path": "data/raw/private.csv",
            "variables": {"composition_fraction": {"values": [1.0], "unit": "fraction"}},
            "credential_policy": {"store_credentials": True},
            "metadata": {"note": "eval(1+1)"},
        }
    )

    assert any("input_path is not allowed" in error for error in errors)
    assert any("store_credentials" in error for error in errors)
    assert any("executable-looking" in error for error in errors)


def test_validate_scientific_input_does_not_read_raw_data_or_train_models():
    config = {
        "schema_version": "2.1",
        "constraint_ids": ["materials.composition_fraction.sum_to_one"],
        "variables": {"composition_fraction": {"values": [0.2, 0.8], "unit": "fraction"}},
        "credential_policy": {"store_credentials": False},
    }

    result = validate_scientific_input(config)

    assert result.valid is True
    assert result.status == "scientifically_consistent"
