import pytest

from indexcards.utils.contrast import auto_text_color, contrast_ratio, relative_luminance


def test_relative_luminance_of_white_is_one():
    assert relative_luminance("#ffffff") == pytest.approx(1.0)


def test_relative_luminance_of_black_is_zero():
    assert relative_luminance("#000000") == pytest.approx(0.0)


def test_contrast_ratio_of_black_and_white_is_21():
    assert contrast_ratio("#ffffff", "#000000") == pytest.approx(21.0, rel=1e-3)


def test_contrast_ratio_is_symmetric():
    assert contrast_ratio("#336699", "#ffffff") == pytest.approx(
        contrast_ratio("#ffffff", "#336699")
    )


def test_contrast_ratio_of_a_color_with_itself_is_one():
    assert contrast_ratio("#336699", "#336699") == pytest.approx(1.0)


def test_auto_text_color_picks_black_on_light_background():
    assert auto_text_color("#f6e27a") == "#000000"  # today's Yellow


def test_auto_text_color_picks_white_on_dark_background():
    assert auto_text_color("#1a1a1a") == "#ffffff"


def test_auto_text_color_on_white_is_black():
    assert auto_text_color("#ffffff") == "#000000"


def test_auto_text_color_on_black_is_white():
    assert auto_text_color("#000000") == "#ffffff"
