from indexcards.models.card import Card
from indexcards.models.document import Document
from indexcards.models.theme import Slot, Theme, duplicate_theme


def _document_with_slots() -> Document:
    theme = Theme(
        id="t_1",
        name="Test Theme",
        origin="custom",
        background_color="#3d6b4f",
        slots=[
            Slot(id="slot_a", label="A", hex="#ff0000"),
            Slot(id="slot_b", label="B", hex="#00ff00"),
            Slot(id="slot_c", label="C", hex="#0000ff"),
        ],
    )
    return Document(name="Test", theme=theme)


def _edited(slots: list[Slot], background_color: str = "#3d6b4f") -> Theme:
    return Theme(
        id="t_1", name="Test Theme", origin="custom", background_color=background_color,
        slots=slots,
    )


def test_set_theme_snapshot_replaces_theme_and_marks_dirty(qtbot):
    document = _document_with_slots()
    new_theme = Theme(id="t_2", name="New", origin="custom", background_color="#000000")

    with qtbot.waitSignal(document.themeChanged, timeout=1000):
        document.set_theme_snapshot(new_theme)

    assert document.theme is new_theme
    assert document.dirty is True


def test_set_theme_snapshot_same_object_is_a_noop():
    document = _document_with_slots()
    theme = document.theme

    received = []
    document.themeChanged.connect(lambda: received.append(True))
    document.set_theme_snapshot(theme)

    assert received == []
    assert document.dirty is False


def test_plan_theme_edit_removes_unused_slot():
    document = _document_with_slots()
    edited = _edited([Slot(id="slot_a", label="A", hex="#ff0000")])

    theme_to_apply, newly_orphaned = document.plan_theme_edit(edited)

    assert {slot.id for slot in theme_to_apply.slots} == {"slot_a"}
    assert newly_orphaned == []


def test_plan_theme_edit_restores_in_use_slot_as_orphaned():
    document = _document_with_slots()
    document.add_card(Card(id="c_1", color_slot="slot_c"))
    edited = _edited([Slot(id="slot_a", label="A", hex="#ff0000")])

    theme_to_apply, newly_orphaned = document.plan_theme_edit(edited)

    assert newly_orphaned == ["slot_c"]
    restored = theme_to_apply.get_slot("slot_c")
    assert restored is not None
    assert restored.orphaned is True
    assert restored.hex == "#0000ff"
    assert restored.label == "C"


def test_plan_theme_edit_does_not_mutate_documents_current_theme():
    document = _document_with_slots()
    document.add_card(Card(id="c_1", color_slot="slot_c"))
    original_slot_ids = {slot.id for slot in document.theme.slots}
    edited = _edited([Slot(id="slot_a", label="A", hex="#ff0000")])

    document.plan_theme_edit(edited)

    assert {slot.id for slot in document.theme.slots} == original_slot_ids


def test_plan_theme_edit_relabels_and_recolors_kept_slot():
    document = _document_with_slots()
    edited = _edited(
        [
            Slot(id="slot_a", label="Renamed", hex="#123456"),
            Slot(id="slot_b", label="B", hex="#00ff00"),
            Slot(id="slot_c", label="C", hex="#0000ff"),
        ]
    )

    theme_to_apply, _ = document.plan_theme_edit(edited)

    slot_a = theme_to_apply.get_slot("slot_a")
    assert slot_a.label == "Renamed"
    assert slot_a.hex == "#123456"


def test_plan_theme_edit_preserves_background_color_change():
    document = _document_with_slots()
    edited = _edited(
        [
            Slot(id="slot_a", label="A", hex="#ff0000"),
            Slot(id="slot_b", label="B", hex="#00ff00"),
            Slot(id="slot_c", label="C", hex="#0000ff"),
        ],
        background_color="#ffffff",
    )

    theme_to_apply, _ = document.plan_theme_edit(edited)

    assert theme_to_apply.background_color == "#ffffff"


def test_plan_theme_edit_multiple_in_use_slots_all_orphaned():
    document = _document_with_slots()
    document.add_card(Card(id="c_1", color_slot="slot_b"))
    document.add_card(Card(id="c_2", color_slot="slot_c"))
    edited = _edited([Slot(id="slot_a", label="A", hex="#ff0000")])

    theme_to_apply, newly_orphaned = document.plan_theme_edit(edited)

    assert set(newly_orphaned) == {"slot_b", "slot_c"}
    assert theme_to_apply.get_slot("slot_b").orphaned is True
    assert theme_to_apply.get_slot("slot_c").orphaned is True


def _target_theme(theme_id: str, slots: list[Slot]) -> Theme:
    return Theme(
        id=theme_id, name="Target", origin="preset", background_color="#000000", slots=slots
    )


def test_plan_theme_switch_to_theme_covering_every_used_color_is_orphan_free():
    document = _document_with_slots()
    document.add_card(Card(id="c_1", color_slot="slot_a"))
    target = _target_theme(
        "preset_target",
        [Slot(id="slot_a", label="A", hex="#ff0000"), Slot(id="slot_x", label="X", hex="#eeeeee")],
    )

    theme_to_apply, newly_orphaned = document.plan_theme_switch(target)

    assert theme_to_apply.id == "preset_target"
    assert newly_orphaned == []
    assert theme_to_apply is not target  # independent clone


def test_plan_theme_switch_missing_color_carries_it_over_as_orphaned():
    document = _document_with_slots()
    document.add_card(Card(id="c_1", color_slot="slot_c"))  # #0000ff, not in target
    target = _target_theme("preset_target", [Slot(id="slot_x", label="X", hex="#eeeeee")])

    theme_to_apply, newly_orphaned = document.plan_theme_switch(target)

    assert newly_orphaned == ["slot_c"]
    assert theme_to_apply.id != "preset_target"  # a fresh custom id, not the target's own
    assert theme_to_apply.origin == "custom"
    carried = theme_to_apply.get_slot("slot_c")
    assert carried is not None
    assert carried.orphaned is True
    assert carried.hex == "#0000ff"
    assert carried.label == "C"
    assert theme_to_apply.get_slot("slot_x") is not None  # target's own slot still present


def test_plan_theme_switch_no_card_visibly_changes_color_when_orphans_result():
    document = _document_with_slots()
    document.add_card(Card(id="c_1", color_slot="slot_c"))
    target = _target_theme("preset_target", [Slot(id="slot_x", label="X", hex="#eeeeee")])

    theme_to_apply, _ = document.plan_theme_switch(target)

    # The card's own color_slot reference is untouched by plan_theme_switch
    # (only document.theme changes) — it still resolves to the same hex,
    # now via the carried-over orphaned slot instead of the old theme's.
    assert document.get_card("c_1").color_slot == "slot_c"
    assert theme_to_apply.get_slot("slot_c").hex == "#0000ff"


def test_plan_theme_switch_to_a_duplicate_of_current_theme_is_orphan_free():
    document = _document_with_slots()
    document.add_card(Card(id="c_1", color_slot="slot_c"))
    duplicate = duplicate_theme(document.theme, "custom_dup", "Duplicate")

    theme_to_apply, newly_orphaned = document.plan_theme_switch(duplicate)

    assert newly_orphaned == []
    assert theme_to_apply.id == "custom_dup"
    assert {slot.id for slot in theme_to_apply.slots} == {"slot_a", "slot_b", "slot_c"}


def test_plan_theme_switch_does_not_mutate_target_theme():
    document = _document_with_slots()
    document.add_card(Card(id="c_1", color_slot="slot_c"))
    target = _target_theme("preset_target", [Slot(id="slot_x", label="X", hex="#eeeeee")])
    original_slot_count = len(target.slots)

    document.plan_theme_switch(target)

    assert len(target.slots) == original_slot_count
