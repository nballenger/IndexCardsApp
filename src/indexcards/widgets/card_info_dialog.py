from __future__ import annotations

import html
import re
from datetime import datetime
from urllib.parse import urlparse

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices, QUndoStack
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

from indexcards.commands.card_commands import ChangeReferencesCommand
from indexcards.models.card import MAX_REFERENCES
from indexcards.models.document import Document
from indexcards.models.reference import Reference

_EXTERNAL_LINK_GLYPH = "↗"
_EDIT_MODE_MIN_WIDTH = 560


def _format_timestamp(iso: str) -> str:
    try:
        parsed = datetime.fromisoformat(iso)
    except ValueError:
        return iso or "—"
    return parsed.strftime("%b %d, %Y at %I:%M %p")


_HAS_SCHEME = re.compile(r"^([a-z][a-z0-9+.-]*://|mailto:)", re.IGNORECASE)


def openable_url(url: str) -> str:
    """A scheme-less value like "mozilla.org" can't be handed to the OS (macOS
    fails with error -50), so it opens as https://. Only the opened URL is
    adjusted; the stored reference stays exactly as typed."""
    url = url.strip()
    return url if _HAS_SCHEME.match(url) else f"https://{url}"


_SCHEME = re.compile(r"^[a-z][a-z0-9+.-]*://", re.IGNORECASE)
_URL_SAFE = re.compile(r"^[A-Za-z0-9\-._~:/?#\[\]@!$&'()*+,;=%]*$")
_HOST_LABEL = r"[^\W_](?:(?:[^\W_]|-)*[^\W_])?"
_HOST = re.compile(
    rf"^(?:{_HOST_LABEL}\.)+[^\W\d_](?:[^\W_]|-)+$|^\d{{1,3}}(?:\.\d{{1,3}}){{3}}$"
)
_EMAIL_LOCAL = re.compile(r"^[A-Za-z0-9._%+\-]+$")


def is_valid_url(url: str) -> bool:
    """A deliberately permissive check for whether a reference URL is worth
    making clickable: only URL-permissible characters (non-ASCII letters are
    tolerated in the host, for internationalized domains), and a host of at
    least `domain.tld` form (or an IPv4 address). Scheme-less values like
    "mozilla.org" pass, since they open as https://. Anything else, such as
    plain words, "localhost", or "javascript:...", is shown as plain text."""
    url = url.strip()
    if not url or any(ch.isspace() or ord(ch) < 32 for ch in url):
        return False
    if url.lower().startswith("mailto:"):
        local, _, host = url[len("mailto:") :].partition("@")
        return bool(_EMAIL_LOCAL.match(local)) and bool(_HOST.match(host))
    scheme = _SCHEME.match(url)
    rest = url[scheme.end() :] if scheme else url
    authority, tail = re.match(r"^([^/?#]*)(.*)$", rest, re.DOTALL).groups()
    userinfo, has_userinfo, hostport = authority.rpartition("@")
    if has_userinfo and not _URL_SAFE.match(userinfo):
        return False
    host = re.sub(r":\d*$", "", hostport)
    return bool(_HOST.match(host)) and bool(_URL_SAFE.match(tail))


def domain_label(url: str) -> str:
    """Display label for a url-only reference: the host without a leading
    "www." (any other subdomain is kept). A scheme-less string like
    "example.com/page" parses as a bare path, so it's retried as a netloc;
    if no host can be found at all, the raw string is shown as-is."""
    host = urlparse(url).hostname or urlparse("//" + url).hostname
    if not host:
        return url
    return host.removeprefix("www.")


def render_reference_html(reference: Reference, prefix: str = "") -> str:
    """Rich-text body for one reference row. Both fields are html-escaped
    since they're free-form user input going into a rich-text QLabel."""
    text = reference.text.strip()
    url = reference.url.strip()
    if url and not is_valid_url(url):
        return f"{prefix}{html.escape(text or url)}"
    if url:
        label = text or domain_label(url)
        return (
            f'{prefix}<a href="{html.escape(url, quote=True)}">{html.escape(label)}</a> '
            f"{_EXTERNAL_LINK_GLYPH}"
        )
    return f"{prefix}{html.escape(text)}"


class CardInfoDialog(QDialog):
    """Read-only card metadata (created/modified) plus up to two references.
    References are shown as plain/linked text until the user asks to edit
    them, at which point the section swaps to four fields with its own
    Save/Cancel, which are its only exits (the Close button is hidden then)."""

    def __init__(
        self,
        document: Document,
        undo_stack: QUndoStack,
        card_id: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Card Info")
        self._document = document
        self._undo_stack = undo_stack
        self._card_id = card_id

        self.created_label = QLabel(self)
        self.modified_label = QLabel(self)
        self._refresh_timestamps()

        # One swappable page rather than a QStackedWidget: a stack sizes
        # itself to its tallest page, so the dialog never shrank back after
        # leaving edit mode.
        self._editing = False
        self._page: QWidget | None = None
        self._page_holder = QVBoxLayout()
        self._page_holder.setContentsMargins(0, 0, 0, 0)

        self.close_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, self)
        self.close_box.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(self.created_label)
        layout.addWidget(self.modified_label)
        layout.addLayout(self._page_holder)
        layout.addWidget(self.close_box)

        self._show_display_page()

    def _card(self):
        return self._document.get_card(self._card_id)

    def _refresh_timestamps(self) -> None:
        card = self._card()
        self.created_label.setText(f"Created: {_format_timestamp(card.created_at)}")
        self.modified_label.setText(f"Modified: {_format_timestamp(card.modified_at)}")

    def _swap_page(self, page: QWidget, editing: bool) -> None:
        if self._page is not None:
            self._page_holder.removeWidget(self._page)
            self._page.hide()
            self._page.setParent(None)
            self._page.deleteLater()
        self._page = page
        self._page_holder.addWidget(page)
        self._editing = editing

        # Save/Cancel are the only exits while editing; a Close button beside
        # them would make it unclear whether edits are kept.
        # Explicit show()/hide() rather than setVisible(): the layout counts
        # the change immediately, so the resize below sees the right height.
        page.show()
        if editing:
            self.close_box.hide()
        else:
            self.close_box.show()
        self.setMinimumWidth(_EDIT_MODE_MIN_WIDTH if editing else 0)
        self.layout().invalidate()
        self.layout().activate()
        self.resize(self.sizeHint())

    def reject(self) -> None:
        """Escape while editing means Cancel, not "close the whole dialog"."""
        if self._editing:
            self._show_display_page()
            return
        super().reject()

    def _show_display_page(self) -> None:
        references = self._card().references
        page = QWidget(self)
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(0, 0, 0, 0)

        self.reference_labels: list[QLabel] = []
        numbered = len(references) > 1
        for index, reference in enumerate(references):
            prefix = f"{index + 1}. " if numbered else ""
            label = QLabel(page)
            label.setTextFormat(Qt.TextFormat.RichText)
            label.setOpenExternalLinks(False)
            label.setWordWrap(True)
            label.setText(render_reference_html(reference, prefix))
            label.linkActivated.connect(self._open_reference_url)
            page_layout.addWidget(label)
            self.reference_labels.append(label)

        toggle_text = "Edit references..." if references else "Add references..."
        self.edit_link_label = QLabel(f'<a href="#">{toggle_text}</a>', page)
        self.edit_link_label.setTextFormat(Qt.TextFormat.RichText)
        self.edit_link_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self.edit_link_label.linkActivated.connect(self._show_edit_page)
        page_layout.addWidget(self.edit_link_label)

        self._swap_page(page, editing=False)

    def _show_edit_page(self, _href: str = "") -> None:
        references = self._card().references
        page = QWidget(self)
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(0, 0, 0, 0)
        form = QFormLayout()
        # macOS's default keeps fields at their hint width regardless of how
        # wide the dialog is.
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)

        self.reference_text_edits: list[QLineEdit] = []
        self.reference_url_edits: list[QLineEdit] = []
        for index in range(MAX_REFERENCES):
            existing = references[index] if index < len(references) else Reference()
            text_edit = QLineEdit(existing.text, page)
            url_edit = QLineEdit(existing.url, page)
            form.addRow(f"Reference {index + 1} Text", text_edit)
            form.addRow(f"Reference {index + 1} URL", url_edit)
            self.reference_text_edits.append(text_edit)
            self.reference_url_edits.append(url_edit)
        page_layout.addLayout(form)

        self.edit_button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel, page
        )
        self.edit_button_box.accepted.connect(self._save_references)
        self.edit_button_box.rejected.connect(self._show_display_page)
        page_layout.addWidget(self.edit_button_box)

        self._swap_page(page, editing=True)

    def _save_references(self) -> None:
        new_references = []
        for text_edit, url_edit in zip(
            self.reference_text_edits, self.reference_url_edits, strict=True
        ):
            text = text_edit.text().strip()
            url = url_edit.text().strip()
            if text or url:
                new_references.append(Reference(text=text, url=url))

        old_references = self._card().references
        if new_references != old_references:
            self._undo_stack.push(
                ChangeReferencesCommand(
                    self._document, self._card_id, old_references, new_references
                )
            )
            self._refresh_timestamps()
        self._show_display_page()

    def _open_reference_url(self, url: str) -> None:
        QDesktopServices.openUrl(QUrl(openable_url(url)))
