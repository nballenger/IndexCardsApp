from __future__ import annotations

from PySide6.QtGui import QColor

from indexcards.models.theme import Theme


def _linearize(channel: float) -> float:
    if channel <= 0.04045:
        return channel / 12.92
    return ((channel + 0.055) / 1.055) ** 2.4


def relative_luminance(hex_value: str) -> float:
    """WCAG 2.x relative luminance of a color, in [0, 1]."""
    color = QColor(hex_value)
    r, g, b = (_linearize(v) for v in (color.redF(), color.greenF(), color.blueF()))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(hex_a: str, hex_b: str) -> float:
    """WCAG 2.x contrast ratio between two colors, in [1, 21]."""
    luminance_a, luminance_b = relative_luminance(hex_a), relative_luminance(hex_b)
    lighter, darker = max(luminance_a, luminance_b), min(luminance_a, luminance_b)
    return (lighter + 0.05) / (darker + 0.05)


def auto_text_color(hex_value: str) -> str:
    """Whichever of black/white has the higher WCAG contrast ratio against
    hex_value; ties favor black."""
    white_contrast = contrast_ratio(hex_value, "#ffffff")
    black_contrast = contrast_ratio(hex_value, "#000000")
    return "#ffffff" if white_contrast > black_contrast else "#000000"


def best_contrasting_color(candidates: list[str], reference_hexes: list[str]) -> str:
    """Whichever hex in candidates has the best worst-case WCAG contrast
    ratio across every color in reference_hexes -- the choice most likely
    to stay visible regardless of which reference color it ends up next
    to. Ties favor whichever candidate appears first in the list."""
    return max(
        candidates,
        key=lambda candidate: min(contrast_ratio(candidate, ref) for ref in reference_hexes),
    )


def selection_outline_color(theme: Theme) -> str:
    """Black or white, whichever keeps a better worst-case WCAG contrast
    against both the theme's canvas background and every non-orphaned
    slot -- so a selected card/stack's outline stays visible no matter
    which color it's using, without a different outline color per item
    (which would look inconsistent across a multi-selection). An orphaned
    slot is excluded: it renders hatched, not as a flat fill, so it isn't
    a real contrast reference the way an active slot is."""
    reference_hexes = [theme.background_color] + [
        slot.hex for slot in theme.slots if not slot.orphaned
    ]
    return best_contrasting_color(["#000000", "#ffffff"], reference_hexes)
