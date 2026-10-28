"""Internal API: expose ONLY on a private Unix socket behind the PHP session gate."""
from pathlib import Path
import json
import os
import shutil
import uuid
import io
import zipfile
import math
import re
from typing import Literal

from fastapi import FastAPI, Depends, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.exceptions import RequestValidationError
from pydantic import Field

from .documents import rgb
from .exchange import validate_state, export_placements, report
from .models import Model, ProjectState, Registration, Box
from .registration import solve
from .store import Store, Conflict
from .worker import run_job


class Actor(Model):
    login: str
    admin: bool


def actor(x_doemo_user: str = Header(min_length=1, max_length=100), x_doemo_role: str = Header()):
    if x_doemo_role not in ("admin", "administration", "dessinateur"):
        raise HTTPException(403, "Rôle non autorisé")
    return Actor(login=x_doemo_user, admin=x_doemo_role in ("admin", "administration"))


def admin(a=Depends(actor)):
    if not a.admin:
        raise HTTPException(403, "Administration requise")
    return a


def upload(file, path, limit):
    count = 0
    with open(path, "xb") as f:
        for chunk in iter(lambda: file.file.read(1024**2), b""):
            count += len(chunk)
            if count > limit:
                raise ValueError("Fichier trop volumineux")
            f.write(chunk)
    if not count:
        raise ValueError("Fichier vide")


class NewProject(Model):
    name: str = Field(min_length=1, max_length=200)
    reference: str = Field(default="", max_length=100)
    client: str = Field(default="", max_length=200)
    address: str = Field(default="", max_length=500)
    building_type: str = Field(default="", max_length=100)
    responsible: str = Field(default="", max_length=100)


class Analysis(Model):
    document_id: str
    page: int = Field(ge=1)
    revision: int = Field(ge=0)
    mode: Literal["local", "multimodal"] = "local"


class Approval(Model):
    approved: bool
    pictogram_candidate: bool


class LegendRead(Model):
    document_id: str
    page: int = Field(ge=1)
    bbox: Box


def create_app(root=None):
    store = Store(root or os.environ.get("DOEMO_RELEVES_DATA", "/var/lib/doemo-studio/releves"))
    app = FastAPI(title="DOEMO Relevés — API privée", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.store = store

    @app.exception_handler(ValueError)
    async def invalid(_, error):
        return JSONResponse(status_code=409 if isinstance(error, Conflict) else 422, content={"detail": str(error)})

    @app.exception_handler(LookupError)
    async def missing(_, error):
        return JSONResponse(status_code=404, content={"detail": "Ressource inaccessible"})

    @app.exception_handler(RequestValidationError)
    async def bad_request(_, error):
        # Never echo uploaded contents, credential-like strings or full request bodies.
        return JSONResponse(status_code=422, content={"detail": "Données invalides : vérifier les champs et leurs limites"})

    def get(ident, who):
        return store.get(ident, who.login, who.admin)

    def doc(ident, document_id, who, page=None):
        project_data = get(ident, who)
        found = next((d for d in project_data["documents"] if d["id"] == document_id), None)
        if not found or (page is not None and not 1 <= page <= len(found["pages"])):
            raise LookupError("Document inaccessible")
        directory = store.root / "documents" / found["id"]
        return found, directory

    from .studio_api import attach
    attach(app, store, actor, admin, get, doc)
    from .queue import attach_queue
    attach_queue(app, store, actor, get, doc)
    from .gpu import attach_gpu
    attach_gpu(app, store, actor, admin)
    from .training import attach_training
    attach_training(app, store, admin, get, doc)

    @app.get("/health")
    def health():
        return {"ok": True, "scope": "private-unix-socket", "multimodal_configured": bool(os.environ.get("DOEMO_VISION_ENDPOINT"))}

    @app.get("/projects")
    def projects(who=Depends(actor)):
        return store.listing(who.login, who.admin)

    @app.post("/projects")
    def new_project(data: NewProject, who=Depends(actor)):
        return get(store.create(who.login, data.name, data.model_dump(exclude={"name"})), who)

    @app.get("/projects/{ident}")
    def project_get(ident, who=Depends(actor)):
        return get(ident, who)

    @app.put("/projects/{ident}/state")
    def project_save(ident, state: ProjectState, who=Depends(actor)):
        p = get(ident, who)
        if state.library_id:
            library = store.library(state.library_id)
            ids = {a["id"] for a in library["assets"]}
            if any(m.asset_id not in ids for m in state.mappings) or any(a.asset_id and a.asset_id not in ids for a in state.annotations):
                raise ValueError("Ressource de correspondance absente de la bibliothèque")
        elif any(a.asset_id for a in state.annotations) or state.mappings:
            raise ValueError("Sélectionner une bibliothèque")
        old = ProjectState.model_validate(p["state"])
        # Client-side review controls are not an authorization boundary.
        previous = {a.id: a for a in old.annotations}
        fields = {"equipment": ("text", "equipment_type"), "asset": ("asset_id",),
                  "floor": ("floor_id",), "position": ("anchor", "target", "source_document_id", "source_page"),
                  "orientation": ("rotation_deg",), "size": ("size_mm",)}
        for annotation in state.annotations:
            prior = previous.get(annotation.id)
            if prior:
                changed = False
                for criterion, keys in fields.items():
                    if any(getattr(prior, key) != getattr(annotation, key) for key in keys):
                        setattr(annotation.review, criterion, False)
                        changed = True
                if changed:
                    annotation.training_accepted = False
                    if annotation.status == "confirmed": annotation.status = "review"
                if prior.bbox != annotation.bbox:
                    annotation.training_accepted = False
            if annotation.status == "confirmed" and (not all(annotation.review.model_dump().values()) or not annotation.anchor or not annotation.asset_id or not annotation.floor_id or not annotation.equipment_type):
                raise ValueError("Confirmer les six critères et renseigner le placement avant validation")
            if annotation.status == "confirmed":
                approved = next((a for a in library["assets"] if a["id"] == annotation.asset_id), None)
                if not approved or not approved["approved"] or not approved["verified"] or not approved["pictogram_candidate"]:
                    raise ValueError("Approuver le pictogramme SAI avant validation du placement")
        if state.workflow == "validated":
            if not who.admin:
                raise HTTPException(403, "Validation finale réservée au responsable ou administrateur")
            if not state.annotations or any(a.status not in ("confirmed", "rejected") for a in state.annotations):
                raise ValueError("Vérifier ou rejeter chaque annotation avant validation finale")
        if [m.model_dump() for m in old.mappings] != [m.model_dump() for m in state.mappings]:
            state.mapping_version = old.mapping_version + 1
        else:
            state.mapping_version = old.mapping_version
        store.save(ident, who.login, validate_state(state, p["documents"]))
        return get(ident, who)

    @app.post("/projects/{ident}/documents")
    def document_add(ident, file: UploadFile = File(), role: Literal["survey", "target"] = Form(), who=Depends(actor)):
        p = get(ident, who)
        if role == "target" and any(d["role"] == "target" for d in p["documents"]):
            raise ValueError("Créer un autre projet pour changer le BAT")
        if role == "survey" and Path(file.filename or "").suffix.lower() not in (".pdf", ".png", ".jpg", ".jpeg"):
            raise ValueError("Formats de relevé : PDF, PNG ou JPEG")
        did = uuid.uuid4().hex
        directory = store.root / "documents" / did
        directory.mkdir(parents=True, mode=0o700)
        try:
            upload(file, directory / "original", 64*1024**2)
            metadata = run_job("document", {"path": str(directory/"original"), "directory": str(directory),
                "original_name": file.filename or "document", "role": role})
            with store.connect() as c:
                c.execute("BEGIN IMMEDIATE")
                # Concurrent BAT imports must not create two targets.
                if role == "target" and c.execute("SELECT 1 FROM documents WHERE project_id=? AND json_extract(metadata,'$.role')='target'", (ident,)).fetchone():
                    raise ValueError("Un BAT est déjà présent")
                c.execute("INSERT INTO documents VALUES(?,?,?)", (did, ident, json.dumps(metadata)))
        except Exception:
            shutil.rmtree(directory)
            raise
        return get(ident, who)

    @app.get("/projects/{ident}/documents/{document_id}/pages/{page}")
    def page_image(ident, document_id, page: int, who=Depends(actor)):
        _, directory = doc(ident, document_id, who, page)
        return FileResponse(directory/f"page-{page}.png", media_type="image/png", headers={"Cache-Control": "private, no-store"})

    @app.get("/projects/{ident}/annotations/{annotation_id}/crop")
    def annotation_crop(ident, annotation_id, who=Depends(actor)):
        p = get(ident, who)
        annotation = next((a for a in p["state"]["annotations"] if a["id"] == annotation_id), None)
        if not annotation:
            raise LookupError("Annotation inaccessible")
        _, directory = doc(ident, annotation["source_document_id"], who, annotation["source_page"])
        from PIL import Image
        with Image.open(directory/f"page-{annotation['source_page']}.png") as im:
            b=annotation["bbox"];w,h=im.size
            crop=im.crop((max(0,int(b["x"]*w)-30),max(0,int(b["y"]*h)-30),min(w,int((b["x"]+b["w"])*w)+30),min(h,int((b["y"]+b["h"])*h)+30)))
            buffer=io.BytesIO();crop.save(buffer,"PNG")
        return Response(buffer.getvalue(),media_type="image/png",headers={"Cache-Control":"private, no-store"})

    @app.post("/projects/{ident}/analyze")
    def analyze(ident, data: Analysis, who=Depends(actor)):
        p = get(ident, who)
        source, directory = doc(ident, data.document_id, who, data.page)
        if source["role"] != "survey":
            raise ValueError("Choisir un relevé")
        state = ProjectState.model_validate(p["state"])
        if data.revision != state.revision:
            raise Conflict("Projet modifié : recharger")
        if any(a.source_document_id == data.document_id and a.source_page == data.page for a in state.annotations):
            raise ValueError("Cette page a déjà des propositions ; conserver les corrections et créer une autre analyse dans un nouveau projet")
        legend = next((l for l in state.legends if (l.source_document_id, l.source_page) == (data.document_id, data.page)), None)
        result = run_job("recognition", {"image_path": str(directory/f"page-{data.page}.png"),
            "document_id": data.document_id, "page": data.page, "mode": data.mode,
            "legend_box": legend.bbox.model_dump() if legend and legend.bbox else None})
        from .models import Annotation
        state.annotations.extend(Annotation.model_validate(a) for a in result["annotations"])
        store.save(ident, who.login, state, "analysis:"+data.mode)
        return {"project": get(ident, who), "analysis": result["report"]}

    @app.post("/projects/{ident}/registration")
    def registration(ident, data: Registration, who=Depends(actor)):
        p = get(ident, who)
        state = ProjectState.model_validate(p["state"])
        state.registrations = [r for r in state.registrations if (r.source_document_id,r.source_page,r.floor_id) !=
                               (data.source_document_id,data.source_page,data.floor_id)] + [data]
        validate_state(state, p["documents"])
        return state.registrations[-1]

    @app.post("/projects/{ident}/automatic-registration")
    def automatic_registration(ident, data: Analysis, floor_id: str, who=Depends(actor)):
        p = get(ident, who)
        state = ProjectState.model_validate(p["state"])
        floor = next((f for f in state.floors if f.id == floor_id), None)
        target = next((d for d in p["documents"] if d["role"] == "target"), None)
        source, directory = doc(ident, data.document_id, who, data.page)
        if not floor or not target or source["role"] != "survey":
            raise ValueError("Choisir un niveau et un BAT")
        return run_job("automatic", {"source": str(directory/f"page-{data.page}.png"),
            "target": str(store.root/"documents"/target["id"]/f"page-{floor.target_page}.png")})

    @app.get("/projects/{ident}/review-export")
    def review_export(ident, who=Depends(actor)):
        p = get(ident, who)
        p["report"] = report(ProjectState.model_validate(p["state"]))
        return p

    @app.post("/projects/{ident}/illustrator-reports")
    def illustrator_report(ident, file: UploadFile = File(), who=Depends(actor)):
        p = get(ident, who)
        raw = file.file.read(4*1024**2+1)
        if len(raw) > 4*1024**2:
            raise ValueError("Rapport trop volumineux")
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, UnicodeError) as e:
            raise ValueError("Rapport JSON invalide") from e
        target = next((d for d in p["documents"] if d["role"] == "target"), None)
        if not isinstance(data, dict) or not target or data.get("schema_version") != "doemo.placement-report/1" or data.get("project_id") != ident or data.get("revision") != p["state"]["revision"] or data.get("original_sha256") != target["sha256"]:
            raise ValueError("Rapport d'un autre projet, BAT ou révision")
        if not isinstance(data.get("items"), list) or len(data["items"]) > 20000 or not isinstance(data.get("measurements"), list) or len(data["measurements"]) > 10000:
            raise ValueError("Contrôles du rapport absents ou excessifs")
        expected = {a["id"] for a in p["state"]["annotations"] if a["status"] == "confirmed"}
        measured = [m.get("placement_id") for m in data["measurements"] if isinstance(m, dict)]
        if not expected or set(measured) != expected or len(measured) != len(expected):
            raise ValueError("Les identifiants mesurés ne correspondent pas aux placements confirmés")
        if any(type(data.get(key)) is not bool for key in ("native_ai_verified", "conformity_passed", "architecture_unchanged")) or type(data.get("placed_total")) is not int or not 0 <= data["placed_total"] <= 20000 or not re.fullmatch(r"[a-f0-9]{64}", str(data.get("output_sha256", ""))):
            raise ValueError("Contrôles natifs du rapport invalides")
        for measurement in data["measurements"]:
            distance = measurement.get("position_error_pt")
            if type(distance) not in (int, float) or not math.isfinite(distance) or distance < 0 or type(measurement.get("validated_placement_matches")) is not bool:
                raise ValueError("Mesure de placement invalide")
        result = {"source": "rapport fourni par le poste Illustrator", "received_by": who.login, "report": data}
        with store.connect() as c:
            c.execute("INSERT INTO events(project_id,actor,action,data) VALUES(?,?,?,?)",
                      (ident, who.login, "illustrator-report", json.dumps(result)))
        return result

    @app.get("/projects/{ident}/illustrator-reports")
    def illustrator_reports(ident, who=Depends(actor)):
        get(ident, who)
        with store.connect() as c:
            rows = c.execute("SELECT data,created FROM events WHERE project_id=? AND action='illustrator-report' ORDER BY id DESC LIMIT 20", (ident,)).fetchall()
        return [dict(json.loads(r["data"]), received_at=r["created"]) for r in rows]

    @app.get("/projects/{ident}/placements")
    def placements(ident, who=Depends(actor)):
        p = get(ident, who)
        return export_placements(p, store.library(p["state"]["library_id"]) if p["state"]["library_id"] else None)

    @app.get("/projects/{ident}/bundle")
    def bundle(ident, who=Depends(actor)):
        p = get(ident, who)
        library = store.library(p["state"]["library_id"]) if p["state"]["library_id"] else None
        exchange = export_placements(p, library)
        target = store.root/"exports"/(uuid.uuid4().hex+".zip")
        target.parent.mkdir(exist_ok=True, mode=0o700)
        from .library import safe_path, digest
        with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as z:
            z.writestr("placements.json", json.dumps(exchange, ensure_ascii=False, indent=2))
            for a in exchange["assets"]:
                path = store.root/"libraries"/library["id"]/str(safe_path(a["relative_path"]))
                if digest(path) != a["sha256"]:
                    target.unlink(missing_ok=True)
                    raise ValueError("Ressource SAI modifiée depuis la vérification")
                z.write(path, "library/"+a["relative_path"])
            scripts = Path(__file__).resolve().parents[2]/"illustrator"
            for name in ("DOEMO-Pose-Pictogrammes.jsx", "doemo-core.js"):
                z.write(scripts/name, name)
        return FileResponse(target, filename="DOEMO-placements.zip", media_type="application/zip",
                            headers={"Cache-Control": "private, no-store"})

    @app.post("/projects/{ident}/legend-read")
    def legend_read(ident, data: LegendRead, who=Depends(actor)):
        _, directory = doc(ident, data.document_id, who, data.page)
        from .recognition import legend_proposals
        return legend_proposals(rgb(directory/f"page-{data.page}.png"), data.bbox)

    @app.get("/projects/{ident}/overlay")
    def overlay(ident, document_id: str, page: int, floor_id: str, who=Depends(actor)):
        p = get(ident, who)
        state = validate_state(ProjectState.model_validate(p["state"]), p["documents"])
        reg = next((r for r in state.registrations if (r.source_document_id,r.source_page,r.floor_id) == (document_id,page,floor_id)), None)
        floor = next((f for f in state.floors if f.id == floor_id), None)
        target = next((d for d in p["documents"] if d["role"] == "target"), None)
        if not reg or not floor or not target:
            raise ValueError("Calculer et sauvegarder le recalage d'abord")
        _, directory = doc(ident, document_id, who, page)
        import cv2
        import numpy as np
        image = rgb(directory/f"page-{page}.png")
        target_page = target["pages"][floor.target_page-1]
        tw, th = target_page["width"], target_page["height"]
        matrix = np.diag([tw,th,1]) @ np.array(reg.matrix) @ np.diag([1/image.shape[1],1/image.shape[0],1])
        rgba = cv2.cvtColor(image, cv2.COLOR_RGB2RGBA)
        warped = cv2.warpPerspective(rgba, matrix, (tw,th), borderValue=(0,0,0,0))
        from PIL import Image
        buffer = io.BytesIO(); Image.fromarray(warped).save(buffer, "PNG")
        return Response(buffer.getvalue(), media_type="image/png", headers={"Cache-Control": "private, no-store"})

    @app.get("/libraries")
    def libraries(who=Depends(actor)):
        return store.libraries()

    @app.post("/libraries")
    def library_add(inventory: UploadFile = File(), archive: UploadFile | None = File(default=None), who=Depends(admin)):
        library_root = store.root/"libraries"
        library_root.mkdir(exist_ok=True, mode=0o700)
        lid = uuid.uuid4().hex
        stage = library_root/(".upload-"+lid)
        stage.mkdir(mode=0o700)
        try:
            upload(inventory, stage/"inventory.json", 8*1024**2)
            if archive:
                upload(archive, stage/"library.cclibs", 512*1024**2)
            result = run_job("library", {"inventory_file": str(stage/"inventory.json"), "output": str(library_root/lid),
                "archive": str(stage/"library.cclibs") if archive else None})
            result["id"] = lid
            store.put_library(result)
        finally:
            shutil.rmtree(stage)
        return result

    @app.put("/libraries/{library_id}/assets/{asset_id}")
    def approve(library_id, asset_id, data: Approval, who=Depends(admin)):
        library = store.library(library_id)
        asset = next((a for a in library["assets"] if a["id"] == asset_id), None)
        if not asset:
            raise LookupError("Ressource introuvable")
        if data.approved and (not library["archive_verified"] or not asset["verified"] or not data.pictogram_candidate):
            raise ValueError("Seul un pictogramme vectoriel vérifié peut être approuvé")
        asset.update(data.model_dump())
        store.put_library(library)
        return asset

    @app.get("/libraries/{library_id}/assets/{asset_id}/preview")
    def preview(library_id, asset_id, who=Depends(actor)):
        library = store.library(library_id)
        asset = next((a for a in library["assets"] if a["id"] == asset_id and a["preview"]), None)
        if not asset:
            raise LookupError("Aperçu indisponible")
        return FileResponse(store.root/"libraries"/library["id"]/(asset["id"]+".png"), media_type="image/png",
                            headers={"Cache-Control": "private, no-store"})

    return app


def app_factory():
    return create_app()
