from indexcards.widgets.search_bar import SearchBar


def test_typing_emits_query_changed(qtbot):
    bar = SearchBar()
    qtbot.addWidget(bar)

    received = []
    bar.queryChanged.connect(received.append)

    qtbot.keyClicks(bar.line_edit, "time")

    assert received[-1] == "time"


def test_clearing_emits_empty_string(qtbot):
    bar = SearchBar()
    qtbot.addWidget(bar)
    bar.line_edit.setText("something")

    received = []
    bar.queryChanged.connect(received.append)
    bar.line_edit.clear()

    assert received[-1] == ""
