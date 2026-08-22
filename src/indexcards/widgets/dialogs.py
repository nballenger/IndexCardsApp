from __future__ import annotations

from PySide6.QtWidgets import QCheckBox, QMessageBox, QWidget

from indexcards.app_settings import AppSettings


def confirm_delete_cards(
    parent: QWidget, card_count: int, incident_link_count: int, settings: AppSettings
) -> bool:
    """Asks the user to confirm deleting card_count card(s), unless the
    user has turned that warning off via Settings.

    Card deletion cascades to incident links, which isn't obvious from the
    action alone, so the message calls out how many links would also go.
    """
    if not settings.warn_before_delete:
        return True

    message = f"Delete {card_count} card{'s' if card_count != 1 else ''}?"
    if incident_link_count:
        plural = "s" if incident_link_count != 1 else ""
        message += f" This will also delete {incident_link_count} connected link{plural}."

    box = QMessageBox(parent)
    box.setWindowTitle("Delete Cards")
    box.setIcon(QMessageBox.Icon.Question)
    box.setText(message)
    box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
    box.setDefaultButton(QMessageBox.StandardButton.No)
    dont_ask_again = QCheckBox("Don't ask again", box)
    box.setCheckBox(dont_ask_again)

    reply = box.exec()

    # Applies regardless of which button closed the dialog — it's a
    # standalone preference toggle, independent of this deletion's outcome.
    if dont_ask_again.isChecked():
        settings.warn_before_delete = False

    return reply == QMessageBox.StandardButton.Yes
