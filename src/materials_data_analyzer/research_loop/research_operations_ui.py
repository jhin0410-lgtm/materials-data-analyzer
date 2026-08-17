"""Read-only HTML rendering for autonomous research episode operations."""
from __future__ import annotations

import html
import json
from collections.abc import Mapping, Sequence
from typing import Any

from .research_episode import validate_episode_state

RESEARCH_OPERATIONS_UI_VERSION = "1.0"


def _render_list(values: Sequence[object]) -> str:
    if not values:
        return "<p>None</p>"
    return "<ul>" + "".join(
        f"<li>{html.escape(str(value))}</li>" for value in values
    ) + "</ul>"


def render_research_episode_html(
    episode: Mapping[str, Any],
    *,
    evidence_records: Sequence[Mapping[str, Any]] = (),
    benchmark_summary: Mapping[str, Any] | None = None,
) -> str:
    """Render verified control-plane state without mutation or execution controls."""
    state = validate_episode_state(dict(episode))
    evidence_rows: list[str] = []
    for record in evidence_records:
        candidate_id = html.escape(str(record.get("candidate_id", "unknown")))
        evidence_class = html.escape(str(record.get("evidence_class", "unknown")))
        provider = html.escape(str(record.get("provider", "unknown")))
        scientific_changed = html.escape(str(record.get("scientific_status_changed", "unknown")))
        evidence_rows.append(
            "<tr>"
            f"<td>{candidate_id}</td><td>{evidence_class}</td>"
            f"<td>{provider}</td><td>{scientific_changed}</td>"
            "</tr>"
        )
    benchmark = "Not evaluated"
    if benchmark_summary is not None:
        benchmark = html.escape(
            json.dumps(dict(benchmark_summary), ensure_ascii=False, sort_keys=True)
        )
    return "".join(
        [
            "<!doctype html><html><head><meta charset='utf-8'>",
            "<title>Research Operations</title>",
            "<style>body{font-family:system-ui;max-width:1100px;margin:2rem auto;padding:0 1rem}",
            "table{border-collapse:collapse;width:100%}td,th{border:1px solid #ccc;padding:.45rem}",
            "code{white-space:pre-wrap}</style></head><body>",
            "<h1>Research Operations — Read Only</h1>",
            f"<p><strong>Episode:</strong> {html.escape(state['episode_id'])}</p>",
            f"<p><strong>Status:</strong> {html.escape(state['status'])}</p>",
            f"<p><strong>Question:</strong> {html.escape(state['research_question'])}</p>",
            f"<p><strong>Iteration:</strong> {state['iteration']} / {state['budgets']['max_iterations']}</p>",
            "<h2>Unresolved gaps</h2>",
            _render_list(state["unresolved_gaps"]),
            "<h2>Human review queue</h2>",
            _render_list(state["review_queue"]),
            "<h2>Blockers</h2>",
            _render_list(state["blockers"]),
            "<h2>Evidence federation</h2>",
            "<table><thead><tr><th>ID</th><th>Class</th><th>Provider</th><th>Scientific status changed</th></tr></thead><tbody>",
            "".join(evidence_rows),
            "</tbody></table>",
            "<h2>Agent benchmark</h2><code>",
            benchmark,
            "</code>",
            "<h2>Action history</h2><code>",
            html.escape(json.dumps(state["action_history"], ensure_ascii=False, indent=2, sort_keys=True)),
            "</code>",
            "<p><em>This surface is intentionally read-only. It cannot approve evidence, execute actions, or modify scientific status.</em></p>",
            "</body></html>",
        ]
    )


__all__ = ["RESEARCH_OPERATIONS_UI_VERSION", "render_research_episode_html"]
