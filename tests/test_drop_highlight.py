from PySide6.QtWidgets import QGraphicsRectItem, QGraphicsScene

from indexcards.canvas.drop_highlight import (
    apply_drop_highlight,
    is_drop_highlighted,
    resolve_highlight_color,
)


def _scene_with_item() -> tuple[QGraphicsScene, QGraphicsRectItem]:
    scene = QGraphicsScene()
    item = QGraphicsRectItem(0.0, 0.0, 200.0, 120.0)
    scene.addItem(item)
    return scene, item


def _other_items(scene: QGraphicsScene, item: QGraphicsRectItem) -> list:
    return [i for i in scene.items() if i is not item]


def test_apply_true_adds_a_ring_with_expected_look():
    scene, item = _scene_with_item()

    apply_drop_highlight(item, True, background_hex="#1f4a3d")

    assert is_drop_highlighted(item) is True
    (ring,) = _other_items(scene, item)
    assert ring.pen().color().name() == "#16ffff"
    effect = ring.graphicsEffect()
    assert effect is not None
    assert effect.color().name() == "#16ffff"
    assert effect.offset().x() == 0
    assert effect.offset().y() == 0
    assert effect.blurRadius() == 24.0


def test_apply_false_removes_the_ring():
    scene, item = _scene_with_item()
    apply_drop_highlight(item, True, background_hex="#1f4a3d")

    apply_drop_highlight(item, False)

    assert is_drop_highlighted(item) is False
    assert _other_items(scene, item) == []


def test_apply_false_on_an_unhighlighted_item_is_a_noop():
    scene, item = _scene_with_item()

    apply_drop_highlight(item, False)

    assert is_drop_highlighted(item) is False
    assert _other_items(scene, item) == []


def test_apply_true_twice_does_not_add_a_second_ring():
    scene, item = _scene_with_item()
    apply_drop_highlight(item, True, background_hex="#1f4a3d")

    apply_drop_highlight(item, True, background_hex="#1f4a3d")

    assert len(_other_items(scene, item)) == 1


def test_apply_true_without_a_scene_is_a_noop():
    item = QGraphicsRectItem(0.0, 0.0, 200.0, 120.0)  # never added to a scene

    apply_drop_highlight(item, True, background_hex="#1f4a3d")

    assert is_drop_highlighted(item) is False


def test_falls_back_to_auto_text_color_when_background_matches_the_halo():
    scene, item = _scene_with_item()

    apply_drop_highlight(item, True, background_hex="#16ffff")

    (ring,) = _other_items(scene, item)
    assert ring.pen().color().name() == "#000000"
    assert ring.graphicsEffect().color().name() == "#000000"


def test_ring_z_value_sits_below_the_dragged_item_not_just_above_the_target():
    # Regression: an earlier version placed the ring far above *everything*
    # (target.zValue() + a large constant), which put it above the actively
    # dragged item too -- so the dragged card visually vanished under the
    # ring's frame the moment it crossed into the trigger zone.
    scene, item = _scene_with_item()
    item.setZValue(5.0)
    dragged = QGraphicsRectItem(0.0, 0.0, 200.0, 120.0)
    dragged.setZValue(9.0)  # freshly raised above the target, as bring_item_to_front would do
    scene.addItem(dragged)

    apply_drop_highlight(item, True, background_hex="#1f4a3d", dragged_item=dragged)

    (ring,) = [i for i in scene.items() if i not in (item, dragged)]
    assert item.zValue() < ring.zValue() < dragged.zValue()


def test_ring_z_value_falls_back_to_above_the_target_without_a_dragged_item():
    scene, item = _scene_with_item()
    item.setZValue(5.0)

    apply_drop_highlight(item, True, background_hex="#1f4a3d")

    (ring,) = _other_items(scene, item)
    assert ring.zValue() > item.zValue()


def test_resolve_highlight_color_returns_halo_color_against_a_normal_background():
    assert resolve_highlight_color("#1f4a3d").name() == "#16ffff"


def test_resolve_highlight_color_falls_back_when_background_matches_the_halo():
    assert resolve_highlight_color("#16ffff").name() == "#000000"
