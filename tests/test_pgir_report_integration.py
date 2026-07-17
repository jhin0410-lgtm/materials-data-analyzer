from src.platform_core.report_generator import build_platform_report, render_report_markdown


def test_platform_report_can_include_pgir_governance_without_recomputation():
    report = build_platform_report(
        {
            "schema_version": "2.0",
            "report_id": "test_pgir_report",
            "formats": ["json", "markdown"],
            "selected_case_studies": ["materials_project"],
            "output_dir": "outputs/platform_reports/test_pgir_report",
            "credential_policy": {"store_credentials": False},
            "include_pgir_governance": True,
        }
    )
    markdown = render_report_markdown(report)

    assert report.scientific_recomputation_performed is False
    assert report.pgir_governance_summary["status"] == "pgir_governance_ready"
    assert report.pgir_governance_summary["execution_boundary"]["api_or_network_called"] is False
    assert "PGIR Architecture And Governance" in markdown
    assert "no physics execution, API call, model run, or raw artifact read" in markdown
