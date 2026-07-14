import json
import subprocess
import sys
from pathlib import Path


def _run_cli(*args):
    return subprocess.run([sys.executable, "-m", "src.cli", *args], check=False, capture_output=True, text=True)


def test_scientific_trust_cli_end_to_end():
    registry_path = "outputs/platform_registry/test_science_trust_cli.sqlite3"
    registry_file = Path(registry_path)
    if registry_file.exists():
        registry_file.unlink()
    execution = _run_cli(
        "--json",
        "execute-scientific-check",
        "configs/examples/xrd_bragg_consistent_check.json",
        "--registry-path",
        registry_path,
        "--persist",
        "--output-dir",
        "outputs/platform_science/test_trust_cli_bragg",
        "--overwrite",
    )
    assert execution.returncode == 0, execution.stderr

    trust = _run_cli("--json", "evaluate-scientific-trust", "xrd_bragg_consistent_check", "--registry-path", registry_path)
    assert trust.returncode == 0, trust.stderr
    trust_payload = json.loads(trust.stdout)
    trust_id = trust_payload["evaluation_id"]
    assert trust_payload["evidence_level"] == "bounded_quantity_estimated"
    assert any(row["claim_id"] == "phase_identification_supported" and row["status"] == "prohibited" for row in trust_payload["claim_boundaries"])

    shown = _run_cli("--json", "show-scientific-trust", trust_id, "--registry-path", registry_path)
    eligibility = _run_cli("--json", "list-feature-eligibility", trust_id, "--registry-path", registry_path)
    feature = _run_cli("--json", "evaluate-scientific-feature", "xrd_bragg_consistent_check", "xrd.bragg_d_spacing", "--registry-path", registry_path)
    claims = _run_cli("--json", "list-scientific-claim-boundaries", "--trust-evaluation-id", trust_id, "--registry-path", registry_path)
    validation = _run_cli("--json", "scientific-trust-validate", "--registry-path", registry_path)
    export = _run_cli(
        "--json",
        "export-scientific-trust",
        "--registry-path",
        registry_path,
        "--output",
        "outputs/platform_science/test_scientific_trust_export.json",
        "--overwrite",
    )

    assert shown.returncode == 0 and json.loads(shown.stdout)["evaluation"]["trust_evaluation_id"] == trust_id
    assert eligibility.returncode == 0 and json.loads(eligibility.stdout)
    assert json.loads(feature.stdout)["eligibility_status"] == "eligible_bounded"
    assert any(row["claim_id"] == "particle_size_estimated" and row["status"] == "prohibited" for row in json.loads(claims.stdout))
    assert validation.returncode == 0 and json.loads(validation.stdout)["valid"] is True
    assert export.returncode == 0 and Path(json.loads(export.stdout)["output"]).exists()


def test_scientific_feature_candidate_cli_is_metadata_only():
    listed = _run_cli("--json", "list-scientific-feature-candidates", "--domain", "materials")
    inspected = _run_cli("--json", "inspect-scientific-feature-candidate", "materials.atomic_radius_mismatch")

    assert listed.returncode == 0
    assert all(row["domain"] == "materials" for row in json.loads(listed.stdout))
    payload = json.loads(inspected.stdout)
    assert payload["feature_id"] == "materials.atomic_radius_mismatch"
    assert payload["validation_status"] == "metadata_only"
