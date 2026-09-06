import pytest
from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import (
    QContextMenuEvent,
    QMouseEvent,
    QNativeGestureEvent,
    QPointingDevice,
    QResizeEvent,
    QUndoStack,
)
from PySide6.QtWidgets import QGraphicsScene

from indexcards.canvas.canvas_scene import CanvasScene
from indexcards.canvas.canvas_view import MAX_ZOOM, MIN_ZOOM, PAN_OVERSCAN_PX, CanvasView
from indexcards.models.card import DEFAULT_CARD_SIZE, Card
from indexcards.models.document import Document
from indexcards.models.stack import Stack


def _double_click_event(x: float, y: float) -> QMouseEvent:
    point = QPointF(x, y)
    return QMouseEvent(
        QEvent.Type.MouseButtonDblClick,
        point,
        point,
        point,
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )


class _FakeAngleDelta:
    def __init__(self, y: int) -> None:
        self._y = y

    def y(self) -> int:
        return self._y


class _FakeWheelEvent:
    def __init__(self, ctrl: bool, angle_y: int) -> None:
        self._ctrl = ctrl
        self._angle_y = angle_y
        self.accepted = False

    def modifiers(self):
        return Qt.KeyboardModifier.ControlModifier if self._ctrl else Qt.KeyboardModifier.NoModifier

    def angleDelta(self) -> _FakeAngleDelta:
        return _FakeAngleDelta(self._angle_y)

    def accept(self) -> None:
        self.accepted = True


def test_zoom_by_increases_and_decreases_zoom(qtbot):
    view = CanvasView()
    qtbot.addWidget(view)

    view.zoom_by(1.5)
    assert view.zoom == 1.5

    view.zoom_by(1 / 1.5)
    assert abs(view.zoom - 1.0) < 1e-9


def test_zoom_by_clamps_to_max(qtbot):
    view = CanvasView()
    qtbot.addWidget(view)

    view.zoom_by(1000.0)
    assert view.zoom == MAX_ZOOM


def test_zoom_by_clamps_to_min(qtbot):
    view = CanvasView()
    qtbot.addWidget(view)

    view.zoom_by(0.0001)
    assert view.zoom == MIN_ZOOM


def test_wheel_event_with_ctrl_zooms_in_on_positive_delta(qtbot):
    view = CanvasView()
    qtbot.addWidget(view)

    event = _FakeWheelEvent(ctrl=True, angle_y=120)
    view.wheelEvent(event)

    assert view.zoom > 1.0
    assert event.accepted is True


def test_wheel_event_with_ctrl_zooms_out_on_negative_delta(qtbot):
    view = CanvasView()
    qtbot.addWidget(view)

    event = _FakeWheelEvent(ctrl=True, angle_y=-120)
    view.wheelEvent(event)

    assert view.zoom < 1.0
    assert event.accepted is True


def _native_zoom_gesture_event(value: float) -> QNativeGestureEvent:
    device = QPointingDevice.primaryPointingDevice()
    point = QPointF(10.0, 10.0)
    return QNativeGestureEvent(
        Qt.NativeGestureType.ZoomNativeGesture,
        device,
        2,
        point,
        point,
        point,
        value,
        QPointF(0.0, 0.0),
    )


def test_native_pinch_gesture_zooms(qtbot):
    view = CanvasView()
    qtbot.addWidget(view)

    view.viewportEvent(_native_zoom_gesture_event(0.5))

    assert view.zoom > 1.0


def test_native_pinch_gesture_does_not_zoom_while_stack_overlay_open(qtbot):
    # Reproduces a reported bug: pinch-to-zoom kept affecting the canvas
    # even while the Stack overlay was open and blocking every other kind
    # of canvas interaction (clicks, wheel-pan/zoom -- see the wheelEvent
    # override in stack_overlay.py). Unlike those, a native gesture is
    # captured directly on the viewport's native view and never reaches
    # StackOverlay as a child-widget event at all, so it has to be blocked
    # here in viewportEvent instead.
    document = Document(name="Test")
    document.add_card(Card(id="c_1", stack_id="s_1"))
    document.add_stack(Stack(id="s_1", card_ids=["c_1"]))
    scene = CanvasScene(document, undo_stack=QUndoStack())
    view = CanvasView()
    qtbot.addWidget(view)
    view.resize(800, 600)
    view.setScene(scene)
    view.stack_overlay.open("s_1", document, QUndoStack())

    view.viewportEvent(_native_zoom_gesture_event(0.5))

    assert view.zoom == 1.0


def test_fit_to_content_with_no_scene_does_not_crash(qtbot):
    view = CanvasView()
    qtbot.addWidget(view)
    view.fit_to_content()


def test_fit_to_content_with_empty_scene_does_not_crash(qtbot):
    view = CanvasView()
    qtbot.addWidget(view)
    view.setScene(QGraphicsScene())
    view.fit_to_content()


def test_fit_to_content_zooms_out_to_show_spread_out_cards(qtbot):
    document = Document(name="Test")
    document.add_card(Card(id="c_1", x=0.0, y=0.0))
    document.add_card(Card(id="c_2", x=2000.0, y=2000.0))
    scene = CanvasScene(document)

    view = CanvasView()
    qtbot.addWidget(view)
    view.resize(800, 600)
    view.setScene(scene)

    view.fit_to_content()

    assert view.zoom == view.transform().m11()
    assert view.zoom < 1.0


def test_center_or_fit_to_content_with_no_scene_does_not_crash(qtbot):
    view = CanvasView()
    qtbot.addWidget(view)
    view.center_or_fit_to_content()


def test_center_or_fit_to_content_with_empty_scene_does_not_crash(qtbot):
    view = CanvasView()
    qtbot.addWidget(view)
    view.setScene(QGraphicsScene())
    view.center_or_fit_to_content()


def test_center_or_fit_to_content_zooms_out_for_spread_out_cards(qtbot):
    document = Document(name="Test")
    document.add_card(Card(id="c_1", x=0.0, y=0.0))
    document.add_card(Card(id="c_2", x=2000.0, y=2000.0))
    scene = CanvasScene(document)

    view = CanvasView()
    qtbot.addWidget(view)
    view.resize(800, 600)
    view.setScene(scene)

    view.center_or_fit_to_content()

    assert view.zoom == view.transform().m11()
    assert view.zoom < 1.0


def test_center_or_fit_to_content_stays_at_native_zoom_when_it_already_fits(qtbot):
    document = Document(name="Test")
    document.add_card(Card(id="c_1", x=0.0, y=0.0))
    document.add_card(Card(id="c_2", x=50.0, y=50.0))
    scene = CanvasScene(document)

    view = CanvasView()
    qtbot.addWidget(view)
    view.resize(800, 600)
    view.setScene(scene)
    view.zoom_by(2.0)  # start away from 1.0 to prove this resets it, not just leaves it alone

    view.center_or_fit_to_content()

    assert view.zoom == 1.0
    assert view.transform().m11() == 1.0
    visible_rect = view.mapToScene(view.viewport().rect()).boundingRect()
    assert visible_rect.contains(scene.itemsBoundingRect())


def test_center_or_fit_to_content_centers_the_content_when_it_already_fits(qtbot):
    document = Document(name="Test")
    document.add_card(Card(id="c_1", x=0.0, y=0.0))
    document.add_card(Card(id="c_2", x=50.0, y=50.0))
    scene = CanvasScene(document)

    view = CanvasView()
    qtbot.addWidget(view)
    view.resize(800, 600)
    view.setScene(scene)
    scene.setSceneRect(-10000.0, -10000.0, 20000.0, 20000.0)
    view.centerOn(QPointF(5000.0, 5000.0))  # scroll far away first

    view.center_or_fit_to_content()

    center_after = view.mapToScene(view.viewport().rect().center())
    expected_center = scene.itemsBoundingRect().center()
    # +/-1px tolerance: viewport().rect().center() is integer pixels, so
    # the mapped-back scene point can be off by a fraction of a unit.
    assert abs(center_after.x() - expected_center.x()) <= 1.0
    assert abs(center_after.y() - expected_center.y()) <= 1.0


def test_restore_view_state_sets_exact_zoom_and_center(qtbot):
    # Spread-out content (mirrors center_or_fit_to_content's own oversized-
    # content fixture): _update_scene_rect() derives its pannable area from
    # content bounds (see its own docstring), re-clamping centerOn()'s
    # target to whatever that computes -- a single tiny card near the
    # origin wouldn't leave (123, 456) reachable at all.
    document = Document(name="Test")
    document.add_card(Card(id="c_1", x=0.0, y=0.0))
    document.add_card(Card(id="c_2", x=2000.0, y=2000.0))
    scene = CanvasScene(document)

    view = CanvasView()
    qtbot.addWidget(view)
    view.resize(800, 600)
    view.setScene(scene)

    view.restore_view_state(0.5, 500.0, 500.0)

    assert view.zoom == 0.5
    assert view.transform().m11() == 0.5
    center = view.mapToScene(view.viewport().rect().center())
    # viewport().rect().center() is integer pixels; at 0.5x zoom, 1px of
    # rounding is 2 scene units.
    assert abs(center.x() - 500.0) <= 2.0
    assert abs(center.y() - 500.0) <= 2.0


def test_restore_view_state_is_not_clamped_to_min_max_zoom(qtbot):
    document = Document(name="Test")
    document.add_card(Card(id="c_1", x=0.0, y=0.0))
    scene = CanvasScene(document)

    view = CanvasView()
    qtbot.addWidget(view)
    view.resize(800, 600)
    view.setScene(scene)

    out_of_range_zoom = MIN_ZOOM / 10
    view.restore_view_state(out_of_range_zoom, 0.0, 0.0)

    assert view.zoom == out_of_range_zoom


def test_fit_to_positions_with_no_positions_does_not_crash(qtbot):
    view = CanvasView()
    qtbot.addWidget(view)
    view.fit_to_positions({})


def test_fit_to_positions_zooms_out_to_show_spread_out_positions(qtbot):
    view = CanvasView()
    qtbot.addWidget(view)
    view.resize(800, 600)
    view.setScene(QGraphicsScene())

    view.fit_to_positions({"c_1": (0.0, 0.0), "c_2": (2000.0, 2000.0)})

    assert view.zoom == view.transform().m11()
    assert view.zoom < 1.0


def test_fit_to_positions_only_frames_given_positions_not_whole_scene(qtbot):
    document = Document(name="Test")
    document.add_card(Card(id="c_1", x=0.0, y=0.0))
    document.add_card(Card(id="c_2", x=5000.0, y=5000.0))
    scene = CanvasScene(document)

    view = CanvasView()
    qtbot.addWidget(view)
    view.resize(800, 600)
    view.setScene(scene)

    # Only frame c_1's own (small) footprint, ignoring c_2's far-off
    # position — should zoom in tight rather than out to fit everything.
    view.fit_to_positions({"c_1": (0.0, 0.0)})

    assert view.zoom > 1.0


def test_ensure_content_visible_with_no_scene_does_not_crash(qtbot):
    view = CanvasView()
    qtbot.addWidget(view)
    view.ensure_content_visible()


def test_ensure_content_visible_with_empty_scene_does_not_crash(qtbot):
    view = CanvasView()
    qtbot.addWidget(view)
    view.setScene(QGraphicsScene())
    view.ensure_content_visible()


def test_ensure_content_visible_does_nothing_when_already_in_view(qtbot):
    document = Document(name="Test")
    document.add_card(Card(id="c_1", x=0.0, y=0.0))
    document.add_card(Card(id="c_2", x=50.0, y=50.0))
    scene = CanvasScene(document)
    view = CanvasView()
    qtbot.addWidget(view)
    view.resize(800, 600)
    view.setScene(scene)
    view.centerOn(scene.itemsBoundingRect().center())
    zoom_before = view.zoom
    center_before = view.mapToScene(view.viewport().rect().center())

    view.ensure_content_visible()

    assert view.zoom == zoom_before
    assert view.mapToScene(view.viewport().rect().center()) == center_before


def test_ensure_content_visible_pans_without_zooming_when_content_fits_but_out_of_view(qtbot):
    document = Document(name="Test")
    document.add_card(Card(id="c_1", x=0.0, y=0.0))
    document.add_card(Card(id="c_2", x=50.0, y=50.0))
    scene = CanvasScene(document)
    view = CanvasView()
    qtbot.addWidget(view)
    view.resize(800, 600)
    view.setScene(scene)
    # Qt clamps centerOn() to the scene rect, which defaults to just past
    # the items' own bounds — widen it so we can actually scroll away.
    scene.setSceneRect(-10000.0, -10000.0, 20000.0, 20000.0)
    view.centerOn(QPointF(5000.0, 5000.0))  # scroll far away from the cards
    zoom_before = view.zoom
    visible_rect_before = view.mapToScene(view.viewport().rect()).boundingRect()
    assert not visible_rect_before.contains(scene.itemsBoundingRect())

    view.ensure_content_visible()

    assert view.zoom == zoom_before
    visible_rect_after = view.mapToScene(view.viewport().rect()).boundingRect()
    assert visible_rect_after.contains(scene.itemsBoundingRect())


def test_ensure_content_visible_zooms_out_when_content_does_not_fit(qtbot):
    document = Document(name="Test")
    document.add_card(Card(id="c_1", x=0.0, y=0.0))
    document.add_card(Card(id="c_2", x=2000.0, y=2000.0))
    scene = CanvasScene(document)
    view = CanvasView()
    qtbot.addWidget(view)
    view.resize(800, 600)
    view.setScene(scene)

    view.ensure_content_visible()

    assert view.zoom == view.transform().m11()
    assert view.zoom < 1.0


def test_double_click_on_empty_space_creates_card(qtbot):
    document = Document(name="Test")
    scene = CanvasScene(document, undo_stack=QUndoStack())
    view = CanvasView()
    qtbot.addWidget(view)
    view.resize(800, 600)
    view.setScene(scene)

    received = []
    view.cardCreated.connect(received.append)

    widget_pos = view.mapFromScene(QPointF(0.0, 0.0))
    view.mouseDoubleClickEvent(_double_click_event(widget_pos.x(), widget_pos.y()))

    assert len(document.cards) == 1
    assert len(received) == 1


def test_double_click_on_existing_card_does_not_create_new_card(qtbot):
    document = Document(name="Test")
    document.add_card(Card(id="c_1", x=0.0, y=0.0))
    scene = CanvasScene(document, undo_stack=QUndoStack())
    view = CanvasView()
    qtbot.addWidget(view)
    view.resize(800, 600)
    view.setScene(scene)

    width, height = DEFAULT_CARD_SIZE
    widget_pos = view.mapFromScene(QPointF(width / 2, height / 2))
    view.mouseDoubleClickEvent(_double_click_event(widget_pos.x(), widget_pos.y()))

    assert len(document.cards) == 1


def test_double_click_while_link_mode_active_does_not_create_card(qtbot):
    document = Document(name="Test")
    scene = CanvasScene(document, undo_stack=QUndoStack())
    view = CanvasView()
    qtbot.addWidget(view)
    view.resize(800, 600)
    view.setScene(scene)
    view.link_controller.set_active(True)

    widget_pos = view.mapFromScene(QPointF(0.0, 0.0))
    view.mouseDoubleClickEvent(_double_click_event(widget_pos.x(), widget_pos.y()))

    assert len(document.cards) == 0


def test_activating_link_mode_shows_cross_cursor_on_cards(qtbot):
    document = Document(name="Test")
    document.add_card(Card(id="c_1", x=0.0, y=0.0))
    scene = CanvasScene(document, undo_stack=QUndoStack())
    view = CanvasView()
    qtbot.addWidget(view)
    view.setScene(scene)

    view.link_controller.set_active(True)

    assert scene.item_for_card("c_1").cursor().shape() == Qt.CursorShape.CrossCursor

    view.link_controller.set_active(False)

    assert not scene.item_for_card("c_1").hasCursor()


def test_setting_scene_while_link_mode_active_applies_cross_cursor(qtbot):
    document = Document(name="Test")
    document.add_card(Card(id="c_1", x=0.0, y=0.0))
    scene = CanvasScene(document, undo_stack=QUndoStack())
    view = CanvasView()
    qtbot.addWidget(view)
    view.setScene(CanvasScene(Document(name="Empty")))
    view.link_controller.set_active(True)

    view.setScene(scene)

    assert scene.item_for_card("c_1").cursor().shape() == Qt.CursorShape.CrossCursor


def test_double_click_without_scene_does_not_crash(qtbot):
    view = CanvasView()
    qtbot.addWidget(view)

    view.mouseDoubleClickEvent(_double_click_event(10.0, 10.0))  # must not raise


def _document_with_stack() -> Document:
    document = Document(name="Test")
    document.add_card(Card(id="c_1", x=0.0, y=0.0, stack_id="s_1"))
    document.add_card(Card(id="c_2", x=0.0, y=0.0, stack_id="s_1"))
    document.add_stack(Stack(id="s_1", card_ids=["c_1", "c_2"], x=0.0, y=0.0))
    return document


def test_stack_overlay_constructed_alongside_color_key_overlay(qtbot):
    view = CanvasView()
    qtbot.addWidget(view)

    from indexcards.canvas.stack_overlay import StackOverlay

    assert isinstance(view.stack_overlay, StackOverlay)


def test_resize_repositions_open_stack_overlay(qtbot):
    document = _document_with_stack()
    scene = CanvasScene(document, undo_stack=QUndoStack())
    view = CanvasView()
    qtbot.addWidget(view)
    view.resize(800, 600)
    view.setScene(scene)
    view.stack_overlay.open("s_1", document, QUndoStack())
    old_size = view.size()

    view.resize(400, 300)
    view.resizeEvent(QResizeEvent(view.size(), old_size))

    assert view.stack_overlay.size().width() == view.viewport().width()
    assert view.stack_overlay.size().height() == view.viewport().height()


def test_setting_new_scene_closes_open_stack_overlay(qtbot):
    document = _document_with_stack()
    scene = CanvasScene(document, undo_stack=QUndoStack())
    view = CanvasView()
    qtbot.addWidget(view)
    view.setScene(scene)
    view.stack_overlay.open("s_1", document, QUndoStack())
    assert view.stack_overlay.is_open is True

    view.setScene(CanvasScene(Document(name="Other")))

    assert view.stack_overlay.is_open is False


def _expected_scene_rect(view: CanvasView, bounds):
    viewport_size = view.viewport().size()
    margin_x = (viewport_size.width() - PAN_OVERSCAN_PX) / view.zoom
    margin_y = (viewport_size.height() - PAN_OVERSCAN_PX) / view.zoom
    return bounds.adjusted(-margin_x, -margin_y, margin_x, margin_y)


def _assert_rects_match(actual, expected) -> None:
    assert actual.left() == pytest.approx(expected.left())
    assert actual.top() == pytest.approx(expected.top())
    assert actual.right() == pytest.approx(expected.right())
    assert actual.bottom() == pytest.approx(expected.bottom())


def test_scene_rect_extends_beyond_items_bounding_rect_for_panning(qtbot):
    document = Document(name="Test")
    document.add_card(Card(id="c_1", x=0.0, y=0.0))
    scene = CanvasScene(document)
    view = CanvasView()
    qtbot.addWidget(view)
    view.resize(800, 600)

    view.setScene(scene)

    _assert_rects_match(scene.sceneRect(), _expected_scene_rect(view, scene.itemsBoundingRect()))


def test_scene_rect_margin_shrinks_in_scene_units_when_zoomed_in(qtbot):
    document = Document(name="Test")
    document.add_card(Card(id="c_1", x=0.0, y=0.0))
    scene = CanvasScene(document)
    view = CanvasView()
    qtbot.addWidget(view)
    view.resize(800, 600)
    view.setScene(scene)
    bounds_width = scene.itemsBoundingRect().width()
    margin_at_1x = (scene.sceneRect().width() - bounds_width) / 2.0

    view.zoom_by(2.0)

    margin_at_2x = (scene.sceneRect().width() - bounds_width) / 2.0
    # Same on-screen overscan needs half the scene-unit margin at 2x zoom.
    assert margin_at_2x == pytest.approx(margin_at_1x / 2.0, rel=0.05)


def test_scene_rect_updates_on_resize(qtbot):
    document = Document(name="Test")
    document.add_card(Card(id="c_1", x=0.0, y=0.0))
    scene = CanvasScene(document)
    view = CanvasView()
    qtbot.addWidget(view)
    view.resize(800, 600)
    view.setScene(scene)
    old_size = view.size()

    # An unshown top-level widget's .resize() updates .size() immediately
    # but defers actually delivering the QResizeEvent, so call the handler
    # directly (same pattern this test file already uses for other event
    # handlers) rather than relying on that delivery happening in time.
    view.resize(400, 300)
    view.resizeEvent(QResizeEvent(view.size(), old_size))

    _assert_rects_match(scene.sceneRect(), _expected_scene_rect(view, scene.itemsBoundingRect()))


def test_scene_rect_updates_when_card_added(qtbot):
    document = Document(name="Test")
    document.add_card(Card(id="c_1", x=0.0, y=0.0))
    scene = CanvasScene(document)
    view = CanvasView()
    qtbot.addWidget(view)
    view.resize(800, 600)
    view.setScene(scene)

    document.add_card(Card(id="c_2", x=2000.0, y=2000.0))

    _assert_rects_match(scene.sceneRect(), _expected_scene_rect(view, scene.itemsBoundingRect()))


def test_scene_rect_updates_when_card_moved(qtbot):
    document = Document(name="Test")
    document.add_card(Card(id="c_1", x=0.0, y=0.0))
    scene = CanvasScene(document)
    view = CanvasView()
    qtbot.addWidget(view)
    view.resize(800, 600)
    view.setScene(scene)

    document.set_card_position("c_1", 3000.0, 3000.0)

    _assert_rects_match(scene.sceneRect(), _expected_scene_rect(view, scene.itemsBoundingRect()))


def test_scene_rect_updates_when_card_removed(qtbot):
    document = Document(name="Test")
    document.add_card(Card(id="c_1", x=0.0, y=0.0))
    document.add_card(Card(id="c_2", x=2000.0, y=2000.0))
    scene = CanvasScene(document)
    view = CanvasView()
    qtbot.addWidget(view)
    view.resize(800, 600)
    view.setScene(scene)

    document.remove_card("c_2")

    _assert_rects_match(scene.sceneRect(), _expected_scene_rect(view, scene.itemsBoundingRect()))


def test_scene_rect_shrinks_to_margin_around_origin_when_no_cards_remain(qtbot):
    document = Document(name="Test")
    document.add_card(Card(id="c_1", x=0.0, y=0.0))
    scene = CanvasScene(document)
    view = CanvasView()
    qtbot.addWidget(view)
    view.resize(800, 600)
    view.setScene(scene)

    document.remove_card("c_1")

    # No items left: falls back to Qt's own auto-derived sceneRect would
    # actually be *wrong* here — that's a high-water mark that doesn't
    # shrink when items are removed, so it'd report the last card's stale
    # tight bounds. Instead this is a fresh margin-only rect centered on
    # the origin (a zero-size "bounds" adjusted outward by the same
    # viewport/zoom-derived margin as any other content).
    _assert_rects_match(scene.sceneRect(), _expected_scene_rect(view, scene.itemsBoundingRect()))


def test_scene_rect_survives_switching_to_a_new_scene(qtbot):
    document_1 = Document(name="One")
    document_1.add_card(Card(id="c_1", x=0.0, y=0.0))
    scene_1 = CanvasScene(document_1)
    document_2 = Document(name="Two")
    document_2.add_card(Card(id="c_2", x=5000.0, y=5000.0))
    scene_2 = CanvasScene(document_2)

    view = CanvasView()
    qtbot.addWidget(view)
    view.resize(800, 600)
    view.setScene(scene_1)

    view.setScene(scene_2)

    expected = _expected_scene_rect(view, scene_2.itemsBoundingRect())
    _assert_rects_match(scene_2.sceneRect(), expected)
    # The old scene's contentBoundsChanged must no longer drive this view —
    # moving a card in it should not raise (disconnected) or touch scene_2.
    document_1.set_card_position("c_1", 9000.0, 9000.0)


def _context_menu_event(x: int, y: int) -> QContextMenuEvent:
    point = QPoint(x, y)
    return QContextMenuEvent(QContextMenuEvent.Reason.Mouse, point, point)


def test_build_background_context_menu_offers_change_background(qtbot):
    view = CanvasView()
    qtbot.addWidget(view)

    _menu, change_background_action = view._build_background_context_menu()

    assert change_background_action.text() == "Change Background"


def test_handle_background_context_menu_choice_emits_when_matched(qtbot):
    view = CanvasView()
    qtbot.addWidget(view)
    _menu, change_background_action = view._build_background_context_menu()
    received = []
    view.backgroundChangeRequested.connect(lambda: received.append(True))

    view._handle_background_context_menu_choice(change_background_action, change_background_action)

    assert received == [True]


def test_handle_background_context_menu_choice_no_emit_when_dismissed(qtbot):
    view = CanvasView()
    qtbot.addWidget(view)
    _menu, change_background_action = view._build_background_context_menu()
    received = []
    view.backgroundChangeRequested.connect(lambda: received.append(True))

    view._handle_background_context_menu_choice(None, change_background_action)

    assert received == []


def test_context_menu_without_scene_does_not_crash(qtbot):
    view = CanvasView()
    qtbot.addWidget(view)

    view.contextMenuEvent(_context_menu_event(10, 10))  # must not raise
