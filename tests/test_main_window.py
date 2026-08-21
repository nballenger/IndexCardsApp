from pathlib import Path

from indexcards.list_view.card_table_model import COLUMN_COLOR, COLUMN_TAGS, COLUMN_TEXT
from indexcards.main_window import MainWindow

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "sample.idxcards"


def test_main_window_has_file_menu(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)

    assert window.windowTitle() == "Index Cards"
    menu_titles = [action.text() for action in window.menuBar().actions()]
    assert "&File" in menu_titles


def test_open_file_populates_list_view(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)

    window.open_file(FIXTURE_PATH)

    assert window.windowTitle() == "Index Cards — Sample Fixture"
    model = window.card_table_model
    assert model.rowCount() == 3
    expected_text = "**Working title**\n\nA story about *time* and index cards."
    assert model.index(0, COLUMN_TEXT).data() == expected_text
    assert model.index(0, COLUMN_COLOR).data() == "#F6E27A"
    assert model.index(0, COLUMN_TAGS).data() == "plot, urgent"
    assert model.index(1, COLUMN_TAGS).data() == ""


def test_open_missing_file_shows_error_without_crashing(qtbot, monkeypatch):
    import indexcards.main_window as main_window_module

    shown_messages = []
    monkeypatch.setattr(
        main_window_module.QMessageBox,
        "critical",
        lambda *args, **kwargs: shown_messages.append(args),
    )

    window = MainWindow()
    qtbot.addWidget(window)

    window.open_file(Path("/nonexistent/path/does_not_exist.idxcards"))

    assert window.document is None
    assert window.card_table_model is None
    assert len(shown_messages) == 1
