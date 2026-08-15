from __future__ import annotations

from pathlib import Path

SOURCE = Path("src/materials_data_analyzer/research_loop/input_evidence_origin_pack.py")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label} anchor count={count}")
    return text.replace(old, new, 1)


text = SOURCE.read_text(encoding="utf-8")
text = replace_once(
    text,
    'INPUT_EVIDENCE_ORIGIN_PACK_SUPPORTED_PLATFORMS = ("windows", "linux")\n',
    'INPUT_EVIDENCE_ORIGIN_PACK_SUPPORTED_PLATFORMS = ("windows", "linux")\n'
    '_ORIGIN_CLASSES = {\n'
    '    "empirical_measurement",\n'
    '    "external_physical_experiment",\n'
    '    "computational_output",\n'
    '    "analysis_output",\n'
    '}\n',
    "origin-classes",
)
old = '''        program_binding = report_item.get("program_evidence_binding")
        if not isinstance(program_binding, Mapping):
            raise InputEvidenceOriginPackError(
                "authenticated request item lacks program evidence identity"
            )
        manifest_items.append(
            {
                "program_evidence_binding": dict(program_binding),
                "origin_class": report_item.get("origin_class"),
'''
new = '''        program_binding = report_item.get("program_evidence_binding")
        if not isinstance(program_binding, Mapping):
            raise InputEvidenceOriginPackError(
                "authenticated request item lacks program evidence identity"
            )
        report_identity = (
            program_binding.get("workstream_id"),
            program_binding.get("role"),
            program_binding.get("sha256"),
        )
        payload_identity = (
            payload.workstream_id,
            payload.role,
            payload.evidence_sha256,
        )
        if report_identity != payload_identity:
            raise InputEvidenceOriginPackError(
                "authenticated request report/payload identity diverged"
            )
        if _sha256(payload.evidence_bytes) != payload.evidence_sha256:
            raise InputEvidenceOriginPackError(
                "authenticated request payload evidence checksum diverged"
            )
        origin_class = report_item.get("origin_class")
        if origin_class not in _ORIGIN_CLASSES:
            raise InputEvidenceOriginPackError(
                "authenticated request returned unsupported origin_class"
            )
        manifest_items.append(
            {
                "program_evidence_binding": dict(program_binding),
                "origin_class": origin_class,
'''
text = replace_once(text, old, new, "report-payload-crosscheck")
SOURCE.write_text(text, encoding="utf-8")
