from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QContextMenuEvent, QMouseEvent, QUndoStack
from PySide6.QtWidgets import QGraphicsScene

from indexcards.canvas.canvas_scene import CanvasScene
from indexcards.canvas.canvas_view import MAX_ZOOM, MIN_ZOOM, CanvasView
from indexcards.models.card import DEFAULT_CARD_SIZE, Card
from indexcards.models.document import Document


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
