from src.platform_core.v2_2_trust_closeout import build_uncertainty_boundary


def test_v2_2_uncertainty_boundaries_do_not_confuse_prediction_and_dft_uncertainty():
    boundary = build_uncertainty_boundary()
    records = {record["uncertainty_id"]: record for record in boundary["uncertainty_records"]}

    assert records["source_uncertainty"]["status"] == "unavailable"
    assert "zero_uncertainty" in records["source_uncertainty"]["prohibited_interpretations"]
    assert records["predictive_interval"]["status"] == "prediction_interval_evaluated"
    assert records["predictive_interval"]["unit"] == "eV/atom"
    assert "DFT_uncertainty" in records["predictive_interval"]["prohibited_interpretations"]
    assert records["model_form_uncertainty"]["status"] == "limitation_recorded"
    assert boundary["prediction_interval_diagnostics"]["target_unit"] == "eV/atom"


def test_v2_2_unit_audit_preserves_target_units():
    boundary = build_uncertainty_boundary()
    units = {row["quantity"]: row["unit"] for row in boundary["unit_audit"]}

    assert units["energy_above_hull"] == "eV/atom"
    assert units["prediction_interval"] == "eV/atom"
    assert units["volume_per_atom"] == "angstrom^3/atom"
