from __future__ import annotations

from pathlib import Path

PATCH = Path("scripts/_tmp_pr202_final_review_fix.py")
text = PATCH.read_text(encoding="utf-8")

redundant_policy = '''plan_test = replace_once(\n    plan_test,\n    '        "schema_version": "1.0",\\n        "source_discrepancy_report_sha256": previous_report_sha,\\n',\n    '        "schema_version": "1.0",\\n        "policy_version": "1.0",\\n        "source_discrepancy_report_sha256": previous_report_sha,\\n',\n    label="plan test handoff policy",\n)\n'''
redundant_ancestry = '''plan_test = replace_once(\n    plan_test,\n    '        "research_objectives": [\\n',\n    '        "source_ancestry": {\\n            "previous_discrepancy_report_sha256": None,\\n            "prior_diagnosis_types": [],\\n            "current_diagnosis_types": ["parameter_or_property_uncertainty"],\\n        },\\n        "research_objectives": [\\n',\n    label="plan test handoff ancestry",\n)\n'''

for label, block in (
    ("policy", redundant_policy),
    ("source ancestry", redundant_ancestry),
):
    if block not in text:
        raise SystemExit(f"expected redundant {label} block was not found")
    text = text.replace(block, "", 1)

PATCH.write_text(text, encoding="utf-8")
