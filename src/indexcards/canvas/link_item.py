from __future__ import annotations

from PySide6.QtCore import QLineF, QPointF, QRectF, Qt
from PySide6.QtGui import (
    QAction,
    QColor,
    QPainterPath,
    QPainterPathStroker,
    QPen,
    QUndoStack,
)
from PySide6.QtWidgets import (
    QGraphicsDropShadowEffect,
    QGraphicsItem,
    QGraphicsLineItem,
    QGraphicsSceneContextMenuEvent,
    QMenu,
)

from indexcards.canvas.card_item import CardItem
from indexcards.canvas.drop_highlight import HALO_BLUR_RADIUS, resolve_highlight_color
from indexcards.commands.link_commands import ChangeLinkLineEndingsCommand
from indexcards.models.document import Document
from indexcards.models.link import LINE_ENDING_OPTIONS
from indexcards.utils.arrow_geometry import arrowhead_half_width, arrowhead_polygon
from indexcards.utils.line_ending_icons import line_ending_icon

_DIMMED_COLOR = QColor(224, 224, 224)  # fixed, theme-independent -- matches today's exact look
_MIN_HIT_WIDTH = 16.0  # clickable width in scene units, regardless of visual pen weight (1-5px) --
# a thin line is hard to click precisely, so the hit area is always at least this wide


def _edge_center_toward(rect: QRectF, direction: QPointF) -> QPointF:
    """One of rect's 4 edge-centers (top/right/bottom/left) — whichever
    side rect's own center faces the given direction vector (pointing
    from rect's center toward the other card). Fixed anchor points, not a
    continuously-sliding boundary crossing — matches multiple links
    sharing one edge-center for now, unspaced (see LinkItem docstring)."""
    center = rect.center()
    if abs(direction.x()) > abs(direction.y()):
        x = rect.right() if direction.x() > 0 else rect.left()
        return QPointF(x, center.y())
    y = rect.bottom() if direction.y() > 0 else rect.top()
    return QPointF(center.x(), y)


class LinkItem(QGraphicsLineItem):
    """A line between two CardItems, kept current as either one moves."""

    def __init__(
        self,
        link_id: str,
        source_item: CardItem,
        target_item: CardItem,
        document: Document,
        undo_stack: QUndoStack | None = None,
    ) -> None:
        super().__init__()
        self.link_id = link_id
        self.source_item = source_item
        self.target_item = target_item
        self._document = document
        self._undo_stack = undo_stack
        self._dimmed = False
        self._line_ending = document.get_link(link_id).line_ending
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setPen(self._build_pen())
        self.setZValue(-1)

        source_item.add_position_listener(self._update_line)
        target_item.add_position_listener(self._update_line)
        self._update_line()

    def disconnect_listeners(self) -> None:
        self.source_item.remove_position_listener(self._update_line)
        self.target_item.remove_position_listener(self._update_line)

    def set_dimmed(self, dimmed: bool) -> None:
        if dimmed == self._dimmed:
            return
        self._dimmed = dimmed
        self.setPen(self._build_pen())

    def refresh(self) -> None:
        """Re-reads the document's current link color/weight and this
        link's own line_ending — called whenever the theme changes
        (whole-theme switch, or the Links > Styling color/weight menus)
        or this link's own line_ending changes (Links > Line Endings, or
        its own context menu). Also re-applies the emphasize glow's color
        if currently emphasized, so a theme/background change doesn't
        leave a stale highlight color behind. self.update() is called
        unconditionally since a line_ending-only change might leave the
        pen itself unchanged, which setPen() alone wouldn't repaint for."""
        self.setPen(self._build_pen())
        self._line_ending = self._document.get_link(self.link_id).line_ending
        self.update()
        if self.graphicsEffect() is not None:
            self._apply_emphasis_effect()

    def set_emphasized(self, emphasized: bool) -> None:
        if emphasized == (self.graphicsEffect() is not None):
            return
        if emphasized:
            self._apply_emphasis_effect()
        else:
            self.setGraphicsEffect(None)

    def _apply_emphasis_effect(self) -> None:
        color = resolve_highlight_color(self._document.canvas_background_color)
        effect = QGraphicsDropShadowEffect()
        effect.setColor(color)
        effect.setOffset(0, 0)
        effect.setBlurRadius(HALO_BLUR_RADIUS)
        self.setGraphicsEffect(effect)

    def _build_pen(self) -> QPen:
        theme = self._document.theme
        color = _DIMMED_COLOR if self._dimmed else QColor(theme.resolved_link_color())
        return QPen(color, theme.link_weight)

    def _update_line(self) -> None:
        """Anchors each end to the closest of the card's 4 edge-centers
        (not its center) — so a later arrowhead/line-ending symbol has
        somewhere to sit that isn't hidden behind the card body. Recomputed
        from scratch on every move (source or target) via the position
        listeners registered in __init__, so which edge each end uses can
        change live as a card is dragged around the other."""
        source_rect = self.source_item.boundingRect().translated(self.source_item.pos())
        target_rect = self.target_item.boundingRect().translated(self.target_item.pos())
        direction = target_rect.center() - source_rect.center()
        source_point = _edge_center_toward(source_rect, direction)
        target_point = _edge_center_toward(target_rect, -direction)
        self.setLine(QLineF(source_point, target_point))

    def boundingRect(self) -> QRectF:
        # A constant worst-case margin (as if an arrowhead were always
        # present at both ends) regardless of the *current* line_ending --
        # avoids any prepareGeometryChange() bookkeeping when line_ending
        # changes at runtime, since only line()/pen() actually vary this
        # rect's inputs, and QGraphicsLineItem's own setLine()/setPen()
        # already call prepareGeometryChange() internally whenever those
        # change. Must also cover shape()'s widened hit area, or Qt's own
        # hit-testing (which intersects the click point against
        # boundingRect() before consulting shape()) would clip it.
        base = super().boundingRect()
        margin = max(arrowhead_half_width(), _MIN_HIT_WIDTH / 2) + self.pen().widthF()
        return base.adjusted(-margin, -margin, margin, margin)

    def shape(self) -> QPainterPath:
        # Widens the clickable/selectable area beyond the thin visual pen
        # stroke (1-5px, per Links > Styling > Line Weight) -- purely a
        # hit-testing affordance, paint() still draws at the real pen
        # width, so nothing about the link's appearance changes.
        path = QPainterPath()
        path.moveTo(self.line().p1())
        path.lineTo(self.line().p2())
        stroker = QPainterPathStroker()
        stroker.setWidth(max(self.pen().widthF(), _MIN_HIT_WIDTH))
        return stroker.createStroke(path)

    def paint(self, painter, option, widget=None) -> None:
        super().paint(painter, option, widget)
        if self._line_ending == "none":
            return
        line = self.line()
        painter.save()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self.pen().color())
        if self._line_ending in ("to_target", "both"):
            painter.drawPolygon(arrowhead_polygon(line.p2(), QPointF(line.dx(), line.dy())))
        if self._line_ending in ("to_source", "both"):
            painter.drawPolygon(arrowhead_polygon(line.p1(), QPointF(-line.dx(), -line.dy())))
        painter.restore()

    def contextMenuEvent(self, event: QGraphicsSceneContextMenuEvent) -> None:
        if self._undo_stack is None:
            event.ignore()
            return
        menu, ending_actions = self._build_context_menu()
        chosen = menu.exec(event.screenPos())
        if chosen in ending_actions:
            link_ids = self._selection_scoped_link_ids()
            self._undo_stack.push(
                ChangeLinkLineEndingsCommand(self._document, link_ids, ending_actions[chosen])
            )

    def _selection_scoped_link_ids(self) -> list[str]:
        """The links a context-menu action from this link should apply
        to: the whole current selection if this link is part of one,
        otherwise just this link — mirrors
        CardItem._selection_scoped_card_ids() exactly, walking
        scene.selectedItems() directly (not CanvasScene.selected_link_ids)
        so it still works against a bare QGraphicsScene in tests."""
        scene = self.scene()
        if scene is not None and self.isSelected():
            selected_ids = [
                item.link_id for item in scene.selectedItems() if isinstance(item, LinkItem)
            ]
            if self.link_id in selected_ids:
                return selected_ids
        return [self.link_id]

    def _build_context_menu(self) -> tuple[QMenu, dict[QAction, str]]:
        """Builds the menu without exec()'ing it, so tests can inspect its
        contents without triggering a real, blocking modal popup."""
        menu = QMenu()
        ending_menu = menu.addMenu("Line Endings")
        ending_actions: dict[QAction, str] = {}
        for value, label in LINE_ENDING_OPTIONS:
            icon = line_ending_icon(value)
            if icon is not None:
                action = ending_menu.addAction(icon, label)
            else:
                action = ending_menu.addAction(label)
            action.setCheckable(True)
            action.setChecked(value == self._line_ending)
            ending_actions[action] = value
        return menu, ending_actions
