from PySide6.QtGui import QUndoStack

from indexcards.models.card import Card
from indexcards.models.document import Document
from indexcards.models.reference import Reference
from indexcards.widgets import card_info_dialog
from indexcards.widgets.card_info_dialog import CardInfoDialog, domain_label


def _dialog(qtbot, references=None) -> tuple[CardInfoDialog, Document, QUndoStack]:
    document = Document(name="Test")
    document.add_card(
        Card(
            id="c_1",
            text="hi",
            references=list(references or []),
            created_at="2026-09-15T15:42:00-04:00",
            modified_at="2026-09-16T09:05:00-04:00",
        )
    )
    stack = QUndoStack()
    dialog = CardInfoDialog(document, stack, "c_1")
    qtbot.addWidget(dialog)
    return dialog, document, stack


def test_domain_label_strips_www_only():
    assert domain_label("https://www.example.com/page") == "example.com"
    assert domain_label("https://blog.example.com") == "blog.example.com"


def test_domain_label_handles_scheme_less_and_unparseable_urls():
    assert domain_label("example.com/some/path") == "example.com"
    assert domain_label("") == ""


def test_shows_created_and_modified_timestamps(qtbot):
    dialog, _document, _stack = _dialog(qtbot)

    assert dialog.created_label.text() == "Created: Sep 15, 2026 at 03:42 PM"
    assert dialog.modified_label.text() == "Modified: Sep 16, 2026 at 09:05 AM"


def test_unparseable_timestamp_is_shown_raw(qtbot):
    dialog, document, _stack = _dialog(qtbot)
    document.get_card("c_1").created_at = "not a date"
    dialog._refresh_timestamps()

    assert dialog.created_label.text() == "Created: not a date"


def test_no_references_shows_add_link_only(qtbot):
    dialog, _document, _stack = _dialog(qtbot)

    assert dialog.reference_labels == []
    assert "Add references..." in dialog.edit_link_label.text()


def test_single_text_and_url_reference_is_a_link_with_arrow_and_no_number(qtbot):
    dialog, _document, _stack = _dialog(
        qtbot, [Reference(text="Dare to Lead", url="https://example.com/dtl")]
    )

    [label] = dialog.reference_labels
    assert label.text() == '<a href="https://example.com/dtl">Dare to Lead</a> ↗'
    assert "Edit references..." in dialog.edit_link_label.text()


def test_text_only_reference_is_plain_with_no_link_or_arrow(qtbot):
    dialog, _document, _stack = _dialog(qtbot, [Reference(text="Dare to Lead; B. Brown; p55")])

    [label] = dialog.reference_labels
    assert label.text() == "Dare to Lead; B. Brown; p55"


def test_url_only_reference_links_with_domain_as_label(qtbot):
    dialog, _document, _stack = _dialog(
        qtbot, [Reference(url="https://www.example.com/some/page")]
    )

    [label] = dialog.reference_labels
    assert label.text() == (
        '<a href="https://www.example.com/some/page">example.com</a> ↗'
    )


def test_two_references_are_numbered(qtbot):
    dialog, _document, _stack = _dialog(
        qtbot, [Reference(text="First"), Reference(text="Second", url="https://b.example")]
    )

    first, second = dialog.reference_labels
    assert first.text() == "1. First"
    assert second.text().startswith("1. ") is False
    assert second.text().startswith("2. <a href=")


def test_reference_text_and_url_are_html_escaped(qtbot):
    dialog, _document, _stack = _dialog(
        qtbot, [Reference(text="<b>bold</b> & co", url="https://x.example/?a=1&b=2")]
    )

    [label] = dialog.reference_labels
    assert "<b>" not in label.text()
    assert "&lt;b&gt;bold&lt;/b&gt; &amp; co" in label.text()
    assert 'href="https://x.example/?a=1&amp;b=2"' in label.text()


def _capture_opened_urls(monkeypatch) -> list[str]:
    opened: list[str] = []
    monkeypatch.setattr(
        card_info_dialog.QDesktopServices,
        "openUrl",
        staticmethod(lambda url: opened.append(url.toString())),
    )
    return opened


def test_clicking_a_reference_link_opens_a_fully_qualified_url_as_is(qtbot, monkeypatch):
    dialog, _document, _stack = _dialog(
        qtbot, [Reference(text="Site", url="https://example.com/a?b=1")]
    )
    opened = _capture_opened_urls(monkeypatch)

    dialog.reference_labels[0].linkActivated.emit("https://example.com/a?b=1")

    assert opened == ["https://example.com/a?b=1"]


def test_clicking_a_scheme_less_link_opens_it_as_https_without_changing_the_data(
    qtbot, monkeypatch
):
    dialog, document, _stack = _dialog(qtbot, [Reference(text="Site", url="mozilla.org")])
    opened = _capture_opened_urls(monkeypatch)

    dialog.reference_labels[0].linkActivated.emit("mozilla.org")

    assert opened == ["https://mozilla.org"]
    assert document.get_card("c_1").references[0].url == "mozilla.org"


def test_openable_url_keeps_mailto_and_other_schemes():
    assert card_info_dialog.openable_url("mailto:a@b.example") == "mailto:a@b.example"
    assert card_info_dialog.openable_url("HTTP://Example.com") == "HTTP://Example.com"
    assert card_info_dialog.openable_url("  example.com/x ") == "https://example.com/x"


def test_edit_link_opens_four_prefilled_fields(qtbot):
    dialog, _document, _stack = _dialog(
        qtbot, [Reference(text="Only", url="https://only.example")]
    )

    dialog.edit_link_label.linkActivated.emit("#")

    assert [edit.text() for edit in dialog.reference_text_edits] == ["Only", ""]
    assert [edit.text() for edit in dialog.reference_url_edits] == ["https://only.example", ""]


def test_cancel_discards_edits_without_pushing_a_command(qtbot):
    dialog, document, stack = _dialog(qtbot)
    dialog.edit_link_label.linkActivated.emit("#")
    dialog.reference_text_edits[0].setText("Typed but discarded")

    dialog.edit_button_box.rejected.emit()

    assert document.get_card("c_1").references == []
    assert not stack.canUndo()
    assert dialog.reference_labels == []


def test_save_pushes_undoable_command_and_returns_to_display(qtbot):
    dialog, document, stack = _dialog(qtbot)
    dialog.edit_link_label.linkActivated.emit("#")
    dialog.reference_text_edits[0].setText("  Dare to Lead  ")
    dialog.reference_url_edits[0].setText("https://example.com")

    dialog.edit_button_box.accepted.emit()

    expected = [Reference(text="Dare to Lead", url="https://example.com")]
    assert document.get_card("c_1").references == expected
    assert len(dialog.reference_labels) == 1
    assert "Edit references..." in dialog.edit_link_label.text()
    stack.undo()
    assert document.get_card("c_1").references == []


def test_save_updates_modified_label(qtbot):
    dialog, _document, _stack = _dialog(qtbot)
    before = dialog.modified_label.text()
    dialog.edit_link_label.linkActivated.emit("#")
    dialog.reference_text_edits[0].setText("Something")

    dialog.edit_button_box.accepted.emit()

    assert dialog.modified_label.text() != before


def test_save_with_only_second_pair_filled_compacts_to_a_single_reference(qtbot):
    dialog, document, _stack = _dialog(qtbot)
    dialog.edit_link_label.linkActivated.emit("#")
    dialog.reference_text_edits[1].setText("Second only")

    dialog.edit_button_box.accepted.emit()

    assert document.get_card("c_1").references == [Reference(text="Second only")]
    [label] = dialog.reference_labels
    assert label.text() == "Second only"


def test_save_with_no_real_change_pushes_nothing(qtbot):
    dialog, _document, stack = _dialog(qtbot, [Reference(text="Same")])
    dialog.edit_link_label.linkActivated.emit("#")

    dialog.edit_button_box.accepted.emit()

    assert not stack.canUndo()


def test_save_with_all_fields_cleared_removes_every_reference(qtbot):
    dialog, document, _stack = _dialog(qtbot, [Reference(text="A"), Reference(text="B")])
    dialog.edit_link_label.linkActivated.emit("#")
    for edit in dialog.reference_text_edits + dialog.reference_url_edits:
        edit.setText("")

    dialog.edit_button_box.accepted.emit()

    assert document.get_card("c_1").references == []
    assert "Add references..." in dialog.edit_link_label.text()


def test_close_button_is_hidden_while_editing_and_returns_after(qtbot):
    dialog, _document, _stack = _dialog(qtbot)
    assert not dialog.close_box.isHidden()

    dialog.edit_link_label.linkActivated.emit("#")
    assert dialog.close_box.isHidden()

    dialog.edit_button_box.rejected.emit()
    assert not dialog.close_box.isHidden()


def test_edit_mode_is_wider_than_display_mode(qtbot):
    dialog, _document, _stack = _dialog(qtbot)
    dialog.edit_link_label.linkActivated.emit("#")

    assert dialog.minimumWidth() >= 560
    assert dialog.width() >= 560

    dialog.edit_button_box.rejected.emit()
    assert dialog.minimumWidth() == 0


def test_escape_while_editing_cancels_instead_of_closing(qtbot):
    dialog, document, stack = _dialog(qtbot)
    dialog.edit_link_label.linkActivated.emit("#")
    dialog.reference_text_edits[0].setText("Typed")

    dialog.reject()

    assert document.get_card("c_1").references == []
    assert not stack.canUndo()
    assert dialog._editing is False


def test_edit_fields_grow_with_the_dialog(qtbot):
    dialog, _document, _stack = _dialog(qtbot)
    dialog.edit_link_label.linkActivated.emit("#")
    dialog.show()
    qtbot.waitExposed(dialog)

    assert dialog.reference_text_edits[0].width() > 300


def test_dialog_shrinks_back_to_its_original_size_after_leaving_edit_mode(qtbot):
    dialog, _document, _stack = _dialog(qtbot)
    dialog.show()
    qtbot.waitExposed(dialog)
    original = dialog.size()

    dialog.edit_link_label.linkActivated.emit("#")
    assert dialog.size() != original
    dialog.edit_button_box.rejected.emit()

    assert dialog.size() == original


def test_is_valid_url_accepts_permissive_real_world_forms():
    for url in (
        "mozilla.org",
        "https://www.example.com/a?b=1&c=%20#frag",
        "sub.example.co.uk:8080/x",
        "http://user:pw@example.com",
        "m\u00fcnchen.de",
        "192.168.0.1/admin",
        "mailto:a@b.example",
        "  example.com  ",
    ):
        assert card_info_dialog.is_valid_url(url), url


def test_is_valid_url_rejects_non_urls():
    for url in (
        "",
        "not a url",
        "localhost",
        "example",
        "example.c",
        "foo.",
        ".com",
        "-bad-.com",
        "https://",
        "https://example.com/<x>",
        "example.com/a b",
        "javascript:alert(1)",
        "file:///etc/passwd",
        "mailto:nobody",
        "exa\x00mple.com",
    ):
        assert not card_info_dialog.is_valid_url(url), url


def test_invalid_url_with_text_shows_plain_text_and_no_link(qtbot):
    dialog, _document, _stack = _dialog(qtbot, [Reference(text="Some Book", url="not a url")])

    [label] = dialog.reference_labels
    assert label.text() == "Some Book"


def test_invalid_url_only_shows_the_raw_value_as_plain_text(qtbot):
    dialog, _document, _stack = _dialog(qtbot, [Reference(url="just some words")])

    [label] = dialog.reference_labels
    assert label.text() == "just some words"
    assert "<a " not in label.text() and "\u2197" not in label.text()
