import pytest
from PySide6.QtWidgets import QMessageBox


@pytest.fixture(autouse=True)
def _use_qapp(qapp):
    return qapp


@pytest.fixture(autouse=True)
def _no_blocking_message_boxes(monkeypatch):
    """Safety net so a dirty MainWindow left open at test teardown (qtbot.
    addWidget calls close() on it) can't pop a real blocking modal — a test
    document is throwaway, so "discard" is the right default. Tests that
    care about a specific QMessageBox.question response set their own
    monkeypatch, which applies after this one and wins."""
    monkeypatch.setattr(
        QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.StandardButton.Discard)
    )
