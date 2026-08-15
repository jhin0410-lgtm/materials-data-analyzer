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
old = '''        for path_field in (
            "evidence_path",
            "origin_declaration_path",
            "origin_verification_decision_path",
        ):
            _strict_text(item[path_field], f"pack request snapshot items[{index}].{path_field}")
'''
new = '''        for path_field in (
            "evidence_path",
            "origin_declaration_path",
            "origin_verification_decision_path",
        ):
            _portable_parts(
                item[path_field],
                f"pack request snapshot items[{index}].{path_field}",
            )
'''
text = replace_once(text, old, new, "request-portable-path-contract")
old = '''        manifest_origin_class = item["origin_class"]
        if manifest_origin_class not in _ORIGIN_CLASSES:
            raise InputEvidenceOriginPackConsumerError(
                "pack manifest contains unsupported origin_class"
            )
'''
new = '''        manifest_origin_class = _strict_text(
            item["origin_class"],
            f"pack manifest items[{index}].origin_class",
        )
        if manifest_origin_class not in _ORIGIN_CLASSES:
            raise InputEvidenceOriginPackConsumerError(
                "pack manifest contains unsupported origin_class"
            )
'''
text = replace_once(text, old, new, "origin-class-type")
SOURCE.write_text(text, encoding="utf-8")

tests = TESTS.read_text(encoding="utf-8")
if "def test_rejects_nonportable_source_path_inside_request_snapshot" not in tests:
    tests += r'''


@pytest.mark.parametrize(
    "field,bad_path",
    [
        ("evidence_path", "../outside.bin"),
        ("origin_declaration_path", "NUL.txt"),
        ("origin_verification_decision_path", "file:stream"),
        ("evidence_path", "dir\\evidence.bin"),
    ],
)
def test_rejects_nonportable_source_path_inside_request_snapshot(
    tmp_path: Path,
    field: str,
    bad_path: str,
) -> None:
    pack = _pack(tmp_path)
    request_path = pack / "request.json"
    request = json.loads(request_path.read_bytes())
    request["items"][0][field] = bad_path
    raw = _json_bytes(request)
    request_path.write_bytes(raw)
    manifest = _manifest(pack)
    manifest["request_artifact"]["sha256"] = hashlib.sha256(raw).hexdigest()
    manifest["request_artifact"]["size_bytes"] = len(raw)
    _write_manifest(pack, manifest)
    with pytest.raises(
        InputEvidenceOriginPackConsumerError,
        match=(
            "portable relative pack path|nonportable|parent components|"
            "Windows-reserved path component"
        ),
    ):
        authenticate_input_evidence_origin_pack(pack)


def test_rejects_non_text_manifest_origin_class(tmp_path: Path) -> None:
    pack = _pack(tmp_path)
    manifest = _manifest(pack)
    manifest["items"][0]["origin_class"] = ["empirical_measurement"]
    _write_manifest(pack, manifest)
    with pytest.raises(InputEvidenceOriginPackConsumerError, match="origin_class must be non-empty text"):
        authenticate_input_evidence_origin_pack(pack)
'''
TESTS.write_text(tests, encoding="utf-8")
