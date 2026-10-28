from pathlib import Path

import pikepdf
import pytest

from doemo_pdf.generate import template_scene, inspect_template, generate_batch
from test_generation import project


def trame(path,commands,layer=None,size=(1200,840)):
    with pikepdf.Pdf.new() as pdf:
        page=pdf.add_blank_page(page_size=size)
        page.Resources=pikepdf.Dictionary()
        if layer:
            oc=pdf.make_indirect(pikepdf.Dictionary(Type=pikepdf.Name.OCG,Name=layer))
            page.Resources.Properties=pikepdf.Dictionary(L=oc)
            commands='/OC /L BDC '+commands+' EMC'
        page.Contents=pdf.make_stream(commands.encode());pdf.save(path)
    return path


@pytest.mark.parametrize('colour',['1 G','1 1 1 RG','0 0 0 0 K'])
def test_white_guide_does_not_require_date_layer_or_cmyk(tmp_path,colour):
    path=trame(tmp_path/'PI-A3-H.pdf',f'{colour} 1 w 30 100 1140 550 re S','ZONE DE DESSIN')
    # Named layer takes precedence, regardless of colour.
    info=inspect_template(path)
    assert info['zone_detection']['method']=='named-layer'
    assert info['zone']==pytest.approx([30,100,1170,650])
    path=trame(tmp_path/'ordinary.pdf',f'{colour} 1 w 30 100 1140 550 re S','Repères')
    info=inspect_template(path)
    assert info['zone_detection']['method']=='white-rectangle'
    assert info['zone']==pytest.approx([30,100,1170,650])


def test_duplicate_and_explicitly_closed_white_rectangles_are_one_zone(tmp_path):
    path=trame(tmp_path/'PI-A3-H.pdf','1 G 30 100 1140 550 re S 30 100 m 1170 100 l 1170 650 l 30 650 l 30 100 l h S')
    assert inspect_template(path)['zone']==[30,100,1170,650]


def test_named_unpainted_guide_is_detected_without_painting_it(tmp_path):
    path=trame(tmp_path/'PI-A3-H.pdf','30 100 1140 550 re n','DOEMO_ZONE_PLAN')
    with pikepdf.open(path) as pdf:
        scene,_,zone,selected=template_scene(pdf)
        assert zone==(30,100,1170,650) and not selected and not scene.items


def test_no_white_rectangle_uses_free_space_between_banner_and_instructions(tmp_path):
    path=trame(tmp_path/'PE-A3-H.pdf','0 1 1 0 k 0 760 1200 80 re f 0 0 0 1 k 0 0 1200 160 re f')
    info=inspect_template(path)
    assert info['zone_detection']['method']=='free-space'
    assert info['zone']==[0,160,1200,760]


def test_border_leaves_its_inside_available(tmp_path):
    path=trame(tmp_path/'PI-A3-H.pdf','0 G 2 w 10 10 1180 820 re S 0 g 10 750 1180 80 re f 10 10 1180 90 re f')
    info=inspect_template(path)
    assert info['zone']==pytest.approx([11,100,1189,750])


def test_two_equal_empty_spaces_are_not_arbitrarily_selected(tmp_path):
    path=trame(tmp_path/'PE-A3-H.pdf','0 g 590 0 20 840 re f')
    with pytest.raises(ValueError,match='Trame PE-A3-H.pdf.*zones libres équivalentes'):inspect_template(path)


def test_no_free_region_never_falls_back_to_entire_page(tmp_path):
    path=trame(tmp_path/'filled.pdf','0 g 0 0 1200 840 re f')
    with pytest.raises(ValueError,match='Aucune zone libre'):inspect_template(path)


def test_white_background_does_not_authorize_overlap_with_printed_instructions(tmp_path):
    path=trame(tmp_path/'PE-A3-H.pdf','1 g 30 30 1140 700 re f 0 g 0 0 1200 200 re f 0 760 1200 80 re f')
    info=inspect_template(path)
    assert info['zone_detection']['method']=='free-space'
    assert info['zone'][1]>=200


def test_known_vertical_templates_keep_their_original_zone():
    root=Path(__file__).resolve().parents[2]/'resources/templates/doemo'
    assert inspect_template(root/'PE-A3-V.pdf')['zone']==pytest.approx([28.346,194.299,813.543,979.496],abs=.002)
    assert inspect_template(root/'PI-A3-V.pdf')['zone']==pytest.approx([28.578,126.004,813.775,974.702],abs=.002)


def test_generation_works_with_templates_without_zone_guides(project,tmp_path):
    source,directory=project
    for name in ['PE-A3-V.pdf','PI-A3-V.pdf']:
        trame(directory/name,'0 1 1 0 k 0 1100 841.89 90.55 re f 0 g 0 0 841.89 150 re f',size=(841.89,1190.55))
    report=generate_batch(source,tmp_path/'generated')
    assert report['count']==3
    for row in report['results']:
        assert row['layout']['zone_detection']['method']=='free-space'
        assert row['layout']['plan_bounds'][1]>150
        assert row['layout']['plan_bounds'][3]<1100
