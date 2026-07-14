from src.platform_core.scientific_applicability import validate_scientific_input
from src.platform_core.scientific_constraint_registry import build_default_scientific_constraint_registry
from src.platform_core.scientific_evaluators import build_default_evaluator_registry, evaluate_constraint


def test_materials_composition_sum_and_negative_bounds():
    registry = build_default_scientific_constraint_registry()
    constraint = registry.get("materials.composition_fraction.sum_to_one")
    findings = evaluate_constraint(
        constraint,
        {"composition_fraction": {"values": [0.4, 0.4], "unit": "fraction"}},
        units={"composition_fraction": "fraction"},
    )

    assert findings[0].status == "inconsistent"
    assert findings[0].remediation_code == "normalize_or_verify_composition_fractions"


def test_battery_cycle_monotonic_and_temperature_conversion():
    config = {
        "schema_version": "2.1",
        "constraint_ids": [
            "battery.cycle_index.non_decreasing",
            "battery.temperature.arrhenius_domain",
        ],
        "variables": {
            "cycle_index": {"values": [1, 3, 2]},
            "temperature": {"value": 25, "unit": "degC"},
        },
        "credential_policy": {"store_credentials": False},
    }

    result = validate_scientific_input(config)
    statuses = {finding.constraint_id: finding.status for finding in result.findings}
    assert statuses["battery.cycle_index.non_decreasing"] == "inconsistent"
    assert statuses["battery.temperature.arrhenius_domain"] == "conditionally_consistent"


def test_xrd_bragg_and_scherrer_claim_boundaries():
    config = {
        "schema_version": "2.1",
        "constraint_ids": ["xrd.bragg.geometry", "xrd.scherrer.preconditions"],
        "variables": {
            "two_theta": {"value": 44.7, "unit": "degree"},
            "wavelength": {"value": 1.5406, "unit": "angstrom"},
            "fwhm": {"value": 0.006, "unit": "rad"},
        },
        "metadata": {"instrumental_broadening_corrected": False},
        "credential_policy": {"store_credentials": False},
    }

    result = validate_scientific_input(config)
    by_id = {finding.constraint_id: finding for finding in result.findings}
    assert by_id["xrd.bragg.geometry"].status == "conditionally_consistent"
    assert "phase identification is not inferred" in by_id["xrd.bragg.geometry"].message
    assert by_id["xrd.scherrer.preconditions"].category == "physics_claim_boundary"
    assert "do not claim particle size" in by_id["xrd.scherrer.preconditions"].message


def test_evaluator_registry_is_code_registered_only():
    registry = build_default_evaluator_registry()

    assert "check_bragg_geometry" in [item["evaluator_id"] for item in registry.snapshot()]
    assert all(item["evaluator_id"].startswith("check_") for item in registry.snapshot())
