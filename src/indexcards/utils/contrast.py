from __future__ import annotations

from PySide6.QtGui import QColor


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
