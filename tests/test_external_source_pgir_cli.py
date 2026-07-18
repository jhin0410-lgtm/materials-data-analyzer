import json
import subprocess
import sys
from pathlib import Path


def _cli(*args: str):
    return subprocess.run(
        [sys.executable, "-m", "src.cli", "--json", *args],
        check=False,
        capture_output=True,
        text=True,
    )


def test_external_source_cli_list_inspect_and_provenance_audit():
    listed = _cli("list-external-source-systems")
    inspected = _cli("inspect-external-source-system", "materials_project")
    audited = _cli("audit-external-source-provenance", "configs/examples/external_source_contract_audit.json")

    assert listed.returncode == inspected.returncode == audited.returncode == 0
    assert json.loads(listed.stdout)["source_system_count"] == 5
    assert json.loads(inspected.stdout)["authentication_environment_variable"] == "MP_API_KEY"
    assert json.loads(audited.stdout)["trust_score_used"] is False


def test_materials_pgir_cli_preview_and_cross_domain_evaluation_do_not_execute_science():
    preview = _cli("preview-materials-pgir-reuse", "configs/examples/materials_structure_pgir_reuse.json")
    evaluated = _cli("evaluate-cross-domain-pgir-reuse", "configs/examples/cross_domain_pgir_reuse_audit.json")

    assert preview.returncode == evaluated.returncode == 0
    preview_payload = json.loads(preview.stdout)
    evaluated_payload = json.loads(evaluated.stdout)
    assert preview_payload["network_called"] is False
    assert preview_payload["descriptor_or_graph_regenerated"] is False
    assert evaluated_payload["physical_operator_reuse"] is False
    assert evaluated_payload["model_or_solver_executed"] is False


def test_cli_rejects_network_enabled_audit_config(tmp_path):
    config = tmp_path / "bad.json"
    config.write_text(json.dumps({"schema_version": "2.4.1", "network_enabled": True}), encoding="utf-8")
    result = _cli("preview-materials-pgir-reuse", str(config))

    assert result.returncode != 0
    assert json.loads(result.stdout)["status"] == "invalid"


def test_cli_rejects_tampered_known_external_source_registry(tmp_path):
    registry = json.loads(
        Path("data/platform/external_source_system_registry_v1.json").read_text(encoding="utf-8")
    )
    registry["source_systems"][0]["publisher"] = "tampered"
    path = tmp_path / "tampered_registry.json"
    path.write_text(json.dumps(registry), encoding="utf-8")

    result = _cli("validate-external-source-contract", str(path))

    assert result.returncode != 0
    assert json.loads(result.stdout)["status"] == "invalid"


def test_cli_shows_tracked_materials_reuse_summary():
    result = _cli("show-materials-pgir-reuse-summary")
    payload = json.loads(result.stdout)

    assert result.returncode == 0
    assert payload["decision_status"] == "second_domain_pgir_reuse_demonstrated_with_restrictions"
    assert payload["representative_model"] == "none"
