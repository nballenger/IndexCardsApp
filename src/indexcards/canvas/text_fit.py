from __future__ import annotations

from PySide6.QtGui import QFont, QTextBlockFormat, QTextCursor, QTextDocument

_DEFAULT_DOCUMENT_MARGIN = 4.0  # Qt's own built-in QTextDocument default
_FONT_STEP = 1.0
_LINE_HEIGHT_STEPS: tuple[int, ...] = (90, 80, 70, 60)
_MARGIN_STEPS: tuple[float, ...] = (3.0, 2.0, 1.0, 0.0)
_FIT_TOLERANCE = 0.5  # px, matches the spirit of _SINGLE_LINE_HEIGHT_TOLERANCE


def _set_font_size(document: QTextDocument, size: float) -> None:
    font = QFont(document.defaultFont())
    font.setPointSizeF(size)
    document.setDefaultFont(font)


def _set_line_height(document: QTextDocument, percent: int) -> None:
    block_format = QTextBlockFormat()
    block_format.setLineHeight(percent, QTextBlockFormat.LineHeightTypes.ProportionalHeight.value)
    cursor = QTextCursor(document)
    cursor.select(QTextCursor.SelectionType.Document)
    cursor.mergeBlockFormat(block_format)


def _set_margin(document: QTextDocument, margin: float) -> None:
    document.setDocumentMargin(margin)


def _fits(document: QTextDocument, width: float, height: float) -> bool:
    size = document.size()
    return size.height() <= height + _FIT_TOLERANCE and size.width() <= width + _FIT_TOLERANCE


def reset_to_baseline(document: QTextDocument, max_font_size: float) -> None:
    """Resets font size, line height, and margin to the unshrunk
    baseline -- used both as fit_text_to_area's own starting point and,
    on its own, by CardItem.enter_edit_mode() so editing always presents
    the same stable, unshrunk view regardless of how the card's resting
    (committed) state currently renders."""
    _set_font_size(document, max_font_size)
    _set_line_height(document, 100)
    _set_margin(document, _DEFAULT_DOCUMENT_MARGIN)


def fit_text_to_area(
    document: QTextDocument,
    width: float,
    height: float,
    max_font_size: float,
    min_font_size: int,
) -> tuple[float, int, float]:
    """Shrinks document's default font size, then line spacing, then
    margin -- in that order, one lever at a time -- until it renders
    within (width, height) at its current textWidth() (the caller must
    already have called setTextWidth(width)). Always resets to the
    baseline (max_font_size, 100% line height, Qt's own default 4.0
    margin) before searching, so a document that no longer needs
    shrinking grows back rather than ratcheting down permanently across
    repeated calls on the same live QTextDocument. Returns the winning
    (font_size, line_height_percent, document_margin) tuple; if nothing
    fits even at every floor, returns the most-shrunk combination and
    leaves the document in that state -- residual overflow is expected
    to be handled by the caller clipping child items to the card shape,
    not by this function."""
    reset_to_baseline(document, max_font_size)

    font_size = max_font_size
    while font_size > min_font_size and not _fits(document, width, height):
        font_size = max(min_font_size, font_size - _FONT_STEP)
        _set_font_size(document, font_size)
    if _fits(document, width, height):
        return (font_size, 100, _DEFAULT_DOCUMENT_MARGIN)

    line_height = 100
    for step in _LINE_HEIGHT_STEPS:
        line_height = step
        _set_line_height(document, line_height)
        if _fits(document, width, height):
            return (font_size, line_height, _DEFAULT_DOCUMENT_MARGIN)

    margin = _DEFAULT_DOCUMENT_MARGIN
    for step in _MARGIN_STEPS:
        margin = step
        _set_margin(document, margin)
        if _fits(document, width, height):
            return (font_size, line_height, margin)

    return (font_size, line_height, margin)
