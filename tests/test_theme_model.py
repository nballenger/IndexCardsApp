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


def test_duplicate_theme_gets_fresh_identity_but_keeps_slot_ids():
    theme = _sample_theme()
    dup = duplicate_theme(theme, new_id="custom_1", new_name="Sample Copy")
    assert dup.id == "custom_1"
    assert dup.name == "Sample Copy"
    assert dup.origin == "custom"
    assert [slot.id for slot in dup.slots] == [slot.id for slot in theme.slots]
    assert dup is not theme
