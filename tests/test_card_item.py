from indexcards.canvas.card_item import CardItem
from indexcards.models.card import DEFAULT_CARD_SIZE, Card
from indexcards.models.document import Document


def _document_with_card() -> Document:
    document = Document(name="Test")
    document.add_card(Card(id="c_1", text="**Bold** idea", x=50.0, y=75.0))
    return document


def test_bounding_rect_matches_default_card_size():
    document = _document_with_card()
    item = CardItem("c_1", document)

    rect = item.boundingRect()
    width, height = DEFAULT_CARD_SIZE
    assert rect.width() == width
    assert rect.height() == height


def test_text_doc_renders_markdown_as_plain_text():
    document = _document_with_card()
    item = CardItem("c_1", document)

    assert item._text_doc.toPlainText() == "Bold idea"


def test_refresh_picks_up_document_text_change():
    document = _document_with_card()
    item = CardItem("c_1", document)

    document.set_card_text("c_1", "Updated *text*")
    item.refresh()

    assert item._text_doc.toPlainText() == "Updated text"
