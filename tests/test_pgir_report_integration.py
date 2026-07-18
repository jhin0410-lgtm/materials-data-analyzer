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


def test_platform_report_can_include_pgir_conformance_and_battery_summary():
    report = build_platform_report(
        {
            "schema_version": "2.0",
            "report_id": "test_pgir_conformance_report",
            "formats": ["json", "markdown"],
            "selected_case_studies": ["battery_archive"],
            "output_dir": "outputs/platform_reports/test_pgir_conformance_report",
            "credential_policy": {"store_credentials": False},
            "include_pgir_conformance": True,
            "include_battery_pgir": True,
            "include_battery_mechanism_audit": True,
            "include_battery_capacity_evaluator": True,
        }
    )
    markdown = render_report_markdown(report)

    assert report.scientific_recomputation_performed is False
    assert report.pgir_conformance_summary["status"] in {"available", "not_available"}
    assert report.battery_pgir_summary["status"] == "available"
    assert report.battery_pgir_summary["prediction_ready"] is False
    assert report.battery_pgir_summary["model_or_solver_executed"] is False
    assert report.battery_mechanism_audit_summary["status"] == "available"
    assert report.battery_mechanism_audit_summary["decision_status"] == "descriptive_evaluator_only"
    assert report.battery_mechanism_audit_summary["model_or_solver_executed"] is False
    assert report.battery_capacity_evaluator_summary["status"] == "available"
    assert report.battery_capacity_evaluator_summary["execution_status"] == "descriptive_evaluator_executed_with_restrictions"
    assert report.battery_capacity_evaluator_summary["evaluated_trajectories"] == 33
    assert report.battery_capacity_evaluator_summary["representative_mechanism"] == "none"
    assert report.battery_capacity_evaluator_summary["model_or_solver_executed"] is False
    assert "Battery PGIR Representation Summary" in markdown
    assert "Battery Mechanism And Identifiability Audit" in markdown
    assert "Battery Capacity-Trajectory Evaluator" in markdown
