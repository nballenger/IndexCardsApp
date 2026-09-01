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
    QUndoStack,
)
from PySide6.QtWidgets import (
    QDialog,
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

from indexcards.arrange.auto_arrange import positions_bbox
from indexcards.canvas.stack_item import StackItem
from indexcards.commands.card_commands import (
    ChangeColorCommand,
    ChangeTagsCommand,
    EditCardTextCommand,
    TogglePinCommand,
)
from indexcards.commands.move_commands import MoveCardCommand, MoveCardsCommand
from indexcards.commands.stack_commands import AddCardsToStackCommand, CreateStackCommand
from indexcards.feature_flags import TAGS_ENABLED
from indexcards.models.card import DEFAULT_CARD_SIZE, MAX_TEXT_LENGTH
from indexcards.models.document import Document
from indexcards.models.stack import Stack
from indexcards.utils.color_icons import paint_color_swatch, swatch_icon
from indexcards.utils.contrast import auto_text_color
from indexcards.utils.ids import new_stack_id
from indexcards.utils.text_limit import enforce_char_limit
from indexcards.widgets.stack_dialogs import (
    CreateStackPromptDialog,
    confirm_add_all_to_stack,
    prompt_optional_stack_label,
)

_TEXT_MARGIN = 8
_CORNER_RADIUS = 0  # sharp corners, matching a real index card
_TAG_DOT_RADIUS = 5
_TAG_DOT_MARGIN = 6
_PIN_ICON_RADIUS = 4
_PIN_ICON_MARGIN = 7
_PIN_ICON_NEEDLE_LENGTH = 6
_SINGLE_LINE_HEIGHT_TOLERANCE = 1.0


def _desaturated(color: QColor) -> QColor:
    """Gray at the same lightness as color — used to de-emphasize a card
    that doesn't match the current search, without making it transparent
    (transparency would let link lines show through its center)."""
    hue, _saturation, value, alpha = color.getHsv()
    return QColor.fromHsv(hue, 0, value, alpha)


_DIMMED_TEXT_VALUE = 0x99  # #999999 -- legible but no longer eye-catching


def _dimmed_text_color(color: QColor) -> QColor:
    """auto_text_color() only ever returns pure black or white, which
    already have zero saturation — running those through _desaturated()
    (which only strips saturation, keeping lightness) would be a
    complete no-op, not the "notably less saturated but still readable"
    look a dimmed card's text needs. Instead, both converge on the same
    fixed mid-gray (rather than each blending partway toward the other,
    which left black text reading as too dark) — zeroing saturation also
    covers the rarer case of a custom, actually-colored text_color
    override, landing it at the same gray regardless of its original
    hue."""
    hue, _saturation, _value, alpha = color.getHsv()
    return QColor.fromHsv(hue, 0, _DIMMED_TEXT_VALUE, alpha)


def _center_quartile_contains(rect: QRectF, point: QPointF) -> bool:
    """True if point falls within the central 50%-width x 50%-height
    sub-rectangle of rect (rect inset by 25% of its width on left/right
    and 25% of its height on top/bottom) — the "center quartile" a card
    must be dropped into to trigger the new-stack prompt."""
    inset_x = rect.width() * 0.25
    inset_y = rect.height() * 0.25
    return rect.adjusted(inset_x, inset_y, -inset_x, -inset_y).contains(point)


class _CardTextItem(QGraphicsTextItem):
    """Child text item rendering a card's markdown text, and becoming
    directly editable in place. Not a QWidget, so it can't host a
    QShortcut — Cmd+B/Cmd+I are handled directly in keyPressEvent instead.
    """

    def __init__(self, on_focus_out: Callable[[], None], parent: QGraphicsItem) -> None:
        super().__init__(parent)
        self._on_focus_out = on_focus_out

    def boundingRect(self) -> QRectF:
        """Wider than QGraphicsTextItem's own content-sized default —
        spans the card's ENTIRE area, edge to edge, not just the
        rendered text. While a card holds only short text (e.g. the
        default "New Card 1"), the natural bounding rect only covers a
        thin sliver near the top of the card; a press anywhere else in
        the card — still well within it, nowhere near "clicking away" —
        would otherwise miss this child item and land on the parent
        CardItem instead, which (via Qt's own scene-level mouse-press
        focus handling, before CardItem.mousePressEvent even runs) ends
        editing right out from under the user.

        This item is positioned at (_TEXT_MARGIN, _TEXT_MARGIN) relative
        to its parent CardItem, so to reach every point of the card's own
        (0, 0)-(width, height) rect — leaving no dead zone at all, not
        even a thin one at the outer edge — this item's own local rect
        must extend from (-_TEXT_MARGIN, -_TEXT_MARGIN) to
        (width - _TEXT_MARGIN, height - _TEXT_MARGIN)."""
        width, height = DEFAULT_CARD_SIZE
        full_card_area = QRectF(-_TEXT_MARGIN, -_TEXT_MARGIN, width, height)
        return super().boundingRect().united(full_card_area)

    def focusOutEvent(self, event) -> None:
        super().focusOutEvent(event)
        if event.reason() == Qt.FocusReason.ActiveWindowFocusReason:
            # The containing view/window merely blipped in or out of
            # OS-level "active" status — most commonly, macOS completing
            # a window's activation handshake asynchronously right after
            # a double-click creates a card and enters edit mode, which
            # can arrive as late as the very next event (often the next
            # mouse move). QGraphicsView propagates that as a genuine
            # focusOutEvent here, with this same reason, even though the
            # user never clicked away or pressed Escape — committing in
            # response would silently kick them out of editing a brand
            # new, untouched card. A real "user backed out" (click
            # elsewhere, Escape) always arrives as OtherFocusReason,
            # which still commits normally below.
            return
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
        movable: bool = True,
    ) -> None:
        super().__init__(parent)
        self.card_id = card_id
        self._document = document
        self._undo_stack = undo_stack
        # Independent of undo_stack: a caller (e.g. StackOverlay) may want a
        # fully editable CardItem — real undo_stack, working context menu —
        # that still must never be draggable, because its pos() lives in a
        # coordinate space (an overlay's own grid scene) that isn't the
        # canvas, and a drag there must never be mistaken for a real
        # MoveCardCommand. See also _on_text_focus_out, which re-arms this
        # same gate after an edit session ends.
        self._movable = movable and undo_stack is not None
        self._press_pos: tuple[float, float] | None = None
        self._drag_group_ids: list[str] | None = None
        self._drag_group_old_positions: dict[str, tuple[float, float]] | None = None
        self._position_listeners: list[Callable[[], None]] = []
        self._dimmed = False
        self._editing = False
        self._link_mode_active = False
        self._char_limit_slot: Callable[[int, int, int], None] | None = None

        flags = (
            QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            | QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
            | QGraphicsItem.GraphicsItemFlag.ItemClipsChildrenToShape
        )
        if self._movable:
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

    @property
    def is_editing(self) -> bool:
        return self._editing

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

        slot = self._document.get_slot(card.color_slot)
        fill_color = QColor(slot.hex)
        if self._dimmed:
            fill_color = _desaturated(fill_color)

        painter.save()
        paint_color_swatch(painter, rect, fill_color.name(), orphaned=slot.orphaned)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen_width = 2 if self.isSelected() else 1
        pen_color = Qt.GlobalColor.black if self.isSelected() else Qt.GlobalColor.darkGray
        painter.setPen(QPen(pen_color, pen_width))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(rect, _CORNER_RADIUS, _CORNER_RADIUS)
        painter.restore()

        if TAGS_ENABLED and card.tags:
            self._paint_tag_indicator(painter, rect)

        if card.pinned:
            self._paint_pin_indicator(painter, rect)

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

    def _paint_pin_indicator(self, painter: QPainter, rect: QRectF) -> None:
        """A small thumbtack glyph (a round head plus a short needle) in
        the top-left corner — the tag dot above lives in the top-right,
        so the two indicators never collide."""
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        head_center = QPointF(
            rect.left() + _PIN_ICON_MARGIN + _PIN_ICON_RADIUS,
            rect.top() + _PIN_ICON_MARGIN + _PIN_ICON_RADIUS,
        )
        painter.setPen(QPen(QColor(120, 20, 20), 1.5))
        painter.drawLine(
            head_center,
            QPointF(head_center.x(), head_center.y() + _PIN_ICON_NEEDLE_LENGTH),
        )
        painter.setBrush(QColor(200, 60, 60))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(head_center, _PIN_ICON_RADIUS, _PIN_ICON_RADIUS)
        painter.restore()

    def _sync_tooltip(self) -> None:
        card = self._document.get_card(self.card_id)
        self.setToolTip(", ".join(card.tags) if TAGS_ENABLED else "")

    def set_dimmed(self, dimmed: bool) -> None:
        if dimmed == self._dimmed:
            return
        self._dimmed = dimmed
        self._apply_text_color()
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
            # Captured before super() (which may change selection as a
            # side effect of this press) so this reflects the selection as
            # it stood going into the drag — "was this card already part
            # of a multi-selection?" — matching how
            # _selection_scoped_card_ids is meant to be read elsewhere.
            self._drag_group_ids = self._selection_scoped_card_ids()
            self._drag_group_old_positions = {
                card_id: (self._document.get_card(card_id).x, self._document.get_card(card_id).y)
                for card_id in self._drag_group_ids
            }
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
        drag_group_ids = self._drag_group_ids or [self.card_id]
        drag_group_old_positions = self._drag_group_old_positions or {self.card_id: old_pos}
        self._drag_group_ids = None
        self._drag_group_old_positions = None

        new_pos = (self.pos().x(), self.pos().y())
        if new_pos == old_pos:
            return
        if len(drag_group_ids) <= 1:
            self._finish_single_card_drag(event, old_pos, new_pos)
        else:
            self._finish_multi_card_drag(event, drag_group_ids, drag_group_old_positions)

    def _finish_single_card_drag(
        self,
        event: QGraphicsSceneMouseEvent,
        old_pos: tuple[float, float],
        new_pos: tuple[float, float],
    ) -> None:
        target = self._resolve_drop_target(event.scenePos(), {self.card_id})
        parent_widget = self.scene().views()[0] if self.scene() and self.scene().views() else None

        if isinstance(target, StackItem):
            self._undo_stack.push(
                AddCardsToStackCommand(self._document, target.stack_id, [self.card_id])
            )
            return

        if isinstance(target, CardItem):
            target_rect = target.mapRectToScene(target.boundingRect())
            if _center_quartile_contains(target_rect, event.scenePos()):
                dialog = CreateStackPromptDialog(
                    "Create a stack containing both cards?", parent_widget
                )
                if dialog.exec() == QDialog.DialogCode.Accepted:
                    target_card = self._document.get_card(target.card_id)
                    new_stack = Stack(
                        id=new_stack_id(self._document.stacks.keys()),
                        x=target_card.x,
                        y=target_card.y,
                        label=dialog.label(),
                    )
                    self._undo_stack.push(
                        CreateStackCommand(
                            self._document, new_stack, [target.card_id, self.card_id]
                        )
                    )
                    return

        self._undo_stack.push(MoveCardCommand(self._document, self.card_id, old_pos, new_pos))

    def _finish_multi_card_drag(
        self,
        event: QGraphicsSceneMouseEvent,
        drag_group_ids: list[str],
        old_positions: dict[str, tuple[float, float]],
    ) -> None:
        scene = self.scene()
        group_ids = set(drag_group_ids)
        new_positions = {}
        if scene is not None:
            for other in scene.items():
                if isinstance(other, CardItem) and other.card_id in group_ids:
                    new_positions[other.card_id] = (other.pos().x(), other.pos().y())

        target = self._resolve_drop_target(event.scenePos(), group_ids)
        if isinstance(target, StackItem):
            parent_widget = (
                self.scene().views()[0] if self.scene() and self.scene().views() else None
            )
            stack = self._document.get_stack(target.stack_id)
            if confirm_add_all_to_stack(parent_widget, stack.label):
                self._undo_stack.push(
                    AddCardsToStackCommand(self._document, target.stack_id, drag_group_ids)
                )
                return

        self._undo_stack.push(MoveCardsCommand(self._document, old_positions, new_positions))

    def _resolve_drop_target(
        self, scene_pos: QPointF, exclude_card_ids: set[str]
    ) -> CardItem | StackItem | None:
        """Whatever CardItem or StackItem is under scene_pos, other than
        this item itself or any card in exclude_card_ids (the whole drag
        group) — walking each raw hit up to its nearest CardItem/StackItem
        ancestor, since a hit may land on a child item (e.g. a card's own
        text item) rather than the card/stack item itself."""
        scene = self.scene()
        if scene is None:
            return None
        for item in scene.items(scene_pos):
            node = item
            while node is not None and not isinstance(node, (CardItem, StackItem)):
                node = node.parentItem()
            if isinstance(node, CardItem) and node.card_id in exclude_card_ids:
                continue
            if isinstance(node, (CardItem, StackItem)):
                return node
        return None

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
        # Scoped to the edit session (connected here, disconnected in
        # _on_text_focus_out) rather than for the document's whole
        # lifetime — otherwise merely loading/displaying a card whose
        # stored text is already over the limit (e.g. from a file saved
        # before this limit existed) would silently clip it.
        self._char_limit_slot = enforce_char_limit(document, MAX_TEXT_LENGTH)
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
        if self._char_limit_slot is not None:
            self._text_item.document().contentsChange.disconnect(self._char_limit_slot)
            self._char_limit_slot = None
        self._text_item.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        self._text_item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsFocusable, False)
        self._text_item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        if self._movable:
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
        (
            menu,
            edit_tags_action,
            select_linked_action,
            pin_action,
            color_actions,
            new_stack_action,
            stack_actions,
        ) = self._build_context_menu()
        chosen = menu.exec(event.screenPos())
        if edit_tags_action is not None and chosen is edit_tags_action:
            self._edit_tags_via_dialog()
        elif chosen is select_linked_action:
            self.select_linked_graph()
        elif chosen is pin_action:
            self._toggle_pin()
        elif chosen in color_actions:
            self._set_color_slot(color_actions[chosen])
        elif new_stack_action is not None and chosen is new_stack_action:
            self._create_new_stack_via_menu()
        elif chosen in stack_actions:
            self._add_to_existing_stack(stack_actions[chosen])

    def _selection_scoped_card_ids(self) -> list[str]:
        """The cards an action from this card's context menu (pin/unpin,
        Cmd-Shift-P/Edit menu, or Add to Stack) should apply to: the whole
        current selection if this card is part of one, otherwise just
        this card — matching the common multi-select convention of
        right-click acting on the whole selection when you right-click
        something already selected in it."""
        scene = self.scene()
        if scene is not None and self.isSelected():
            selected_ids = [
                item.card_id for item in scene.selectedItems() if isinstance(item, CardItem)
            ]
            if self.card_id in selected_ids:
                return selected_ids
        return [self.card_id]

    def _toggle_pin(self) -> None:
        target_ids = self._selection_scoped_card_ids()
        pin = not self._document.all_pinned(target_ids)
        self._undo_stack.push(TogglePinCommand(self._document, target_ids, pin))

    def _build_context_menu(
        self,
    ) -> tuple[
        QMenu,
        QAction | None,
        QAction,
        QAction,
        dict[QAction, str],
        QAction | None,
        dict[QAction, str],
    ]:
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

        target_ids = self._selection_scoped_card_ids()
        verb = "Unpin" if self._document.all_pinned(target_ids) else "Pin"
        noun = "Card" if len(target_ids) == 1 else "Cards"
        pin_action = menu.addAction(f"{verb} {noun}")

        menu.addSeparator()
        edit_tags_action = menu.addAction("Edit Tags…") if TAGS_ENABLED else None
        color_menu = menu.addMenu("Color")
        color_actions = {}
        for slot in self._document.theme.slots:
            if slot.orphaned:
                continue
            action = color_menu.addAction(swatch_icon(slot.hex), slot.label)
            action.setCheckable(True)
            action.setChecked(slot.id == card.color_slot)
            color_actions[action] = slot.id

        # A CardItem on the main canvas always has card.stack_id is None
        # (see CanvasScene._add_item_for_card's guard) — but a StackOverlay
        # tile is a real CardItem for a card that IS already stacked, so
        # this submenu must stay hidden there: add_cards_to_stack only sets
        # the new stack_id, it never removes the card from its previous
        # stack's card_ids, which would leave a stale member reference.
        new_stack_action: QAction | None = None
        stack_actions: dict[QAction, str] = {}
        if card.stack_id is None:
            stack_menu = menu.addMenu("Add to Stack")
            new_stack_action = stack_menu.addAction("New Stack...")
            if self._document.stacks:
                stack_menu.addSeparator()
                for stack in self._document.iter_stacks():
                    label = stack.label or f"Stack ({len(stack.card_ids)} cards)"
                    action = stack_menu.addAction(label)
                    stack_actions[action] = stack.id

        return (
            menu,
            edit_tags_action,
            select_linked_action,
            pin_action,
            color_actions,
            new_stack_action,
            stack_actions,
        )

    def _create_new_stack_via_menu(self) -> None:
        """New Stack position: the single target card's own position, or
        (for a multi-selection) the center of its bounding box minus half
        a card's footprint, so the new Stack symbol lands roughly where
        the selection was rather than at one arbitrary member's spot."""
        target_ids = self._selection_scoped_card_ids()
        parent_widget = self.scene().views()[0] if self.scene() and self.scene().views() else None
        label = prompt_optional_stack_label(parent_widget)
        stack_id = new_stack_id(self._document.stacks.keys())
        if len(target_ids) == 1:
            target_card = self._document.get_card(target_ids[0])
            x, y = target_card.x, target_card.y
        else:
            positions = {
                cid: (self._document.get_card(cid).x, self._document.get_card(cid).y)
                for cid in target_ids
            }
            min_x, min_y, max_x, max_y = positions_bbox(positions)
            width, height = DEFAULT_CARD_SIZE
            x = (min_x + max_x) / 2 - width / 2
            y = (min_y + max_y) / 2 - height / 2
        new_stack = Stack(id=stack_id, x=x, y=y, label=label)
        self._undo_stack.push(CreateStackCommand(self._document, new_stack, target_ids))

    def _add_to_existing_stack(self, stack_id: str) -> None:
        target_ids = self._selection_scoped_card_ids()
        self._undo_stack.push(AddCardsToStackCommand(self._document, stack_id, target_ids))

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

    def _set_color_slot(self, new_slot_id: str) -> None:
        old_slot_id = self._document.get_card(self.card_id).color_slot
        if new_slot_id == old_slot_id:
            return
        self._undo_stack.push(
            ChangeColorCommand(self._document, self.card_id, old_slot_id, new_slot_id)
        )

    def _sync_text_item(self) -> None:
        card = self._document.get_card(self.card_id)
        self._text_item.document().setMarkdown(card.text)
        self._text_item.document().setModified(False)
        self._apply_rendered_layout()
        self._apply_text_color()

    def _apply_text_color(self) -> None:
        """Split out of _sync_text_item so set_dimmed() can update just
        the color without touching markdown content — resetting the
        document from card.text on every dim toggle would blow away an
        in-progress edit if a search query changes while a card is being
        actively typed into."""
        card = self._document.get_card(self.card_id)
        slot = self._document.get_slot(card.color_slot)
        text_hex = slot.text_color or auto_text_color(slot.hex)
        text_color = QColor(text_hex)
        if self._dimmed:
            text_color = _dimmed_text_color(text_color)
        self._text_item.setDefaultTextColor(text_color)

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
