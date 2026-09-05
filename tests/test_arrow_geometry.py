from PySide6.QtCore import QPointF

from indexcards.utils.arrow_geometry import arrowhead_half_width, arrowhead_polygon


def test_arrowhead_polygon_points_right():
    polygon = arrowhead_polygon(QPointF(100.0, 0.0), QPointF(1.0, 0.0), length=10.0)

    tip, left, right = polygon[0], polygon[1], polygon[2]
    assert tip == QPointF(100.0, 0.0)
    assert left.x() == right.x() == 90.0
    assert left.y() == -right.y()


def test_arrowhead_polygon_points_left():
    polygon = arrowhead_polygon(QPointF(0.0, 0.0), QPointF(-1.0, 0.0), length=10.0)

    tip, left, right = polygon[0], polygon[1], polygon[2]
    assert tip == QPointF(0.0, 0.0)
    assert left.x() == right.x() == 10.0


def test_arrowhead_polygon_points_down():
    polygon = arrowhead_polygon(QPointF(0.0, 100.0), QPointF(0.0, 1.0), length=10.0)

    tip, left, right = polygon[0], polygon[1], polygon[2]
    assert tip == QPointF(0.0, 100.0)
    assert left.y() == right.y() == 90.0


def test_arrowhead_polygon_wings_are_symmetric_about_the_shaft():
    polygon = arrowhead_polygon(QPointF(50.0, 50.0), QPointF(3.0, 4.0), length=10.0)

    tip, left, right = polygon[0], polygon[1], polygon[2]
    midpoint = QPointF((left.x() + right.x()) / 2, (left.y() + right.y()) / 2)
    # The midpoint of the two wings sits exactly on the shaft's own line
    # back from the tip, at (length) distance -- not off to one side.
    back_distance = ((tip.x() - midpoint.x()) ** 2 + (tip.y() - midpoint.y()) ** 2) ** 0.5
    assert abs(back_distance - 10.0) < 1e-9


def test_arrowhead_polygon_direction_need_not_be_normalized():
    normalized = arrowhead_polygon(QPointF(0.0, 0.0), QPointF(1.0, 0.0), length=10.0)
    unnormalized = arrowhead_polygon(QPointF(0.0, 0.0), QPointF(50.0, 0.0), length=10.0)

    assert list(normalized) == list(unnormalized)


def test_arrowhead_polygon_zero_direction_does_not_crash():
    polygon = arrowhead_polygon(QPointF(0.0, 0.0), QPointF(0.0, 0.0), length=10.0)

    assert len(polygon) == 3


def test_arrowhead_half_width_grows_with_length():
    assert arrowhead_half_width(20.0) > arrowhead_half_width(10.0)
