from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/run_live_in625_authorized_row_intake.py"
TEST = ROOT / "tests/test_live_in625_authorized_row_intake_transport.py"
WORKFLOW = ROOT / ".github/workflows/in625-authorized-network-row-intake.yml"

text = SCRIPT.read_text(encoding="utf-8")
text = text.replace("import urllib.parse\nimport urllib.request\n", "")

import_anchor = "from materials_data_analyzer.research_loop.planning_adapter import plan_research_next_action\n"
public_import = '''from materials_data_analyzer.research_loop.public_data_acquisition import (\n    fetch_https_bytes,\n)\n'''
if public_import not in text:
    text = text.replace(import_anchor, import_anchor + public_import)

const_anchor = "\n\ndef _sha256_file(path: Path) -> str:\n"
if "_ZENODO_CONTROL_PLANE_MAX_BYTES" not in text:
    text = text.replace(
        const_anchor,
        "\n\n_ZENODO_CONTROL_PLANE_MAX_BYTES = 8 * 1024 * 1024\n" + const_anchor,
    )

start = text.index("def _exact_zenodo_get(")
end = text.index("\n\ndef _require", start)
new_helper = '''def _exact_zenodo_get(\n    url: str,\n    *,\n    max_bytes: int,\n    timeout: float = 60.0,\n) -> bytes:\n    result = fetch_https_bytes(\n        url,\n        allowed_hosts=("zenodo.org",),\n        max_bytes=max_bytes,\n        timeout_seconds=timeout,\n        headers={\n            "User-Agent": "materials-data-analyzer/in625-preauthorization-metadata"\n        },\n    )\n    return result.body\n'''
text = text[:start] + new_helper + text[end:]

old_metadata = "    metadata_bytes = _exact_zenodo_get(metadata_url)\n"
new_metadata = '''    metadata_bytes = _exact_zenodo_get(\n        metadata_url,\n        max_bytes=_ZENODO_CONTROL_PLANE_MAX_BYTES,\n    )\n'''
if old_metadata in text:
    text = text.replace(old_metadata, new_metadata)

old_readme = "    readme_bytes = _exact_zenodo_get(readme_url)\n"
new_readme = '''    readme_max_bytes = config["zenodo"]["files"][readme_name]["size_bytes"]\n    readme_bytes = _exact_zenodo_get(\n        readme_url,\n        max_bytes=readme_max_bytes,\n    )\n'''
if old_readme in text:
    text = text.replace(old_readme, new_readme)

SCRIPT.write_text(text, encoding="utf-8")

TEST.write_text(
    '''from __future__ import annotations\n\nimport ast\nimport importlib.util\nimport sys\nfrom pathlib import Path\n\nimport pytest\n\nfrom materials_data_analyzer.research_loop.public_data_acquisition import (\n    FetchResult,\n    PublicAcquisitionError,\n    PublicAcquisitionTransportError,\n)\n\nROOT = Path(__file__).resolve().parents[1]\nSCRIPT = ROOT / "scripts/run_live_in625_authorized_row_intake.py"\n\n\ndef _load_runner():\n    name = "_test_live_in625_authorized_row_intake"\n    spec = importlib.util.spec_from_file_location(name, SCRIPT)\n    assert spec is not None and spec.loader is not None\n    module = importlib.util.module_from_spec(spec)\n    sys.modules[name] = module\n    spec.loader.exec_module(module)\n    return module\n\n\ndef test_runner_has_no_private_urllib_urlopen_escape_hatch() -> None:\n    tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))\n    for node in ast.walk(tree):\n        if not isinstance(node, ast.Call):\n            continue\n        func = node.func\n        if not isinstance(func, ast.Attribute) or func.attr != "urlopen":\n            continue\n        pytest.fail("live IN625 runner may not call a private urlopen transport path")\n\n\ndef test_exact_zenodo_get_delegates_to_shared_bounded_fetch(monkeypatch: pytest.MonkeyPatch) -> None:\n    runner = _load_runner()\n    observed: dict[str, object] = {}\n\n    def fake_fetch(url: str, **kwargs: object) -> FetchResult:\n        observed["url"] = url\n        observed.update(kwargs)\n        return FetchResult(\n            body=b"trusted-bytes",\n            status_code=200,\n            final_url=url,\n            content_type="application/octet-stream",\n        )\n\n    monkeypatch.setattr(runner, "fetch_https_bytes", fake_fetch)\n    body = runner._exact_zenodo_get(\n        "https://zenodo.org/api/records/20503603",\n        max_bytes=12345,\n        timeout=7.5,\n    )\n\n    assert body == b"trusted-bytes"\n    assert observed["url"] == "https://zenodo.org/api/records/20503603"\n    assert observed["allowed_hosts"] == ("zenodo.org",)\n    assert observed["max_bytes"] == 12345\n    assert observed["timeout_seconds"] == 7.5\n    assert observed["headers"] == {\n        "User-Agent": "materials-data-analyzer/in625-preauthorization-metadata"\n    }\n\n\n@pytest.mark.parametrize(\n    "error_type",\n    [PublicAcquisitionTransportError, PublicAcquisitionError],\n)\ndef test_exact_zenodo_get_preserves_shared_transport_taxonomy(\n    monkeypatch: pytest.MonkeyPatch,\n    error_type: type[PublicAcquisitionError],\n) -> None:\n    runner = _load_runner()\n    sentinel = error_type("sentinel")\n\n    def fail_fetch(*args: object, **kwargs: object) -> FetchResult:\n        raise sentinel\n\n    monkeypatch.setattr(runner, "fetch_https_bytes", fail_fetch)\n    with pytest.raises(error_type) as caught:\n        runner._exact_zenodo_get(\n            "https://zenodo.org/api/records/20503603",\n            max_bytes=1024,\n        )\n    assert caught.value is sentinel\n\n\ndef test_run_live_chain_passes_repository_bounded_control_plane_limits() -> None:\n    tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))\n    assignments: dict[str, ast.Call] = {}\n    for node in ast.walk(tree):\n        if not isinstance(node, ast.Assign) or len(node.targets) != 1:\n            continue\n        target = node.targets[0]\n        if not isinstance(target, ast.Name) or not isinstance(node.value, ast.Call):\n            continue\n        if isinstance(node.value.func, ast.Name) and node.value.func.id == "_exact_zenodo_get":\n            assignments[target.id] = node.value\n\n    metadata_call = assignments["metadata_bytes"]\n    readme_call = assignments["readme_bytes"]\n    metadata_limit = next(kw.value for kw in metadata_call.keywords if kw.arg == "max_bytes")\n    readme_limit = next(kw.value for kw in readme_call.keywords if kw.arg == "max_bytes")\n    assert isinstance(metadata_limit, ast.Name)\n    assert metadata_limit.id == "_ZENODO_CONTROL_PLANE_MAX_BYTES"\n    assert isinstance(readme_limit, ast.Name)\n    assert readme_limit.id == "readme_max_bytes"\n\n    source = SCRIPT.read_text(encoding="utf-8")\n    assert 'readme_max_bytes = config["zenodo"]["files"][readme_name]["size_bytes"]' in source\n''',
    encoding="utf-8",
)

workflow = WORKFLOW.read_text(encoding="utf-8")
test_path_entry = '      - "tests/test_live_in625_authorized_row_intake_transport.py"\n'
path_anchor = '      - "tests/test_in625_archive_network_acquisition.py"\n'
if test_path_entry not in workflow:
    workflow = workflow.replace(path_anchor, path_anchor + test_path_entry)

command_entry = "          tests/test_live_in625_authorized_row_intake_transport.py\n"
command_anchor = "          tests/test_in625_archive_network_acquisition.py\n"
if command_entry not in workflow:
    workflow = workflow.replace(command_anchor, command_anchor + command_entry)

if workflow.count("tests/test_live_in625_authorized_row_intake_transport.py") != 3:
    raise RuntimeError("live transport regression must be wired into both path filters and pre-network pytest gate")
WORKFLOW.write_text(workflow, encoding="utf-8")
