from __future__ import annotations

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QWidget

from indexcards.models.document import Document
from indexcards.models.theme import Slot
from indexcards.utils.color_icons import paint_color_swatch

_MARGIN = 12.0
_PADDING = 8.0
_SWATCH_SIZE = 14.0
_ROW_HEIGHT = 20.0
_ROW_GAP = 2.0
_TEXT_GAP = 6.0
_BACKGROUND = QColor(255, 255, 255, 230)


class ColorKeyOverlay(QWidget):
    """A floating, non-interactive, corner-anchored overlay listing every
    color currently in use on the board — including orphaned ones,
    hatched, since a card rendering hatched needs the same explanation as
    any other color. Visibility and content both track the active
    Document reactively; nothing here is ever set imperatively from
    outside besides which Document to watch and where the viewport is."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._document: Document | None = None
        self.hide()

    def set_document(self, document: Document | None) -> None:
        if self._document is not None:
            self._document.cardAdded.disconnect(self._refresh)
            self._document.cardRemoved.disconnect(self._refresh)
            self._document.cardChanged.disconnect(self._on_card_changed)
            self._document.themeChanged.disconnect(self._refresh)
            self._document.themeSlotChanged.disconnect(self._on_theme_slot_changed)
            self._document.colorKeyVisibleChanged.disconnect(self._on_visibility_changed)
        self._document = document
        if document is not None:
            document.cardAdded.connect(self._refresh)
            document.cardRemoved.connect(self._refresh)
            document.cardChanged.connect(self._on_card_changed)
            document.themeChanged.connect(self._refresh)
            document.themeSlotChanged.connect(self._on_theme_slot_changed)
            document.colorKeyVisibleChanged.connect(self._on_visibility_changed)
        self._refresh()

    def _on_card_changed(self, card_id: str, fields: frozenset[str]) -> None:
        if "color_slot" in fields:
            self._refresh()

    def _on_theme_slot_changed(self, slot_id: str) -> None:
        self._refresh()

    def _on_visibility_changed(self, visible: bool) -> None:
        self._refresh()

    def _entries(self) -> list[Slot]:
        """Every color slot at least one card currently uses — active
        slots in the theme's own order, then orphans after, matching the
        same ordering rule used for sorting and arrange-by-color."""
        if self._document is None:
            return []
        used_ids = {card.color_slot for card in self._document.iter_cards()}
        theme = self._document.theme
        ordered_ids = [slot.id for slot in theme.slots if not slot.orphaned and slot.id in used_ids]
        ordered_ids += [slot.id for slot in theme.slots if slot.orphaned and slot.id in used_ids]
        return [theme.get_slot(slot_id) for slot_id in ordered_ids]

    def _refresh(self) -> None:
        visible = self._document is not None and self._document.color_key_visible
        entries = self._entries() if visible else []
        if not entries:
            self.setVisible(False)
            self.resize(0, 0)
            return

        metrics = self.fontMetrics()
        text_width = max(metrics.horizontalAdvance(slot.label) for slot in entries)
        width = _PADDING * 2 + _SWATCH_SIZE + _TEXT_GAP + text_width
        height = _PADDING * 2 + len(entries) * _ROW_HEIGHT + (len(entries) - 1) * _ROW_GAP
        self.resize(int(width), int(height))
        self.setVisible(True)
        self._reposition()
        self.update()

    def _reposition(self) -> None:
        parent = self.parentWidget()
        if parent is None:
            return
        x = parent.width() - self.width() - _MARGIN
        y = parent.height() - self.height() - _MARGIN
        self.move(max(0, int(x)), max(0, int(y)))

    def reposition(self, viewport_size: QSize) -> None:
        """Called by CanvasView on resize — the overlay's own size only
        changes via _refresh(), but its anchor point depends on the
        viewport's size too, which only the view knows changed."""
        del viewport_size  # geometry is read fresh from parentWidget()
        self._reposition()

    def paintEvent(self, event) -> None:
        del event
        entries = self._entries()
        if not entries:
            return
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setBrush(_BACKGROUND)
            painter.setPen(Qt.GlobalColor.darkGray)
            painter.drawRoundedRect(self.rect().adjusted(0, 0, -1, -1), 6, 6)

            y = _PADDING
            for slot in entries:
                swatch_rect = QRectF(_PADDING, y, _SWATCH_SIZE, _SWATCH_SIZE)
                paint_color_swatch(painter, swatch_rect, slot.hex, orphaned=slot.orphaned)
                painter.setPen(Qt.GlobalColor.darkGray)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRect(swatch_rect)

                text_rect = QRectF(
                    _PADDING + _SWATCH_SIZE + _TEXT_GAP,
                    y,
                    self.width() - _PADDING - _SWATCH_SIZE - _TEXT_GAP,
                    _ROW_HEIGHT,
                )
                painter.setPen(Qt.GlobalColor.black)
                alignment = Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft
                painter.drawText(text_rect, alignment, slot.label)
                y += _ROW_HEIGHT + _ROW_GAP
        finally:
            painter.end()
