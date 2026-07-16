from pathlib import Path


TRACKED_CLOSEOUT = [
    Path("data/platform/v2_2_capability_matrix.json"),
    Path("data/platform/materials_prediction_context_registry_v2.json"),
    Path("data/processed/materials_v2_2_capability_matrix.json"),
    Path("data/processed/materials_v2_2_evidence_summary.json"),
    Path("data/processed/materials_v2_2_claim_matrix.json"),
    Path("data/processed/materials_v2_2_uncertainty_boundary.json"),
    Path("data/processed/materials_v2_2_prediction_contexts.json"),
    Path("data/processed/materials_v2_2_closeout_decision.json"),
    Path("data/processed/materials_v2_2_closeout_summary.md"),
]


def test_v2_2_closeout_outputs_have_no_row_level_payloads_or_secrets():
    forbidden = [
        "MP_API_KEY",
        "KAGGLE_KEY",
        "fractional_coordinates",
        '"sites": [',
        "mp-",
        "C:/",
        "C:\\",
        "/Users/",
        "pickle",
    ]

    for path in TRACKED_CLOSEOUT:
        text = path.read_text(encoding="utf-8")
        for token in forbidden:
            assert token not in text, f"{token!r} leaked into {path}"


def test_v2_2_closeout_module_does_not_execute_dynamic_code_or_models():
    source = Path("src/platform_core/v2_2_trust_closeout.py").read_text(encoding="utf-8")

    for token in ["eval(", "exec(", "importlib", "subprocess", "mp_api", "MPRester", "fit(", "predict("]:
        assert token not in source
