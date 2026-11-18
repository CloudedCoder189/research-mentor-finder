from services.recommendations import _snippet

def test_reason_excerpt_keeps_late_matching_phrase():
    text = "Earlier research and unrelated methods. " * 10 + "Environmental policy analysis and regional water systems."
    excerpt = _snippet({"research_interests": text}, "fallback", "Environmental policy")
    assert "Environmental policy" in excerpt
    assert len(excerpt) <= 142
    assert excerpt.startswith("…")

def test_missing_focus_does_not_fabricate_evidence():
    assert _snippet({"research_interests": "Recorded robotics research"}, "fallback", "biology") == "Recorded robotics research"
