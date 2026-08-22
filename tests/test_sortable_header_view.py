from PySide6.QtCore import QEvent, QPoint, Qt
from PySide6.QtGui import QMouseEvent, QStandardItemModel

from indexcards.list_view.sortable_header_view import SortableColumnsHeaderView


def _header_with_columns(column_count: int) -> SortableColumnsHeaderView:
    model = QStandardItemModel(1, column_count)
    header = SortableColumnsHeaderView(frozenset({0, 1}))
    header.setModel(model)
    for column in range(column_count):
        header.resizeSection(column, 50)
    return header


def _press_event(pos: QPoint) -> QMouseEvent:
    return QMouseEvent(
        QEvent.Type.MouseButtonPress,
        pos,
        pos,  # globalPos — unused by the header's own logic, so just reuse pos
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )


def test_is_sortable_click_true_for_sortable_column():
    header = _header_with_columns(3)
    pos = QPoint(header.sectionViewportPosition(0) + 5, 5)

    assert header._is_sortable_click(_press_event(pos)) is True


def test_is_sortable_click_false_for_non_sortable_column():
    header = _header_with_columns(3)
    pos = QPoint(header.sectionViewportPosition(2) + 5, 5)

    assert header._is_sortable_click(_press_event(pos)) is False


def test_click_on_non_sortable_column_leaves_indicator_unchanged():
    header = _header_with_columns(3)
    header.setSectionsClickable(True)
    header.setSortIndicator(1, Qt.SortOrder.AscendingOrder)
    pos = QPoint(header.sectionViewportPosition(2) + 5, 5)

    header.mousePressEvent(_press_event(pos))
    header.mouseReleaseEvent(_press_event(pos))

    # If our override hadn't blocked this, a real click-to-sort would have
    # moved the indicator to section 2 — it stays at 1, proving it did.
    assert header.sortIndicatorSection() == 1


def test_click_on_sortable_column_moves_indicator_there():
    header = _header_with_columns(3)
    header.setSectionsClickable(True)
    header.setSortIndicator(1, Qt.SortOrder.AscendingOrder)
    pos = QPoint(header.sectionViewportPosition(0) + 5, 5)

    header.mousePressEvent(_press_event(pos))
    header.mouseReleaseEvent(_press_event(pos))

    assert header.sortIndicatorSection() == 0
