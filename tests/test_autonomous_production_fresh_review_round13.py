from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from materials_data_analyzer.research_loop import autonomous_production_live_verifier as live_verifier

_BASE_PATH = Path(__file__).with_name("test_autonomous_production_transport_recovery.py")
_SPEC = importlib.util.spec_from_file_location("_round13_transport_fixture", _BASE_PATH)
assert _SPEC is not None and _SPEC.loader is not None
_fixture = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_fixture)


def _write(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _transport_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    output = _fixture._prepare_pretransport_state(root, "outputs/run")
    _fixture._base._run_transport_stop(monkeypatch, root=root)
    assert live_verifier.verify_live_autonomous_output(output) == "typed_nist_transport_stop_verified"
    return output


def test_transport_stop_rejects_equal_valued_float_in_policy_request_budget(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = _transport_output(tmp_path, monkeypatch)
    path = output / "nist-network-policy-qualification.json"
    qualification = json.loads(path.read_text(encoding="utf-8"))
    qualification["maximum_network_requests"] = float(qualification["maximum_network_requests"])
    _fixture._rehash(qualification, "qualification_sha256")
    _write(path, qualification)

    with pytest.raises(live_verifier.AutonomousProductionLiveVerificationError):
        live_verifier.verify_live_autonomous_output(output)


def test_transport_stop_rejects_equal_valued_float_in_authorization_budget(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = _transport_output(tmp_path, monkeypatch)
    _fixture._base._rehash_authorization_chain(
        output,
        lambda authorization: authorization.__setitem__(
            "maximum_network_requests",
            float(authorization["maximum_network_requests"]),
        ),
    )

    with pytest.raises(live_verifier.AutonomousProductionLiveVerificationError):
        live_verifier.verify_live_autonomous_output(output)


def test_transport_stop_rejects_equal_valued_float_nested_expected_file_size(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = _transport_output(tmp_path, monkeypatch)
    path = output / "nist-network-policy-qualification.json"
    qualification = json.loads(path.read_text(encoding="utf-8"))
    expected_files = qualification["expected_files"]
    first_name = sorted(expected_files)[0]
    expected_files[first_name]["size_bytes"] = float(expected_files[first_name]["size_bytes"])
    _fixture._rehash(qualification, "qualification_sha256")
    _write(path, qualification)

    with pytest.raises(live_verifier.AutonomousProductionLiveVerificationError):
        live_verifier.verify_live_autonomous_output(output)


def test_transport_stop_rejects_equal_valued_float_cycle_index(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = _transport_output(tmp_path, monkeypatch)
    path = output / "autonomous-production-manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    cycle3 = dict(manifest["cycles"][2])
    cycle3.pop("cycle_sha256")
    cycle3["cycle_index"] = 3.0
    cycle3["cycle_sha256"] = _fixture._base.recovery._canonical_sha(cycle3)
    manifest["cycles"][2] = cycle3
    _fixture._rehash(manifest, "manifest_sha256")
    _write(path, manifest)

    with pytest.raises(live_verifier.AutonomousProductionLiveVerificationError):
        live_verifier.verify_live_autonomous_output(output)


def test_transport_stop_rejects_equal_valued_float_manifest_measurement_count(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = _transport_output(tmp_path, monkeypatch)
    path = output / "autonomous-production-manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest["measurement_row_count"] = float(manifest["measurement_row_count"])
    _fixture._rehash(manifest, "manifest_sha256")
    _write(path, manifest)

    with pytest.raises(live_verifier.AutonomousProductionLiveVerificationError):
        live_verifier.verify_live_autonomous_output(output)
