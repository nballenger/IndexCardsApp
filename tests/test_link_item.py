import pytest
from PySide6.QtCore import QAbstractAnimation, QEvent, QPointF, QRectF
from PySide6.QtGui import QImage, QPainter, QUndoStack
from PySide6.QtWidgets import (
    QGraphicsScene,
    QGraphicsSceneContextMenuEvent,
    QStyleOptionGraphicsItem,
)

from indexcards.canvas.card_item import CardItem
from indexcards.canvas.link_item import (
    _FLASH_FADE_DURATION_MS,
    _FLASH_GROW_DURATION_MS,
    _FLASH_WEIGHT_END,
    _FLASH_WEIGHT_START,
    LinkItem,
    _closest_interval_points,
    _closest_points_between_rects,
    _pull_away_from_corner,
)
from indexcards.models.card import DEFAULT_CARD_SIZE, Card
from indexcards.models.document import Document
from indexcards.models.link import Link

_WIDTH, _HEIGHT = DEFAULT_CARD_SIZE


def _document_with_two_cards() -> Document:
    document = Document(name="Test")
    document.add_card(Card(id="c_1", x=0.0, y=0.0))
    document.add_card(Card(id="c_2", x=300.0, y=0.0))
    document.add_link(Link(id="l_1", source="c_1", target="c_2"))
    return document


def test_closest_interval_points_when_a_is_entirely_before_b():
    assert _closest_interval_points(0.0, 10.0, 20.0, 30.0) == (10.0, 20.0)


def test_closest_interval_points_when_b_is_entirely_before_a():
    assert _closest_interval_points(20.0, 30.0, 0.0, 10.0) == (20.0, 10.0)


def test_closest_interval_points_when_the_intervals_overlap():
    # Any point in the overlap ([5, 10]) is equally close on this axis --
    # the overlap's own midpoint is used for both.
    assert _closest_interval_points(0.0, 10.0, 5.0, 15.0) == (7.5, 7.5)


def test_closest_interval_points_when_the_intervals_just_touch():
    assert _closest_interval_points(0.0, 10.0, 10.0, 20.0) == (10.0, 10.0)


def test_closest_points_between_rects_directly_horizontal():
    # Two rects with identical y-ranges, separated in x: the shortest
    # segment is horizontal, landing on the facing edge-centers -- the
    # same result the old fixed-edge-center scheme gave for this case.
    rect_a = QRectF(0.0, 0.0, 200.0, 120.0)
    rect_b = QRectF(300.0, 0.0, 200.0, 120.0)
    point_a, point_b = _closest_points_between_rects(rect_a, rect_b)
    assert point_a == QPointF(200.0, 60.0)
    assert point_b == QPointF(300.0, 60.0)


def test_closest_points_between_rects_diagonal_avoids_facing_corners():
    # Separated in both x and y -- the raw shortest segment would run
    # corner-to-corner, but a corner attachment reads as confusing, so
    # each point is pulled inward along whichever edge the connecting
    # line is more nearly perpendicular to. Here the horizontal gap
    # (200) is larger than the vertical gap (180), so the line is
    # closer to horizontal and each point lands on a vertical (left or
    # right) edge, nudged up from the exact corner by rect_a/rect_b's
    # own 12px corner margin (10% of the 120px side height).
    rect_a = QRectF(0.0, 0.0, 200.0, 120.0)
    rect_b = QRectF(400.0, 300.0, 200.0, 120.0)
    point_a, point_b = _closest_points_between_rects(rect_a, rect_b)
    assert point_a == QPointF(200.0, 108.0)
    assert point_b == QPointF(400.0, 312.0)


def test_closest_points_between_rects_partial_vertical_overlap():
    # Separated horizontally, but the y-ranges partially overlap -- the
    # shortest segment is a horizontal line through the overlap, not a
    # corner-to-corner diagonal.
    rect_a = QRectF(0.0, 0.0, 200.0, 120.0)  # y: [0, 120]
    rect_b = QRectF(300.0, 60.0, 200.0, 120.0)  # y: [60, 180]
    point_a, point_b = _closest_points_between_rects(rect_a, rect_b)
    assert point_a.y() == point_b.y() == 90.0  # midpoint of the overlap [60, 120]
    assert point_a.x() == 200.0
    assert point_b.x() == 300.0


def test_pull_away_from_corner_leaves_a_safely_centered_point_untouched():
    rect = QRectF(0.0, 0.0, 200.0, 120.0)
    point = QPointF(200.0, 60.0)  # right edge, dead center -- well clear of any margin

    assert _pull_away_from_corner(rect, point, gap_x=100.0, gap_y=0.0) == point


def test_pull_away_from_corner_clamps_a_flat_edge_point_too_close_to_the_end():
    rect = QRectF(0.0, 0.0, 200.0, 120.0)
    # On the right edge (x=200), 5px from the top -- inside the 12px
    # (10% of the 120px side) margin, even though this isn't a literal
    # corner (gap_x/gap_y are irrelevant here since only one axis is on
    # the rect's own boundary).
    point = QPointF(200.0, 5.0)

    result = _pull_away_from_corner(rect, point, gap_x=999.0, gap_y=0.0)

    assert result == QPointF(200.0, 12.0)


def test_pull_away_from_corner_leaves_a_flat_edge_point_within_range_unchanged():
    rect = QRectF(0.0, 0.0, 200.0, 120.0)
    point = QPointF(50.0, 120.0)  # bottom edge, 50px from the left -- well inside [20, 180]

    result = _pull_away_from_corner(rect, point, gap_x=0.0, gap_y=999.0)

    assert result == point


def test_pull_away_from_corner_exact_corner_prefers_vertical_edge_when_horizontal_gap_dominates():
    rect = QRectF(0.0, 0.0, 200.0, 120.0)
    point = QPointF(200.0, 120.0)  # bottom-right corner

    result = _pull_away_from_corner(rect, point, gap_x=500.0, gap_y=100.0)

    # x (the vertical right edge) stays pinned; y is pulled up off the corner.
    assert result == QPointF(200.0, 108.0)


def test_pull_away_from_corner_exact_corner_prefers_horizontal_edge_when_vertical_gap_dominates():
    rect = QRectF(0.0, 0.0, 200.0, 120.0)
    point = QPointF(200.0, 120.0)  # bottom-right corner

    result = _pull_away_from_corner(rect, point, gap_x=100.0, gap_y=500.0)

    # y (the horizontal bottom edge) stays pinned; x is pulled left off the corner.
    assert result == QPointF(180.0, 120.0)


def test_pull_away_from_corner_returns_unchanged_point_when_rects_overlap_both_axes():
    rect = QRectF(0.0, 0.0, 200.0, 120.0)
    point = QPointF(100.0, 60.0)  # interior point, on neither edge

    assert _pull_away_from_corner(rect, point, gap_x=0.0, gap_y=0.0) == point


def test_link_item_line_anchors_to_the_shortest_segment(qtbot):
    # c_1 at (0,0), c_2 at (300,0): directly to the right with identical
    # y-ranges, so each end anchors to the facing edge-center, not
    # either card's own center.
    document = _document_with_two_cards()
    item1 = CardItem("c_1", document)
    item1.setPos(0.0, 0.0)
    item2 = CardItem("c_2", document)
    item2.setPos(300.0, 0.0)

    link = LinkItem("l_1", item1, item2, document)

    line = link.line()
    assert line.p1() == QPointF(_WIDTH, _HEIGHT / 2)
    assert line.p2() == QPointF(300.0, _HEIGHT / 2)


def test_link_item_line_follows_card_move_and_recomputes_shortest_path(qtbot):
    document = _document_with_two_cards()
    item1 = CardItem("c_1", document)
    item1.setPos(0.0, 0.0)
    item2 = CardItem("c_2", document)
    item2.setPos(300.0, 0.0)
    link = LinkItem("l_1", item1, item2, document)

    # c_1's new rect [500,700]x[600,720] sits above-and-left of c_2's
    # rect [300,500]x[0,120] -- their x-ranges just touch at x=500,
    # which is literally c_1's top-left corner and c_2's bottom-right
    # corner at once. Both ends get pulled off that shared corner along
    # their own top/bottom edge (the vertical gap dwarfs the zero
    # horizontal gap, so a top/bottom edge is picked), landing the line
    # just barely off vertical rather than corner-to-corner.
    item1.setPos(500.0, 600.0)

    line = link.line()
    assert line.p1() == QPointF(520.0, 600.0)
    assert line.p2() == QPointF(480.0, 120.0)


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


def test_start_flash_uses_the_higher_contrast_color(qtbot):
    document = _document_with_two_cards()
    document.set_canvas_background_color("#000000")
    item1 = CardItem("c_1", document)
    item2 = CardItem("c_2", document)
    link = LinkItem("l_1", item1, item2, document)

    link.start_flash(on_finished=lambda: None)
    # setCurrentTime(0) alone is a no-op here -- start() already put the
    # animation at t=0 internally, so nothing actually *changes* and
    # valueChanged never fires; nudge to t=1 to force a real emission.
    link._flash_grow.setCurrentTime(1)

    assert link.pen().color().name() == "#ffffff"


def test_start_flash_grows_pen_width_over_the_grow_phase(qtbot):
    document = _document_with_two_cards()
    item1 = CardItem("c_1", document)
    item2 = CardItem("c_2", document)
    link = LinkItem("l_1", item1, item2, document)

    link.start_flash(on_finished=lambda: None)
    link._flash_grow.setCurrentTime(_FLASH_GROW_DURATION_MS // 2)

    assert link.pen().widthF() == pytest.approx((_FLASH_WEIGHT_START + _FLASH_WEIGHT_END) / 2)


def test_start_flash_starts_fading_once_the_grow_phase_completes(qtbot):
    document = _document_with_two_cards()
    item1 = CardItem("c_1", document)
    item2 = CardItem("c_2", document)
    link = LinkItem("l_1", item1, item2, document)

    link.start_flash(on_finished=lambda: None)
    link._flash_grow.setCurrentTime(_FLASH_GROW_DURATION_MS)

    assert link.pen().widthF() == pytest.approx(_FLASH_WEIGHT_END)
    assert link._flash_fade is not None
    assert link._flash_fade.state() == QAbstractAnimation.State.Running
    assert link.opacity() == pytest.approx(1.0)  # fade hasn't progressed yet


def test_start_flash_fades_opacity_toward_zero(qtbot):
    document = _document_with_two_cards()
    item1 = CardItem("c_1", document)
    item2 = CardItem("c_2", document)
    link = LinkItem("l_1", item1, item2, document)

    link.start_flash(on_finished=lambda: None)
    link._flash_grow.setCurrentTime(_FLASH_GROW_DURATION_MS)
    link._flash_fade.setCurrentTime(_FLASH_FADE_DURATION_MS // 2)

    assert link.opacity() == pytest.approx(0.5)


def test_start_flash_restores_the_real_pen_and_opacity_when_done(qtbot):
    document = _document_with_two_cards()
    item1 = CardItem("c_1", document)
    item2 = CardItem("c_2", document)
    link = LinkItem("l_1", item1, item2, document)
    real_pen_color = link.pen().color()
    real_pen_width = link.pen().widthF()

    finished = []
    link.start_flash(on_finished=lambda: finished.append(True))
    link._flash_grow.setCurrentTime(_FLASH_GROW_DURATION_MS)
    link._flash_fade.setCurrentTime(_FLASH_FADE_DURATION_MS)

    assert finished == [True]
    assert link.opacity() == pytest.approx(1.0)
    assert link.pen().color() == real_pen_color
    assert link.pen().widthF() == pytest.approx(real_pen_width)


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
