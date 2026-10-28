import math
import pytest

from doemo_pdf.geometry import Matrix, Rect, fit, rotation_to_up, component_transform
from doemo_pdf.pdf import parse_label


@pytest.mark.parametrize("direction,expected", [((0,1),0), ((1,0),90), ((0,-1),180),
                                               ((-1,0),-90), ((1,1),45), ((-1,-1),-135)])
def test_direction_to_up(direction, expected):
    assert rotation_to_up(direction) == pytest.approx(expected)
    matrix, scale, _ = fit(Rect(-10,20,80,170), Rect(20,30,320,600), direction)
    dx, dy = matrix.vector(direction)
    assert dx == pytest.approx(0, abs=1e-9)
    assert dy > 0
    assert math.hypot(dx,dy) == pytest.approx(scale*math.hypot(*direction))


@pytest.mark.parametrize("degrees", [0, 17.25, 45, 90, 123, 180, 249.6, 359.9])
def test_inverse_proportions_centering_and_fit(degrees):
    direction = (math.cos(math.radians(degrees)), math.sin(math.radians(degrees)))
    source, zone = Rect(-120,35,280,600), Rect(25,75,800,1100)
    m, scale, _ = fit(source,zone,direction)
    assert zone.contains(m.bounds(source))
    assert m.point(source.center) == pytest.approx(zone.center)
    assert m.a*m.d-m.b*m.c == pytest.approx(scale**2)
    assert m.a*m.c+m.b*m.d == pytest.approx(0,abs=1e-10)
    for p in source.corners + ((13,45),):
        assert m.inverse().point(m.point(p)) == pytest.approx(p, abs=1e-8)


def test_reduce_only_and_margins():
    source = Rect(0,0,10,20)
    zone = Rect(0,0,200,300).inset(12)
    assert fit(source,zone,(0,1),False)[1] == 1
    assert fit(source,zone,(0,1),True)[1] > 1


@pytest.mark.parametrize("direction", [(0,0),(float('nan'),1),(1,float('inf'))])
def test_invalid_directions_rejected(direction):
    with pytest.raises(ValueError):
        rotation_to_up(direction)


@pytest.mark.parametrize("bounds", [(0,0,0,1),(1,0,0,1),(0,2,1,1),(0,0,float('nan'),3)])
def test_invalid_rectangles_rejected(bounds):
    with pytest.raises(ValueError):
        Rect(*bounds)


@pytest.mark.parametrize("label,kind,orientation", [('PE H','PE','H'),('pe.v','PE','V'),
    ('PI-H','PI','H'),('PI1 V','PI','V'),('PE2 V','PE','V'),('PEV','PE','V'),('PI.V.A3','PI','V')])
def test_labels(label,kind,orientation):
    parsed = parse_label(label)
    assert (parsed['type'], parsed['orientation']) == (kind,orientation)


@pytest.mark.parametrize("label", ['EVACUATION','SORTIE','PE','H','RAPIDE','PIV libre'])
def test_other_text_not_classified_as_vei(label):
    assert parse_label(label) is None


@pytest.mark.parametrize('direction',[(1,0),(-1,0),(0,-1),(2,3)])
def test_counter_rotation_keeps_reference_reading_orientation_and_anchor(direction):
    m,scale,angle=fit(Rect(0,0,400,600),Rect(12,12,800,1100),direction)
    anchor=(125,210)
    upright=component_transform(m,angle,anchor,directional=False)
    assert upright.point(anchor)==pytest.approx(m.point(anchor))
    assert upright.vector((1,0))==pytest.approx((scale,0),abs=1e-9)
    # A pre-rotated symbol retains its own reference orientation.
    assert upright.vector((2,-3))==pytest.approx((2*scale,-3*scale))
    directional=component_transform(m,angle,anchor,directional=True)
    assert directional.values==m.values


def test_symbol_pair_positions_follow_one_global_transform():
    m,scale,angle=fit(Rect(0,0,400,600),Rect(12,12,800,1100),(-1,0))
    a,b=(100,200),(250,360)
    ca=component_transform(m,angle,a,False).point(a)
    cb=component_transform(m,angle,b,False).point(b)
    assert (cb[0]-ca[0],cb[1]-ca[1])==pytest.approx(m.vector((b[0]-a[0],b[1]-a[1])))
