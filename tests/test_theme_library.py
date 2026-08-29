from indexcards.models.theme import Theme
from indexcards.theme_library import ThemeLibrary


def _theme(theme_id: str = "custom_1", name: str = "My Theme") -> Theme:
    return Theme(id=theme_id, name=name, origin="custom", background_color="#123456")


def test_in_memory_library_starts_empty():
    library = ThemeLibrary()
    assert library.all() == []


def test_add_makes_theme_retrievable():
    library = ThemeLibrary()
    theme = _theme()

    library.add(theme)

    assert library.get("custom_1") is theme
    assert library.all() == [theme]


def test_get_returns_none_for_unknown_id():
    library = ThemeLibrary()
    assert library.get("nope") is None


def test_update_replaces_existing_entry():
    library = ThemeLibrary()
    library.add(_theme(name="Original"))

    library.update(_theme(name="Renamed"))

    assert library.get("custom_1").name == "Renamed"
    assert len(library.all()) == 1


def test_remove_drops_entry():
    library = ThemeLibrary()
    library.add(_theme())

    library.remove("custom_1")

    assert library.get("custom_1") is None
    assert library.all() == []


def test_remove_unknown_id_is_a_noop():
    library = ThemeLibrary()
    library.remove("nope")  # must not raise
    assert library.all() == []


def test_in_memory_library_never_touches_disk(tmp_path, monkeypatch):
    def fail_if_called(*args, **kwargs):
        raise AssertionError("save_custom_themes should not be called for an in-memory library")

    monkeypatch.setattr("indexcards.theme_library.save_custom_themes", fail_if_called)

    library = ThemeLibrary()
    library.add(_theme())
    library.update(_theme(name="Renamed"))
    library.remove("custom_1")


def test_persisted_library_round_trips_through_a_fresh_instance(tmp_path):
    path = tmp_path / "custom_themes.json"
    library = ThemeLibrary(path)
    library.add(_theme())

    reloaded = ThemeLibrary(path)

    assert reloaded.get("custom_1").name == "My Theme"


def test_persisted_library_survives_add_update_remove_round_trip(tmp_path):
    path = tmp_path / "custom_themes.json"
    library = ThemeLibrary(path)
    library.add(_theme("custom_1", "First"))
    library.add(_theme("custom_2", "Second"))
    library.update(_theme("custom_1", "First Renamed"))
    library.remove("custom_2")

    reloaded = ThemeLibrary(path)

    assert [theme.id for theme in reloaded.all()] == ["custom_1"]
    assert reloaded.get("custom_1").name == "First Renamed"


def test_constructing_with_a_nonexistent_path_starts_empty(tmp_path):
    library = ThemeLibrary(tmp_path / "does_not_exist_yet.json")
    assert library.all() == []
