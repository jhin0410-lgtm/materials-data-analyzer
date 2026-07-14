from src.platform_core.artifact_resolver import ArtifactResolver
from src.platform_core.artifacts import build_default_artifact_registry
from src.platform_core.report_extractors import extract_case_study_results


def _resolver():
    return ArtifactResolver(".", build_default_artifact_registry())


def test_materials_project_trust_result_extracted_from_compact_artifacts():
    extracted = extract_case_study_results("materials_project", _resolver())

    assert extracted.representative_model_status == "none_selected"
    assert extracted.key_compact_results["model_eligibility"] == "no_model_eligible_for_interpretation"
    assert all(not artifact.artifact.local_only for artifact in extracted.artifacts)


def test_smart_factory_trust_result_extracted_from_compact_artifacts():
    extracted = extract_case_study_results("smart_factory", _resolver())

    assert extracted.key_compact_results["rows"] == "1567"
    assert extracted.representative_model_status == "none"
    assert extracted.trust_result == "diagnostic_only"


def test_reliability_top_risk_values_are_read_from_operational_boundary():
    extracted = extract_case_study_results("reliability", _resolver())

    assert extracted.key_compact_results["rows"] == "5091501"
    assert extracted.key_compact_results["combined_top_1_precision"] == "0.0702576112412178"
    assert extracted.key_compact_results["combined_top_1_lift"] == "62.92330620199473"
    assert extracted.key_compact_results["representative_model"] == "none_selected"


def test_battery_archive_legacy_trust_status_preserved():
    extracted = extract_case_study_results("battery_archive", _resolver())

    assert extracted.trust_result == "unavailable_or_legacy"
    assert extracted.representative_model_status == "unavailable"
    assert extracted.key_compact_results["series_count"] == 196
