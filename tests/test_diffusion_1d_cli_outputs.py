import json
from pathlib import Path

from src.cli import main
from src.platform_core.diffusion_1d_benchmark import export_diffusion_benchmark_summary


BENCHMARK_CONFIG = "configs/examples/pgir_diffusion_1d_benchmark.json"
REFINEMENT_CONFIG = "configs/examples/pgir_diffusion_1d_refinement_audit.json"


def test_preview_cli_is_side_effect_free_and_reports_no_solver_execution(capsys, tmp_path, monkeypatch):
    monkeypatch.chdir(Path(__file__).parents[1])
    before = set(tmp_path.rglob("*"))
    code = main(["--json", "preview-diffusion-1d-benchmark", BENCHMARK_CONFIG])
    payload = json.loads(capsys.readouterr().out)

    assert code == 0
    assert payload["status"] == "benchmark_preview_ready"
    assert payload["solver_executed"] is False
    assert set(tmp_path.rglob("*")) == before


def test_model_contract_inspection_and_validation_cli(capsys, tmp_path):
    assert main(["--json", "inspect-pgir-model-contract"]) == 0
    contract = json.loads(capsys.readouterr().out)
    path = tmp_path / "contract.json"
    path.write_text(json.dumps(contract), encoding="utf-8")

    assert main(["--json", "validate-pgir-model-contract", str(path)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["valid"] is True


def test_run_and_refinement_cli_return_compact_json(capsys, tmp_path, monkeypatch):
    repo_root = Path(__file__).parents[1]
    monkeypatch.chdir(repo_root)
    assert main(["--json", "run-diffusion-1d-benchmark", BENCHMARK_CONFIG]) == 0
    run_payload = json.loads(capsys.readouterr().out)
    assert run_payload["status"] == "benchmark_executed_with_documented_numerical_error"
    assert "values" not in json.dumps(run_payload)

    assert main(["--json", "run-diffusion-1d-refinement-audit", REFINEMENT_CONFIG]) == 0
    refinement = json.loads(capsys.readouterr().out)
    assert refinement["error_strictly_decreases"] is True


def test_exported_compact_outputs_parse_and_contain_no_arrays_or_absolute_paths(tmp_path):
    benchmark = json.loads(Path(BENCHMARK_CONFIG).read_text(encoding="utf-8"))
    refinement = json.loads(Path(REFINEMENT_CONFIG).read_text(encoding="utf-8"))
    result = export_diffusion_benchmark_summary(benchmark, refinement, repo_root=tmp_path)

    assert result["status"] == "benchmark_summary_exported"
    for relative_path in result["written"]:
        assert (tmp_path / relative_path).exists()
    tracked_json = list((tmp_path / "data" / "processed").glob("v2_4_diffusion_*.json"))
    assert tracked_json
    for path in tracked_json:
        serialized = path.read_text(encoding="utf-8")
        assert '"values"' not in serialized
        assert str(tmp_path).replace("\\", "/") not in serialized.replace("\\", "/")


def test_source_contains_no_dynamic_or_unsafe_execution():
    source = Path("src/platform_core/diffusion_1d_benchmark.py").read_text(encoding="utf-8")
    contract_source = Path("src/platform_core/pgir_model_contracts.py").read_text(encoding="utf-8")
    forbidden = ("eval(", "exec(", "importlib", "subprocess", "pickle", "requests.", "http://", "https://")
    assert not any(token in source for token in forbidden)
    assert not any(token in contract_source for token in forbidden)
