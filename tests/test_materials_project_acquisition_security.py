import json
import subprocess
import sys

from src.platform_core.materials_project_acquisition import preview_existing_id_enrichment


def test_preview_performs_no_network_and_reports_preview_only():
    result = preview_existing_id_enrichment(["mp-1"], max_records=1).to_dict()

    assert result["status"] == "preview_only_no_network"
    assert result["requested_count"] == 1
    assert result["output_policy"] == "local_only"


def test_execute_flag_requires_bounded_existing_id_policy(tmp_path):
    config_path = tmp_path / "broad_query.json"
    config_path.write_text(
        json.dumps(
            {
                "schema_version": "2.2.4",
                "mode": "expand_query_universe",
                "requested_fields": ["material_id", "structure"],
                "max_records": 1,
            }
        ),
        encoding="utf-8",
    )
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "src.cli",
            "--json",
            "enrich-mp-structures",
            str(config_path),
            "--execute",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "enrichment_failed"
    assert "only enrich_existing_ids mode is allowed" in payload["error"]


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
