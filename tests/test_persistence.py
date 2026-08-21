import json

import pytest

from indexcards.models.card import Card
from indexcards.models.document import DEFAULT_CANVAS_BACKGROUND_COLOR, Document
from indexcards.models.link import Link
from indexcards.persistence.file_io import load_document, save_document


def _build_document() -> Document:
    document = Document(name="Round Trip Test")
    document.add_card(
        Card(
            id="c_1",
            text="**Bold idea** with unicode: café, naïve, 日本語",
            x=12.5,
            y=-34.25,
            color="#F6E27A",
            tags=["plot", "urgent"],
        )
    )
    document.add_card(Card(id="c_2", text="second card", x=100.0, y=200.0))
    document.add_link(Link(id="l_1", source="c_1", target="c_2", label="relates to"))
    return document


def test_round_trip_preserves_all_fields(tmp_path):
    original = _build_document()
    path = tmp_path / "test.idxcards"

    save_document(original, path)
    reloaded = load_document(path)

    assert reloaded.name == original.name
    assert set(reloaded.cards) == set(original.cards)
    for card_id, original_card in original.cards.items():
        reloaded_card = reloaded.cards[card_id]
        assert reloaded_card.text == original_card.text
        assert reloaded_card.x == original_card.x
        assert reloaded_card.y == original_card.y
        assert reloaded_card.color == original_card.color
        assert reloaded_card.tags == original_card.tags

    assert set(reloaded.links) == set(original.links)
    for link_id, original_link in original.links.items():
        reloaded_link = reloaded.links[link_id]
        assert reloaded_link.source == original_link.source
        assert reloaded_link.target == original_link.target
        assert reloaded_link.label == original_link.label

    assert reloaded.canvas_background_color == original.canvas_background_color


def test_round_trip_preserves_custom_canvas_background_color(tmp_path):
    document = _build_document()
    document.set_canvas_background_color("#123456")
    path = tmp_path / "test.idxcards"

    save_document(document, path)
    reloaded = load_document(path)

    assert reloaded.canvas_background_color == "#123456"


def test_loading_old_v1_file_gets_default_background_color(tmp_path):
    path = tmp_path / "old.idxcards"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "file": {"name": "Old File"},
                "cards": [{"id": "c_1", "text": "hi", "position": {"x": 0, "y": 0}}],
                "links": [],
            }
        ),
        encoding="utf-8",
    )

    document = load_document(path)

    assert document.canvas_background_color == DEFAULT_CANVAS_BACKGROUND_COLOR


def test_save_marks_document_clean(tmp_path):
    document = _build_document()
    assert document.dirty is True
    save_document(document, tmp_path / "test.idxcards")
    assert document.dirty is False


def test_saved_file_is_readable_json_with_expected_shape(tmp_path):
    document = _build_document()
    path = tmp_path / "test.idxcards"
    save_document(document, path)

    raw = path.read_text(encoding="utf-8")
    assert raw.endswith("\n")

    data = json.loads(raw)
    assert data["schema_version"] == 2
    assert data["file"]["name"] == "Round Trip Test"
    assert "canvas_background_color" in data["file"]
    assert len(data["cards"]) == 2
    assert len(data["links"]) == 1
    assert data["links"][0]["source"] == "c_1"
    assert data["links"][0]["target"] == "c_2"


def test_load_document_with_malformed_json_raises_value_error(tmp_path):
    path = tmp_path / "broken.idxcards"
    path.write_text("{not valid json", encoding="utf-8")

    with pytest.raises(ValueError):
        load_document(path)


def test_load_document_missing_card_id_raises_value_error_not_key_error(tmp_path):
    path = tmp_path / "broken.idxcards"
    path.write_text(
        json.dumps({"schema_version": 1, "cards": [{"text": "no id here"}], "links": []}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError):
        load_document(path)


def test_load_document_with_wrong_top_level_shape_raises_value_error(tmp_path):
    path = tmp_path / "broken.idxcards"
    path.write_text(json.dumps(["not", "an", "object"]), encoding="utf-8")

    with pytest.raises(ValueError):
        load_document(path)


def test_load_document_with_dangling_link_raises_value_error(tmp_path):
    path = tmp_path / "broken.idxcards"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "cards": [{"id": "c_1", "position": {"x": 0, "y": 0}}],
                "links": [{"id": "l_1", "source": "c_1", "target": "c_missing"}],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError):
        load_document(path)


def test_load_document_with_unreadable_path_raises_oserror(tmp_path):
    missing_path = tmp_path / "does_not_exist.idxcards"

    with pytest.raises(OSError):
        load_document(missing_path)


def test_loading_does_not_retroactively_trim_existing_whitespace(tmp_path):
    # Whitespace trimming (M14) is a Document.set_card_text() behavior for
    # active edits, deliberately not applied on load — opening a file
    # someone hasn't touched shouldn't silently rewrite their data.
    path = tmp_path / "padded.idxcards"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "cards": [
                    {"id": "c_1", "text": "  padded on disk  ", "position": {"x": 0, "y": 0}}
                ],
                "links": [],
            }
        ),
        encoding="utf-8",
    )

    document = load_document(path)

    assert document.get_card("c_1").text == "  padded on disk  "
