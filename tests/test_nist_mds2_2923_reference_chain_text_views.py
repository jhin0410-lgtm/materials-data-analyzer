from __future__ import annotations

from materials_data_analyzer.research_loop import nist_mds2_2923_reference_chain_evidence as evidence


def test_claim_uses_layout_only_when_plain_view_loses_document_order() -> None:
    fragments = ("AMMT", "195 W", "800 mm/s", "Weaver", "[7]")
    views = {
        "plain": ["Weaver [7] AMMT 195 W 800 mm/s"],
        "layout": ["AMMT 195 W 800 mm/s More details Weaver [7]"],
    }

    receipt = evidence._claim_receipt("claim", fragments, "scope", views)

    assert receipt["matched"] is True
    assert receipt["selected_text_extraction_mode"] == "layout"
    assert receipt["allowed_text_extraction_modes"] == ["plain", "layout"]
    assert receipt["match_count"] == 1
    assert receipt["matches"][0]["text_extraction_mode"] == "layout"


def test_unordered_fragment_presence_cannot_satisfy_claim_in_any_view() -> None:
    fragments = ("AMMT", "195 W", "800 mm/s", "Weaver", "[7]")
    views = {
        "plain": ["Weaver [7] AMMT 195 W 800 mm/s"],
        "layout": ["AMMT Weaver [7] 195 W 800 mm/s"],
    }

    receipt = evidence._claim_receipt("claim", fragments, "scope", views)

    assert receipt["matched"] is False
    assert receipt["selected_text_extraction_mode"] is None
    assert receipt["match_count"] == 0


def test_ordered_claim_span_must_remain_within_exact_utf8_byte_budget() -> None:
    fragments = ("AMMT", "Weaver")
    oversized_gap = "x" * (evidence.MAX_CLAIM_SPAN_UTF8_BYTES + 1)
    views = {
        "plain": [f"AMMT {oversized_gap} Weaver"],
        "layout": [f"AMMT {oversized_gap} Weaver"],
    }

    receipt = evidence._claim_receipt("claim", fragments, "scope", views)

    assert receipt["matched"] is False
    assert receipt["selected_text_extraction_mode"] is None


def test_plain_view_is_deterministically_preferred_when_both_views_match() -> None:
    fragments = ("AMMT", "195 W", "Weaver")
    views = {
        "plain": ["AMMT 195 W Weaver"],
        "layout": ["AMMT 195 W Weaver"],
    }

    first = evidence._claim_receipt("claim", fragments, "scope", views)
    second = evidence._claim_receipt("claim", fragments, "scope", views)

    assert first == second
    assert first["selected_text_extraction_mode"] == "plain"
    assert first["matches"][0]["text_extraction_mode"] == "plain"
