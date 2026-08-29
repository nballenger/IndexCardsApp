from PySide6.QtCore import QRect
from PySide6.QtGui import QImage, QPainter
from PySide6.QtWidgets import QComboBox, QStyleOptionViewItem

from indexcards.list_view.color_delegate import ColorDelegate
from indexcards.models.document import Document

_SWATCH_WIDTH = 16


class _FakeModel:
    def __init__(self, document: Document, slot_id: str) -> None:
        self.document = document
        self._slot_id = slot_id

    def data(self, index, role):
        return self._slot_id


class _FakeIndex:
    def __init__(self, model: _FakeModel) -> None:
        self._model = model

    def model(self) -> _FakeModel:
        return self._model


def _paint_and_capture_swatch(width: int, height: int, monkeypatch) -> QRect:
    captured = []
    monkeypatch.setattr(QPainter, "drawRect", lambda self, rect: captured.append(rect))

    delegate = ColorDelegate()
    option = QStyleOptionViewItem()
    option.rect = QRect(0, 0, width, height)
    index = _FakeIndex(_FakeModel(Document(name="Test"), "slot_white"))

    image = QImage(max(width, 1), max(height, 1), QImage.Format.Format_ARGB32)
    painter = QPainter(image)
    try:
        delegate.paint(painter, option, index)
    finally:
        painter.end()

    return captured[0]


def test_swatch_is_horizontally_centered(monkeypatch):
    swatch = _paint_and_capture_swatch(100, 30, monkeypatch)

    expected_left = (100 - _SWATCH_WIDTH) // 2
    assert swatch.left() == expected_left
    assert swatch.width() == _SWATCH_WIDTH


def test_swatch_stays_centered_in_a_wider_column(monkeypatch):
    swatch = _paint_and_capture_swatch(200, 30, monkeypatch)

    expected_left = (200 - _SWATCH_WIDTH) // 2
    assert swatch.left() == expected_left


def test_editor_combo_has_swatch_icon_per_entry(qtbot):
    delegate = ColorDelegate()
    document = Document(name="Test")
    editor = delegate.createEditor(None, None, _FakeIndex(_FakeModel(document, "slot_white")))
    qtbot.addWidget(editor)

    assert isinstance(editor, QComboBox)
    assert editor.count() == len(document.theme.slots)
    for position in range(editor.count()):
        assert not editor.itemIcon(position).isNull()


def test_editor_combo_excludes_orphaned_slots(qtbot):
    delegate = ColorDelegate()
    document = Document(name="Test")
    document.theme.slots[0].orphaned = True

    editor = delegate.createEditor(None, None, _FakeIndex(_FakeModel(document, "slot_white")))
    qtbot.addWidget(editor)

    assert editor.count() == len(document.theme.slots) - 1


def test_set_editor_data_selects_current_slot(qtbot):
    delegate = ColorDelegate()
    document = Document(name="Test")
    target_slot = document.theme.slots[2]

    editor = delegate.createEditor(None, None, _FakeIndex(_FakeModel(document, target_slot.id)))
    qtbot.addWidget(editor)
    delegate.setEditorData(editor, _FakeIndex(_FakeModel(document, target_slot.id)))

    assert editor.currentData() == target_slot.id
