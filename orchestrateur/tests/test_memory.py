import pytest
from doemo_orchestrator.db import Database
from doemo_orchestrator import memory, service as svc
from doemo_orchestrator.service import Orchestrator


@pytest.fixture
def o():
    orch = Orchestrator(Database(":memory:"))
    for a in ("releves", "redessin"):
        orch.create_app(a, a)
    return orch


def test_global_memory_needs_admin_validation(o):
    d = memory.propose_global(o, "releves", "abbreviation", "RIA", {"sens": "robinet d'incendie armé"}, "alice")
    assert d["status"] == "draft"
    assert memory.read_for_app(o, "redessin")["validated"] == []          # pas encore visible des autres
    memory.validate_global(o, d["id"], "julien")
    assert [e["key"] for e in memory.read_for_app(o, "redessin")["validated"]] == ["RIA"]


def test_app_memory_is_private(o):
    memory.put_app(o, "releves", "instruction", "ton", {"v": "précis"}, "alice")
    assert len(memory.read_for_app(o, "releves")["validated"]) == 1
    assert memory.read_for_app(o, "redessin")["validated"] == []


def test_app_memory_update_replaces_previous(o):
    memory.put_app(o, "releves", "parameter", "seuil", {"v": 1}, "a")
    memory.put_app(o, "releves", "parameter", "seuil", {"v": 2}, "a")
    entries = memory.read_for_app(o, "releves")["validated"]
    assert len(entries) == 1 and entries[0]["value"] == {"v": 2}


def test_cannot_overwrite_global_key_by_proposal(o):
    memory.set_global(o, "reading_rule", "RIA", {"v": 1}, "julien")
    with pytest.raises(svc.Conflict):
        memory.propose_global(o, "releves", "reading_rule", "RIA", {"v": 2}, "alice")


def test_correction_is_persisted_with_traceability(o):
    cid = memory.submit_correction(o, "releves", "paddleocr", "texte", "alice",
                                   {"format": "ocr_lines", "lines": ["EXT 6kg"]}, project_id="p1", model_version="v3")
    row = memory.list_corrections(o, "releves")[0]
    assert row["id"] == cid and row["status"] == "pending" and row["project_id"] == "p1" and row["author"] == "alice"
    assert memory.list_corrections(o, "redessin") == []                  # isolement entre applications


def test_dataset_only_validated_and_reusable(o):
    ok = memory.submit_correction(o, "releves", "rtmdet", "boite", "a", {"format": "coco_boxes", "bbox": [1, 2, 3, 4]})
    private = memory.submit_correction(o, "releves", "rtmdet", "boite", "a", {"format": "coco_boxes", "bbox": [5, 6, 7, 8]})
    pending = memory.submit_correction(o, "releves", "rtmdet", "boite", "a", {"format": "coco_boxes", "bbox": [9, 9, 9, 9]})
    memory.validate_correction(o, ok, "julien", reuse_allowed=True)
    memory.validate_correction(o, private, "julien", reuse_allowed=False)  # validée pour l'application, pas partagée
    data = memory.export_dataset(o, "rtmdet")
    assert data["count"] == 1 and data["records"][0]["id"] == ok and data["records"][0]["validated_by"] == "julien"
    assert memory.export_dataset(o, "qwen")["count"] == 0                   # jeux distincts par moteur
    with pytest.raises(svc.Conflict):
        memory.validate_correction(o, ok, "julien", True)


def test_formats_are_not_mixed(o):
    with pytest.raises(svc.OrchestratorError):
        memory.submit_correction(o, "releves", "qwen", "x", "a", {"format": "coco_boxes"})
    with pytest.raises(svc.OrchestratorError):
        memory.submit_correction(o, "releves", "inconnu", "x", "a", {"format": "qa_json"})


def test_rejected_never_in_dataset(o):
    cid = memory.submit_correction(o, "releves", "murs", "mur", "a", {"format": "wall_segments", "s": []})
    memory.reject_correction(o, cid, "julien")
    assert memory.export_dataset(o, "murs")["count"] == 0
