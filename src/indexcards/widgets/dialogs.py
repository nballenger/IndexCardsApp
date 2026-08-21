from __future__ import annotations

from PySide6.QtWidgets import QMessageBox, QWidget


def confirm_delete_cards(parent: QWidget, card_count: int, incident_link_count: int) -> bool:
    """Asks the user to confirm deleting card_count card(s).

    Card deletion cascades to incident links, which isn't obvious from the
    action alone, so the message calls out how many links would also go.
    """
    message = f"Delete {card_count} card{'s' if card_count != 1 else ''}?"
    if incident_link_count:
        plural = "s" if incident_link_count != 1 else ""
        message += f" This will also delete {incident_link_count} connected link{plural}."

    reply = QMessageBox.question(
        parent,
        "Delete Cards",
        message,
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.No,
    )
    return reply == QMessageBox.StandardButton.Yes
