from PySide6.QtCore import QRectF
from PySide6.QtGui import QImage, QPainter, QUndoStack
from PySide6.QtWidgets import QGraphicsItem

from indexcards.canvas.canvas_scene import CanvasScene
from indexcards.canvas.link_item import LinkItem
from indexcards.models.card import Card
from indexcards.models.document import Document
from indexcards.models.link import Link


def _document_with_cards() -> Document:
    document = Document(name="Test")
    document.add_card(Card(id="c_1", text="first", x=10.0, y=20.0))
    document.add_card(Card(id="c_2", text="second", x=200.0, y=300.0))
    return document


def test_scene_creates_items_at_stored_positions():
    document = _document_with_cards()
    scene = CanvasScene(document)

    item1 = scene.item_for_card("c_1")
    item2 = scene.item_for_card("c_2")
    assert item1 is not None
    assert item2 is not None
    assert (item1.pos().x(), item1.pos().y()) == (10.0, 20.0)
    assert (item2.pos().x(), item2.pos().y()) == (200.0, 300.0)
    assert len(scene.items()) == 2


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
    assert len(scene.items()) == 1


def test_scene_refreshes_item_on_card_changed():
    document = _document_with_cards()
    scene = CanvasScene(document)

    document.set_card_text("c_1", "updated text")

    item = scene.item_for_card("c_1")
    assert item._text_doc.toPlainText() == "updated text"


def test_scene_repositions_item_on_card_moved():
    document = _document_with_cards()
    scene = CanvasScene(document)

    document.set_card_position("c_1", 500.0, 600.0)

    item = scene.item_for_card("c_1")
    assert (item.pos().x(), item.pos().y()) == (500.0, 600.0)


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
    assert len(scene.items()) == 3


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
    assert len(scene.items()) == 1


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


def test_draw_background_does_not_crash_with_cards():
    document = _document_with_cards()
    scene = CanvasScene(document)
    _render_background(scene)  # must not raise


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
