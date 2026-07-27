from __future__ import annotations

import importlib.util
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_ROOT / "scripts" / "audit_cross_repository_release_readiness.py"


def _module():
    spec = importlib.util.spec_from_file_location("release_readiness", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_current_repository_is_ready_for_external_v2_7_release_action() -> None:
    result = _module().audit_data_repository(PROJECT_ROOT)

    assert result["status"] == "ready_for_current_head_release_action"
    assert result["public_release_version"] == "2.7.0"
    assert result["runtime_platform_version"] == "2.7.0"
    assert result["citation_version"] == "2.7.0"
    assert result["citation_date_released"] == "2026-07-28"
    assert result["highest_unreleased_named_version"] is None
    assert result["main_contains_post_release_work"] is False
    assert result["current_main_tagging_allowed"] is True
    assert result["stable_release_metadata_valid"] is True
    assert result["blockers"] == []


def test_no_unreleased_marker_is_not_treated_as_feature_work() -> None:
    module = _module()
    changelog = (
        "# Changelog\n\n## Unreleased\n\n"
        "No unreleased changes at the v2.7.0 promotion boundary.\n\n"
        "## v2.7.0\n"
    )

    assert module.unreleased_contains_work(changelog) is False
    assert module.highest_version(module.unreleased_text(changelog)) is None


def test_historical_v2_6_tests_use_current_v2_7_runtime_without_artifact_rewrite() -> None:
    paths = (
        "tests/test_battery_comparability_evidence.py",
        "tests/test_battery_external_cohort_admission.py",
        "tests/test_battery_forecast_failure_diagnostics.py",
    )

    for relative in paths:
        text = (PROJECT_ROOT / relative).read_text(encoding="utf-8")
        assert 'assert PLATFORM_VERSION == "2.7.0"' in text
        assert 'assert PLATFORM_VERSION == "2.4.0"' not in text
        assert "Tracked v2.6 artifacts retain historical checksums" in text
