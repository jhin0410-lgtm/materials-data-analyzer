from pathlib import Path


PGIR_FILES = [
    Path("src/platform_core/pgir_governance.py"),
    Path("data/platform/pgir_concept_registry_v1.json"),
    Path("data/platform/pgir_current_mapping_matrix_v1.json"),
    Path("data/platform/pgir_representation_governance_v1.json"),
    Path("data/platform/pgir_schema_ownership_registry_v1.json"),
    Path("data/platform/pgir_capability_stage_registry_v1.json"),
]


def test_pgir_governance_contains_no_dynamic_execution_network_or_pickle():
    combined = "\n".join(path.read_text(encoding="utf-8") for path in PGIR_FILES)

    for token in ["eval(", "exec(", "importlib", "subprocess", "requests", "urllib", "socket", "pickle", "cloudpickle"]:
        assert token not in combined
    for token in ["MP_API_KEY", "KAGGLE_KEY", "MPRester", "mp_api", "fit(", "predict("]:
        assert token not in combined


def test_pgir_tracked_artifacts_have_no_paths_credentials_or_row_level_payloads():
    for path in PGIR_FILES[1:]:
        text = path.read_text(encoding="utf-8")
        for token in ["C:/", "C:\\", "/Users/", "data/raw", "fractional_coordinates", '"sites": [', "serial_number"]:
            assert token not in text
