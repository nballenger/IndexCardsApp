import pytest


@pytest.fixture(autouse=True)
def _use_qapp(qapp):
    return qapp
