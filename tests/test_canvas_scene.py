from PySide6.QtCore import QEvent, QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QUndoStack
from PySide6.QtWidgets import (
    QGraphicsItem,
    QGraphicsRectItem,
    QGraphicsSceneMouseEvent,
    QGraphicsSimpleTextItem,
    QGraphicsView,
)

from indexcards.canvas.canvas_scene import CanvasScene
from indexcards.canvas.link_item import LinkItem
from indexcards.canvas.stack_item import StackItem
from indexcards.models.card import DEFAULT_CARD_SIZE, Card
from indexcards.models.document import Document
from indexcards.models.link import Link
from indexcards.models.stack import Stack


def _document_with_cards() -> Document:
    document = Document(name="Test")
    document.add_card(Card(id="c_1", text="first", x=10.0, y=20.0))
    document.add_card(Card(id="c_2", text="second", x=200.0, y=300.0))
    return document


def _top_level_items(scene: CanvasScene) -> list[QGraphicsItem]:
    # Each CardItem owns a child _CardTextItem for its editable text —
    # scene.items() returns the whole item tree flat, so filter down to
    # one entry per Card/Link the way these tests expect.
    return [item for item in scene.items() if item.parentItem() is None]


def test_scene_creates_items_at_stored_positions():
    document = _document_with_cards()
    scene = CanvasScene(document)

    item1 = scene.item_for_card("c_1")
    item2 = scene.item_for_card("c_2")
    assert item1 is not None
    assert item2 is not None
    assert (item1.pos().x(), item1.pos().y()) == (10.0, 20.0)
    assert (item2.pos().x(), item2.pos().y()) == (200.0, 300.0)
    assert len(_top_level_items(scene)) == 2


def test_scene_adds_item_on_card_added():
    document = _document_with_cards()
    scene = CanvasScene(document)

    document.add_card(Card(id="c_3", text="third", x=1.0, y=2.0))

    item = scene.item_for_card("c_3")
    assert item is not None
    assert (item.pos().x(), item.pos().y()) == (1.0, 2.0)


def test_scene_removes_item_on_card_removed():
    document = _document_with_cards()
    scene = CanvasScene(document)

    document.remove_card("c_1")

    assert scene.item_for_card("c_1") is None
    assert len(_top_level_items(scene)) == 1


def test_scene_refreshes_item_on_card_changed():
    document = _document_with_cards()
    scene = CanvasScene(document)

    document.set_card_text("c_1", "updated text")

    item = scene.item_for_card("c_1")
    assert item._text_item.toPlainText() == "updated text"


def test_scene_repositions_item_on_card_moved():
    document = _document_with_cards()
    scene = CanvasScene(document)

    document.set_card_position("c_1", 500.0, 600.0)

    item = scene.item_for_card("c_1")
    assert (item.pos().x(), item.pos().y()) == (500.0, 600.0)


def test_content_bounds_changed_emitted_on_card_added(qtbot):
    document = _document_with_cards()
    scene = CanvasScene(document)

    with qtbot.waitSignal(scene.contentBoundsChanged, timeout=1000):
        document.add_card(Card(id="c_3", text="third", x=1.0, y=2.0))


def test_content_bounds_changed_emitted_on_card_removed(qtbot):
    document = _document_with_cards()
    scene = CanvasScene(document)

    with qtbot.waitSignal(scene.contentBoundsChanged, timeout=1000):
        document.remove_card("c_1")


def test_content_bounds_changed_emitted_on_card_moved(qtbot):
    document = _document_with_cards()
    scene = CanvasScene(document)

    with qtbot.waitSignal(scene.contentBoundsChanged, timeout=1000):
        document.set_card_position("c_1", 500.0, 600.0)


def test_content_bounds_changed_emitted_on_cards_bulk_moved(qtbot):
    document = _document_with_cards()
    scene = CanvasScene(document)

    with qtbot.waitSignal(scene.contentBoundsChanged, timeout=1000):
        document.bulk_set_positions({"c_1": (11.0, 22.0), "c_2": (33.0, 44.0)})


def test_scene_passes_undo_stack_to_items_making_them_movable():
    document = _document_with_cards()
    stack = QUndoStack()
    scene = CanvasScene(document, undo_stack=stack)

    item = scene.item_for_card("c_1")
    assert item.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsMovable


def test_scene_without_undo_stack_items_are_not_movable():
    document = _document_with_cards()
    scene = CanvasScene(document)

    item = scene.item_for_card("c_1")
    assert not (item.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsMovable)


def test_scene_repositions_items_on_bulk_move():
    document = _document_with_cards()
    scene = CanvasScene(document)

    document.bulk_set_positions({"c_1": (11.0, 22.0), "c_2": (33.0, 44.0)})

    assert (scene.item_for_card("c_1").pos().x(), scene.item_for_card("c_1").pos().y()) == (
        11.0,
        22.0,
    )
    assert (scene.item_for_card("c_2").pos().x(), scene.item_for_card("c_2").pos().y()) == (
        33.0,
        44.0,
    )


def test_scene_creates_link_item_for_existing_link():
    document = _document_with_cards()
    document.add_link(Link(id="l_1", source="c_1", target="c_2"))
    scene = CanvasScene(document)

    link_items = [item for item in scene.items() if isinstance(item, LinkItem)]
    assert len(link_items) == 1
    assert link_items[0].link_id == "l_1"
    assert len(_top_level_items(scene)) == 3


def test_scene_adds_link_item_on_link_added():
    document = _document_with_cards()
    scene = CanvasScene(document)

    document.add_link(Link(id="l_1", source="c_1", target="c_2"))

    link_items = [item for item in scene.items() if isinstance(item, LinkItem)]
    assert len(link_items) == 1


def test_scene_removes_link_item_on_link_removed():
    document = _document_with_cards()
    document.add_link(Link(id="l_1", source="c_1", target="c_2"))
    scene = CanvasScene(document)

    document.remove_link("l_1")

    link_items = [item for item in scene.items() if isinstance(item, LinkItem)]
    assert link_items == []


def test_set_links_visible_hides_existing_link_items():
    document = _document_with_cards()
    document.add_link(Link(id="l_1", source="c_1", target="c_2"))
    scene = CanvasScene(document)
    link_item = next(item for item in scene.items() if isinstance(item, LinkItem))
    assert link_item.isVisible()

    scene.set_links_visible(False)

    assert not link_item.isVisible()


def test_set_links_visible_true_shows_hidden_link_items():
    document = _document_with_cards()
    document.add_link(Link(id="l_1", source="c_1", target="c_2"))
    scene = CanvasScene(document)
    link_item = next(item for item in scene.items() if isinstance(item, LinkItem))
    scene.set_links_visible(False)

    scene.set_links_visible(True)

    assert link_item.isVisible()


def test_new_link_added_while_hidden_starts_hidden():
    document = _document_with_cards()
    scene = CanvasScene(document)
    scene.set_links_visible(False)

    document.add_link(Link(id="l_1", source="c_1", target="c_2"))

    link_item = next(item for item in scene.items() if isinstance(item, LinkItem))
    assert not link_item.isVisible()


def test_set_link_mode_active_updates_existing_cards():
    document = _document_with_cards()
    scene = CanvasScene(document)
    item = scene.item_for_card("c_1")
    assert not item.hasCursor()

    scene.set_link_mode_active(True)

    assert item.cursor().shape() == Qt.CursorShape.CrossCursor

    scene.set_link_mode_active(False)

    assert not item.hasCursor()


def test_new_card_added_while_link_mode_active_starts_with_cross_cursor():
    document = _document_with_cards()
    scene = CanvasScene(document)
    scene.set_link_mode_active(True)

    document.add_card(Card(id="c_3", text="third", x=1.0, y=2.0))

    item = scene.item_for_card("c_3")
    assert item.cursor().shape() == Qt.CursorShape.CrossCursor


def test_scene_selected_link_ids():
    document = _document_with_cards()
    document.add_link(Link(id="l_1", source="c_1", target="c_2"))
    scene = CanvasScene(document)

    assert scene.selected_link_ids() == []

    link_item = next(item for item in scene.items() if isinstance(item, LinkItem))
    link_item.setSelected(True)

    assert scene.selected_link_ids() == ["l_1"]


def test_scene_selected_card_ids():
    document = _document_with_cards()
    scene = CanvasScene(document)

    assert scene.selected_card_ids() == []

    scene.item_for_card("c_1").setSelected(True)
    scene.item_for_card("c_2").setSelected(True)

    assert set(scene.selected_card_ids()) == {"c_1", "c_2"}


def test_deleting_card_cascades_to_remove_link_item():
    document = _document_with_cards()
    document.add_link(Link(id="l_1", source="c_1", target="c_2"))
    scene = CanvasScene(document)

    document.remove_card("c_1")

    assert scene.item_for_card("c_1") is None
    link_items = [item for item in scene.items() if isinstance(item, LinkItem)]
    assert link_items == []
    assert len(_top_level_items(scene)) == 1


def test_search_query_dims_non_matching_cards():
    document = _document_with_cards()
    scene = CanvasScene(document)

    scene.set_search_query("first")

    assert scene.item_for_card("c_1")._dimmed is False
    assert scene.item_for_card("c_2")._dimmed is True
    # Cards stay fully opaque even when dimmed (dimming is a desaturated
    # fill color, not transparency) so a link line can't show through.
    assert scene.item_for_card("c_1").opacity() == 1.0
    assert scene.item_for_card("c_2").opacity() == 1.0


def test_clearing_search_query_restores_full_opacity():
    document = _document_with_cards()
    scene = CanvasScene(document)
    scene.set_search_query("first")

    scene.set_search_query("")

    assert scene.item_for_card("c_1")._dimmed is False
    assert scene.item_for_card("c_2")._dimmed is False


def test_new_card_respects_current_search_query():
    document = _document_with_cards()
    scene = CanvasScene(document)
    scene.set_search_query("zzz")

    document.add_card(Card(id="c_3", text="does not contain the query"))

    assert scene.item_for_card("c_3")._dimmed is True


def test_text_edit_updates_dim_state():
    document = _document_with_cards()
    scene = CanvasScene(document)
    scene.set_search_query("zzz")
    assert scene.item_for_card("c_1")._dimmed is True

    document.set_card_text("c_1", "now mentions zzz")

    assert scene.item_for_card("c_1")._dimmed is False


def test_link_dimmed_when_either_endpoint_does_not_match():
    document = _document_with_cards()
    document.add_link(Link(id="l_1", source="c_1", target="c_2"))
    scene = CanvasScene(document)

    scene.set_search_query("first")  # only c_1 matches

    link_item = next(item for item in scene.items() if isinstance(item, LinkItem))
    assert link_item._dimmed is True


def test_link_not_dimmed_when_both_endpoints_match():
    document = _document_with_cards()
    document.add_link(Link(id="l_1", source="c_1", target="c_2"))
    scene = CanvasScene(document)

    scene.set_search_query("")  # both match (empty query)

    link_item = next(item for item in scene.items() if isinstance(item, LinkItem))
    assert link_item._dimmed is False


def test_new_link_respects_current_search_query():
    document = _document_with_cards()
    scene = CanvasScene(document)
    scene.set_search_query("first")

    document.add_link(Link(id="l_1", source="c_1", target="c_2"))

    link_item = next(item for item in scene.items() if isinstance(item, LinkItem))
    assert link_item._dimmed is True


def test_editing_card_text_redims_its_incident_links():
    document = _document_with_cards()
    document.add_link(Link(id="l_1", source="c_1", target="c_2"))
    scene = CanvasScene(document)
    scene.set_search_query("zzz")
    link_item = next(item for item in scene.items() if isinstance(item, LinkItem))
    assert link_item._dimmed is True

    document.set_card_text("c_1", "now mentions zzz")
    document.set_card_text("c_2", "also mentions zzz")

    assert link_item._dimmed is False


def _render_background(scene: CanvasScene) -> None:
    image = QImage(200, 200, QImage.Format.Format_ARGB32)
    painter = QPainter(image)
    try:
        scene.drawBackground(painter, QRectF(0, 0, 200, 200))
    finally:
        painter.end()


def test_draw_background_does_not_crash_when_empty():
    document = Document(name="Test")
    scene = CanvasScene(document)
    _render_background(scene)  # must not raise


def test_visible_scene_rect_falls_back_to_passed_rect_with_no_view():
    document = Document(name="Test")
    scene = CanvasScene(document)

    fallback = QRectF(0, 0, 200, 200)
    assert scene._visible_scene_rect(fallback) == fallback


def test_visible_scene_rect_uses_view_viewport_not_a_small_dirty_rect(qtbot):
    document = Document(name="Test")
    scene = CanvasScene(document)
    view = QGraphicsView(scene)
    qtbot.addWidget(view)
    view.resize(400, 300)
    view.show()
    qtbot.waitExposed(view)

    # A small, arbitrarily-positioned rect, standing in for the partial
    # "dirty" region Qt passes during e.g. a rubber-band drag frame or a
    # window-activation partial repaint.
    dirty_rect = QRectF(5, 5, 15, 15)

    visible_rect = scene._visible_scene_rect(dirty_rect)

    assert visible_rect != dirty_rect
    assert visible_rect.width() > dirty_rect.width()
    assert visible_rect.height() > dirty_rect.height()


def test_draw_background_centers_text_in_visible_area_not_dirty_rect(qtbot, monkeypatch):
    # Regression: the empty-state text used to be centered within whatever
    # small sub-region Qt was currently repainting, instead of the actual
    # visible viewport — it would jump position (sometimes off-screen) on
    # every partial repaint, and "paint" mis-centered text fragments along
    # a rubber-band drag path since drawBackground fires once per frame.
    captured_rects = []

    def fake_draw_text(self, rect, alignment, text):
        captured_rects.append(rect)

    monkeypatch.setattr(QPainter, "drawText", fake_draw_text)

    document = Document(name="Test")
    scene = CanvasScene(document)
    view = QGraphicsView(scene)
    qtbot.addWidget(view)
    view.resize(400, 300)
    view.show()
    qtbot.waitExposed(view)

    small_dirty_rect = QRectF(5, 5, 15, 15)
    image = QImage(400, 300, QImage.Format.Format_ARGB32)
    painter = QPainter(image)
    try:
        scene.drawBackground(painter, small_dirty_rect)
    finally:
        painter.end()

    assert len(captured_rects) == 1
    assert captured_rects[0] != small_dirty_rect
    assert captured_rects[0].width() > small_dirty_rect.width()


def test_draw_background_does_not_crash_with_cards():
    document = _document_with_cards()
    scene = CanvasScene(document)
    _render_background(scene)  # must not raise


def test_draw_background_omits_empty_state_text_with_only_a_stack(monkeypatch):
    # Regression: a canvas holding only a Stack (no loose CardItems) still
    # showed the "No cards yet..." placeholder, since drawBackground only
    # checked self._items (cards), never self._stack_items.
    captured_calls = []

    def fake_draw_text(self, rect, alignment, text):
        captured_calls.append(text)

    monkeypatch.setattr(QPainter, "drawText", fake_draw_text)

    document = Document(name="Test")
    document.add_stack(Stack(id="s_1"))
    scene = CanvasScene(document)

    _render_background(scene)

    assert captured_calls == []


def _track_update_calls(monkeypatch) -> list:
    calls = []
    monkeypatch.setattr(CanvasScene, "update", lambda self, *a, **k: calls.append(True))
    return calls


def test_card_added_forces_full_repaint_for_empty_state(monkeypatch):
    # Regression: Qt only invalidates the newly-added item's own bounds
    # by default, leaving the rest of a previously-drawn "No cards yet"
    # placeholder stale until some unrelated repaint (e.g. a window
    # activation change) happens to redraw the whole viewport. Adding the
    # first card must force a full repaint so the placeholder disappears
    # immediately.
    document = Document(name="Test")
    _scene = CanvasScene(document)
    calls = _track_update_calls(monkeypatch)

    document.add_card(Card(id="c_1"))

    assert calls


def test_card_removed_forces_full_repaint_for_empty_state(monkeypatch):
    document = _document_with_cards()
    _scene = CanvasScene(document)
    calls = _track_update_calls(monkeypatch)

    document.remove_card("c_1")
    document.remove_card("c_2")

    assert calls


def test_stack_added_forces_full_repaint_for_empty_state(monkeypatch):
    document = Document(name="Test")
    _scene = CanvasScene(document)
    calls = _track_update_calls(monkeypatch)

    document.add_stack(Stack(id="s_1"))

    assert calls


def test_stack_removed_forces_full_repaint_for_empty_state(monkeypatch):
    document = Document(name="Test")
    document.add_stack(Stack(id="s_1"))
    _scene = CanvasScene(document)
    calls = _track_update_calls(monkeypatch)

    document.remove_stack("s_1")

    assert calls


def test_card_joining_stack_forces_full_repaint_for_empty_state(monkeypatch):
    document = Document(name="Test")
    document.add_card(Card(id="c_1"))
    document.add_stack(Stack(id="s_1"))
    _scene = CanvasScene(document)
    calls = _track_update_calls(monkeypatch)

    document.add_cards_to_stack("s_1", ["c_1"])

    assert calls


def test_scene_background_brush_matches_document_on_construction():
    document = _document_with_cards()
    document.set_canvas_background_color("#123456")

    scene = CanvasScene(document)

    assert scene.backgroundBrush().color().name() == "#123456"


def test_scene_background_brush_updates_live():
    document = _document_with_cards()
    scene = CanvasScene(document)

    document.set_canvas_background_color("#abcdef")

    assert scene.backgroundBrush().color().name() == "#abcdef"


def test_theme_changed_signal_refreshes_the_background_brush():
    # Regression: switching themes (or editing the current theme's
    # background via the Theme Editor) only ever emits themeChanged, not
    # backgroundColorChanged (that one's specific to
    # set_canvas_background_color) — the scene's brush must still update.
    document = _document_with_cards()
    scene = CanvasScene(document)
    assert scene.backgroundBrush().color().name() != "#654321"

    document.theme.background_color = "#654321"
    document.themeChanged.emit()

    assert scene.backgroundBrush().color().name() == "#654321"


def test_theme_changed_signal_refreshes_card_text_color():
    document = _document_with_cards()
    scene = CanvasScene(document)
    item = scene.item_for_card("c_1")
    assert item._text_item.defaultTextColor() == QColor("#000000")

    # Mutate the slot in place (no cardChanged fires) to isolate that this
    # is themeChanged's own refresh wiring, not the existing cardChanged path.
    document.get_slot("slot_white").hex = "#101010"
    document.themeChanged.emit()

    assert item._text_item.defaultTextColor() == QColor("#ffffff")


def test_theme_slot_changed_signal_refreshes_card_text_color():
    document = _document_with_cards()
    scene = CanvasScene(document)
    item = scene.item_for_card("c_1")
    assert item._text_item.defaultTextColor() == QColor("#000000")

    document.get_slot("slot_white").hex = "#101010"
    document.themeSlotChanged.emit("slot_white")

    assert item._text_item.defaultTextColor() == QColor("#ffffff")


def test_link_changed_signal_refreshes_the_right_link_item():
    document = _document_with_cards()
    document.add_link(Link(id="l_1", source="c_1", target="c_2"))
    scene = CanvasScene(document)
    link_item = scene._link_items["l_1"]
    assert link_item._line_ending == "none"

    document.set_link_line_ending("l_1", "both")

    assert link_item._line_ending == "both"


def test_theme_changed_signal_refreshes_link_pen():
    document = _document_with_cards()
    document.add_link(Link(id="l_1", source="c_1", target="c_2"))
    scene = CanvasScene(document)
    link_item = scene._link_items["l_1"]
    original_color = link_item.pen().color().name()

    document.theme.link_color_mode = "white"
    document.themeChanged.emit()

    assert link_item.pen().color().name() == "#ffffff"
    assert link_item.pen().color().name() != original_color


def test_link_color_mode_changed_signal_refreshes_every_link():
    document = _document_with_cards()
    document.add_link(Link(id="l_1", source="c_1", target="c_2"))
    scene = CanvasScene(document)
    link_item = scene._link_items["l_1"]

    document.set_theme_link_color_mode("white")

    assert link_item.pen().color().name() == "#ffffff"


def test_link_weight_changed_signal_refreshes_every_link():
    document = _document_with_cards()
    document.add_link(Link(id="l_1", source="c_1", target="c_2"))
    scene = CanvasScene(document)
    link_item = scene._link_items["l_1"]

    document.set_theme_link_weight(5)

    assert link_item.pen().width() == 5


def test_set_links_emphasized_applies_to_existing_links():
    document = _document_with_cards()
    document.add_link(Link(id="l_1", source="c_1", target="c_2"))
    scene = CanvasScene(document)
    link_item = scene._link_items["l_1"]

    scene.set_links_emphasized(True)
    assert link_item.graphicsEffect() is not None

    scene.set_links_emphasized(False)
    assert link_item.graphicsEffect() is None


def test_set_links_emphasized_applies_to_a_link_added_afterward():
    document = _document_with_cards()
    scene = CanvasScene(document)
    scene.set_links_emphasized(True)

    document.add_link(Link(id="l_1", source="c_1", target="c_2"))

    assert scene._link_items["l_1"].graphicsEffect() is not None


def test_add_card_at_centers_card_on_given_point():
    document = _document_with_cards()
    stack = QUndoStack()
    scene = CanvasScene(document, undo_stack=stack)
    width, height = DEFAULT_CARD_SIZE

    card_id = scene.add_card_at(500.0, 400.0)

    assert card_id is not None
    card = document.get_card(card_id)
    assert card.x == 500.0 - width / 2
    assert card.y == 400.0 - height / 2


def test_add_card_at_is_undoable():
    document = _document_with_cards()
    stack = QUndoStack()
    scene = CanvasScene(document, undo_stack=stack)

    card_id = scene.add_card_at(500.0, 400.0)
    assert card_id in document.cards
    assert stack.canUndo()

    stack.undo()
    assert card_id not in document.cards


def test_add_card_at_without_undo_stack_is_noop():
    document = _document_with_cards()
    scene = CanvasScene(document)

    card_id = scene.add_card_at(500.0, 400.0)

    assert card_id is None
    assert len(document.cards) == 2


def test_add_card_at_gets_default_placeholder_text():
    document = _document_with_cards()
    stack = QUndoStack()
    scene = CanvasScene(document, undo_stack=stack)

    card_id = scene.add_card_at(0.0, 0.0)

    assert document.get_card(card_id).text == "New Card 3"


def _stack_labels(scene: CanvasScene) -> list[QGraphicsSimpleTextItem]:
    return [item for item in scene.items() if isinstance(item, QGraphicsSimpleTextItem)]


def test_show_tag_stack_labels_creates_two_labels_for_mixed_set():
    document = Document(name="Test")
    document.add_card(Card(id="c_1", x=0.0, y=0.0, tags=["plot"]))
    document.add_card(Card(id="c_2", x=300.0, y=0.0, tags=[]))
    scene = CanvasScene(document)

    scene.show_tag_stack_labels("plot")

    labels = _stack_labels(scene)
    assert len(labels) == 2
    texts = {label.text() for label in labels}
    assert texts == {'Has "plot"', 'No "plot"'}


def test_stack_labels_are_black_text_on_a_white_chip_for_legibility():
    # Plain gray fill (and later, a white text outline) were both hard to
    # read against a colored canvas background; a solid white chip behind
    # black text reads clearly against any background.
    document = Document(name="Test")
    document.add_card(Card(id="c_1", x=0.0, y=0.0, tags=["plot"]))
    scene = CanvasScene(document)

    scene.show_tag_stack_labels("plot")

    chips = [item for item in scene.items() if isinstance(item, QGraphicsRectItem)]
    assert len(chips) == 1
    assert chips[0].brush().color() == QColor(Qt.GlobalColor.white)

    text_item = _stack_labels(scene)[0]
    assert text_item.brush().color() == QColor(Qt.GlobalColor.black)
    assert text_item.parentItem() is chips[0]
    # The chip should be sized to fit the text, not some arbitrary size.
    chip_rect = chips[0].rect()
    text_rect = text_item.boundingRect()
    assert chip_rect.width() > text_rect.width()
    assert chip_rect.height() > text_rect.height()


def test_show_tag_stack_labels_only_one_label_when_all_cards_match():
    document = Document(name="Test")
    document.add_card(Card(id="c_1", x=0.0, y=0.0, tags=["plot"]))
    document.add_card(Card(id="c_2", x=300.0, y=0.0, tags=["plot"]))
    scene = CanvasScene(document)

    scene.show_tag_stack_labels("plot")

    labels = _stack_labels(scene)
    assert len(labels) == 1
    assert labels[0].text() == 'Has "plot"'


def test_show_tag_stack_labels_replaces_previous_labels():
    document = Document(name="Test")
    document.add_card(Card(id="c_1", x=0.0, y=0.0, tags=["plot"]))
    document.add_card(Card(id="c_2", x=300.0, y=0.0, tags=["urgent"]))
    scene = CanvasScene(document)

    scene.show_tag_stack_labels("plot")
    scene.show_tag_stack_labels("urgent")

    labels = _stack_labels(scene)
    assert len(labels) == 2
    texts = {label.text() for label in labels}
    assert texts == {'Has "urgent"', 'No "urgent"'}


def test_stack_labels_cleared_when_card_added():
    document = _document_with_cards()
    document.set_card_tags("c_1", ["plot"])
    scene = CanvasScene(document)
    scene.show_tag_stack_labels("plot")
    assert len(_stack_labels(scene)) == 2

    document.add_card(Card(id="c_3", text="third"))

    assert _stack_labels(scene) == []


def test_stack_labels_cleared_when_card_removed():
    document = _document_with_cards()
    document.set_card_tags("c_1", ["plot"])
    scene = CanvasScene(document)
    scene.show_tag_stack_labels("plot")
    assert len(_stack_labels(scene)) == 2

    document.remove_card("c_2")

    assert _stack_labels(scene) == []


def test_stack_labels_cleared_when_card_moved():
    document = _document_with_cards()
    document.set_card_tags("c_1", ["plot"])
    scene = CanvasScene(document)
    scene.show_tag_stack_labels("plot")
    assert len(_stack_labels(scene)) == 2

    document.set_card_position("c_1", 999.0, 999.0)

    assert _stack_labels(scene) == []


def test_stack_labels_cleared_on_bulk_move():
    document = _document_with_cards()
    document.set_card_tags("c_1", ["plot"])
    scene = CanvasScene(document)
    scene.show_tag_stack_labels("plot")
    assert len(_stack_labels(scene)) == 2

    document.bulk_set_positions({"c_1": (1.0, 1.0), "c_2": (2.0, 2.0)})

    assert _stack_labels(scene) == []


def test_stacked_card_gets_no_card_item():
    document = Document(name="Test")
    document.add_card(Card(id="c_1", stack_id="s_1"))
    document.add_stack(Stack(id="s_1", card_ids=["c_1"]))

    scene = CanvasScene(document)

    assert scene.item_for_card("c_1") is None
    assert scene.item_for_stack("s_1") is not None


def test_scene_creates_stack_item_at_stored_position():
    document = _document_with_cards()
    document.add_stack(Stack(id="s_1", x=50.0, y=60.0))
    scene = CanvasScene(document)

    item = scene.item_for_stack("s_1")
    assert item is not None
    assert (item.pos().x(), item.pos().y()) == (50.0, 60.0)


def test_scene_adds_stack_item_on_stack_added():
    document = _document_with_cards()
    scene = CanvasScene(document)

    document.add_stack(Stack(id="s_1", x=1.0, y=2.0))

    item = scene.item_for_stack("s_1")
    assert item is not None
    assert (item.pos().x(), item.pos().y()) == (1.0, 2.0)


def test_scene_removes_stack_item_on_stack_removed():
    document = _document_with_cards()
    document.add_stack(Stack(id="s_1"))
    scene = CanvasScene(document)

    document.remove_stack("s_1")

    assert scene.item_for_stack("s_1") is None


def test_scene_moves_stack_item_on_stack_moved():
    document = _document_with_cards()
    document.add_stack(Stack(id="s_1"))
    scene = CanvasScene(document)

    document.set_stack_position("s_1", 40.0, 50.0)

    item = scene.item_for_stack("s_1")
    assert (item.pos().x(), item.pos().y()) == (40.0, 50.0)


def test_scene_moves_stack_item_on_stacks_bulk_moved():
    document = _document_with_cards()
    document.add_stack(Stack(id="s_1"))
    document.add_stack(Stack(id="s_2"))
    scene = CanvasScene(document)

    document.bulk_set_stack_positions({"s_1": (10.0, 10.0), "s_2": (20.0, 20.0)})

    assert (scene.item_for_stack("s_1").pos().x(), scene.item_for_stack("s_1").pos().y()) == (
        10.0,
        10.0,
    )
    assert (scene.item_for_stack("s_2").pos().x(), scene.item_for_stack("s_2").pos().y()) == (
        20.0,
        20.0,
    )


def test_card_joining_stack_removes_its_card_item():
    document = _document_with_cards()
    document.add_stack(Stack(id="s_1"))
    scene = CanvasScene(document)
    assert scene.item_for_card("c_1") is not None

    document.add_cards_to_stack("s_1", ["c_1"])

    assert scene.item_for_card("c_1") is None


def test_card_leaving_stack_recreates_its_card_item():
    document = Document(name="Test")
    document.add_card(Card(id="c_1", x=5.0, y=6.0, stack_id="s_1"))
    document.add_stack(Stack(id="s_1", card_ids=["c_1"]))
    scene = CanvasScene(document)
    assert scene.item_for_card("c_1") is None

    document.remove_cards_from_stack("s_1", ["c_1"])

    item = scene.item_for_card("c_1")
    assert item is not None
    assert (item.pos().x(), item.pos().y()) == (5.0, 6.0)


def test_selected_stack_ids_returns_only_selected_stacks():
    document = _document_with_cards()
    document.add_stack(Stack(id="s_1"))
    document.add_stack(Stack(id="s_2"))
    scene = CanvasScene(document)

    scene.item_for_stack("s_1").setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
    scene.item_for_stack("s_1").setSelected(True)

    assert scene.selected_stack_ids() == ["s_1"]


def test_stack_changed_refreshes_stack_item():
    document = _document_with_cards()
    document.add_stack(Stack(id="s_1"))
    scene = CanvasScene(document)
    item = scene.item_for_stack("s_1")
    assert isinstance(item, StackItem)

    # Just confirms this doesn't raise — refresh() calls update(), which
    # has no externally observable effect outside of a real paint cycle.
    document.set_stack_label("s_1", "Chapter 1")


def _document_with_stack() -> Document:
    document = Document(name="Test")
    document.add_card(Card(id="c_1", text="alpha", stack_id="s_1"))
    document.add_card(Card(id="c_2", text="beta", stack_id="s_1"))
    document.add_stack(Stack(id="s_1", card_ids=["c_1", "c_2"]))
    return document


def test_stack_no_member_matches_dims_the_stack():
    document = _document_with_stack()
    scene = CanvasScene(document)

    scene.set_search_query("zzz")

    item = scene.item_for_stack("s_1")
    assert item._search_match_count == 0
    assert item.opacity() < 1.0


def test_stack_some_members_match_stays_full_opacity_with_match_count():
    document = _document_with_stack()
    scene = CanvasScene(document)

    scene.set_search_query("alpha")  # matches c_1 only

    item = scene.item_for_stack("s_1")
    assert item._search_match_count == 1
    assert item.opacity() == 1.0


def test_stack_all_members_match_still_reports_a_match_count():
    document = _document_with_stack()
    scene = CanvasScene(document)

    scene.set_search_query("a")  # matches both "alpha" and "beta"

    item = scene.item_for_stack("s_1")
    assert item._search_match_count == 2
    assert item.opacity() == 1.0


def test_clearing_search_query_returns_stack_to_default_state():
    document = _document_with_stack()
    scene = CanvasScene(document)
    scene.set_search_query("zzz")
    item = scene.item_for_stack("s_1")
    assert item.opacity() < 1.0

    scene.set_search_query("")

    assert item._search_match_count is None
    assert item.opacity() == 1.0


def test_new_stack_respects_current_search_query():
    document = _document_with_stack()
    scene = CanvasScene(document)
    scene.set_search_query("zzz")

    document.add_card(Card(id="c_3", text="does not match", stack_id="s_2"))
    document.add_stack(Stack(id="s_2", card_ids=["c_3"]))

    item = scene.item_for_stack("s_2")
    assert item._search_match_count == 0
    assert item.opacity() < 1.0


def test_stacked_member_text_edit_updates_stack_dim_state():
    document = _document_with_stack()
    scene = CanvasScene(document)
    scene.set_search_query("zzz")
    item = scene.item_for_stack("s_1")
    assert item._search_match_count == 0

    document.set_card_text("c_1", "now mentions zzz")

    assert item._search_match_count == 1
    assert item.opacity() == 1.0


def test_card_joining_stack_updates_its_match_count():
    document = Document(name="Test")
    document.add_card(Card(id="c_1", text="alpha", stack_id="s_1"))
    document.add_card(Card(id="c_2", text="zzz"))
    document.add_stack(Stack(id="s_1", card_ids=["c_1"]))
    scene = CanvasScene(document)
    scene.set_search_query("zzz")
    item = scene.item_for_stack("s_1")
    assert item._search_match_count == 0

    document.add_cards_to_stack("s_1", ["c_2"])

    assert item._search_match_count == 1


def test_card_leaving_stack_updates_its_match_count():
    document = Document(name="Test")
    document.add_card(Card(id="c_1", text="zzz", stack_id="s_1"))
    document.add_card(Card(id="c_2", text="not a match", stack_id="s_1"))
    document.add_stack(Stack(id="s_1", card_ids=["c_1", "c_2"]))
    scene = CanvasScene(document)
    scene.set_search_query("zzz")
    item = scene.item_for_stack("s_1")
    assert item._search_match_count == 1

    document.remove_cards_from_stack("s_1", ["c_1"])

    assert item._search_match_count == 0


def _press(item) -> None:
    event = QGraphicsSceneMouseEvent(QEvent.Type.GraphicsSceneMousePress)
    item.mousePressEvent(event)


def test_clicking_a_card_brings_it_above_a_later_added_card():
    document = _document_with_cards()  # c_1 added first, c_2 second
    scene = CanvasScene(document)
    item1 = scene.item_for_card("c_1")
    item2 = scene.item_for_card("c_2")
    assert item2.zValue() > item1.zValue()  # added later, starts on top

    _press(item1)

    assert item1.zValue() > item2.zValue()


def test_newly_added_card_starts_above_a_previously_clicked_card():
    document = _document_with_cards()
    scene = CanvasScene(document)
    item1 = scene.item_for_card("c_1")
    _press(item1)

    document.add_card(Card(id="c_3"))

    item3 = scene.item_for_card("c_3")
    assert item3.zValue() > item1.zValue()


def test_clicking_a_card_in_a_multi_selection_raises_the_whole_group():
    document = _document_with_cards()
    document.add_card(Card(id="c_3"))  # added last -- currently on top
    scene = CanvasScene(document)
    item1 = scene.item_for_card("c_1")
    item2 = scene.item_for_card("c_2")
    item3 = scene.item_for_card("c_3")
    item1.setSelected(True)
    item2.setSelected(True)

    _press(item1)

    assert item1.zValue() > item3.zValue()
    assert item2.zValue() > item3.zValue()


def test_clicking_an_unselected_card_only_raises_itself():
    document = _document_with_cards()
    document.add_card(Card(id="c_3"))  # added last -- currently on top
    scene = CanvasScene(document)
    item1 = scene.item_for_card("c_1")
    item2 = scene.item_for_card("c_2")
    item3 = scene.item_for_card("c_3")
    item2.setSelected(True)  # c_1 (about to be pressed) is not selected

    _press(item1)

    assert item1.zValue() > item3.zValue()
    # c_2 wasn't selected alongside the pressed card, so it's untouched.
    assert item2.zValue() < item3.zValue()


def test_clicking_a_stack_in_a_mixed_selection_raises_the_card_too():
    # CanvasScene's initial construction adds every card, then every
    # stack (see __init__) -- not interleaved in document-add order -- so
    # a stack always starts on top of any card present at construction
    # time. To get a genuinely-later item, add it live, after the scene
    # already exists, going through _on_card_added like a real new card.
    document = Document(name="Test")
    document.add_card(Card(id="c_1"))
    document.add_stack(Stack(id="s_1"))
    scene = CanvasScene(document)
    card_item = scene.item_for_card("c_1")
    stack_item = scene.item_for_stack("s_1")

    document.add_card(Card(id="c_2"))
    other_item = scene.item_for_card("c_2")
    assert other_item.zValue() > card_item.zValue()
    assert other_item.zValue() > stack_item.zValue()

    card_item.setSelected(True)
    stack_item.setSelected(True)
    _press(stack_item)

    assert card_item.zValue() > other_item.zValue()
    assert stack_item.zValue() > other_item.zValue()
