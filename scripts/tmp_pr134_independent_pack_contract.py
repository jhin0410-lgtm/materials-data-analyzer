from __future__ import annotations

from pathlib import Path

SOURCE = Path("src/materials_data_analyzer/research_loop/input_evidence_origin_pack_consumer.py")
TESTS = Path("tests/test_input_evidence_origin_pack_consumer.py")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label} anchor count={count}")
    return text.replace(old, new, 1)


text = SOURCE.read_text(encoding="utf-8")
text = replace_once(
    text,
    '''from .input_evidence_origin_pack import (
    INPUT_EVIDENCE_ORIGIN_PACK_POLICY_VERSION,
    INPUT_EVIDENCE_ORIGIN_PACK_SCHEMA_VERSION,
)
''',
    '',
    "remove-producer-constant-import",
)
text = replace_once(
    text,
    'INPUT_EVIDENCE_ORIGIN_PACK_CONSUMER_POLICY_VERSION = "1.0"\n',
    'INPUT_EVIDENCE_ORIGIN_PACK_CONSUMER_POLICY_VERSION = "1.0"\n'
    '_EXPECTED_PACK_SCHEMA_VERSION = "1.0"\n'
    '_EXPECTED_PACK_POLICY_VERSION = "1.0"\n'
    '_EXPECTED_PUBLICATION_PLATFORMS = ("windows", "linux")\n',
    "local-pack-contract",
)
text = text.replace(
    'INPUT_EVIDENCE_ORIGIN_PACK_SCHEMA_VERSION',
    '_EXPECTED_PACK_SCHEMA_VERSION',
)
text = text.replace(
    'INPUT_EVIDENCE_ORIGIN_PACK_POLICY_VERSION',
    '_EXPECTED_PACK_POLICY_VERSION',
)
old = '''    if manifest["request_source_path_authoritative"] is not False:
        raise InputEvidenceOriginPackConsumerError(
            "pack must keep request source paths non-authoritative"
        )
'''
new = '''    publication_platform = manifest["publication_platform"]
    if publication_platform not in _EXPECTED_PUBLICATION_PLATFORMS:
        raise InputEvidenceOriginPackConsumerError(
            "pack publication_platform is outside the supported producer contract"
        )
    if manifest["supported_publication_platforms"] != list(
        _EXPECTED_PUBLICATION_PLATFORMS
    ):
        raise InputEvidenceOriginPackConsumerError(
            "pack supported_publication_platforms diverge from the expected producer contract"
        )
    if manifest["request_source_path_authoritative"] is not False:
        raise InputEvidenceOriginPackConsumerError(
            "pack must keep request source paths non-authoritative"
        )
'''
text = replace_once(text, old, new, "platform-contract")
old = '''        for artifact in (
            evidence_binding,
            declaration_binding,
            verification_binding,
        ):
'''
new = '''        expected_root = f"items/{index:04d}"
        expected_paths = {
            "evidence": f"{expected_root}/evidence.bin",
            "origin_declaration": f"{expected_root}/origin_declaration.json",
            "origin_verification_decision": (
                f"{expected_root}/origin_verification_decision.json"
            ),
        }
        actual_paths = {
            "evidence": evidence_binding["path"],
            "origin_declaration": declaration_binding["path"],
            "origin_verification_decision": verification_binding["path"],
        }
        if actual_paths != expected_paths:
            raise InputEvidenceOriginPackConsumerError(
                "pack item snapshot paths do not match the deterministic producer shape"
            )
        for artifact in (
            evidence_binding,
            declaration_binding,
            verification_binding,
        ):
'''
text = replace_once(text, old, new, "deterministic-paths")
old = '''        "positive_closeout_granted": False,
    }
'''
new = '''        "positive_closeout_granted": False,
        "pack_immutability_after_return_authenticated": False,
        "hostile_concurrent_writer_resistance_authenticated": False,
    }
'''
text = replace_once(text, old, new, "post-return-boundary")
SOURCE.write_text(text, encoding="utf-8")

tests = TESTS.read_text(encoding="utf-8")
tests += r'''


def test_consumer_does_not_import_pack_publisher_module_for_schema_authority() -> None:
    source = Path(
        "src/materials_data_analyzer/research_loop/input_evidence_origin_pack_consumer.py"
    ).read_text(encoding="utf-8")
    assert "from .input_evidence_origin_pack import" not in source
    assert '_EXPECTED_PACK_SCHEMA_VERSION = "1.0"' in source
    assert '_EXPECTED_PACK_POLICY_VERSION = "1.0"' in source


def test_rejects_self_consistent_alternate_snapshot_path_shape(tmp_path: Path) -> None:
    pack = _pack(tmp_path)
    old_path = pack / "items/0000/evidence.bin"
    new_path = pack / "items/0000/renamed-evidence.bin"
    old_path.rename(new_path)
    manifest = _manifest(pack)
    manifest["items"][0]["evidence_artifact"]["path"] = (
        "items/0000/renamed-evidence.bin"
    )
    _write_manifest(pack, manifest)
    with pytest.raises(InputEvidenceOriginPackConsumerError, match="deterministic producer shape"):
        authenticate_input_evidence_origin_pack(pack)


def test_rejects_publication_platform_contract_drift(tmp_path: Path) -> None:
    pack = _pack(tmp_path)
    manifest = _manifest(pack)
    manifest["publication_platform"] = "darwin"
    _write_manifest(pack, manifest)
    with pytest.raises(InputEvidenceOriginPackConsumerError, match="publication_platform"):
        authenticate_input_evidence_origin_pack(pack)


def test_reports_post_return_mutability_boundary(tmp_path: Path) -> None:
    report = authenticate_input_evidence_origin_pack(_pack(tmp_path))
    assert report["pack_immutability_after_return_authenticated"] is False
    assert report["hostile_concurrent_writer_resistance_authenticated"] is False
'''
TESTS.write_text(tests, encoding="utf-8")
