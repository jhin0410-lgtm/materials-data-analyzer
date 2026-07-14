from pathlib import Path


DIAGNOSTIC_FILES = [
    Path("src/platform_core/claim_diagnostics.py"),
    Path("src/platform_core/diagnostic_rules.py"),
    Path("src/platform_core/diagnostic_service.py"),
    Path("src/platform_core/diagnostics.py"),
    Path("src/platform_core/evidence_graph.py"),
]


def test_diagnostics_have_no_dynamic_execution_network_or_subprocess():
    combined = "\n".join(path.read_text(encoding="utf-8") for path in DIAGNOSTIC_FILES)

    assert "eval(" not in combined
    assert "exec(" not in combined
    assert "import subprocess" not in combined
    assert "subprocess." not in combined
    assert "requests" not in combined
    assert "urllib" not in combined
    assert "socket" not in combined
    assert "importlib" not in combined


def test_diagnostic_sources_do_not_contain_local_absolute_paths_or_credentials():
    combined = "\n".join(path.read_text(encoding="utf-8").lower() for path in DIAGNOSTIC_FILES)

    assert "c:/" not in combined
    assert "c:\\" not in combined
    assert "\\users\\" not in combined
    assert "/users/" not in combined
    assert "api_key" not in combined
    assert "password" not in combined
    assert "secret" not in combined
    assert "token" not in combined
