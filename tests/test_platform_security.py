from pathlib import Path


PLATFORM_FILES = [
    Path("src/platform_core/adapters.py"),
    Path("src/platform_core/adapter_registry.py"),
    Path("src/platform_core/plugins.py"),
    Path("src/platform_core/registry.py"),
    Path("src/platform_core/artifacts.py"),
    Path("src/platform_core/validation_registry.py"),
    Path("src/platform_core/trust_registry.py"),
    Path("src/platform_core/config.py"),
    Path("src/platform_core/planner.py"),
    Path("src/platform_core/manifests.py"),
    Path("src/cli.py"),
]


def test_platform_scaffold_has_no_dynamic_execution_or_network_imports():
    combined = "\n".join(path.read_text(encoding="utf-8") for path in PLATFORM_FILES)

    assert "eval(" not in combined
    assert "exec(" not in combined
    assert "subprocess" not in combined
    assert "requests" not in combined
    assert "urllib" not in combined
    assert "socket" not in combined


def test_platform_config_contract_prohibits_executable_config():
    text = Path("data/platform/pipeline_config_schema_v2.json").read_text(encoding="utf-8")

    assert "eval" in text
    assert "exec" in text
    assert "arbitrary imports are prohibited" in text
