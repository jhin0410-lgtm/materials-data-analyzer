import json
import subprocess
import sys

from src.platform_core.materials_project_acquisition import preview_existing_id_enrichment


def test_preview_performs_no_network_and_reports_preview_only():
    result = preview_existing_id_enrichment(["mp-1"], max_records=1).to_dict()

    assert result["status"] == "preview_only_no_network"
    assert result["requested_count"] == 1
    assert result["output_policy"] == "local_only"


def test_execute_flag_is_blocked_by_unified_cli():
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "src.cli",
            "--json",
            "enrich-mp-structures",
            "configs/examples/materials_project_structure_enrichment_preview.json",
            "--execute",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "blocked_execution_not_implemented_in_platform_core"
    assert payload["network_called"] is False


def test_scope_audit_cli_has_no_credential_value():
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "src.cli",
            "--json",
            "audit-materials-project-scope",
            "configs/examples/materials_project_scope_audit.json",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    payload = result.stdout
    assert "MP_API_KEY" in payload
    assert "ghp_" not in payload
    assert "redacted-secret-sentinel" not in payload.lower()
