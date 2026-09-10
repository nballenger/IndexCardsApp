import json
import tempfile
from pathlib import Path

from indexcards.models.card import MAX_TEXT_LENGTH
from indexcards.persistence.file_io import load_document
from indexcards.persistence.format_guide import FORMAT_GUIDE


def test_format_guide_is_a_nonempty_string():
    assert isinstance(FORMAT_GUIDE, str)
    assert len(FORMAT_GUIDE) > 0


def test_format_guide_documents_the_core_entities():
    for term in ("cards", "stacks", "links", "theme", "color_slot"):
        assert term in FORMAT_GUIDE


def test_format_guide_uses_literal_escape_sequences_not_real_newlines():
    # The Markdown-hard-line-break note must describe the literal two-
    # character escape sequence "\n\n" as it appears in JSON, not an actual
    # embedded newline -- this is prose describing JSON string content.
    assert r"\n\n" in FORMAT_GUIDE


def test_format_guide_documents_the_id_convention():
    assert "opaque unique" in FORMAT_GUIDE
    assert "c_" in FORMAT_GUIDE and "l_" in FORMAT_GUIDE and "s_" in FORMAT_GUIDE


def test_format_guide_documents_pinned_semantics_and_the_unpinned_hedge():
    assert "pinned" in FORMAT_GUIDE
    assert "auto-arrange" in FORMAT_GUIDE
    # The explicit hedge: unpinned position is real but brittle, not noise.
    assert "brittle" in FORMAT_GUIDE


def test_format_guide_documents_links_as_a_graph():
    assert "directed edge list" in FORMAT_GUIDE


def test_format_guide_documents_optional_fields():
    assert "Only `id` is truly required" in FORMAT_GUIDE


def test_format_guide_states_the_real_character_cap():
    # Regression guard: this is a hand-written literal, not interpolated
    # from MAX_TEXT_LENGTH, so it has drifted from the real constant before
    # (the cap moved 160 -> 560 without a mechanical link between the two).
    assert f"capped at {MAX_TEXT_LENGTH} characters" in FORMAT_GUIDE


def _extract_minimal_template() -> dict:
    marker = "Minimal document template"
    tail = FORMAT_GUIDE[FORMAT_GUIDE.index(marker) :]
    json_lines: list[str] = []
    started = False
    for line in tail.split("\n"):
        if line.startswith("    {"):
            started = True
        if started:
            json_lines.append(line)
            if line.strip() == "}" and len(json_lines) > 1:
                break
    snippet = "\n".join(line[4:] if line.startswith("    ") else line for line in json_lines)
    return json.loads(snippet)


def test_minimal_template_is_valid_json():
    data = _extract_minimal_template()
    assert data["cards"][0]["id"] == "c_1"


def test_minimal_template_loads_cleanly_with_no_repairs_needed():
    data = _extract_minimal_template()
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "minimal.idxcards"
        path.write_text(json.dumps(data), encoding="utf-8")
        document = load_document(path)

    assert document.load_warnings == []
    assert len(document.cards) == 1
