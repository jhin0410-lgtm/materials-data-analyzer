from __future__ import annotations

from pathlib import Path

SOURCE = Path("src/materials_data_analyzer/research_loop/acquisition_record_binding.py")

text = SOURCE.read_text(encoding="utf-8")
old = '''        expected = claim["expected_value"]
        if isinstance(actual, (dict, list, float)) or actual != expected:
            raise AcquisitionRecordBindingError(
                f"manifest claim {claim['claim']!r} does not equal its exact declared value"
            )
'''
new = '''        expected = claim["expected_value"]
        if (
            isinstance(actual, (dict, list, float))
            or type(actual) is not type(expected)
            or actual != expected
        ):
            raise AcquisitionRecordBindingError(
                f"manifest claim {claim['claim']!r} does not equal its exact declared value/type"
            )
'''
if text.count(old) != 1:
    raise SystemExit(f"strict scalar comparison anchor count={text.count(old)}")
SOURCE.write_text(text.replace(old, new, 1), encoding="utf-8")
