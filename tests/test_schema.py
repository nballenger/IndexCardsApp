import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from indexcards.models.card import Card
from indexcards.models.document import Document
from indexcards.models.link import Link
from indexcards.models.stack import Stack
from indexcards.persistence.serializer import to_dict

SCHEMA_PATH = Path(__file__).parent.parent / "schema" / "idxcards.schema.json"


def _schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def _build_document() -> Document:
    document = Document(name="Schema Test")
    document.add_card(Card(id="c_1", text="Hello", x=1.0, y=2.0))
    document.add_card(Card(id="c_2"))
    document.add_link(Link(id="l_1", source="c_1", target="c_2"))
    document.add_stack(Stack(id="s_1", card_ids=[]))
    return document


def test_schema_file_is_valid_json_schema():
    Draft202012Validator.check_schema(_schema())


def test_real_document_validates_cleanly():
    validator = Draft202012Validator(_schema())
    data = to_dict(_build_document())

    errors = list(validator.iter_errors(data))

    assert errors == []


def test_committed_fixtures_validate_cleanly():
    validator = Draft202012Validator(_schema())
    fixtures_dir = Path(__file__).parent / "fixtures"

    for path in fixtures_dir.glob("*.idxcards"):
        data = json.loads(path.read_text(encoding="utf-8"))
        errors = list(validator.iter_errors(data))
        assert errors == [], f"{path.name}: {[e.message for e in errors]}"


@pytest.mark.parametrize(
    "mutate",
    [
        lambda data: data.update(unknown_top_level_field="surprise"),
        lambda data: data["links"][0].update(line_ending="sideways"),
        lambda data: data["cards"][0].update(colour_slot="typo"),
        lambda data: data["cards"][0].pop("id"),
    ],
)
def test_broken_documents_fail_validation(mutate):
    validator = Draft202012Validator(_schema())
    data = to_dict(_build_document())
    mutate(data)

    errors = list(validator.iter_errors(data))

    assert errors != []
