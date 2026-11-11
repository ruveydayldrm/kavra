from kavra.pipeline.schemas import QuestionDraft
from kavra.pipeline.verify import locate_quote, normalize, structural_issues

EXCERPT = "İnsülin pankreastaki beta hücreleri tarafından üretilir.\nGlukagon ise alfa hücrelerinden salgılanır ve kan şekerini yükseltir."


def q(**kw):
    base = dict(
        type="mcq",
        difficulty="easy",
        stem="İnsülini hangi hücreler üretir?",
        options=["beta", "alfa", "delta", "gama"],
        correct_index=0,
        answer="beta",
        accepted=[],
        key_points=[],
        explanation="x",
        source_quote="İnsülin pankreastaki beta hücreleri tarafından üretilir.",
    )
    base.update(kw)
    return QuestionDraft(**base)


def test_exact_quote_found_with_offsets():
    m = locate_quote(EXCERPT, "insülin pankreastaki beta hücreleri tarafından üretilir.")
    assert m and m.score == 100.0
    assert EXCERPT[m.start : m.end].startswith("İnsülin")


def test_fuzzy_quote_survives_quote_style_and_spacing():
    m = locate_quote(
        EXCERPT, "Glukagon ise  alfa hücrelerinden salgılanır ve kan şekerini yükseltir"
    )
    assert m is not None


def test_fabricated_quote_rejected():
    assert (
        locate_quote(
            EXCERPT, "Tiroid bezi metabolizma hızını düzenleyen tiroksin hormonunu salgılar."
        )
        is None
    )


def test_too_short_quote_rejected():
    assert locate_quote(EXCERPT, "beta") is None


def test_turkish_dotted_i_normalisation_keeps_length():
    t = "İSTANBUL ışık"
    assert normalize(t) == "istanbul ışık"


def test_mcq_answer_index_repaired_from_text():
    # models get the answer text right more often than the index (off-by-one) -> text wins
    fixed, issues = structural_issues(q(correct_index=0, answer="delta"), EXCERPT)
    assert not issues
    assert fixed.correct_index == 2 and fixed.answer == "delta"
    # answer text matches nothing -> index wins, answer rewritten
    fixed, _ = structural_issues(q(correct_index=1, answer="???"), EXCERPT)
    assert fixed.answer == "alfa"


def test_mcq_needs_four_unique_options():
    _, issues = structural_issues(q(options=["beta", "beta", "alfa", "gama"]), EXCERPT)
    assert "duplicate options" in issues
    _, issues = structural_issues(q(options=["beta", "alfa"]), EXCERPT)
    assert any("4 options" in i for i in issues)


def test_tf_answer_normalised():
    fixed, issues = structural_issues(
        q(type="tf", options=[], correct_index=-1, answer="Doğru"), EXCERPT
    )
    assert not issues and fixed.answer == "true"


def test_cloze_requires_blank_and_answer_in_text():
    _, issues = structural_issues(
        q(
            type="cloze",
            stem="İnsülin pankreastaki hücrelerden üretilir.",
            answer="beta",
            options=[],
        ),
        EXCERPT,
    )
    assert "cloze stem has no blank" in issues
    fixed, issues = structural_issues(
        q(type="cloze", stem="İnsülin ___ hücrelerinden üretilir.", answer="beta", options=[]),
        EXCERPT,
    )
    assert not issues and "____" in fixed.stem
    _, issues = structural_issues(
        q(type="cloze", stem="İnsülin ____ üretilir.", answer="karaciğer", options=[]), EXCERPT
    )
    assert "cloze answer not in excerpt" in issues


def test_open_needs_key_points():
    _, issues = structural_issues(q(type="open", options=[], key_points=["tek"]), EXCERPT)
    assert issues
