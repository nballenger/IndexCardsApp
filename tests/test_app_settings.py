from PySide6.QtCore import QSettings

from indexcards.app_settings import DEFAULT_ARRANGE_COLUMN_LIMIT, AppSettings
from indexcards.models.document import DEFAULT_CANVAS_BACKGROUND_COLOR


def test_defaults_with_no_backing():
    settings = AppSettings()

    assert settings.warn_before_delete is True
    assert settings.default_background_color == DEFAULT_CANVAS_BACKGROUND_COLOR
    assert settings.limit_arrange_columns is False
    assert settings.arrange_column_limit == DEFAULT_ARRANGE_COLUMN_LIMIT


def test_setting_values_with_no_backing_does_not_touch_qsettings(monkeypatch):
    def fail_if_constructed(*args, **kwargs):
        raise AssertionError("QSettings should not be constructed with no backing")

    monkeypatch.setattr(QSettings, "__init__", fail_if_constructed)

    settings = AppSettings()
    settings.warn_before_delete = False
    settings.default_background_color = "#111111"
    settings.limit_arrange_columns = True
    settings.arrange_column_limit = 5

    assert settings.warn_before_delete is False
    assert settings.default_background_color == "#111111"
    assert settings.limit_arrange_columns is True
    assert settings.arrange_column_limit == 5


def test_arrange_column_limit_setter_clamps_below_minimum():
    settings = AppSettings()

    settings.arrange_column_limit = 1

    assert settings.arrange_column_limit == 2


def _temp_backing(tmp_path) -> QSettings:
    return QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)


def test_backing_constructor_reads_existing_stored_values(tmp_path):
    backing = _temp_backing(tmp_path)
    backing.setValue("warnBeforeDelete", False)
    backing.setValue("defaultBackgroundColor", "#222222")
    backing.setValue("limitArrangeColumns", True)
    backing.setValue("arrangeColumnLimit", 8)

    settings = AppSettings(backing)

    assert settings.warn_before_delete is False
    assert settings.default_background_color == "#222222"
    assert settings.limit_arrange_columns is True
    assert settings.arrange_column_limit == 8


def test_setting_a_value_persists_to_backing(tmp_path):
    backing = _temp_backing(tmp_path)
    settings = AppSettings(backing)

    settings.warn_before_delete = False
    settings.default_background_color = "#333333"
    settings.limit_arrange_columns = True
    settings.arrange_column_limit = 9

    reloaded = AppSettings(backing)
    assert reloaded.warn_before_delete is False
    assert reloaded.default_background_color == "#333333"
    assert reloaded.limit_arrange_columns is True
    assert reloaded.arrange_column_limit == 9


def test_backing_with_corrupted_column_limit_below_minimum_is_clamped_on_load(tmp_path):
    backing = _temp_backing(tmp_path)
    backing.setValue("arrangeColumnLimit", 0)

    settings = AppSettings(backing)

    assert settings.arrange_column_limit == 2


def test_bool_round_trips_correctly_through_a_fresh_instance(tmp_path):
    # Guards a known Qt gotcha: some QSettings backends round-trip bool
    # through string storage and hand back a truthy non-empty string on
    # read, which would make bool(value) always True without type=bool.
    backing = _temp_backing(tmp_path)
    settings = AppSettings(backing)
    settings.warn_before_delete = False

    reloaded = AppSettings(_temp_backing(tmp_path))
    assert reloaded.warn_before_delete is False
