import json
import subprocess
import sys
from pathlib import Path


def _run_cli(*args):
    return subprocess.run([sys.executable, "-m", "src.cli", *args], check=False, capture_output=True, text=True)


def test_scientific_cli_lists_and_inspects_constraints_and_packs():
    constraints = _run_cli("--json", "list-scientific-constraints", "--domain", "xrd")
    constraint = _run_cli("--json", "inspect-scientific-constraint", "xrd.bragg.geometry")
    packs = _run_cli("list-knowledge-packs")
    pack = _run_cli("--json", "inspect-knowledge-pack", "materials_basic_v1")

    assert constraints.returncode == 0
    assert {item["domain"] for item in json.loads(constraints.stdout)} == {"xrd"}
    assert json.loads(constraint.stdout)["equation_display"] == "n lambda = 2 d sin(theta)"
    assert "materials_basic_v1" in packs.stdout
    assert json.loads(pack.stdout)["domain"] == "materials"


def test_scientific_cli_validates_examples_and_converts_units():
    materials = _run_cli("--json", "validate-scientific-input", "configs/examples/scientific_constraints_materials_basic.json")
    xrd = _run_cli("--json", "validate-scientific-input", "configs/examples/scientific_constraints_xrd_bragg_scherrer.json")
    conversion = _run_cli("--json", "convert-unit", "--value", "25", "--from", "degC", "--to", "K")

    assert materials.returncode == 0
    assert json.loads(materials.stdout)["status"] == "scientifically_consistent"
    assert xrd.returncode == 0
    assert any(finding["category"] == "physics_claim_boundary" for finding in json.loads(xrd.stdout)["findings"])
    assert json.loads(conversion.stdout)["converted_value"] == 298.15


def test_scientific_cli_export_is_local_only_and_rejects_absolute_path(tmp_path):
    absolute = _run_cli("--json", "export-scientific-registry", "--output", str(tmp_path / "registry.json"))
    output = "outputs/platform_science/test_cli_scientific_registry.json"
    exported = _run_cli("--json", "export-scientific-registry", "--output", output, "--overwrite")

    assert absolute.returncode == 9
    assert exported.returncode == 0
    payload = json.loads(exported.stdout)
    assert payload["output"] == output
    assert Path(output).exists()
