import json

import httpx
import pytest
from PIL import Image

from doemo_releves.recognition import multimodal_proposals, vision_response_format


def vision_call(monkeypatch, tmp_path, marks, region=None):
    monkeypatch.setenv("DOEMO_VISION_ENDPOINT", "https://vision.example/v1/chat/completions")
    monkeypatch.setenv("DOEMO_VISION_MODEL", "test-vision")
    monkeypatch.delenv("DOEMO_VISION_API_KEY", raising=False)
    picture = tmp_path / "survey.png"
    Image.new("RGB", (32, 32), "white").save(picture)

    def respond(self, url, **kwargs):
        return httpx.Response(200, request=httpx.Request("POST", url), json={
            "choices": [{"message": {"content": json.dumps({"annotations": marks})}}]
        })

    monkeypatch.setattr(httpx.Client, "post", respond)
    return multimodal_proposals(picture, "survey", 1, region)[0]


def mark(text="PE", kind="arrow_tip"):
    return {"bbox": {"x": .1, "y": .2, "w": .1, "h": .1},
            "anchor": {"x": .3, "y": .4}, "anchor_kind": kind,
            "text": text, "equipment_type": "Plan d'évacuation" if text == "PE" else "Extincteur portatif",
            "confidence": .99, "evidence": "Observation à contrôler"}


def test_plans_and_equipment_stay_unapproved(monkeypatch, tmp_path):
    annotations = vision_call(monkeypatch, tmp_path, [mark(), mark("EXT", "direct")])
    assert [a.equipment_type for a in annotations] == ["Plan d'évacuation", "Extincteur portatif"]
    for a in annotations:
        assert a.status == "review"
        assert a.asset_id is None and a.target is None
        assert not any(a.review.model_dump().values())


@pytest.mark.parametrize("kind", ["unknown", "centre_du_texte"])
def test_unknown_anchor_coordinates_are_not_placements(monkeypatch, tmp_path, kind):
    a = vision_call(monkeypatch, tmp_path, [mark(kind=kind)])[0]
    assert a.anchor is None
    assert a.anchor_kind == "unknown"
    assert a.status == "uncertain_position"


def test_invalid_geometry_rejects_entire_response(monkeypatch, tmp_path):
    invalid = mark()
    invalid["bbox"]["x"] = .95
    with pytest.raises(ValueError, match="Boîte hors page"):
        vision_call(monkeypatch, tmp_path, [mark(), invalid])


def test_openai_schema_requires_nested_fields_without_changing_other_providers():
    schema = vision_response_format("https://api.openai.com/v1/chat/completions")["json_schema"]
    assert schema["strict"] is True
    for obj in [schema["schema"], *schema["schema"]["$defs"].values()]:
        if obj.get("type") == "object":
            assert set(obj["required"]) == set(obj["properties"])
            assert obj["additionalProperties"] is False
    assert "default" not in json.dumps(schema)
    assert vision_response_format("https://vision.example/chat") == {"type": "json_object"}


def test_crop_positions_return_to_original_page_frame(monkeypatch, tmp_path):
    a = vision_call(monkeypatch, tmp_path, [mark()], {"x": .25, "y": .5, "w": .5, "h": .5})[0]
    assert a.anchor.x == pytest.approx(.4)
    assert a.anchor.y == pytest.approx(.7)
    assert a.bbox.x == pytest.approx(.3)
    assert a.bbox.y == pytest.approx(.6)
    assert a.bbox.w == pytest.approx(.05)
    assert a.bbox.h == pytest.approx(.05)
    assert not a.review.position
