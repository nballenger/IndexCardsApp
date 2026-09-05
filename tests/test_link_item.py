from PySide6.QtCore import QEvent, QPointF, QRectF
from PySide6.QtGui import QImage, QPainter, QUndoStack
from PySide6.QtWidgets import (
    QGraphicsScene,
    QGraphicsSceneContextMenuEvent,
    QStyleOptionGraphicsItem,
)

from indexcards.canvas.card_item import CardItem
from indexcards.canvas.link_item import LinkItem, _edge_center_toward
from indexcards.models.card import DEFAULT_CARD_SIZE, Card
from indexcards.models.document import Document
from indexcards.models.link import Link

_WIDTH, _HEIGHT = DEFAULT_CARD_SIZE
_CENTER_OFFSET = QPointF(_WIDTH / 2, _HEIGHT / 2)
_RECT = QRectF(0.0, 0.0, 200.0, 120.0)


def _document_with_two_cards() -> Document:
    document = Document(name="Test")
    document.add_card(Card(id="c_1", x=0.0, y=0.0))
    document.add_card(Card(id="c_2", x=300.0, y=0.0))
    document.add_link(Link(id="l_1", source="c_1", target="c_2"))
    return document


def test_edge_center_toward_right():
    assert _edge_center_toward(_RECT, QPointF(1.0, 0.0)) == QPointF(200.0, 60.0)


def test_edge_center_toward_left():
    assert _edge_center_toward(_RECT, QPointF(-1.0, 0.0)) == QPointF(0.0, 60.0)


def test_edge_center_toward_bottom():
    assert _edge_center_toward(_RECT, QPointF(0.0, 1.0)) == QPointF(100.0, 120.0)


def test_edge_center_toward_top():
    assert _edge_center_toward(_RECT, QPointF(0.0, -1.0)) == QPointF(100.0, 0.0)


def test_edge_center_toward_picks_dominant_axis_horizontal():
    # A shallow diagonal, mostly rightward -- horizontal wins even though
    # there's a small vertical component too.
    assert _edge_center_toward(_RECT, QPointF(10.0, 1.0)) == QPointF(200.0, 60.0)


def test_edge_center_toward_picks_dominant_axis_vertical():
    assert _edge_center_toward(_RECT, QPointF(1.0, 10.0)) == QPointF(100.0, 120.0)


def test_link_item_line_anchors_to_facing_edge_centers(qtbot):
    # c_1 at (0,0), c_2 at (300,0): centers are (100,60) and (400,60) --
    # directly to the right, so each end anchors to the horizontal edge
    # facing the other card (right edge of c_1, left edge of c_2), not
    # either card's center.
    document = _document_with_two_cards()
    item1 = CardItem("c_1", document)
    item1.setPos(0.0, 0.0)
    item2 = CardItem("c_2", document)
    item2.setPos(300.0, 0.0)

    link = LinkItem("l_1", item1, item2, document)

    line = link.line()
    assert line.p1() == QPointF(_WIDTH, _HEIGHT / 2)
    assert line.p2() == QPointF(300.0, _HEIGHT / 2)


def test_link_item_line_follows_card_move_and_switches_edge(qtbot):
    document = _document_with_two_cards()
    item1 = CardItem("c_1", document)
    item1.setPos(0.0, 0.0)
    item2 = CardItem("c_2", document)
    item2.setPos(300.0, 0.0)
    link = LinkItem("l_1", item1, item2, document)

    # c_1's new center (600,660) sits above-and-left of c_2's center
    # (400,60) with a much larger vertical gap than horizontal, so the
    # anchor should switch to the vertical edges (top of c_1, bottom of
    # c_2) rather than staying on the horizontal ones.
    item1.setPos(500.0, 600.0)

    line = link.line()
    assert line.p1() == QPointF(600.0, 600.0)
    assert line.p2() == QPointF(400.0, 120.0)


def test_disconnect_listeners_stops_line_from_following(qtbot):
    document = _document_with_two_cards()
    item1 = CardItem("c_1", document)
    item1.setPos(0.0, 0.0)
    item2 = CardItem("c_2", document)
    item2.setPos(300.0, 0.0)
    link = LinkItem("l_1", item1, item2, document)

    link.disconnect_listeners()
    item1.setPos(999.0, 999.0)

    line = link.line()
    assert line.p1() == QPointF(_WIDTH, _HEIGHT / 2)


def test_set_dimmed_changes_pen(qtbot):
    document = _document_with_two_cards()
    item1 = CardItem("c_1", document)
    item2 = CardItem("c_2", document)
    link = LinkItem("l_1", item1, item2, document)
    normal_pen = link.pen()

    link.set_dimmed(True)
    dimmed_pen = link.pen()
    assert dimmed_pen.color() != normal_pen.color()

    link.set_dimmed(False)
    assert link.pen().color() == normal_pen.color()


def test_pen_reflects_theme_link_color_and_weight(qtbot):
    document = _document_with_two_cards()
    document.theme.link_color_mode = "black"
    document.theme.link_weight = 5
    item1 = CardItem("c_1", document)
    item2 = CardItem("c_2", document)

    link = LinkItem("l_1", item1, item2, document)

    assert link.pen().color().name() == "#000000"
    assert link.pen().width() == 5


def test_refresh_picks_up_a_changed_theme(qtbot):
    document = _document_with_two_cards()
    item1 = CardItem("c_1", document)
    item2 = CardItem("c_2", document)
    link = LinkItem("l_1", item1, item2, document)

    document.theme.link_color_mode = "white"
    document.theme.link_weight = 4
    link.refresh()

    assert link.pen().color().name() == "#ffffff"
    assert link.pen().width() == 4


def test_set_emphasized_toggles_a_drop_shadow_effect(qtbot):
    document = _document_with_two_cards()
    item1 = CardItem("c_1", document)
    item2 = CardItem("c_2", document)
    link = LinkItem("l_1", item1, item2, document)

    link.set_emphasized(True)
    assert link.graphicsEffect() is not None

    link.set_emphasized(False)
    assert link.graphicsEffect() is None


def test_set_emphasized_true_twice_does_not_replace_the_effect(qtbot):
    document = _document_with_two_cards()
    item1 = CardItem("c_1", document)
    item2 = CardItem("c_2", document)
    link = LinkItem("l_1", item1, item2, document)

    link.set_emphasized(True)
    first_effect = link.graphicsEffect()
    link.set_emphasized(True)

    assert link.graphicsEffect() is first_effect


def test_refresh_recolors_the_emphasis_effect_while_emphasized(qtbot):
    document = _document_with_two_cards()
    item1 = CardItem("c_1", document)
    item2 = CardItem("c_2", document)
    link = LinkItem("l_1", item1, item2, document)
    link.set_emphasized(True)

    document.set_canvas_background_color("#16ffff")  # matches the halo color
    link.refresh()

    assert link.graphicsEffect().color().name() == "#000000"


def test_bounding_rect_is_wider_than_the_line_itself():
    # The margin is constant regardless of the *current* line_ending
    # (avoids prepareGeometryChange bookkeeping when it changes at
    # runtime) -- so it's already wider than the bare line even at the
    # default "none".
    document = _document_with_two_cards()
    item1 = CardItem("c_1", document)
    item2 = CardItem("c_2", document)
    link = LinkItem("l_1", item1, item2, document)

    plain_rect = QRectF(link.line().p1(), link.line().p2()).normalized()
    assert link.boundingRect().width() > plain_rect.width()
    assert link.boundingRect().height() > plain_rect.height()


def test_shape_is_wider_than_the_thin_pen_stroke():
    # A default 2px-weight line has a shape() much narrower than the
    # minimum hit width if it weren't widened -- confirms the click target
    # is meaningfully bigger than the visual stroke.
    document = _document_with_two_cards()
    item1 = CardItem("c_1", document)
    item1.setPos(0.0, 0.0)
    item2 = CardItem("c_2", document)
    item2.setPos(300.0, 0.0)
    link = LinkItem("l_1", item1, item2, document)

    midpoint = QPointF(
        (link.line().p1().x() + link.line().p2().x()) / 2,
        (link.line().p1().y() + link.line().p2().y()) / 2,
    )
    # A point 6px above the line's midpoint (well outside a 2px-wide
    # stroke, but inside a 16px-wide one) should still register as a hit.
    off_line_point = QPointF(midpoint.x(), midpoint.y() - 6.0)
    assert link.shape().contains(off_line_point)


def test_shape_does_not_shrink_below_a_thick_pen():
    document = _document_with_two_cards()
    document.set_theme_link_weight(5)
    item1 = CardItem("c_1", document)
    item1.setPos(0.0, 0.0)
    item2 = CardItem("c_2", document)
    item2.setPos(300.0, 0.0)
    link = LinkItem("l_1", item1, item2, document)

    assert link.pen().widthF() == 5
    # The hit area must never be narrower than the pen it's covering.
    shape_bounds = link.shape().boundingRect()
    assert shape_bounds.height() >= link.pen().widthF()


def test_bounding_rect_covers_the_widened_shape():
    document = _document_with_two_cards()
    item1 = CardItem("c_1", document)
    item1.setPos(0.0, 0.0)
    item2 = CardItem("c_2", document)
    item2.setPos(300.0, 0.0)
    link = LinkItem("l_1", item1, item2, document)

    assert link.boundingRect().contains(link.shape().boundingRect())


def test_paint_does_not_crash_for_every_line_ending(qtbot):
    document = _document_with_two_cards()
    item1 = CardItem("c_1", document)
    item2 = CardItem("c_2", document)
    link = LinkItem("l_1", item1, item2, document)

    image = QImage(400, 400, QImage.Format.Format_ARGB32)
    option = QStyleOptionGraphicsItem()
    for ending in ("none", "to_target", "to_source", "both"):
        document.set_link_line_ending("l_1", ending)
        painter = QPainter(image)
        try:
            link.paint(painter, option)
        finally:
            painter.end()


def test_refresh_picks_up_a_changed_line_ending(qtbot):
    document = _document_with_two_cards()
    item1 = CardItem("c_1", document)
    item2 = CardItem("c_2", document)
    link = LinkItem("l_1", item1, item2, document)
    assert link._line_ending == "none"

    document.get_link("l_1").line_ending = "both"  # mutate in place, no signal
    link.refresh()

    assert link._line_ending == "both"


def test_context_menu_reflects_current_line_ending(qtbot):
    document = _document_with_two_cards()
    document.set_link_line_ending("l_1", "to_target")
    item1 = CardItem("c_1", document)
    item2 = CardItem("c_2", document)
    link = LinkItem("l_1", item1, item2, document, undo_stack=QUndoStack())

    _menu, ending_actions = link._build_context_menu()

    checked = [value for action, value in ending_actions.items() if action.isChecked()]
    assert checked == ["to_target"]


def test_context_menu_has_no_icon_for_no_arrows(qtbot):
    document = _document_with_two_cards()
    item1 = CardItem("c_1", document)
    item2 = CardItem("c_2", document)
    link = LinkItem("l_1", item1, item2, document, undo_stack=QUndoStack())

    _menu, ending_actions = link._build_context_menu()

    no_arrows_action = next(a for a, v in ending_actions.items() if v == "none")
    assert no_arrows_action.icon().isNull()


def test_context_menu_without_undo_stack_does_not_crash(qtbot):
    document = _document_with_two_cards()
    item1 = CardItem("c_1", document)
    item2 = CardItem("c_2", document)
    link = LinkItem("l_1", item1, item2, document)  # no undo_stack
    scene = QGraphicsScene()
    scene.addItem(link)

    event = QGraphicsSceneContextMenuEvent(QEvent.Type.GraphicsSceneContextMenu)
    link.contextMenuEvent(event)  # must not raise, must not pop a real menu


def _document_with_two_links() -> Document:
    document = Document(name="Test")
    document.add_card(Card(id="c_1", x=0.0, y=0.0))
    document.add_card(Card(id="c_2", x=300.0, y=0.0))
    document.add_card(Card(id="c_3", x=600.0, y=0.0))
    document.add_link(Link(id="l_1", source="c_1", target="c_2"))
    document.add_link(Link(id="l_2", source="c_2", target="c_3"))
    return document


def test_selection_scoped_link_ids_is_just_this_link_when_unselected():
    document = _document_with_two_links()
    item1 = CardItem("c_1", document)
    item2 = CardItem("c_2", document)
    item3 = CardItem("c_3", document)
    link1 = LinkItem("l_1", item1, item2, document)
    link2 = LinkItem("l_2", item2, item3, document)
    scene = QGraphicsScene()
    for item in (item1, item2, item3, link1, link2):
        scene.addItem(item)
    link2.setSelected(True)  # a different link is selected, not this one

    assert link1._selection_scoped_link_ids() == ["l_1"]


def test_selection_scoped_link_ids_is_whole_selection_when_part_of_it():
    document = _document_with_two_links()
    item1 = CardItem("c_1", document)
    item2 = CardItem("c_2", document)
    item3 = CardItem("c_3", document)
    link1 = LinkItem("l_1", item1, item2, document)
    link2 = LinkItem("l_2", item2, item3, document)
    scene = QGraphicsScene()
    for item in (item1, item2, item3, link1, link2):
        scene.addItem(item)
    link1.setSelected(True)
    link2.setSelected(True)

    assert set(link1._selection_scoped_link_ids()) == {"l_1", "l_2"}
