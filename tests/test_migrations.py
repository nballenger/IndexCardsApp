import pytest

from indexcards.persistence.migrations import CURRENT_SCHEMA_VERSION, migrate


def test_migrate_current_version_is_a_no_op():
    data = {"schema_version": CURRENT_SCHEMA_VERSION, "cards": [], "links": []}
    assert migrate(data) == data


def test_migrate_rejects_future_schema_version():
    data = {"schema_version": CURRENT_SCHEMA_VERSION + 1}
    with pytest.raises(ValueError):
        migrate(data)
