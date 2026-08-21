from indexcards.main_window import MainWindow


def test_main_window_has_file_menu(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)

    assert window.windowTitle() == "Index Cards"
    menu_titles = [action.text() for action in window.menuBar().actions()]
    assert "&File" in menu_titles
