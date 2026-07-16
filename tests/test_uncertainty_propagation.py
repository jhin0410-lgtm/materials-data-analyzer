import math

import pytest

from src.platform_core.uncertainty_propagation import propagate_bragg_uncertainty, scherrer_uncertainty_eligibility


def _bragg_config():
    return {
        "operator_id": "xrd_bragg_uncertainty_v2_2",
        "wavelength": {"value": 1.5406, "unit": "angstrom", "uncertainty": {"kind": "absolute", "value": 0.0001, "unit": "angstrom"}},
        "two_theta": {"value": 44.7, "unit": "degree", "uncertainty": {"kind": "absolute", "value": 0.01, "unit": "degree"}},
        "diffraction_order": 1,
        "output_unit": "angstrom",
    }


def test_bragg_uncertainty_matches_hand_calculation():
    result = propagate_bragg_uncertainty(_bragg_config())

    theta = math.radians(44.7) / 2
    d_spacing = 1.5406 / (2 * math.sin(theta))
    d_lambda = 1 / (2 * math.sin(theta))
    d_twotheta = -1.5406 * math.cos(theta) / (4 * math.sin(theta) ** 2)
    expected_sigma = math.sqrt((d_lambda * 0.0001) ** 2 + (d_twotheta * math.radians(0.01)) ** 2)
    assert result["status"] == "propagated"
    assert result["value"] == pytest.approx(d_spacing)
    assert result["output_uncertainty"]["value"] == pytest.approx(expected_sigma)


def test_bragg_missing_uncertainty_and_invalid_domain_are_unavailable():
    missing = _bragg_config()
    del missing["two_theta"]["uncertainty"]
    assert propagate_bragg_uncertainty(missing)["status"] == "unavailable"

    invalid = _bragg_config()
    invalid["two_theta"]["value"] = 0
    result = propagate_bragg_uncertainty(invalid)
    assert result["status"] == "unavailable"
    assert "two_theta_outside_supported_domain" in result["warnings"]


def test_scherrer_uncertainty_reports_partial_boundary_not_particle_claim():
    result = scherrer_uncertainty_eligibility(
        {
            "operator_id": "xrd_scherrer_uncertainty_v2_2",
            "wavelength": {"value": 1.5406, "unit": "angstrom", "uncertainty": {"kind": "absolute", "value": 0.0001, "unit": "angstrom"}},
            "fwhm": {"value": 0.18, "unit": "degree", "uncertainty": {"kind": "absolute", "value": 0.01, "unit": "degree"}},
            "two_theta": {"value": 44.7, "unit": "degree", "uncertainty": {"kind": "absolute", "value": 0.01, "unit": "degree"}},
            "shape_factor": {"value": 0.9, "unit": "fraction", "uncertainty": {"kind": "absolute", "value": 0.05, "unit": "fraction"}},
        }
    )

    assert result["status"] == "partial"
    assert "particle_size" in result["prohibited_claims"]
