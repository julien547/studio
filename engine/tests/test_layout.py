import pytest

from doemo_pdf.layout import title_position,level_title


@pytest.mark.parametrize('name',['NIVEAU 0','NIVEAU 1','RDC','R+1','Sous-sol','Étage 2'])
def test_recognizes_titles(name):
    assert level_title(name)


def test_room_names_are_not_level_titles():
    assert not level_title('BUREAU')
    assert not level_title('SALLE DE REUNION')


def test_level_title_falls_back_to_the_side_when_below_is_occupied():
    region=(50,50,150,150)
    target,placement=title_position((0,0,40,12),region,(0,0,220,200),[region,(0,0,220,49)])
    assert placement=='side' and target[0]>region[2]


def test_title_never_silently_overlaps_when_no_space_exists():
    with pytest.raises(ValueError,match='Pas de place'):
        title_position((0,0,40,12),(0,0,100,100),(0,0,100,100),[(0,0,100,100)])
