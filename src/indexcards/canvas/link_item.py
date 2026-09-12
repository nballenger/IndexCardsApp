from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QLineF, QPointF, QRectF, Qt, QVariantAnimation
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
from indexcards.utils.contrast import auto_text_color
from indexcards.utils.line_ending_icons import line_ending_icon

_DIMMED_COLOR = QColor(224, 224, 224)  # fixed, theme-independent -- matches today's exact look
_MIN_HIT_WIDTH = 16.0  # clickable width in scene units, regardless of visual pen weight (1-5px) --
# a thin line is hard to click precisely, so the hit area is always at least this wide
_FLASH_WEIGHT_START = 2.0
_FLASH_WEIGHT_END = 8.0
_FLASH_GROW_DURATION_MS = 900
_FLASH_FADE_DURATION_MS = 300


def _closest_interval_points(
    a_min: float, a_max: float, b_min: float, b_max: float
) -> tuple[float, float]:
    """The closest pair of values, one from [a_min, a_max] and one from
    [b_min, b_max] -- if the intervals don't overlap, their two nearest
    endpoints; if they do overlap, the midpoint of the overlap for both
    (any point in the overlap is equally close along this one axis; the
    midpoint is just a stable, centered choice among them)."""
    if a_max < b_min:
        return a_max, b_min
    if b_max < a_min:
        return a_min, b_max
    overlap_min = max(a_min, b_min)
    overlap_max = min(a_max, b_max)
    mid = (overlap_min + overlap_max) / 2
    return mid, mid


_CORNER_MARGIN_FRACTION = 0.10  # each end of a side is off-limits for this fraction of its length


def _pull_away_from_corner(rect: QRectF, point: QPointF, gap_x: float, gap_y: float) -> QPointF:
    """A corner attachment reads as visually confusing, so a point
    lying on rect's own perimeter is never allowed within
    _CORNER_MARGIN_FRACTION of either end of whichever side it's on --
    slides it inward along that side to the nearest allowed position.
    `gap_x`/`gap_y` (the actual separation between the two rects on
    each axis) only matter for breaking the tie when `point` sits
    exactly at a corner (both axes on the boundary at once, i.e. the
    rects are diagonally separated on both axes): the side more
    perpendicular to the dominant direction of approach is the one
    that gets nudged, so a mostly-horizontal line lands on a vertical
    (left/right) edge and a mostly-vertical line lands on a horizontal
    (top/bottom) edge, matching which edge the line would naturally
    cross first if drawn as a straight ray between the two rects."""
    on_left_or_right = point.x() in (rect.left(), rect.right())
    on_top_or_bottom = point.y() in (rect.top(), rect.bottom())
    if on_left_or_right and on_top_or_bottom:
        on_left_or_right = gap_x >= gap_y
        on_top_or_bottom = not on_left_or_right
    if on_left_or_right:
        margin = rect.height() * _CORNER_MARGIN_FRACTION
        y = min(max(point.y(), rect.top() + margin), rect.bottom() - margin)
        return QPointF(point.x(), y)
    if on_top_or_bottom:
        margin = rect.width() * _CORNER_MARGIN_FRACTION
        x = min(max(point.x(), rect.left() + margin), rect.right() - margin)
        return QPointF(x, point.y())
    return point  # rects overlap on both axes -- no perimeter edge to speak of


def _closest_points_between_rects(rect_a: QRectF, rect_b: QRectF) -> tuple[QPointF, QPointF]:
    """The shortest segment between two axis-aligned, filled rectangles
    -- one endpoint on each rectangle's own perimeter (a corner, when
    the rectangles are diagonally separated; a point along a facing
    edge otherwise), continuously sliding as either rectangle moves,
    rather than snapping between a fixed set of anchor points. Computed
    per-axis via _closest_interval_points, independently for x and y:
    the standard closed-form AABB-to-AABB shortest-distance
    construction. If the rectangles overlap along both axes (the cards
    themselves overlap), this degenerates to a point in the shared
    region on each axis -- a reasonable answer for an otherwise
    ill-defined case. Each raw point is then pulled away from its own
    card's corners via _pull_away_from_corner, per the user's explicit
    request that a corner attachment reads as confusing."""
    xa, xb = _closest_interval_points(rect_a.left(), rect_a.right(), rect_b.left(), rect_b.right())
    ya, yb = _closest_interval_points(rect_a.top(), rect_a.bottom(), rect_b.top(), rect_b.bottom())
    gap_x, gap_y = abs(xb - xa), abs(yb - ya)
    point_a = _pull_away_from_corner(rect_a, QPointF(xa, ya), gap_x, gap_y)
    point_b = _pull_away_from_corner(rect_b, QPointF(xb, yb), gap_x, gap_y)
    return point_a, point_b


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
        # Hold strong references for as long as an animation is running --
        # LinkItem is a QGraphicsLineItem, not a QObject, so it can't be
        # passed as a QVariantAnimation's parent; without these, nothing
        # would keep the animation alive past start_flash() returning.
        self._flash_grow: QVariantAnimation | None = None
        self._flash_fade: QVariantAnimation | None = None
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setPen(self._build_pen())
        self.setZValue(-1)

        source_item.add_position_listener(self._update_line)
        target_item.add_position_listener(self._update_line)
        self._update_line()

    def disconnect_listeners(self) -> None:
        self.source_item.remove_position_listener(self._update_line)
        self.target_item.remove_position_listener(self._update_line)

    def start_flash(self, on_finished: Callable[[], None]) -> None:
        """Draws attention to a link that was just created while Links
        are hidden (see CanvasScene._flash_new_link), since it would
        otherwise vanish with no visible trace it was ever made: the
        line switches to solid black or white -- whichever contrasts
        more against the canvas background -- and grows from
        _FLASH_WEIGHT_START to _FLASH_WEIGHT_END over
        _FLASH_GROW_DURATION_MS, then fades out (opacity 1 -> 0) over
        _FLASH_FADE_DURATION_MS. Restores the real themed pen and full
        opacity before calling on_finished() -- this method only owns
        the animation itself, not what happens to visibility/emphasis
        afterward, which is the caller's call (literally)."""
        flash_color = QColor(auto_text_color(self._document.canvas_background_color))

        self._flash_grow = QVariantAnimation()
        self._flash_grow.setStartValue(_FLASH_WEIGHT_START)
        self._flash_grow.setEndValue(_FLASH_WEIGHT_END)
        self._flash_grow.setDuration(_FLASH_GROW_DURATION_MS)
        self._flash_grow.valueChanged.connect(
            lambda width: self.setPen(QPen(flash_color, width))
        )

        self._flash_fade = QVariantAnimation()
        self._flash_fade.setStartValue(1.0)
        self._flash_fade.setEndValue(0.0)
        self._flash_fade.setDuration(_FLASH_FADE_DURATION_MS)
        self._flash_fade.valueChanged.connect(self.setOpacity)

        def _finish() -> None:
            self.setOpacity(1.0)
            self.setPen(self._build_pen())
            on_finished()

        self._flash_grow.finished.connect(self._flash_fade.start)
        self._flash_fade.finished.connect(_finish)
        self._flash_grow.start()

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
        """Anchors each end to the closest point on that card's own
        perimeter to the other card -- the shortest possible segment
        between the two card rectangles, so the link reads as the
        shortest visual path between them rather than jumping between a
        fixed set of points. Recomputed from scratch on every move
        (source or target) via the position listeners registered in
        __init__, so both attachment points slide continuously as a
        card is dragged around the other."""
        source_rect = self.source_item.boundingRect().translated(self.source_item.pos())
        target_rect = self.target_item.boundingRect().translated(self.target_item.pos())
        source_point, target_point = _closest_points_between_rects(source_rect, target_rect)
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
