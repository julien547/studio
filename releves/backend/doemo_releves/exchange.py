import hashlib
import json
from .models import ProjectState
from .registration import solve, project


def validate_state(state, documents):
    docs = {d["id"]: d for d in documents}
    targets = [d for d in documents if d["role"] == "target"]
    floors = {f.id: f for f in state.floors}
    if len(targets) > 1:
        raise ValueError("Un seul BAT par projet")
    target = targets[0] if targets else None
    for f in state.floors:
        if target is None or f.target_page > len(target["pages"]):
            raise ValueError("Page BAT du niveau introuvable")
    for a in state.annotations:
        doc = docs.get(a.source_document_id)
        if not doc or doc["role"] != "survey" or a.source_page > len(doc["pages"]):
            raise ValueError("Annotation sans page de relevé valide")
        if a.floor_id and a.floor_id not in floors:
            raise ValueError("Niveau introuvable")
    for legend in state.legends:
        doc = docs.get(legend.source_document_id)
        if not doc or doc["role"] != "survey" or legend.source_page > len(doc["pages"]):
            raise ValueError("Légende sans document")
    for r in state.registrations:
        source = docs.get(r.source_document_id)
        floor = floors.get(r.floor_id)
        if not source or source["role"] != "survey" or r.source_page > len(source["pages"]) or not floor or not target:
            raise ValueError("Références de recalage invalides")
        page = target["pages"][floor.target_page - 1]
        measured = solve([[p.x,p.y] for p in r.source_points], [[p.x,p.y] for p in r.target_points],
                         r.model, page["width"], page["height"],
                         [[p.x,p.y] for p in r.check_source_points], [[p.x,p.y] for p in r.check_target_points])
        # Never trust client-supplied matrices or residuals.
        r.matrix = measured["matrix"]
        r.fit_error_px = measured["fit_error_px"]
        r.check_error_px = measured["check_error_px"]
        if max(r.check_error_px, r.fit_error_px) > r.max_error_px:
            r.confirmed = False
    return state


def report(state):
    return {"detected": len(state.annotations), "mapped": sum(bool(a.asset_id) for a in state.annotations),
            "confirmed": sum(a.status == "confirmed" for a in state.annotations),
            "rejected": sum(a.status == "rejected" for a in state.annotations),
            "missing_assets": sum(not a.asset_id and a.status != "rejected" for a in state.annotations),
            "uncertain_positions": sum((not a.review.position or a.anchor is None) and a.status != "rejected" for a in state.annotations),
            "placed_in_illustrator": None, "native_ai_verified": False}


def export_placements(project_data, library):
    state = validate_state(ProjectState.model_validate(project_data["state"]), project_data["documents"])
    if not library or library["id"] != state.library_id or not library["archive_verified"]:
        raise ValueError("Bibliothèque vectorielle non vérifiée ; exporter le dossier de revue pour poursuivre")
    target = next((d for d in project_data["documents"] if d["role"] == "target"), None)
    if not target:
        raise ValueError("BAT AI manquant")
    if not state.annotations or all(a.status == "rejected" for a in state.annotations):
        raise ValueError("Aucun placement confirmé")
    assets = {a["id"]: a for a in library["assets"]}
    floors = {f.id: f for f in state.floors}
    mapping_hash = hashlib.sha256(json.dumps([m.model_dump() for m in state.mappings], sort_keys=True).encode()).hexdigest()
    placements, export_assets = [], {}
    for a in state.annotations:
        if a.status == "rejected":
            continue
        if a.status != "confirmed" or not all(a.review.model_dump().values()):
            raise ValueError(f"Annotation {a.id} : confirmer séparément les six critères ou rejeter la détection")
        asset, floor = assets.get(a.asset_id), floors.get(a.floor_id)
        if not asset or not asset["verified"] or not asset["approved"] or not asset["pictogram_candidate"]:
            raise ValueError(f"Annotation {a.id} : pictogramme SAI non approuvé ou manquant")
        if not floor or not floor.confirmed or not a.anchor:
            raise ValueError(f"Annotation {a.id} : niveau ou ancrage non confirmé")
        if not any(m.confirmed and m.asset_id == a.asset_id and m.equipment_type == a.equipment_type for m in state.mappings):
            raise ValueError(f"Annotation {a.id} : correspondance métier non confirmée")
        reg = next((r for r in state.registrations if (r.source_document_id, r.source_page, r.floor_id) ==
                    (a.source_document_id, a.source_page, a.floor_id)), None)
        if not reg or not reg.confirmed or not reg.architecture_confirmed:
            raise ValueError(f"Annotation {a.id} : recalage et état architectural à confirmer")
        if max(reg.fit_error_px, reg.check_error_px) > reg.max_error_px:
            raise ValueError("Erreur de recalage excessive")
        mapped = project(reg.matrix, [[a.anchor.x, a.anchor.y]])[0]
        point = [a.target.x, a.target.y] if a.target else mapped.tolist()
        if not all(0 <= v <= 1 for v in point):
            raise ValueError("Placement hors page BAT")
        dimensions = target["pages"][floor.target_page-1]["pdf_size_pt"]
        if not dimensions:
            raise ValueError("Dimensions BAT en points introuvables")
        component = next((c for c in asset["components"] if c.get("role") == "primary"), asset["components"][0])
        export_assets[asset["id"]] = {"asset_id": asset["id"], "name": asset["name"],
            "relative_path": component["archive_path"], "sha256": component["sha256"]}
        placements.append({"placement_id": a.id, "source_document_id": a.source_document_id,
            "source_page": a.source_page, "floor_id": a.floor_id, "annotation_source": a.text,
            "equipment_type": a.equipment_type, "asset_id": a.asset_id,
            "x": point[0]*dimensions[0], "y": point[1]*dimensions[1],
            "rotation_deg": a.rotation_deg, "size_mm": a.size_mm, "confidence": a.confidence,
            "validated": True, "review": a.review.model_dump(), "mapping_version": state.mapping_version,
            "source_anchor": a.anchor.model_dump(), "registration_matrix": reg.matrix,
            "manual_target_override": a.target.model_dump() if a.target else None})
    return {"schema_version": "doemo.placements/1", "project_id": project_data["id"],
            "revision": state.revision, "mapping_version": state.mapping_version, "mapping_sha256": mapping_hash,
            "coordinate_system": {"unit": "pt", "origin": "artboard_top_left", "x_axis": "right", "y_axis": "down",
                "size_rule": "longest_visible_edge_mm_before_rotation", "rotation_rule": "clockwise_degrees",
                "illustrator_conversion": "[artboardRect[0]+x, artboardRect[1]-y]"},
            "target": {"sha256": target["sha256"], "name": target["name"],
                "pages": target["pages"], "floors": [f.model_dump() for f in state.floors]},
            "library_id": library["id"], "assets": list(export_assets.values()), "placements": placements,
            "report": report(state)}
