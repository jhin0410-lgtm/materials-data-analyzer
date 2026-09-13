from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/cycle1-zenodo-transport-contract.yml"
TEST = ROOT / "tests/test_cycle1_exact_zenodo_route_hardening.py"
DEPENDENCY = "src/materials_data_analyzer/research_loop/in625_network_policy.py"

workflow = WORKFLOW.read_text(encoding="utf-8")
entry = f'      - "{DEPENDENCY}"\n'
anchor = '      - "src/materials_data_analyzer/research_loop/in625_archive_network_acquisition.py"\n'
if workflow.count(entry) == 0:
    if workflow.count(anchor) != 2:
        raise RuntimeError("expected exactly two mirrored workflow anchors")
    workflow = workflow.replace(anchor, anchor + entry)
if workflow.count(entry) != 2:
    raise RuntimeError("network-policy dependency must appear exactly twice")
WORKFLOW.write_text(workflow, encoding="utf-8")

test = TEST.read_text(encoding="utf-8")
test = test.replace(
    "def test_cycle1_workflow_tracks_metadata_normalizer_dependencies() -> None:\n",
    "def test_cycle1_workflow_tracks_transport_authority_dependencies() -> None:\n",
)
anchor_test = '        "src/materials_data_analyzer/research_loop/zenodo_evidence_acquisition.py",\n'
entry_test = f'        "{DEPENDENCY}",\n'
if entry_test not in test:
    if test.count(anchor_test) != 1:
        raise RuntimeError("expected one dependency tuple anchor")
    test = test.replace(anchor_test, anchor_test + entry_test)
if test.count(entry_test) != 1:
    raise RuntimeError("network-policy dependency regression must appear exactly once")
TEST.write_text(test, encoding="utf-8")
