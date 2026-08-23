from materials_data_analyzer.research_loop import nist_mds2_2923_reference_chain_evidence as evidence


def test_pdf_discretionary_break_controls_are_removed_without_collapsing_words() -> None:
    raw = "scal\x02ing manu\x02facturing Measure\x02ments soft\u00adhyphen"
    assert evidence._normalize_text(raw) == (
        "scaling manufacturing Measurements softhyphen"
    )


def test_reference_claim_matches_after_pdf_control_normalization() -> None:
    page = evidence._normalize_text(
        "7. Weaver JS, Heigel JC, Lane BM (2022) Laser spot size and "
        "scal\x02ing laws for laser beam additive manu\x02facturing."
    )
    receipt = evidence._claim_receipt(
        "weaver",
        r"7\.\s*Weaver JS.*Heigel JC.*Lane BM.*Laser spot size and scaling laws for laser beam additive manufacturing",
        "fixture",
        [page],
    )
    assert receipt["matched"] is True
    assert receipt["match_count"] == 1
