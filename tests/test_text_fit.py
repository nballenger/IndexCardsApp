from PySide6.QtGui import QTextDocument

from indexcards.canvas.text_fit import fit_text_to_area

_WIDTH = 184.0  # DEFAULT_CARD_SIZE width (200) minus 2 * _TEXT_MARGIN (8)
_HEIGHT = 104.0  # DEFAULT_CARD_SIZE height (120) minus 2 * _TEXT_MARGIN (8)
_MAX_FONT_SIZE = 13.0
_MIN_FONT_SIZE = 9


def _document(text: str) -> QTextDocument:
    document = QTextDocument()
    document.setPlainText(text)
    document.setTextWidth(_WIDTH)
    return document


def test_short_text_needs_no_shrink():
    document = _document("Hello world")

    result = fit_text_to_area(document, _WIDTH, _HEIGHT, _MAX_FONT_SIZE, _MIN_FONT_SIZE)

    assert result == (_MAX_FONT_SIZE, 100, 4.0)


def test_unbreakable_long_string_shrinks_font_only():
    document = _document("x" * 160)

    font_size, line_height, margin = fit_text_to_area(
        document, _WIDTH, _HEIGHT, _MAX_FONT_SIZE, _MIN_FONT_SIZE
    )

    assert font_size < _MAX_FONT_SIZE
    assert line_height == 100
    assert margin == 4.0
    assert document.size().height() <= _HEIGHT + 0.5
    assert document.size().width() <= _WIDTH + 0.5


def test_pathological_manual_paragraph_breaks_engage_all_three_tiers():
    text = "\n\n".join(f"Line {i}" for i in range(1, 9))
    document = _document(text)

    font_size, line_height, margin = fit_text_to_area(
        document, _WIDTH, _HEIGHT, _MAX_FONT_SIZE, _MIN_FONT_SIZE
    )

    assert font_size == _MIN_FONT_SIZE
    assert line_height < 100
    assert margin < 4.0


def test_respects_a_custom_minimum_font_size_floor():
    text = "x" * 160

    loose_font_size, _loose_line_height, _loose_margin = fit_text_to_area(
        _document(text), _WIDTH, _HEIGHT, _MAX_FONT_SIZE, min_font_size=6
    )
    tight_font_size, _tight_line_height, _tight_margin = fit_text_to_area(
        _document(text), _WIDTH, _HEIGHT, _MAX_FONT_SIZE, min_font_size=12
    )

    assert loose_font_size <= tight_font_size


def test_unrescuable_input_falls_back_to_most_shrunk_combination_without_raising():
    text = "\n\n".join(f"Paragraph {i} of many short lines" for i in range(1, 30))
    document = _document(text)

    font_size, line_height, margin = fit_text_to_area(
        document, _WIDTH, _HEIGHT, _MAX_FONT_SIZE, _MIN_FONT_SIZE
    )

    assert font_size == _MIN_FONT_SIZE
    assert line_height == 60
    assert margin == 0.0


def test_calling_again_after_shortening_text_returns_to_baseline():
    document = _document("x" * 160)
    shrunk = fit_text_to_area(document, _WIDTH, _HEIGHT, _MAX_FONT_SIZE, _MIN_FONT_SIZE)
    assert shrunk[0] < _MAX_FONT_SIZE

    document.setPlainText("Hi")
    result = fit_text_to_area(document, _WIDTH, _HEIGHT, _MAX_FONT_SIZE, _MIN_FONT_SIZE)

    assert result == (_MAX_FONT_SIZE, 100, 4.0)
