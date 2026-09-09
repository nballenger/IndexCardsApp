from PySide6.QtCore import QEvent, QPoint, QPointF, QSize, Qt
from PySide6.QtGui import (
    QFocusEvent,
    QKeyEvent,
    QMouseEvent,
    QTextCursor,
    QUndoStack,
    QWheelEvent,
)
from PySide6.QtWidgets import QApplication, QGraphicsItem, QGraphicsSceneMouseEvent, QWidget

from indexcards.canvas.canvas_scene import CanvasScene
from indexcards.canvas.canvas_view import CanvasView
from indexcards.canvas.card_item import CardItem, _CardTextItem
from indexcards.canvas.stack_item import _STACK_DEPTH
from indexcards.canvas.stack_overlay import OverlayCardItem, StackOverlay
from indexcards.commands.stack_commands import ReorderStackCommand
from indexcards.models.card import DEFAULT_CARD_SIZE, Card
from indexcards.models.document import Document
from indexcards.models.stack import Stack


def _document_with_stack(card_ids: list[str]) -> Document:
    document = Document(name="Test")
    for card_id in card_ids:
        document.add_card(Card(id=card_id, x=0.0, y=0.0, stack_id="s_1"))
    document.add_stack(Stack(id="s_1", card_ids=list(card_ids)))
    return document


def _open_overlay(
    qtbot, card_ids: list[str], viewport_size: QSize | None = None
) -> tuple[StackOverlay, Document, QUndoStack, QWidget]:
    # Returns (overlay, document, undo_stack, parent) — the caller must
    # keep parent referenced for as long as overlay is used, or Python
    # GC'ing it deletes the underlying C++ objects it owns (overlay
    # included) along with it. Mirrors _overlay(qtbot) in
    # tests/test_color_key_overlay.py.
    document = _document_with_stack(card_ids)
    undo_stack = QUndoStack()
    parent = QWidget()
    parent.resize(viewport_size or QSize(800, 600))
    qtbot.addWidget(parent)
    parent.show()
    # Real window activation, not just isVisible() — the Escape-while-
    # editing test depends on genuine widget focus reaching the grid view
    # (see _StackGridView.keyPressEvent's scene().focusItem() check), which
    # in a full-suite run can otherwise still belong to whatever widget an
    # earlier test last focused.
    qtbot.waitActive(parent)
    overlay = StackOverlay(parent)
    overlay.open("s_1", document, undo_stack)
    return overlay, document, undo_stack, parent


def _escape_event() -> QKeyEvent:
    return QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier)


def _press_event(point: QPointF) -> QMouseEvent:
    return QMouseEvent(
        QEvent.Type.MouseButtonPress,
        point,
        point,
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )


def _double_click_event(point: QPointF) -> QMouseEvent:
    return QMouseEvent(
        QEvent.Type.MouseButtonDblClick,
        point,
        point,
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )


def _simulate_typing(item: CardItem, text: str) -> None:
    cursor = item._text_item.textCursor()
    cursor.select(QTextCursor.SelectionType.Document)
    cursor.insertText(text)


def _press_tile(tile: OverlayCardItem) -> None:
    tile.mousePressEvent(QGraphicsSceneMouseEvent(QEvent.Type.GraphicsSceneMousePress))


def _release_tile(tile: OverlayCardItem) -> None:
    tile.mouseReleaseEvent(QGraphicsSceneMouseEvent(QEvent.Type.GraphicsSceneMouseRelease))


def test_open_creates_one_tile_per_member_card(qtbot):
    overlay, _document, _undo, _parent = _open_overlay(qtbot, ["c_1", "c_2", "c_3"])

    assert overlay.is_open is True
    assert overlay.isVisible() is True
    assert set(overlay._tiles.keys()) == {"c_1", "c_2", "c_3"}
    assert all(isinstance(tile, CardItem) for tile in overlay._tiles.values())


def test_open_with_undo_stack_creates_movable_overlay_card_item_tiles(qtbot):
    overlay, _document, _undo, _parent = _open_overlay(qtbot, ["c_1", "c_2"])

    for tile in overlay._tiles.values():
        assert isinstance(tile, OverlayCardItem)
        assert tile.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsMovable


def test_open_without_undo_stack_creates_non_movable_plain_tiles(qtbot):
    document = _document_with_stack(["c_1", "c_2"])
    parent = QWidget()
    parent.resize(800, 600)
    qtbot.addWidget(parent)
    parent.show()
    overlay = StackOverlay(parent)

    overlay.open("s_1", document, None)

    for tile in overlay._tiles.values():
        assert type(tile) is CardItem
        assert not (tile.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsMovable)


def test_open_positions_tiles_in_grid_order(qtbot):
    overlay, _document, _undo, _parent = _open_overlay(qtbot, ["c_1", "c_2", "c_3", "c_4"])

    positions = [overlay._tiles[cid].pos() for cid in ["c_1", "c_2", "c_3", "c_4"]]
    # Row-major: c_1/c_2 share a y (row 0), c_3/c_4 share a lower y (row 1),
    # and within each row x strictly increases.
    assert positions[0].y() == positions[1].y()
    assert positions[2].y() == positions[3].y()
    assert positions[2].y() > positions[0].y()
    assert positions[1].x() > positions[0].x()
    assert positions[3].x() > positions[2].x()


def test_double_click_on_stack_item_opens_overlay(qtbot):
    document = _document_with_stack(["c_1", "c_2"])
    scene = CanvasScene(document, undo_stack=QUndoStack())
    view = CanvasView()
    qtbot.addWidget(view)
    view.resize(800, 600)
    view.setScene(scene)
    stack_item = scene.item_for_stack("s_1")

    press = QGraphicsSceneMouseEvent(QEvent.Type.GraphicsSceneMouseDoubleClick)
    stack_item.mouseDoubleClickEvent(press)

    assert view.stack_overlay.is_open is True
    assert set(view.stack_overlay._tiles.keys()) == {"c_1", "c_2"}


def test_escape_closes_overlay_and_tears_down_tiles(qtbot):
    overlay, document, _undo, _parent = _open_overlay(qtbot, ["c_1", "c_2"])

    overlay._grid_view.keyPressEvent(_escape_event())

    assert overlay.is_open is False
    assert overlay._tiles == {}
    assert overlay.isVisible() is False

    # Signal connections were actually dropped — mutating a former member
    # card must not raise or resurrect any overlay state.
    document.set_card_color_slot("c_1", document.theme.slots[1].id)
    assert overlay._tiles == {}


def test_escape_while_editing_commits_edit_without_closing_overlay(qtbot, monkeypatch):
    # A headless/unfocused-window test run can't rely on real clearFocus()
    # actually firing focusOutEvent — same limitation and same workaround
    # as test_escape_commits_text_change in tests/test_card_item.py.
    def fake_clear_focus(self) -> None:
        self.focusOutEvent(QFocusEvent(QEvent.Type.FocusOut, Qt.FocusReason.OtherFocusReason))

    monkeypatch.setattr(_CardTextItem, "clearFocus", fake_clear_focus)

    overlay, document, _undo, _parent = _open_overlay(qtbot, ["c_1"])
    tile = overlay._tiles["c_1"]
    tile.enter_edit_mode()
    _simulate_typing(tile, "New text")

    overlay._grid_view.keyPressEvent(_escape_event())
    assert overlay.is_open is True
    assert tile._editing is False
    assert document.get_card("c_1").text == "New text"

    overlay._grid_view.keyPressEvent(_escape_event())
    assert overlay.is_open is False


def test_click_on_scrim_outside_grid_closes_overlay(qtbot):
    overlay, _document, _undo, _parent = _open_overlay(qtbot, ["c_1"])

    # top-left corner of the full-viewport overlay — outside the grid
    overlay.mousePressEvent(_press_event(QPointF(2.0, 2.0)))

    # Dismiss is deferred one double-click interval (see mousePressEvent's
    # own docstring) so a following double-click can cancel it instead --
    # still open immediately after the press, only actually dismissed
    # once that interval elapses without a second click.
    assert overlay.is_open is True
    qtbot.wait(QApplication.doubleClickInterval() + 50)
    assert overlay.is_open is False


def test_double_click_on_scrim_creates_a_card_instead_of_dismissing(qtbot):
    overlay, document, undo_stack, _parent = _open_overlay(qtbot, ["c_1"])

    # A real double-click still delivers its first press through
    # mousePressEvent (Qt can't know in advance it'll become a double-
    # click) before mouseDoubleClickEvent itself fires.
    overlay.mousePressEvent(_press_event(QPointF(2.0, 2.0)))
    overlay.mouseDoubleClickEvent(_double_click_event(QPointF(2.0, 2.0)))
    # create_card() is deferred via QTimer.singleShot(0, ...) -- pushing
    # its command synchronously here would rebuild the scene while still
    # inside this very mouseDoubleClickEvent dispatch.
    qtbot.waitUntil(lambda: undo_stack.count() == 1)

    assert overlay.is_open is True
    assert len(document.get_stack("s_1").card_ids) == 2
    assert undo_stack.canUndo()

    # The deferred single-click dismiss from the first press must have
    # been canceled, not just superseded -- confirm it never fires late.
    qtbot.wait(QApplication.doubleClickInterval() + 50)
    assert overlay.is_open is True


def test_click_inside_grid_view_does_not_close_overlay(qtbot):
    overlay, _document, _undo, _parent = _open_overlay(qtbot, ["c_1"])

    # A press dispatched to _grid_view itself (not the outer overlay) is
    # normal QGraphicsView click handling — it must never reach
    # StackOverlay.mousePressEvent/dismiss.
    overlay._grid_view.mousePressEvent(_press_event(QPointF(2.0, 2.0)))

    assert overlay.is_open is True


def test_create_card_adds_a_card_to_the_open_stack_and_enters_edit_mode(qtbot):
    overlay, document, undo_stack, _parent = _open_overlay(qtbot, ["c_1"])

    new_card_id = overlay.create_card()

    assert new_card_id is not None
    assert document.get_card(new_card_id).stack_id == "s_1"
    assert document.get_stack("s_1").card_ids == ["c_1", new_card_id]
    assert new_card_id in overlay._tiles
    assert overlay._tiles[new_card_id]._editing is True
    assert overlay.is_open is True

    assert undo_stack.canUndo()
    undo_stack.undo()
    assert new_card_id not in document.cards
    assert document.get_stack("s_1").card_ids == ["c_1"]


def test_create_card_is_a_noop_when_overlay_is_closed(qtbot):
    document = _document_with_stack(["c_1"])
    undo_stack = QUndoStack()
    parent = QWidget()
    parent.resize(QSize(800, 600))
    qtbot.addWidget(parent)
    overlay = StackOverlay(parent)

    result = overlay.create_card()

    assert result is None
    assert len(document.cards) == 1
    assert undo_stack.canUndo() is False


def test_create_card_is_a_noop_for_a_read_only_overlay(qtbot):
    document = _document_with_stack(["c_1"])
    parent = QWidget()
    parent.resize(QSize(800, 600))
    qtbot.addWidget(parent)
    parent.show()
    qtbot.waitActive(parent)
    overlay = StackOverlay(parent)
    overlay.open("s_1", document, undo_stack=None)

    result = overlay.create_card()

    assert result is None
    assert len(document.cards) == 1


def test_double_click_on_empty_grid_space_creates_a_card(qtbot):
    overlay, document, undo_stack, _parent = _open_overlay(qtbot, ["c_1"])

    # (2, 2) sits inside _grid_view's own geometry but well before the
    # first tile's slot (which starts at _CELL_SPACING / 2 = 12 in scene
    # coords) -- empty grid space, no item underneath.
    overlay._grid_view.mouseDoubleClickEvent(_double_click_event(QPointF(2.0, 2.0)))
    # create_card() is deferred via QTimer.singleShot(0, ...) -- see the
    # override's own docstring for why.
    qtbot.waitUntil(lambda: undo_stack.count() == 1)

    assert overlay.is_open is True
    assert document.get_stack("s_1").card_ids != ["c_1"]  # a second card was added
    assert len(document.get_stack("s_1").card_ids) == 2
    assert undo_stack.canUndo()


def test_double_click_on_an_existing_tile_does_not_create_a_second_card(qtbot):
    overlay, document, _undo, _parent = _open_overlay(qtbot, ["c_1"])

    # (50, 50) lands squarely inside the first tile's slot (12,12) to
    # (212,132) for a DEFAULT_CARD_SIZE of (200, 120) -- an existing item,
    # so this must defer to super().mouseDoubleClickEvent() instead of
    # creating a card (CardItem's own double-click-to-edit behavior is
    # pre-existing and covered separately in tests/test_card_item.py --
    # not re-verified here, since routing a synthetic QMouseEvent through
    # QGraphicsView's internal scene-item dispatch this way doesn't
    # reliably reproduce it without a real preceding press).
    overlay._grid_view.mouseDoubleClickEvent(_double_click_event(QPointF(50.0, 50.0)))

    assert overlay.is_open is True
    assert document.get_stack("s_1").card_ids == ["c_1"]


class _FakeWheelEvent:
    """Mirrors test_canvas_view.py's own _FakeWheelEvent — only needs
    accept() for this override, which ignores the event's actual contents
    entirely."""

    def __init__(self) -> None:
        self.accepted = False

    def accept(self) -> None:
        self.accepted = True


def test_wheel_event_on_scrim_is_accepted_not_propagated(qtbot):
    overlay, _document, _undo, _parent = _open_overlay(qtbot, ["c_1"])

    event = _FakeWheelEvent()
    overlay.wheelEvent(event)

    assert event.accepted is True


def test_wheel_scroll_over_scrim_does_not_pan_the_canvas_underneath(qtbot):
    # Reproduces the reported bug directly: with the overlay open, a
    # trackpad/wheel scroll landing on the scrim must not reach
    # CanvasView.wheelEvent underneath (which pans/zooms) -- only
    # _grid_view's own wheel handling should ever fire while the overlay
    # is up.
    document = _document_with_stack(["c_1"])
    # A card far outside the initial viewport gives the canvas real,
    # visible scroll range to pan through if the leak isn't fixed.
    document.add_card(Card(id="c_far", x=5000.0, y=5000.0))
    scene = CanvasScene(document, undo_stack=QUndoStack())
    view = CanvasView()
    qtbot.addWidget(view)
    view.resize(800, 600)
    view.setScene(scene)
    view.stack_overlay.open("s_1", document, QUndoStack())
    center_before = view.mapToScene(view.viewport().rect().center())

    event = QWheelEvent(
        QPointF(400.0, 300.0),
        QPointF(400.0, 300.0),
        QPoint(0, 0),
        QPoint(0, -240),
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.NoScrollPhase,
        False,
    )
    QApplication.sendEvent(view.stack_overlay, event)

    center_after = view.mapToScene(view.viewport().rect().center())
    assert center_after == center_before


def test_resize_reflows_grid(qtbot):
    overlay, _document, _undo, parent = _open_overlay(
        qtbot, ["c_1", "c_2", "c_3", "c_4"], viewport_size=QSize(500, 600)
    )
    narrow_cols = len({round(tile.pos().x()) for tile in overlay._tiles.values()})

    # Mirrors the real flow: CanvasView.resizeEvent only calls
    # stack_overlay.reposition(...) after the viewport itself has already
    # resized, so _layout_grid's own parentWidget().size() read reflects
    # it too.
    parent.resize(1600, 600)
    overlay.reposition(QSize(1600, 600))

    wide_cols = len({round(tile.pos().x()) for tile in overlay._tiles.values()})
    assert wide_cols > narrow_cols


def test_resize_while_closed_is_noop(qtbot):
    parent = QWidget()
    parent.resize(800, 600)
    qtbot.addWidget(parent)
    overlay = StackOverlay(parent)

    overlay.reposition(QSize(1600, 600))  # must not raise

    assert overlay.is_open is False


def test_editing_tile_text_while_open_pushes_command_and_refreshes(qtbot):
    overlay, document, undo_stack, _parent = _open_overlay(qtbot, ["c_1"])
    tile = overlay._tiles["c_1"]

    tile.enter_edit_mode()
    _simulate_typing(tile, "Edited")
    tile._on_text_focus_out()

    assert undo_stack.count() == 1
    assert document.get_card("c_1").text == "Edited"


def test_changing_color_via_tile_context_menu_refreshes_overlay_live(qtbot):
    overlay, document, _undo, _parent = _open_overlay(qtbot, ["c_1"])
    tile = overlay._tiles["c_1"]
    refresh_calls = []
    original_refresh = tile.refresh
    tile.refresh = lambda: (refresh_calls.append(True), original_refresh())[-1]

    new_slot_id = document.theme.slots[1].id
    tile._set_color_slot(new_slot_id)

    assert document.get_card("c_1").color_slot == new_slot_id
    assert refresh_calls == [True]


def test_card_leaving_stack_rebuilds_grid(qtbot):
    overlay, document, _undo, _parent = _open_overlay(qtbot, ["c_1", "c_2"])

    document.remove_cards_from_stack("s_1", ["c_1"])

    assert set(overlay._tiles.keys()) == {"c_2"}


def test_stack_removed_closes_overlay(qtbot):
    overlay, document, _undo, _parent = _open_overlay(qtbot, ["c_1", "c_2"])
    document.remove_cards_from_stack("s_1", ["c_1", "c_2"])

    document.remove_stack("s_1")

    assert overlay.is_open is False


# -- drag-to-reorder (Milestone 2) -------------------------------------------


def test_dragging_into_a_neighboring_slot_reorders_live(qtbot):
    overlay, document, undo_stack, _parent = _open_overlay(
        qtbot, ["c_1", "c_2", "c_3", "c_4"], viewport_size=QSize(800, 600)
    )
    dragged = overlay._tiles["c_1"]
    target_pos = overlay._tiles["c_2"].pos()

    _press_tile(dragged)
    dragged.setPos(target_pos)

    assert overlay._tile_order == ["c_2", "c_1", "c_3", "c_4"]
    # c_2 slides away to make room (Milestone 4: animated, not an instant
    # jump) — check the animation's own target rather than pos() right
    # away, since the slide hasn't had any event-loop time to progress yet.
    assert overlay._animations["c_2"].endValue() != target_pos

    _release_tile(dragged)  # drain the resulting commit so nothing leaks into later tests
    qtbot.waitUntil(lambda: undo_stack.count() == 1)
    assert document.get_stack("s_1").card_ids == ["c_2", "c_1", "c_3", "c_4"]


def test_dragging_back_to_original_slot_before_release_pushes_no_command(qtbot):
    overlay, document, undo_stack, _parent = _open_overlay(
        qtbot, ["c_1", "c_2", "c_3", "c_4"], viewport_size=QSize(800, 600)
    )
    dragged = overlay._tiles["c_1"]
    original_pos = dragged.pos()
    neighbor_pos = overlay._tiles["c_2"].pos()

    _press_tile(dragged)
    dragged.setPos(neighbor_pos)
    dragged.setPos(original_pos)
    _release_tile(dragged)

    assert overlay._tile_order == ["c_1", "c_2", "c_3", "c_4"]
    assert undo_stack.count() == 0
    assert dragged.pos() == original_pos
    assert document.get_stack("s_1").card_ids == ["c_1", "c_2", "c_3", "c_4"]


def test_completed_reorder_pushes_command_and_rebuilds(qtbot):
    overlay, document, undo_stack, _parent = _open_overlay(
        qtbot, ["c_1", "c_2", "c_3", "c_4"], viewport_size=QSize(800, 600)
    )
    dragged = overlay._tiles["c_1"]
    target_pos = overlay._tiles["c_2"].pos()

    _press_tile(dragged)
    dragged.setPos(target_pos)
    _release_tile(dragged)

    qtbot.waitUntil(lambda: undo_stack.count() == 1)
    assert isinstance(undo_stack.command(0), ReorderStackCommand)
    assert document.get_stack("s_1").card_ids == ["c_2", "c_1", "c_3", "c_4"]
    assert set(overlay._tiles.keys()) == {"c_1", "c_2", "c_3", "c_4"}
    assert overlay._tiles["c_1"] is not dragged  # rebuilt into a fresh instance


def test_undo_after_reorder_restores_original_order_live(qtbot):
    overlay, document, undo_stack, _parent = _open_overlay(
        qtbot, ["c_1", "c_2", "c_3", "c_4"], viewport_size=QSize(800, 600)
    )
    dragged = overlay._tiles["c_1"]
    target_pos = overlay._tiles["c_2"].pos()
    _press_tile(dragged)
    dragged.setPos(target_pos)
    _release_tile(dragged)
    qtbot.waitUntil(lambda: undo_stack.count() == 1)

    undo_stack.undo()

    assert document.get_stack("s_1").card_ids == ["c_1", "c_2", "c_3", "c_4"]
    assert overlay._tile_order == ["c_1", "c_2", "c_3", "c_4"]


def test_position_changed_ignored_for_non_dragging_tile(qtbot):
    overlay, _document, _undo, _parent = _open_overlay(
        qtbot, ["c_1", "c_2"], viewport_size=QSize(800, 600)
    )
    original_order = list(overlay._tile_order)

    # No drag in progress (_dragging_card_id is None) — a stray position-
    # changed notification for any card must be a no-op, not a reorder.
    overlay._on_tile_position_changed("c_2")

    assert overlay._tile_order == original_order


def test_reorder_still_commits_if_overlay_dismissed_before_deferred_push(qtbot):
    overlay, document, undo_stack, _parent = _open_overlay(
        qtbot, ["c_1", "c_2", "c_3", "c_4"], viewport_size=QSize(800, 600)
    )
    dragged = overlay._tiles["c_1"]
    target_pos = overlay._tiles["c_2"].pos()
    _press_tile(dragged)
    dragged.setPos(target_pos)
    _release_tile(dragged)

    overlay.dismiss()  # closes in the brief window before the deferred timer fires

    qtbot.waitUntil(lambda: undo_stack.count() == 1)
    assert document.get_stack("s_1").card_ids == ["c_2", "c_1", "c_3", "c_4"]


# -- drag-out-to-eject (Milestone 3) -----------------------------------------

_FAR_OUTSIDE_GRID = QPointF(2000.0, 2000.0)


def _spy_update(overlay: StackOverlay) -> list:
    calls = []
    original = overlay.update
    overlay.update = lambda *a: (calls.append(a), original(*a))[-1]
    return calls


def test_in_grid_reorder_does_not_repaint_the_overlay(qtbot):
    # The grid_view's own QGraphicsScene repaints reordered tiles on its
    # own — StackOverlay's own (viewport-sized) paintEvent has nothing to
    # do during a plain in-grid reorder and must not be invalidated for it,
    # since that would compete for paint time with unrelated, rarer
    # repaints elsewhere (e.g. the Stack's own card-count badge).
    overlay, _document, undo_stack, _parent = _open_overlay(
        qtbot, ["c_1", "c_2", "c_3", "c_4"], viewport_size=QSize(800, 600)
    )
    dragged = overlay._tiles["c_1"]
    target_pos = overlay._tiles["c_2"].pos()
    calls = _spy_update(overlay)

    _press_tile(dragged)
    dragged.setPos(target_pos)
    _release_tile(dragged)

    assert calls == []
    qtbot.waitUntil(lambda: undo_stack.count() == 1)  # drain the deferred reorder push


def test_eject_ghost_repaint_is_scoped_to_a_small_rect_not_the_whole_widget(qtbot):
    overlay, _document, undo_stack, _parent = _open_overlay(
        qtbot, ["c_1", "c_2"], viewport_size=QSize(800, 600)
    )
    dragged = overlay._tiles["c_1"]
    calls = _spy_update(overlay)

    _press_tile(dragged)
    dragged.setPos(_FAR_OUTSIDE_GRID)

    assert len(calls) == 1
    (rect,) = calls[0]
    width, height = DEFAULT_CARD_SIZE
    assert rect.width() < overlay.width() / 2
    assert rect.height() < overlay.height() / 2
    assert rect.width() >= width and rect.height() >= height

    _release_tile(dragged)
    qtbot.waitUntil(lambda: undo_stack.count() == 1)


def test_dragging_past_grid_edge_sets_ghost_and_leaves_tile_order_untouched(qtbot):
    overlay, _document, undo_stack, _parent = _open_overlay(
        qtbot, ["c_1", "c_2", "c_3", "c_4"], viewport_size=QSize(800, 600)
    )
    dragged = overlay._tiles["c_1"]
    original_order = list(overlay._tile_order)

    _press_tile(dragged)
    dragged.setPos(_FAR_OUTSIDE_GRID)

    assert overlay._eject_preview_pos is not None
    assert overlay._tile_order == original_order

    _release_tile(dragged)
    qtbot.waitUntil(lambda: undo_stack.count() == 1)  # drain the deferred eject


def test_dragging_back_inside_after_going_past_edge_resumes_reorder(qtbot):
    overlay, document, undo_stack, _parent = _open_overlay(
        qtbot, ["c_1", "c_2", "c_3", "c_4"], viewport_size=QSize(800, 600)
    )
    dragged = overlay._tiles["c_1"]
    neighbor_pos = overlay._tiles["c_2"].pos()

    _press_tile(dragged)
    dragged.setPos(_FAR_OUTSIDE_GRID)
    assert overlay._eject_preview_pos is not None

    dragged.setPos(neighbor_pos)
    assert overlay._eject_preview_pos is None
    assert overlay._tile_order == ["c_2", "c_1", "c_3", "c_4"]

    _release_tile(dragged)
    qtbot.waitUntil(lambda: undo_stack.count() == 1)
    assert document.get_stack("s_1").card_ids == ["c_2", "c_1", "c_3", "c_4"]


def test_releasing_past_grid_edge_ejects_card_leaving_stack_intact(qtbot):
    overlay, document, undo_stack, _parent = _open_overlay(
        qtbot, ["c_1", "c_2", "c_3", "c_4"], viewport_size=QSize(800, 600)
    )
    stack = document.get_stack("s_1")
    dragged = overlay._tiles["c_1"]

    _press_tile(dragged)
    dragged.setPos(_FAR_OUTSIDE_GRID)
    _release_tile(dragged)

    qtbot.waitUntil(lambda: undo_stack.count() == 1)
    assert "c_1" not in document.get_stack("s_1").card_ids
    assert document.get_card("c_1").stack_id is None
    landed_x, landed_y = document.get_card("c_1").x, document.get_card("c_1").y
    # The first eject in a session lands a clear gutter to the right of the
    # stack's own rendered footprint (card width + its isometric depth),
    # at the same y — not overlapping the StackItem box, and not yet
    # cascaded diagonally (that only kicks in from the second eject on).
    assert landed_x > stack.x + DEFAULT_CARD_SIZE[0] + _STACK_DEPTH
    assert landed_y == stack.y
    assert "s_1" in document.stacks
    assert overlay.is_open is True
    assert set(overlay._tiles.keys()) == {"c_2", "c_3", "c_4"}

    undo_stack.undo()
    assert document.get_stack("s_1").card_ids == ["c_1", "c_2", "c_3", "c_4"]
    assert document.get_card("c_1").stack_id == "s_1"
    assert (document.get_card("c_1").x, document.get_card("c_1").y) == (0.0, 0.0)


def test_sequential_ejects_in_one_session_cascade_from_each_other(qtbot):
    overlay, document, undo_stack, _parent = _open_overlay(
        qtbot, ["c_1", "c_2", "c_3", "c_4"], viewport_size=QSize(800, 600)
    )

    first = overlay._tiles["c_1"]
    _press_tile(first)
    first.setPos(_FAR_OUTSIDE_GRID)
    _release_tile(first)
    qtbot.waitUntil(lambda: undo_stack.count() == 1)
    first_x, first_y = document.get_card("c_1").x, document.get_card("c_1").y

    second = overlay._tiles["c_2"]  # rebuilt tile after the first eject
    _press_tile(second)
    second.setPos(_FAR_OUTSIDE_GRID)
    _release_tile(second)
    qtbot.waitUntil(lambda: undo_stack.count() == 2)
    second_x, second_y = document.get_card("c_2").x, document.get_card("c_2").y

    # The second eject cascades diagonally from where the first landed,
    # by the same step in both axes — not the same spot, and not
    # re-anchored back at the stack's own position.
    assert second_x > first_x
    assert second_y > first_y
    assert (second_x - first_x) == (second_y - first_y)


def test_releasing_past_grid_edge_on_two_card_stack_dissolves_it(qtbot):
    overlay, document, undo_stack, _parent = _open_overlay(
        qtbot, ["c_1", "c_2"], viewport_size=QSize(800, 600)
    )
    dragged = overlay._tiles["c_1"]

    _press_tile(dragged)
    dragged.setPos(_FAR_OUTSIDE_GRID)
    _release_tile(dragged)

    qtbot.waitUntil(lambda: "s_1" not in document.stacks)
    assert document.get_card("c_1").stack_id is None
    assert document.get_card("c_2").stack_id is None
    assert (document.get_card("c_2").x, document.get_card("c_2").y) == (0.0, 0.0)
    assert overlay.is_open is False

    undo_stack.undo()
    assert document.get_stack("s_1").card_ids == ["c_1", "c_2"]
    assert document.get_card("c_1").stack_id == "s_1"
    assert document.get_card("c_2").stack_id == "s_1"


def test_dismiss_is_noop_while_drag_in_progress(qtbot):
    overlay, _document, _undo, _parent = _open_overlay(qtbot, ["c_1", "c_2"])
    dragged = overlay._tiles["c_1"]

    _press_tile(dragged)
    overlay.dismiss()
    assert overlay.is_open is True

    _release_tile(dragged)  # avoid leaking a pressed tile into later tests


def test_paint_does_not_crash_with_eject_ghost_active(qtbot):
    overlay, _document, undo_stack, _parent = _open_overlay(qtbot, ["c_1"])
    dragged = overlay._tiles["c_1"]

    _press_tile(dragged)
    dragged.setPos(_FAR_OUTSIDE_GRID)
    assert overlay._eject_preview_pos is not None

    overlay.repaint()  # must not raise

    _release_tile(dragged)
    qtbot.waitUntil(lambda: undo_stack.count() == 1)  # drain the deferred eject


# -- slide animation (Milestone 4) -------------------------------------------


def test_initial_layout_does_not_animate(qtbot):
    overlay, _document, _undo, _parent = _open_overlay(qtbot, ["c_1", "c_2", "c_3", "c_4"])

    assert overlay._animations == {}


def test_snap_back_after_no_op_drag_animates(qtbot):
    overlay, _document, undo_stack, _parent = _open_overlay(
        qtbot, ["c_1", "c_2", "c_3", "c_4"], viewport_size=QSize(800, 600)
    )
    dragged = overlay._tiles["c_1"]
    original_pos = dragged.pos()

    _press_tile(dragged)
    dragged.setPos(QPointF(original_pos.x() + 5, original_pos.y() + 5))  # nudge, not a reorder
    _release_tile(dragged)

    assert "c_1" in overlay._animations
    assert overlay._animations["c_1"].endValue() == original_pos
    assert undo_stack.count() == 0

    qtbot.waitUntil(lambda: dragged.pos() == original_pos)  # animation actually completes


def test_external_mutation_mid_drag_defers_rebuild_until_release(qtbot):
    # A rebuild triggered while a drag is still active must not tear down
    # the scene immediately — that would delete the tile whose mouse grab
    # the drag still holds. This can genuinely happen: e.g. a deferred
    # eject/reorder command from an earlier drag landing (via its own
    # QTimer.singleShot(0, ...)) just as a new drag has already started.
    overlay, document, undo_stack, _parent = _open_overlay(
        qtbot, ["c_1", "c_2", "c_3", "c_4"], viewport_size=QSize(800, 600)
    )
    dragged = overlay._tiles["c_1"]
    target_pos = overlay._tiles["c_2"].pos()

    _press_tile(dragged)
    dragged.setPos(target_pos)
    assert overlay._animations  # c_2 sliding away

    document.remove_cards_from_stack("s_1", ["c_3"])  # simulates a concurrent mutation

    assert overlay._rebuild_pending is True
    assert overlay._animations  # untouched — no rebuild has happened yet
    assert "c_1" in overlay._tiles  # the dragged tile is still the same, live object

    _release_tile(dragged)

    # The deferred rebuild runs instead of this drag's own (now-stale)
    # outcome — no ReorderStackCommand gets pushed for it.
    assert overlay._rebuild_pending is False
    assert overlay._animations == {}
    assert set(overlay._tiles.keys()) == {"c_1", "c_2", "c_4"}
    assert undo_stack.count() == 0


# -- multi-select drag (Milestone 4) -----------------------------------------


def test_pressing_a_multi_selected_tile_collapses_to_just_that_tile(qtbot):
    overlay, _document, _undo, _parent = _open_overlay(qtbot, ["c_1", "c_2", "c_3"])
    overlay._tiles["c_1"].setSelected(True)
    overlay._tiles["c_2"].setSelected(True)

    _press_tile(overlay._tiles["c_1"])

    assert overlay._tiles["c_1"].isSelected() is True
    assert overlay._tiles["c_2"].isSelected() is False
    _release_tile(overlay._tiles["c_1"])


def test_pressing_a_singly_selected_tile_does_not_clear_selection(qtbot):
    overlay, _document, _undo, _parent = _open_overlay(qtbot, ["c_1", "c_2"])
    overlay._tiles["c_1"].setSelected(True)

    _press_tile(overlay._tiles["c_1"])

    assert overlay._tiles["c_1"].isSelected() is True
    _release_tile(overlay._tiles["c_1"])


# -- keyboard navigation (Milestone 4) ---------------------------------------


def _key_event(key) -> QKeyEvent:
    return QKeyEvent(QEvent.Type.KeyPress, key, Qt.KeyboardModifier.NoModifier)


def test_first_tile_is_focused_on_open(qtbot):
    overlay, _document, _undo, _parent = _open_overlay(qtbot, ["c_1", "c_2", "c_3", "c_4"])

    assert overlay._focused_card_id() == "c_1"


def test_arrow_keys_move_focus_across_the_grid(qtbot):
    # 4 cards at 800x600 lay out as a 2x2 grid (see test_open_positions_
    # tiles_in_grid_order for the same layout assumption).
    overlay, _document, _undo, _parent = _open_overlay(
        qtbot, ["c_1", "c_2", "c_3", "c_4"], viewport_size=QSize(800, 600)
    )
    assert overlay._focused_card_id() == "c_1"

    overlay._grid_view.keyPressEvent(_key_event(Qt.Key.Key_Right))
    assert overlay._focused_card_id() == "c_2"

    overlay._grid_view.keyPressEvent(_key_event(Qt.Key.Key_Down))
    assert overlay._focused_card_id() == "c_4"

    overlay._grid_view.keyPressEvent(_key_event(Qt.Key.Key_Left))
    assert overlay._focused_card_id() == "c_3"

    overlay._grid_view.keyPressEvent(_key_event(Qt.Key.Key_Up))
    assert overlay._focused_card_id() == "c_1"


def test_arrow_key_at_grid_edge_leaves_focus_unchanged(qtbot):
    overlay, _document, _undo, _parent = _open_overlay(
        qtbot, ["c_1", "c_2", "c_3", "c_4"], viewport_size=QSize(800, 600)
    )
    assert overlay._focused_card_id() == "c_1"

    overlay._grid_view.keyPressEvent(_key_event(Qt.Key.Key_Left))
    assert overlay._focused_card_id() == "c_1"

    overlay._grid_view.keyPressEvent(_key_event(Qt.Key.Key_Up))
    assert overlay._focused_card_id() == "c_1"


def test_enter_activates_focused_tile_for_editing(qtbot):
    overlay, _document, _undo, _parent = _open_overlay(qtbot, ["c_1", "c_2"])

    overlay._grid_view.keyPressEvent(_key_event(Qt.Key.Key_Return))

    assert overlay._tiles["c_1"]._editing is True


def test_space_activates_focused_tile_for_editing(qtbot):
    overlay, _document, _undo, _parent = _open_overlay(qtbot, ["c_1", "c_2"])

    overlay._grid_view.keyPressEvent(_key_event(Qt.Key.Key_Space))

    assert overlay._tiles["c_1"]._editing is True


def test_arrow_keys_do_not_navigate_while_editing(qtbot):
    overlay, _document, _undo, _parent = _open_overlay(
        qtbot, ["c_1", "c_2", "c_3", "c_4"], viewport_size=QSize(800, 600)
    )
    overlay._tiles["c_1"].enter_edit_mode()

    overlay._grid_view.keyPressEvent(_key_event(Qt.Key.Key_Right))

    # Focus (selection) is unaffected — the arrow key went to the text
    # cursor instead, same as _StackGridView already does for Escape.
    assert overlay._tiles["c_1"].isSelected() is True


def test_focus_follows_mouse_selection(qtbot):
    overlay, _document, _undo, _parent = _open_overlay(qtbot, ["c_1", "c_2", "c_3"])

    overlay._grid_scene.clearSelection()
    overlay._tiles["c_2"].setSelected(True)

    assert overlay._focused_card_id() == "c_2"


def test_focus_preserved_across_rebuild_when_card_still_present(qtbot):
    overlay, document, _undo, _parent = _open_overlay(qtbot, ["c_1", "c_2", "c_3"])
    overlay._focus_tile("c_2")

    document.set_card_color_slot("c_2", document.theme.slots[1].id)  # triggers refresh, not rebuild
    assert overlay._focused_card_id() == "c_2"

    document.remove_cards_from_stack("s_1", ["c_1"])  # triggers a real rebuild
    assert overlay._focused_card_id() == "c_2"


def test_focus_falls_back_to_first_tile_when_previously_focused_card_is_gone(qtbot):
    overlay, document, _undo, _parent = _open_overlay(qtbot, ["c_1", "c_2", "c_3"])
    overlay._focus_tile("c_1")

    document.remove_cards_from_stack("s_1", ["c_1"])

    assert overlay._focused_card_id() == "c_2"


def test_eject_card_produces_same_outcome_as_dragging_past_the_edge(qtbot):
    overlay, document, undo_stack, _parent = _open_overlay(
        qtbot, ["c_1", "c_2", "c_3", "c_4"], viewport_size=QSize(800, 600)
    )
    stack = document.get_stack("s_1")

    overlay.eject_card("c_1")

    qtbot.waitUntil(lambda: undo_stack.count() == 1)
    assert "c_1" not in document.get_stack("s_1").card_ids
    assert document.get_card("c_1").stack_id is None
    landed_x, landed_y = document.get_card("c_1").x, document.get_card("c_1").y
    assert landed_x > stack.x + DEFAULT_CARD_SIZE[0] + _STACK_DEPTH
    assert landed_y == stack.y
    assert overlay.is_open is True
    assert set(overlay._tiles.keys()) == {"c_2", "c_3", "c_4"}


def test_eject_card_is_a_noop_for_a_card_not_in_the_overlay(qtbot):
    overlay, _document, undo_stack, _parent = _open_overlay(qtbot, ["c_1", "c_2"])

    overlay.eject_card("not_a_tile")

    assert undo_stack.count() == 0


def test_selected_card_id_tracks_focused_tile(qtbot):
    overlay, _document, _undo, _parent = _open_overlay(qtbot, ["c_1", "c_2", "c_3"])

    overlay._focus_tile("c_2")

    assert overlay.selected_card_id == "c_2"


def test_selected_card_id_is_none_when_nothing_focused(qtbot):
    overlay, _document, _undo, _parent = _open_overlay(qtbot, ["c_1", "c_2"])

    overlay._grid_scene.clearSelection()

    assert overlay.selected_card_id is None


def test_opened_changed_emits_true_then_false_across_open_and_dismiss(qtbot):
    document = _document_with_stack(["c_1", "c_2"])
    undo_stack = QUndoStack()
    parent = QWidget()
    parent.resize(800, 600)
    qtbot.addWidget(parent)
    parent.show()
    overlay = StackOverlay(parent)
    emissions: list[bool] = []
    overlay.openedChanged.connect(emissions.append)

    overlay.open("s_1", document, undo_stack)
    assert emissions == [True]

    overlay.dismiss()
    assert emissions == [True, False]


def test_grid_view_only_allows_vertical_scrolling(qtbot):
    overlay, _document, _undo, _parent = _open_overlay(qtbot, ["c_1", "c_2"])

    assert (
        overlay._grid_view.horizontalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
    )
    assert overlay._grid_view.verticalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAsNeeded


def test_open_pins_overlay_position_to_the_viewport_origin(qtbot):
    document = _document_with_stack(["c_1", "c_2"])
    undo_stack = QUndoStack()
    parent = QWidget()
    parent.resize(800, 600)
    qtbot.addWidget(parent)
    parent.show()
    overlay = StackOverlay(parent)
    # Simulate the stale/uninitialized geometry a freshly constructed
    # widget can carry before its first real show+layout pass — open()
    # must reset this explicitly rather than assume it's already correct.
    overlay.move(-127, -95)

    overlay.open("s_1", document, undo_stack)

    assert overlay.pos() == QPoint(0, 0)


def test_reposition_also_repins_overlay_position(qtbot):
    overlay, _document, _undo, parent = _open_overlay(
        qtbot, ["c_1", "c_2"], viewport_size=QSize(800, 600)
    )
    overlay.move(-40, -30)

    overlay.reposition(parent.size())

    assert overlay.pos() == QPoint(0, 0)


def test_refresh_tiles_refreshes_every_open_tile(qtbot):
    document = _document_with_stack(["c_1", "c_2"])
    document.set_card_text("c_1", "x" * 160)
    undo_stack = QUndoStack()
    parent = QWidget()
    parent.resize(800, 600)
    qtbot.addWidget(parent)
    parent.show()
    floor = 9
    overlay = StackOverlay(parent, get_minimum_font_size=lambda: floor)
    overlay.open("s_1", document, undo_stack)
    tile = overlay._tiles["c_1"]
    shrunk_at_9 = tile._text_item.document().defaultFont().pointSizeF()

    floor = 6
    overlay.refresh_tiles()

    shrunk_at_6 = tile._text_item.document().defaultFont().pointSizeF()
    assert shrunk_at_6 <= shrunk_at_9


def test_get_minimum_font_size_threads_into_interactive_and_read_only_tiles(qtbot):
    document = _document_with_stack(["c_1"])
    document.set_card_text("c_1", "x" * 160)

    # Interactive branch (real undo_stack -> OverlayCardItem).
    undo_stack = QUndoStack()
    parent = QWidget()
    parent.resize(800, 600)
    qtbot.addWidget(parent)
    parent.show()
    interactive_overlay = StackOverlay(parent, get_minimum_font_size=lambda: 6)
    interactive_overlay.open("s_1", document, undo_stack)
    interactive_tile = interactive_overlay._tiles["c_1"]
    assert isinstance(interactive_tile, OverlayCardItem)

    # Read-only branch (no undo_stack -> plain CardItem).
    other_parent = QWidget()
    other_parent.resize(800, 600)
    qtbot.addWidget(other_parent)
    other_parent.show()
    read_only_overlay = StackOverlay(other_parent, get_minimum_font_size=lambda: 6)
    read_only_overlay.open("s_1", document, None)
    read_only_tile = read_only_overlay._tiles["c_1"]
    assert type(read_only_tile) is CardItem

    default_floor_overlay = StackOverlay(other_parent)
    default_floor_overlay.open("s_1", document, None)
    default_floor_tile = default_floor_overlay._tiles["c_1"]

    assert (
        interactive_tile._text_item.document().defaultFont().pointSizeF()
        <= default_floor_tile._text_item.document().defaultFont().pointSizeF()
    )
    assert (
        read_only_tile._text_item.document().defaultFont().pointSizeF()
        <= default_floor_tile._text_item.document().defaultFont().pointSizeF()
    )
