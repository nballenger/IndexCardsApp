from PySide6.QtCore import Qt

from indexcards.canvas.canvas_view import MAX_ZOOM, MIN_ZOOM, CanvasView


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
