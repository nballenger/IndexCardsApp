from indexcards.models.theme import Slot, Theme, clone_theme, duplicate_theme


def _sample_theme() -> Theme:
    return Theme(
        id="t_1",
        name="Sample",
        origin="custom",
        background_color="#112233",
        slots=[
            Slot(id="slot_a", label="A", hex="#ff0000"),
            Slot(id="slot_b", label="B", hex="#00ff00", text_color="#000000", orphaned=True),
        ],
    )


def test_slot_to_dict_and_from_dict_round_trip():
    slot = Slot(id="s1", label="Urgent", hex="#ff0000", text_color="#ffffff", orphaned=True)
    restored = Slot.from_dict(slot.to_dict())
    assert restored == slot


def test_slot_from_dict_defaults_missing_optional_fields():
    slot = Slot.from_dict({"id": "s1", "hex": "#ff0000"})
    assert slot.label == ""
    assert slot.text_color is None
    assert slot.orphaned is False


def test_theme_to_dict_and_from_dict_round_trip():
    theme = _sample_theme()
    restored = Theme.from_dict(theme.to_dict())
    assert restored == theme


def test_theme_get_slot_returns_matching_slot():
    theme = _sample_theme()
    slot = theme.get_slot("slot_b")
    assert slot is not None
    assert slot.label == "B"


def test_theme_get_slot_returns_none_for_unknown_id():
    theme = _sample_theme()
    assert theme.get_slot("nope") is None


def test_clone_theme_is_independent_copy():
    theme = _sample_theme()
    clone = clone_theme(theme)
    assert clone == theme
    assert clone is not theme
    clone.slots.append(Slot(id="slot_c", label="C", hex="#0000ff"))
    assert len(theme.slots) == 2


def test_theme_link_styling_fields_default():
    theme = _sample_theme()
    assert theme.link_color == "#808080"
    assert theme.link_color_mode == "theme"
    assert theme.link_weight == 2


def test_theme_link_styling_round_trips_non_default_values():
    theme = Theme(
        id="t_1",
        name="Sample",
        origin="custom",
        background_color="#112233",
        link_color="#336699",
        link_color_mode="white",
        link_weight=5,
    )
    restored = Theme.from_dict(theme.to_dict())
    assert restored == theme


def test_theme_from_dict_defaults_missing_link_styling_fields():
    theme = Theme.from_dict(
        {"id": "t_1", "name": "Sample", "origin": "custom", "background_color": "#112233"}
    )
    assert theme.link_color == "#808080"
    assert theme.link_color_mode == "theme"
    assert theme.link_weight == 2


def test_resolved_link_color_theme_mode_uses_link_color():
    theme = _sample_theme()
    theme.link_color = "#336699"
    theme.link_color_mode = "theme"
    assert theme.resolved_link_color() == "#336699"


def test_resolved_link_color_white_mode_ignores_link_color():
    theme = _sample_theme()
    theme.link_color = "#336699"
    theme.link_color_mode = "white"
    assert theme.resolved_link_color() == "#ffffff"


def test_resolved_link_color_black_mode_ignores_link_color():
    theme = _sample_theme()
    theme.link_color = "#336699"
    theme.link_color_mode = "black"
    assert theme.resolved_link_color() == "#000000"


def test_duplicate_theme_gets_fresh_identity_but_keeps_slot_ids():
    theme = _sample_theme()
    dup = duplicate_theme(theme, new_id="custom_1", new_name="Sample Copy")
    assert dup.id == "custom_1"
    assert dup.name == "Sample Copy"
    assert dup.origin == "custom"
    assert [slot.id for slot in dup.slots] == [slot.id for slot in theme.slots]
    assert dup is not theme
