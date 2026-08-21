from indexcards.models.card import DEFAULT_CARD_SIZE, Card
from indexcards.models.palette import DEFAULT_COLOR, PALETTE


def test_default_card_size_is_5_by_3_ratio():
    width, height = DEFAULT_CARD_SIZE
    assert width / height == 5 / 3


def test_default_card_color_is_white():
    assert DEFAULT_COLOR == "#FFFFFF"
    assert PALETTE["White"] == "#FFFFFF"


def test_new_card_defaults_to_white():
    card = Card(id="c_1")
    assert card.color == "#FFFFFF"
