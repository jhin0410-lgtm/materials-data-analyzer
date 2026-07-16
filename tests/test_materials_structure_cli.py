import json
import subprocess
import sys
from pathlib import Path


def _run(*args):
    return subprocess.run([sys.executable, "-m", "src.cli", "--json", *args], check=True, capture_output=True, text=True)


def test_structure_cli_preview_and_local_builds(tmp_path):
    preview = json.loads(_run("preview-mp-structure-enrichment", "configs/examples/materials_project_structure_enrichment.json").stdout)
    assert preview["network_called"] is False
    assert preview["query_plan"]["existing_id_only"] is True

    converted = json.loads(_run("convert-mp-structures-to-entities", "configs/examples/materials_project_structure_entity_conversion.json").stdout)
    entity_path = tmp_path / "entities.jsonl"
    entity_path.write_text(json.dumps(converted["structure_entity"]) + "\n", encoding="utf-8")

    validate = json.loads(_run("validate-crystal-structure-entities", str(entity_path)).stdout)
    assert validate["status"] == "validated"

    descriptor_config = tmp_path / "descriptor.json"
    descriptor_output = tmp_path / "descriptors.csv"
    descriptor_config.write_text(json.dumps({"entities_path": str(entity_path), "output": str(descriptor_output)}), encoding="utf-8")
    result = subprocess.run(
        [sys.executable, "-m", "src.cli", "--json", "build-materials-structure-descriptors", str(descriptor_config)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0

    repo_entity_path = Path("outputs") / "pytest_cli_entities.jsonl"
    repo_entity_path.write_text(entity_path.read_text(encoding="utf-8"), encoding="utf-8")

    repo_descriptor_config = Path("outputs") / "pytest_cli_descriptor_config.json"
    repo_descriptor_output = Path("outputs") / "pytest_cli_descriptors.csv"
    repo_descriptor_config.write_text(
        json.dumps({"entities_path": repo_entity_path.as_posix(), "output": repo_descriptor_output.as_posix()}),
        encoding="utf-8",
    )
    built = json.loads(_run("build-materials-structure-descriptors", repo_descriptor_config.as_posix()).stdout)
    assert built["status"] == "descriptors_written"
    validated = json.loads(_run("validate-materials-structure-descriptors", repo_descriptor_output.as_posix()).stdout)
    assert validated["valid"] is True

    graph_config = Path("outputs") / "pytest_cli_graph_config.json"
    graph_output = Path("outputs") / "pytest_cli_graphs.jsonl"
    graph_config.write_text(json.dumps({"entities_path": repo_entity_path.as_posix(), "output": graph_output.as_posix()}), encoding="utf-8")
    graph = json.loads(_run("build-crystal-graph-artifacts", graph_config.as_posix()).stdout)
    assert graph["status"] == "graphs_written"
    graph_validated = json.loads(_run("validate-crystal-graph-artifacts", graph_output.as_posix()).stdout)
    assert graph_validated["valid"] is True
