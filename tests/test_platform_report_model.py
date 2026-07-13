from src.platform_core.report_generator import build_platform_report, render_report_json, render_report_markdown


def _config():
    return {
        "schema_version": "2.0",
        "report_id": "test_report_model",
        "formats": ["json", "markdown"],
        "selected_case_studies": [
            "battery_archive",
            "materials_project",
            "smart_factory",
            "reliability",
        ],
        "output_dir": "outputs/platform_reports/test_report_model",
        "credential_policy": {"store_credentials": False},
    }


def test_platform_report_represents_all_case_studies_without_recomputation():
    report = build_platform_report(_config())

    assert report.scientific_recomputation_performed is False
    assert [case.case_study_id for case in report.case_studies] == [
        "battery_archive",
        "materials_project",
        "smart_factory",
        "reliability",
    ]
    assert {case.case_study_id: case.representative_model_status for case in report.case_studies} == {
        "battery_archive": "unavailable",
        "materials_project": "none_selected",
        "smart_factory": "none",
        "reliability": "none_selected",
    }


def test_platform_report_renders_deterministically():
    report = build_platform_report(_config())

    assert render_report_json(report) == render_report_json(report)
    assert render_report_markdown(report) == render_report_markdown(report)
    assert "Scientific recomputation performed: `false`" in render_report_markdown(report)


def test_platform_report_policy_sections_are_present():
    report = build_platform_report(_config())

    assert report.registry_snapshot["case_studies"]
    assert report.maturity_matrix
    assert report.execution_matrix
    assert report.artifact_policy_summary["report_output_policy"].startswith("platform reports")
    assert all(policy["production_claim_allowed"] is False for policy in report.trust_policy_summary)
