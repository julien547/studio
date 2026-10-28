"""Private SAI catalog. An inventory is provisional until its archive is verified."""
from collections import Counter
from pathlib import Path, PurePosixPath
import hashlib
import json
import re
import shutil
import stat
import tempfile
import zipfile

from .documents import render_page

MAX_ARCHIVE = 512 * 1024**2
MAX_EXPANDED = 1024**3
MAX_MEMBER = 64 * 1024**2


def safe_path(name):
    path = PurePosixPath(name)
    if (not name or "\\" in name or "\x00" in name or path.is_absolute()
            or any(p in ("", ".", "..") or ":" in p for p in name.split("/"))):
        raise ValueError("Chemin d'archive invalide")
    return path


def digest(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1024**2), b""):
            h.update(block)
    return h.hexdigest()


def inventory(path):
    if Path(path).stat().st_size > 8 * 1024**2:
        raise ValueError("Inventaire trop volumineux")
    data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    assets = data.get("assets", [])
    if not assets or len(assets) > 5000 or len({a["id"] for a in assets}) != len(assets):
        raise ValueError("Inventaire absent ou identifiants dupliqués")
    for a in assets:
        if not re.fullmatch(r"[a-zA-Z0-9_-]{1,100}", a["id"]):
            raise ValueError("Identifiant de ressource invalide")
        if not isinstance(a.get("name"), str) or not isinstance(a.get("groups", []), list):
            raise ValueError("Métadonnées invalides")
        for c in a.get("components", []):
            safe_path(c["archive_path"])
    counts = Counter(a["type"].split(".element.")[-1].split("+")[0] for a in assets)
    if data.get("total_items") != len(assets) or dict(counts) != data.get("counts_by_type"):
        raise ValueError("Comptages de l'inventaire incohérents")
    return data


def catalog(data, library_id):
    assets = []
    for a in data["assets"]:
        ai = [c for c in a.get("components", []) if c.get("type") == "application/illustrator"]
        # Groups are suggestions, never an approval of a pictogram or equipment mapping.
        excluded = bool(set(a.get("groups", [])) & {"Logo Agences", "Couleurs", "Polices d'écritures", "Consignes"})
        assets.append({"id": a["id"], "name": a["name"], "type": a["type"],
                       "groups": a.get("groups", []), "components": ai,
                       "pictogram_candidate": bool(ai) and not excluded,
                       "verified": False, "approved": False, "preview": False})
    return {"id": library_id, "name": data.get("source_library_name", "SAI"),
            "source_library_id": data.get("source_library_id"),
            "archive_verified": False, "counts": data["counts_by_type"], "assets": assets,
            "warnings": ["Inventaire seul : manifeste et ressources vectorielles non vérifiés."]}


def _manifest_items(value):
    found = {}
    if isinstance(value, dict):
        ident = value.get("id", value.get("identifier"))
        kind = value.get("type", "")
        if isinstance(ident, str) and isinstance(kind, str) and ".element." in kind:
            if ident in found:
                raise ValueError("Identifiant dupliqué dans le manifeste")
            found[ident] = value
        for child in value.values():
            for key, item in _manifest_items(child).items():
                if key in found:
                    raise ValueError("Identifiant dupliqué dans le manifeste")
                found[key] = item
    elif isinstance(value, list):
        for child in value:
            for key, item in _manifest_items(child).items():
                if key in found:
                    raise ValueError("Identifiant dupliqué dans le manifeste")
                found[key] = item
    return found


def import_library(inventory_file, output, archive=None):
    data = inventory(inventory_file)
    library_id = digest(inventory_file)[:32] if archive is None else digest(archive)[:32]
    result = catalog(data, library_id)
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise ValueError("La destination existe déjà")
    stage = Path(tempfile.mkdtemp(prefix=".sai-", dir=output.parent))
    try:
        if archive is not None:
            if Path(archive).stat().st_size > MAX_ARCHIVE:
                raise ValueError("Archive limitée à 512 Mio")
            with zipfile.ZipFile(archive) as z:
                infos = z.infolist()
                if len(infos) > 5000 or sum(x.file_size for x in infos) > MAX_EXPANDED:
                    raise ValueError("Archive décompressée trop volumineuse")
                seen = set()
                for info in infos:
                    name = info.filename.rstrip("/")
                    safe_path(name)
                    if name.casefold() in seen:
                        raise ValueError("Chemins d'archive dupliqués")
                    seen.add(name.casefold())
                    if stat.S_ISLNK(info.external_attr >> 16) or info.flag_bits & 1:
                        raise ValueError("Liens ou fichiers chiffrés refusés")
                    if info.file_size > MAX_MEMBER or info.file_size / max(1, info.compress_size) > 200:
                        raise ValueError("Membre excessivement volumineux")
                manifests = [x for x in infos if PurePosixPath(x.filename).name.lower() in ("manifest", "manifest.json")]
                all_items, manifest_names = {}, []
                for m in manifests:
                    if m.file_size > 8 * 1024**2:
                        raise ValueError("Manifeste trop volumineux")
                    try:
                        items = _manifest_items(json.loads(z.read(m).decode("utf-8-sig")))
                    except (UnicodeError, json.JSONDecodeError):
                        continue
                    if items:
                        if set(all_items) & set(items):
                            raise ValueError("Ressources répétées entre manifestes")
                        all_items.update(items)
                        manifest_names.append(m.filename)
                if set(all_items) != {a["id"] for a in data["assets"]}:
                    raise ValueError("Manifeste incompatible ou identifiants différents de l'inventaire ; import refusé")
                for a in data["assets"]:
                    m = all_items[a["id"]]
                    if m.get("type") != a["type"] or m.get("name") != a["name"]:
                        raise ValueError("Nom ou type différent du manifeste")
                    manifest_components = {}
                    for component in m.get("components", []):
                        full_path = str(safe_path(m.get("path", m["id"]) + "/" + component["path"]))
                        manifest_components[full_path] = component
                    for component in a.get("components", []):
                        declared = manifest_components.get(component["archive_path"])
                        if not declared or declared.get("type") != component.get("type") or declared.get("length") != component.get("size_bytes"):
                            raise ValueError("Composant différent du manifeste")
                        if declared.get("library#sha256") and component.get("sha256") not in (None, declared["library#sha256"]):
                            raise ValueError("Empreinte déclarée différente du manifeste")
                        if declared.get("library#sha256"):
                            component["sha256"] = declared["library#sha256"]
                    # Include every native component; an inventory cannot silently omit one.
                    expected_ai = {path for path, c in manifest_components.items() if c.get("type") == "application/illustrator"}
                    inventoried_ai = {c["archive_path"] for c in a.get("components", []) if c.get("type") == "application/illustrator"}
                    if expected_ai != inventoried_ai:
                        raise ValueError("Inventaire incomplet des composants AI")
                # Rebuild after manifest-authoritative checksums have been attached.
                result = catalog(data, library_id)
                for a in result["assets"]:
                    for c in a["components"]:
                        name = c["archive_path"]
                        try:
                            info = z.getinfo(name)
                        except KeyError as e:
                            raise ValueError("Ressource AI absente de l'archive") from e
                        if info.file_size != c.get("size_bytes"):
                            raise ValueError("Taille AI différente de l'inventaire")
                        target = stage.joinpath(*safe_path(name).parts)
                        target.parent.mkdir(parents=True, exist_ok=True)
                        with z.open(info) as source, target.open("wb") as dest:
                            shutil.copyfileobj(source, dest, 1024**2)
                        checksum = digest(target)
                        if c.get("sha256") and checksum != c["sha256"]:
                            raise ValueError("Empreinte AI différente de l'inventaire")
                        c["sha256"] = checksum
                        if target.read_bytes()[:5] not in (b"%PDF-", b"%!PS-"):
                            raise ValueError("Ressource non reconnue comme Illustrator")
                    a["verified"] = bool(a["components"])
                    if a["verified"]:
                        try:
                            render_page(stage / a["components"][0]["archive_path"], 1, stage / (a["id"] + ".png"), max_side=256)
                            a["preview"] = True
                        except (ValueError, RuntimeError):
                            pass
                result.update(archive_verified=True, warnings=[], manifest_files=manifest_names)
                result["archive_sha256"] = digest(archive)
        (stage / "catalog.json").write_text(json.dumps(result, ensure_ascii=False, indent=2))
        stage.rename(output)
    except Exception:
        shutil.rmtree(stage)
        raise
    return result
