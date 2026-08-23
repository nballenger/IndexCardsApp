from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QAction,
    QColor,
    QCursor,
    QFont,
    QKeySequence,
    QPainter,
    QPen,
    QTextCharFormat,
    QTextCursor,
    QTextOption,
    QUndoStack,
)
from PySide6.QtWidgets import (
    QGraphicsItem,
    QGraphicsObject,
    QGraphicsSceneContextMenuEvent,
    QGraphicsSceneMouseEvent,
    QGraphicsTextItem,
    QInputDialog,
    QMenu,
    QStyleOptionGraphicsItem,
    QWidget,
)

from indexcards.commands.card_commands import (
    ChangeColorCommand,
    ChangeTagsCommand,
    EditCardTextCommand,
)
from indexcards.commands.move_commands import MoveCardCommand
from indexcards.feature_flags import TAGS_ENABLED
from indexcards.models.card import DEFAULT_CARD_SIZE
from indexcards.models.document import Document
from indexcards.models.palette import PALETTE
from indexcards.utils.color_icons import swatch_icon

_TEXT_MARGIN = 8
_CORNER_RADIUS = 0  # sharp corners, matching a real index card
_TAG_DOT_RADIUS = 5
_TAG_DOT_MARGIN = 6
_SINGLE_LINE_HEIGHT_TOLERANCE = 1.0


def _desaturated(color: QColor) -> QColor:
    """Gray at the same lightness as color — used to de-emphasize a card
    that doesn't match the current search, without making it transparent
    (transparency would let link lines show through its center)."""
    hue, _saturation, value, alpha = color.getHsv()
    return QColor.fromHsv(hue, 0, value, alpha)


class _CardTextItem(QGraphicsTextItem):
    """Child text item rendering a card's markdown text, and becoming
    directly editable in place. Not a QWidget, so it can't host a
    QShortcut — Cmd+B/Cmd+I are handled directly in keyPressEvent instead.
    """

    def __init__(self, on_focus_out: Callable[[], None], parent: QGraphicsItem) -> None:
        super().__init__(parent)
        self._on_focus_out = on_focus_out

    def focusOutEvent(self, event) -> None:
        super().focusOutEvent(event)
        self._on_focus_out()

    def keyPressEvent(self, event) -> None:
        if event.matches(QKeySequence.StandardKey.Bold):
            self._toggle_bold()
            event.accept()
            return
        if event.matches(QKeySequence.StandardKey.Italic):
            self._toggle_italic()
            event.accept()
            return
        if event.key() == Qt.Key.Key_Escape:
            self.clearFocus()  # triggers focusOutEvent, which commits
            event.accept()
            return
        super().keyPressEvent(event)

    def _toggle_bold(self) -> None:
        cursor = self.textCursor()
        is_bold = cursor.charFormat().fontWeight() == QFont.Weight.Bold
        fmt = QTextCharFormat()
        fmt.setFontWeight(QFont.Weight.Normal if is_bold else QFont.Weight.Bold)
        cursor.mergeCharFormat(fmt)
        self.setTextCursor(cursor)

    def _toggle_italic(self) -> None:
        cursor = self.textCursor()
        fmt = QTextCharFormat()
        fmt.setFontItalic(not cursor.charFormat().fontItalic())
        cursor.mergeCharFormat(fmt)
        self.setTextCursor(cursor)


class CardItem(QGraphicsObject):
    """Renders one Card at its stored position, and hosts its editing.

    Draggable only when constructed with an undo_stack: mouseReleaseEvent
    pushes a MoveCardCommand rather than leaving the moved position as
    view-only state, so a drag on the canvas persists and undoes the same
    way a list-view edit does. Text is edited in place: double-click (or
    an external enter_edit_mode() call, e.g. right after creation) swaps
    the child text item into an editable state; losing focus commits the
    change as an EditCardTextCommand on the same shared undo stack. Color
    is edited via a right-click context menu (tag editing lives there too,
    gated behind feature_flags.TAGS_ENABLED).
    """

    def __init__(
        self,
        card_id: str,
        document: Document,
        undo_stack: QUndoStack | None = None,
        parent: QGraphicsItem | None = None,
    ) -> None:
        super().__init__(parent)
        self.card_id = card_id
        self._document = document
        self._undo_stack = undo_stack
        self._press_pos: tuple[float, float] | None = None
        self._position_listeners: list[Callable[[], None]] = []
        self._dimmed = False
        self._editing = False
        self._link_mode_active = False

        flags = (
            QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            | QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
            | QGraphicsItem.GraphicsItemFlag.ItemClipsChildrenToShape
        )
        if undo_stack is not None:
            flags |= QGraphicsItem.GraphicsItemFlag.ItemIsMovable
        self.setFlags(flags)

        width, _height = DEFAULT_CARD_SIZE
        self._text_item = _CardTextItem(self._on_text_focus_out, self)
        self._text_item.setPos(_TEXT_MARGIN, _TEXT_MARGIN)
        self._text_item.setTextWidth(width - 2 * _TEXT_MARGIN)
        self._text_item.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        self._text_item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self._sync_text_item()
        self._sync_tooltip()

    def boundingRect(self) -> QRectF:
        width, height = DEFAULT_CARD_SIZE
        return QRectF(0, 0, width, height)

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionGraphicsItem,
        widget: QWidget | None = None,
    ) -> None:
        card = self._document.get_card(self.card_id)
        rect = self.boundingRect()

        fill_color = QColor(card.color)
        if self._dimmed:
            fill_color = _desaturated(fill_color)

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(fill_color)
        pen_width = 2 if self.isSelected() else 1
        pen_color = Qt.GlobalColor.black if self.isSelected() else Qt.GlobalColor.darkGray
        painter.setPen(QPen(pen_color, pen_width))
        painter.drawRoundedRect(rect, _CORNER_RADIUS, _CORNER_RADIUS)
        painter.restore()

        if TAGS_ENABLED and card.tags:
            self._paint_tag_indicator(painter, rect)

    def refresh(self) -> None:
        if not self._editing:
            self._sync_text_item()
        self._sync_tooltip()
        self.update()

    def _paint_tag_indicator(self, painter: QPainter, rect: QRectF) -> None:
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QColor(90, 90, 90))
        painter.setPen(Qt.PenStyle.NoPen)
        center = QPointF(
            rect.right() - _TAG_DOT_MARGIN - _TAG_DOT_RADIUS,
            rect.top() + _TAG_DOT_MARGIN + _TAG_DOT_RADIUS,
        )
        painter.drawEllipse(center, _TAG_DOT_RADIUS, _TAG_DOT_RADIUS)
        painter.restore()

    def _sync_tooltip(self) -> None:
        card = self._document.get_card(self.card_id)
        self.setToolTip(", ".join(card.tags) if TAGS_ENABLED else "")

    def set_dimmed(self, dimmed: bool) -> None:
        if dimmed == self._dimmed:
            return
        self._dimmed = dimmed
        self.update()

    def add_position_listener(self, callback: Callable[[], None]) -> None:
        self._position_listeners.append(callback)

    def remove_position_listener(self, callback: Callable[[], None]) -> None:
        if callback in self._position_listeners:
            self._position_listeners.remove(callback)

    def itemChange(self, change: QGraphicsItem.GraphicsItemChange, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            for listener in self._position_listeners:
                listener()
        elif change == QGraphicsItem.GraphicsItemChange.ItemSelectedHasChanged:
            self._refresh_cursor()
        return super().itemChange(change, value)

    def set_link_mode_active(self, active: bool) -> None:
        self._link_mode_active = active
        self._refresh_cursor()

    def _refresh_cursor(self) -> None:
        """Shows a grab-hand cursor while hovering a selected, draggable
        card (Qt applies an item's cursor automatically on hover, no
        explicit hover-event handling needed) — or a crosshair whenever
        Link Mode is active, since dragging is impossible then regardless
        of selection (CanvasView routes every press to the link-drawing
        controller first while Link Mode is on, never reaching this
        item). Grab-hand is gated on ItemIsMovable rather than just
        self._undo_stack, since that flag is also temporarily cleared
        while the card is being text-edited — a grab cursor would be
        misleading there, since the card can't be dragged until editing
        ends."""
        if self._link_mode_active:
            self.setCursor(QCursor(Qt.CursorShape.CrossCursor))
        elif self.isSelected() and bool(
            self.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsMovable
        ):
            self.setCursor(QCursor(Qt.CursorShape.OpenHandCursor))
        else:
            self.unsetCursor()

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if self._editing:
            # A press elsewhere on the card (outside the text item's own
            # rect) doesn't otherwise steal focus from it — commit and
            # drop out of edit mode before falling through to normal
            # select/drag handling.
            self._text_item.clearFocus()
        if self._undo_stack is not None:
            self._press_pos = (self.pos().x(), self.pos().y())
        super().mousePressEvent(event)
        # After super(), since a plain click on a previously-unselected item
        # selects it as a side effect of that call — which would otherwise
        # leave the grab-hand (not grab-and-close) cursor showing. Never
        # actually reached in the real app while Link Mode is active (see
        # _refresh_cursor), but guarded anyway for direct callers (tests).
        if (
            self._undo_stack is not None
            and event.button() == Qt.MouseButton.LeftButton
            and not self._link_mode_active
        ):
            self.setCursor(QCursor(Qt.CursorShape.ClosedHandCursor))

    def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        super().mouseReleaseEvent(event)
        if event.button() == Qt.MouseButton.LeftButton:
            self._refresh_cursor()
        if self._undo_stack is None or self._press_pos is None:
            return
        old_pos = self._press_pos
        self._press_pos = None
        new_pos = (self.pos().x(), self.pos().y())
        if new_pos != old_pos:
            self._undo_stack.push(MoveCardCommand(self._document, self.card_id, old_pos, new_pos))

    def mouseDoubleClickEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        self.enter_edit_mode()
        event.accept()

    def enter_edit_mode(self) -> None:
        """Swaps the text item into an editable state, selecting all its
        text (so a brand-new card's placeholder text is replaced by the
        first keystroke, and an existing card's text can be typed over or
        clicked into to reposition the cursor)."""
        if self._undo_stack is None or self._editing:
            return
        self._editing = True
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
        self._refresh_cursor()
        # Editing always shows the plain top-left/left-aligned layout,
        # regardless of how this card renders (possibly centered) when not
        # being edited — _apply_rendered_layout() restores the real layout
        # once editing ends.
        document = self._text_item.document()
        option = document.defaultTextOption()
        option.setAlignment(Qt.AlignmentFlag.AlignLeft)
        document.setDefaultTextOption(option)
        self._text_item.setPos(_TEXT_MARGIN, _TEXT_MARGIN)
        self._text_item.setTextInteractionFlags(Qt.TextInteractionFlag.TextEditorInteraction)
        self._text_item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsFocusable, True)
        self._text_item.setAcceptedMouseButtons(Qt.MouseButton.LeftButton)
        cursor = self._text_item.textCursor()
        cursor.select(QTextCursor.SelectionType.Document)
        self._text_item.setTextCursor(cursor)
        if self.scene() is not None and self.scene().views():
            self.scene().views()[0].setFocus()
        self._text_item.setFocus(Qt.FocusReason.MouseFocusReason)

    def _on_text_focus_out(self) -> None:
        self._editing = False
        self._text_item.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        self._text_item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsFocusable, False)
        self._text_item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        if self._undo_stack is not None:
            self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
            self._refresh_cursor()
        self._commit_text()
        # Unconditional (not just when _commit_text() actually pushed a
        # command): a no-op edit — enter edit mode, change nothing, click
        # away — still needs its rendered layout restored, since nothing
        # changed to trigger the cardChanged -> refresh() path below.
        self._apply_rendered_layout()

    def _commit_text(self) -> None:
        if not self._text_item.document().isModified():
            return
        if self.card_id not in self._document.cards:
            return
        new_text = self._text_item.document().toMarkdown()
        old_text = self._document.get_card(self.card_id).text
        if new_text != old_text:
            self._undo_stack.push(
                EditCardTextCommand(self._document, self.card_id, old_text, new_text)
            )
        self._text_item.document().setModified(False)

    def contextMenuEvent(self, event: QGraphicsSceneContextMenuEvent) -> None:
        if self._undo_stack is None:
            event.ignore()
            return
        menu, edit_tags_action, select_linked_action, color_actions = self._build_context_menu()
        chosen = menu.exec(event.screenPos())
        if edit_tags_action is not None and chosen is edit_tags_action:
            self._edit_tags_via_dialog()
        elif chosen is select_linked_action:
            self.select_linked_graph()
        elif chosen in color_actions:
            self._set_color(color_actions[chosen])

    def _build_context_menu(
        self,
    ) -> tuple[QMenu, QAction | None, QAction, dict[QAction, str]]:
        """Builds the menu without exec()'ing it, so tests can inspect its
        contents without triggering a real, blocking modal popup."""
        card = self._document.get_card(self.card_id)

        menu = QMenu()
        select_linked_action = menu.addAction("Select Linked")
        has_links = any(
            self.card_id in (link.source, link.target)
            for link in self._document.links.values()
        )
        select_linked_action.setEnabled(has_links)
        menu.addSeparator()
        edit_tags_action = menu.addAction("Edit Tags…") if TAGS_ENABLED else None
        color_menu = menu.addMenu("Color")
        color_actions = {}
        for name, hex_value in PALETTE.items():
            action = color_menu.addAction(swatch_icon(hex_value), name)
            action.setCheckable(True)
            action.setChecked(hex_value.lower() == card.color.lower())
            color_actions[action] = hex_value

        return menu, edit_tags_action, select_linked_action, color_actions

    def select_linked_graph(self, union: bool = False) -> None:
        """Selects this card plus every card transitively linked to it. By
        default replaces the current selection; with union=True, adds the
        linked graph to whatever is already selected instead."""
        scene = self.scene()
        if scene is None:
            return
        graph_ids = self._document.connected_card_ids(self.card_id)
        if not union:
            scene.clearSelection()
        for item in scene.items():
            if isinstance(item, CardItem) and item.card_id in graph_ids:
                item.setSelected(True)

    def _edit_tags_via_dialog(self) -> None:
        card = self._document.get_card(self.card_id)
        parent_widget = self.scene().views()[0] if self.scene() and self.scene().views() else None
        text, ok = QInputDialog.getText(
            parent_widget, "Edit Tags", "Tags (comma-separated):", text=", ".join(card.tags)
        )
        if not ok:
            return
        new_tags = [tag.strip() for tag in text.split(",") if tag.strip()]
        if new_tags == card.tags:
            return
        self._undo_stack.push(ChangeTagsCommand(self._document, self.card_id, card.tags, new_tags))

    def _set_color(self, new_color: str) -> None:
        old_color = self._document.get_card(self.card_id).color
        if new_color.lower() == old_color.lower():
            return
        self._undo_stack.push(
            ChangeColorCommand(self._document, self.card_id, old_color, new_color)
        )

    def _sync_text_item(self) -> None:
        card = self._document.get_card(self.card_id)
        self._text_item.document().setMarkdown(card.text)
        self._text_item.document().setModified(False)
        self._apply_rendered_layout()

    def _renders_as_single_line(self) -> bool:
        """True if this card's text, laid out at the card's actual text
        width, comes out as exactly one visual line — i.e. word-wrap
        didn't add a line, and there's no explicit line break. Qt's
        QTextDocument.lineCount() can't answer this directly: it only
        reflects QPlainTextDocumentLayout, not the rich-text layout
        setMarkdown() uses, so a wrapped paragraph still reports 1.
        Comparing rendered height at the real width against unlimited
        width catches word-wrap; blockCount() catches an explicit break
        (which produces equal heights at both widths, since a hard break
        persists regardless of width)."""
        document = self._text_item.document()
        if document.blockCount() != 1:
            return False
        current_width = self._text_item.textWidth()
        wrapped_height = document.size().height()
        document.setTextWidth(-1)
        unwrapped_height = document.size().height()
        document.setTextWidth(current_width)  # restore — other code relies on it staying set
        return abs(wrapped_height - unwrapped_height) < _SINGLE_LINE_HEIGHT_TOLERANCE

    def _apply_rendered_layout(self) -> None:
        """Centers the text item both horizontally and vertically when its
        text renders as exactly one visual line. Only meaningful outside
        of active editing — enter_edit_mode() resets to the plain
        top-left/left-aligned editing view regardless of this, and
        restores it again on exit."""
        single_line = self._renders_as_single_line()
        document = self._text_item.document()
        option = document.defaultTextOption()
        option.setAlignment(
            Qt.AlignmentFlag.AlignHCenter if single_line else Qt.AlignmentFlag.AlignLeft
        )
        document.setDefaultTextOption(option)

        _width, height = DEFAULT_CARD_SIZE
        y = _TEXT_MARGIN
        if single_line:
            content_height = document.size().height()
            y = max(_TEXT_MARGIN, (height - content_height) / 2)
        self._text_item.setPos(_TEXT_MARGIN, y)
