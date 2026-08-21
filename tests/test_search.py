from indexcards.models.card import Card
from indexcards.search import matches


def _card(text: str = "", tags: list[str] | None = None) -> Card:
    return Card(id="c_1", text=text, tags=tags or [])


def test_empty_query_matches_everything():
    assert matches(_card(text="anything"), "") is True


def test_matches_text_case_insensitive():
    card = _card(text="A story about Time travel")
    assert matches(card, "time") is True
    assert matches(card, "TIME") is True
    assert matches(card, "story") is True


def test_matches_tag_case_insensitive():
    card = _card(text="unrelated", tags=["Plot", "urgent"])
    assert matches(card, "plot") is True
    assert matches(card, "URGENT") is True


def test_no_match_returns_false():
    card = _card(text="hello world", tags=["a", "b"])
    assert matches(card, "xyz") is False


def test_partial_substring_matches():
    card = _card(text="hello world")
    assert matches(card, "wor") is True
