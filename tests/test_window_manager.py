from pathlib import Path

from indexcards.window_manager import WindowManager

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "sample.idxcards"


def test_open_new_window_tracks_and_shows_window(qtbot):
    manager = WindowManager()
    window = manager.open_new_window()
    qtbot.addWidget(window)

    assert window in manager._windows
    assert window.document is not None
    assert window.document.name == "Untitled"


def test_open_new_window_multiple_times_creates_separate_windows(qtbot):
    manager = WindowManager()
    window1 = manager.open_new_window()
    window2 = manager.open_new_window()
    qtbot.addWidget(window1)
    qtbot.addWidget(window2)

    assert window1 is not window2
    assert len(manager._windows) == 2


def test_open_file_opens_new_window_with_document_loaded(qtbot):
    manager = WindowManager()
    window = manager.open_file(FIXTURE_PATH)
    qtbot.addWidget(window)

    assert window.document.name == "Sample Fixture"
    assert window.current_path == FIXTURE_PATH
    assert len(manager._windows) == 1


def test_open_file_already_open_focuses_existing_window(qtbot):
    manager = WindowManager()
    first = manager.open_file(FIXTURE_PATH)
    qtbot.addWidget(first)

    second = manager.open_file(FIXTURE_PATH)

    assert second is first
    assert len(manager._windows) == 1


def test_open_file_twice_with_different_files_creates_two_windows(qtbot, tmp_path):
    from indexcards.models.card import Card
    from indexcards.models.document import Document
    from indexcards.persistence.file_io import save_document

    other_path = tmp_path / "other.idxcards"
    document = Document(name="Other")
    document.add_card(Card(id="c_1"))
    save_document(document, other_path)

    manager = WindowManager()
    first = manager.open_file(FIXTURE_PATH)
    second = manager.open_file(other_path)
    qtbot.addWidget(first)
    qtbot.addWidget(second)

    assert first is not second
    assert len(manager._windows) == 2


def test_forget_window_removes_from_tracking(qtbot):
    manager = WindowManager()
    window = manager.open_new_window()
    qtbot.addWidget(window)

    manager.forget_window(window)

    assert window not in manager._windows


def test_forget_window_not_tracked_is_a_noop(qtbot):
    manager = WindowManager()
    window = manager.open_new_window()
    qtbot.addWidget(window)
    manager.forget_window(window)

    manager.forget_window(window)  # already removed; must not raise

    assert window not in manager._windows


def test_windows_share_the_same_undo_group(qtbot):
    manager = WindowManager()
    window1 = manager.open_new_window()
    window2 = manager.open_new_window()
    qtbot.addWidget(window1)
    qtbot.addWidget(window2)

    assert window1.undo_stack in manager.undo_group.stacks()
    assert window2.undo_stack in manager.undo_group.stacks()
