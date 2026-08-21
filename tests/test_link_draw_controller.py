from PySide6.QtCore import QPoint, QPointF
from PySide6.QtWidgets import QGraphicsScene

from indexcards.canvas.card_item import CardItem
from indexcards.canvas.link_draw_controller import LinkDrawController
from indexcards.models.card import Card
from indexcards.models.document import Document


class _FakeView:
    """Duck-typed stand-in for CanvasView: treats widget coords as scene
    coords directly, so tests don't depend on real viewport transforms."""

    def __init__(self, scene: QGraphicsScene) -> None:
        self._scene = scene

    def mapToScene(self, point: QPoint) -> QPointF:
        return QPointF(point)

    def scene(self) -> QGraphicsScene:
        return self._scene


class _FakeMouseEvent:
    def __init__(self, x: float, y: float) -> None:
        self._pos = QPointF(x, y)

    def position(self) -> QPointF:
        return self._pos


def _build_scene_with_two_cards() -> tuple[QGraphicsScene, CardItem, CardItem]:
    document = Document(name="Test")
    document.add_card(Card(id="c_1", x=0.0, y=0.0))
    document.add_card(Card(id="c_2", x=300.0, y=0.0))
    scene = QGraphicsScene()
    item1 = CardItem("c_1", document)
    item1.setPos(0.0, 0.0)
    scene.addItem(item1)
    item2 = CardItem("c_2", document)
    item2.setPos(300.0, 0.0)
    scene.addItem(item2)
    return scene, item1, item2


def test_inactive_controller_consumes_nothing(qtbot):
    scene, *_ = _build_scene_with_two_cards()
    controller = LinkDrawController(_FakeView(scene))

    assert controller.mouse_press(_FakeMouseEvent(50, 50)) is False
    assert controller.mouse_move(_FakeMouseEvent(60, 60)) is False
    assert controller.mouse_release(_FakeMouseEvent(60, 60)) is False


def test_press_on_empty_space_is_not_consumed(qtbot):
    scene, *_ = _build_scene_with_two_cards()
    controller = LinkDrawController(_FakeView(scene))
    controller.set_active(True)

    assert controller.mouse_press(_FakeMouseEvent(9999, 9999)) is False


def test_drag_from_card_to_card_emits_link_requested(qtbot):
    scene, *_ = _build_scene_with_two_cards()
    controller = LinkDrawController(_FakeView(scene))
    controller.set_active(True)
    received = []
    controller.linkRequested.connect(lambda s, t: received.append((s, t)))

    assert controller.mouse_press(_FakeMouseEvent(50, 50)) is True
    assert controller.mouse_move(_FakeMouseEvent(320, 20)) is True
    assert controller.mouse_release(_FakeMouseEvent(320, 20)) is True

    assert received == [("c_1", "c_2")]


def test_drag_released_on_empty_space_cancels(qtbot):
    scene, *_ = _build_scene_with_two_cards()
    controller = LinkDrawController(_FakeView(scene))
    controller.set_active(True)
    received = []
    controller.linkRequested.connect(lambda s, t: received.append((s, t)))

    controller.mouse_press(_FakeMouseEvent(50, 50))
    controller.mouse_release(_FakeMouseEvent(9999, 9999))

    assert received == []


def test_drag_released_on_same_card_cancels(qtbot):
    scene, *_ = _build_scene_with_two_cards()
    controller = LinkDrawController(_FakeView(scene))
    controller.set_active(True)
    received = []
    controller.linkRequested.connect(lambda s, t: received.append((s, t)))

    controller.mouse_press(_FakeMouseEvent(50, 50))
    controller.mouse_release(_FakeMouseEvent(60, 60))

    assert received == []


def test_deactivating_mid_drag_cancels_temp_line(qtbot):
    scene, *_ = _build_scene_with_two_cards()
    controller = LinkDrawController(_FakeView(scene))
    controller.set_active(True)

    controller.mouse_press(_FakeMouseEvent(50, 50))
    assert controller._temp_line is not None

    controller.set_active(False)
    assert controller._temp_line is None
