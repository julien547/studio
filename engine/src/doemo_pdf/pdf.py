"""Preserve source Form streams and resources. Never infer separable symbols.

This first implementation emits diagnostic compositions only. It deliberately
does not export production variants from an unstructured PDF.
"""

from collections import Counter
import hashlib
import json
from pathlib import Path
import re

import pikepdf
from pypdf import PdfReader

from .geometry import Rect, fit

MAX_BYTES = 64 * 1024 * 1024
MAX_PAGES = 100
PAINT = {"S", "s", "f", "F", "f*", "B", "B*", "b", "b*"}
LABEL = re.compile(r"^(PE|PI)(\d*)[.\-_]?([HV])(?:[.\-_]?(A[0-4]))?$", re.I)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def file_hash(path):
    with Path(path).open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def parse_label(text):
    m = LABEL.fullmatch(re.sub(r"\s+", "", text))
    return None if m is None else dict(type=m[1].upper(), number=m[2],
                                      orientation=m[3].upper(), paper=(m[4] or "A3").upper())


def open_pdf(path):
    path = Path(path)
    if not path.is_file() or not 0 < path.stat().st_size <= MAX_BYTES:
        raise ValueError("PDF absent, vide ou supérieur à 64 Mio.")
    with path.open("rb") as f:
        if not f.read(8).startswith(b"%PDF-"):
            raise ValueError("Aucune représentation PDF en tête du fichier ; exporter un PDF vectoriel.")
    pdf = pikepdf.Pdf.open(path, attempt_recovery=False)
    try:
        if pdf.is_encrypted:
            raise ValueError("Les PDF chiffrés ne sont pas pris en charge.")
        if not 0 < len(pdf.pages) <= MAX_PAGES:
            raise ValueError("Nombre de pages non pris en charge.")
        if any(key in pdf.Root for key in ("/OpenAction", "/AA", "/AcroForm")):
            raise ValueError("PDF interactif non pris en charge pour cet essai.")
        names = pdf.Root.get("/Names", {})
        if any(key in names for key in ("/JavaScript", "/EmbeddedFiles")):
            raise ValueError("Scripts ou pièces jointes PDF non pris en charge.")
        errors = pdf.check_pdf_syntax()
        if errors:
            raise ValueError("Anomalie de structure PDF : " + "; ".join(errors[:3]))
        return pdf
    except Exception:
        pdf.close()
        raise


def selected_page(pdf, index):
    if index < 0 or index >= len(pdf.pages):
        raise ValueError("Numéro de page hors limites.")
    page = pdf.pages[index]
    if int(page.obj.get("/Rotate", 0)) % 360:
        raise ValueError("Rotation de page préexistante : normalisation non validée dans cette version.")
    if float(page.obj.get("/UserUnit", 1)) != 1:
        raise ValueError("Unité PDF personnalisée non prise en charge dans cette version.")
    if page.obj.get("/Annots") or "/AA" in page.obj:
        raise ValueError("Annotations/actions de page non prises en charge.")
    return page


def resources_fingerprint(obj):
    """Multiset of decoded embedded streams, independent of PDF object numbers."""
    seen = set()
    result = []

    def visit(value, depth=0):
        if depth > 80:
            raise ValueError("Ressources PDF trop imbriquées.")
        if not isinstance(value, pikepdf.Object):
            return
        if value.is_indirect:
            if value.objgen in seen:
                return
            seen.add(value.objgen)
        if isinstance(value, pikepdf.Stream):
            # Some images use codecs which cannot be decoded as a generic stream.
            try:
                payload = value.read_bytes()
                mode = "decoded"
            except pikepdf.PdfError:
                payload = value.read_raw_bytes()
                mode = "encoded"
            result.append((str(value.get("/Subtype", "stream")), mode, digest(payload)))
        if isinstance(value, (pikepdf.Dictionary, pikepdf.Stream)):
            for key, child in value.items():
                if key not in ("/Parent", "/P", "/Length", "/Filter", "/DecodeParms"):
                    visit(child, depth+1)
        elif isinstance(value, pikepdf.Array):
            for child in value:
                visit(child, depth+1)

    visit(obj)
    return sorted(result)


def vector_stats(page):
    counts = Counter()
    visited = set()

    def visit(container, depth=0):
        if depth > 40:
            raise ValueError("Form XObjects trop imbriqués.")
        for instruction in pikepdf.parse_content_stream(container):
            counts[str(instruction.operator)] += 1
        resources = container.obj.get("/Resources", {}) if isinstance(container, pikepdf.Page) else container.get("/Resources", {})
        for _, obj in resources.get("/XObject", {}).items():
            if obj.objgen in visited:
                continue
            visited.add(obj.objgen)
            if obj.get("/Subtype") == pikepdf.Name.Form:
                counts["form_resources"] += 1
                visit(obj, depth+1)
            elif obj.get("/Subtype") == pikepdf.Name.Image:
                counts["image_resources"] += 1

    visit(page)
    return {"path_paint_operators": sum(counts[x] for x in PAINT),
            "image_resources": counts["image_resources"],
            "form_resources": counts["form_resources"],
            "text_show_operators": counts["Tj"]+counts["TJ"]+counts["'"]+counts['"'],
            "note": "Preuve de tracés présents, pas une certification que tout le bâtiment est vectoriel."}


def inspect_pdf(path):
    path = Path(path)
    initial = file_hash(path)
    with open_pdf(path) as pdf:
        reader = PdfReader(path, strict=True)
        pages = []
        for i, page in enumerate(pdf.pages):
            text = reader.pages[i].extract_text() or ""
            candidates = []
            for line in text.splitlines():
                parsed = parse_label(line)
                if parsed:
                    candidates.append({"label": line, **parsed, "direction": None,
                                       "reviewed": False, "status": "label_only_not_verified_vei"})
            pages.append({"page": i+1, "media_box": list(map(float, page.mediabox)),
                          "crop_box": list(map(float, page.cropbox)),
                          "rotation": int(page.obj.get("/Rotate", 0)),
                          "vector_evidence": vector_stats(page),
                          "label_candidates": candidates,
                          "unicode_extraction_warning": any(ord(x) < 32 and x not in "\n\r\t" for x in text)})
        oc = pdf.Root.get("/OCProperties", {})
        layers = [{"name": str(x.get("/Name", "")), "object": list(x.objgen)} for x in oc.get("/OCGs", [])]
    if file_hash(path) != initial:
        raise ValueError("Le fichier source a changé pendant l'inspection.")
    return {"file": path.name, "sha256": initial, "page_count": len(pages),
            "pages": pages, "layers": layers, "source_unchanged": True,
            "production_ready": False, "symbol_separation": "unverified"}


def copy_optional_content(source, destination):
    source_oc = source.Root.get("/OCProperties")
    if source_oc is None:
        return
    copied = destination.copy_foreign(source.make_indirect(source_oc))
    if "/OCProperties" not in destination.Root:
        destination.Root.OCProperties = copied
        return
    target = destination.Root.OCProperties
    target_default = target.get("/D")
    if target_default is None:
        target_default = pikepdf.Dictionary()
        target.D = target_default
    source_default = copied.get("/D", {})
    base_on = source_default.get("/BaseState", pikepdf.Name.ON) == pikepdf.Name.ON
    on_ids = {x.objgen for x in source_default.get("/ON", [])}
    off_ids = {x.objgen for x in source_default.get("/OFF", [])}
    for key in ("/OCGs",):
        target[key] = pikepdf.Array(list(target.get(key, [])) + list(copied.get(key, [])))
    for layer in copied.get("/OCGs", []):
        enabled = layer.objgen in on_ids or (base_on and layer.objgen not in off_ids)
        key = "/ON" if enabled else "/OFF"
        target_default[key] = pikepdf.Array(list(target_default.get(key, [])) + [layer])
    target_default.Order = pikepdf.Array(list(target_default.get("/Order", [])) + list(copied.get("/OCGs", [])))


def compose_diagnostic(source_path, template_path, output_path, zone, direction,
                       source_page=0, margin=12, allow_upscale=True):
    """Full BAT page composition. No automatic content exclusion or production flag."""
    source_path, template_path, output_path = map(Path, (source_path, template_path, output_path))
    report_path = output_path.with_suffix(".report.json")
    if output_path.suffix.lower() != ".pdf":
        raise ValueError("La sortie doit être un PDF.")
    if output_path.exists() or report_path.exists():
        raise ValueError("Refus d'écraser une sortie ou son rapport.")
    for path in (source_path, template_path):
        if output_path.resolve() == path.resolve() or report_path.resolve() == path.resolve():
            raise ValueError("Une source ne peut pas être une destination.")
    hashes = {str(p): file_hash(p) for p in (source_path, template_path)}
    source_info = inspect_pdf(source_path)
    with open_pdf(source_path) as source, open_pdf(template_path) as output:
        if len(output.pages) != 1:
            raise ValueError("Sélection d'une trame à page unique requise.")
        page = selected_page(source, source_page)
        target = selected_page(output, 0)
        if vector_stats(page)["path_paint_operators"] == 0:
            raise ValueError("Aucun tracé vectoriel détecté dans la page source.")
        if source.Root.get("/OutputIntents") or output.Root.get("/OutputIntents"):
            raise ValueError("Profils OutputIntents : compatibilité colorimétrique non validée dans cette version.")
        page_bounds = Rect(*map(float, page.cropbox))
        target_bounds = Rect(*map(float, target.cropbox))
        if not target_bounds.contains(zone):
            raise ValueError("ZONE_PLAN est hors de la trame.")
        useful = zone.inset(margin)
        matrix, scale, angle = fit(page_bounds, useful, direction, allow_upscale)
        form = page.as_form_xobject()
        source_stream = digest(form.read_bytes())
        resources_before = resources_fingerprint(form)
        imported = output.copy_foreign(form)
        copy_optional_content(source, output)
        if "/XObject" not in target.Resources:
            target.Resources.XObject = pikepdf.Dictionary()
        key = "/DOEMO_SOURCE"
        if key in target.Resources.XObject:
            raise ValueError("Nom de ressource réservé déjà présent dans la trame.")
        target.Resources.XObject[key] = imported
        coefficients = " ".join(format(v, ".12f") for v in matrix.values)
        # Isolate the existing template graphics state before importing the BAT.
        # Its final CTM, color or clipping must not leak into the source Form.
        target.contents_add(b"q\n", prepend=True)
        target.contents_add(("Q\nq\n" + coefficients + " cm\n" + key + " Do\nQ\n").encode(), prepend=False)
        output.docinfo["/Title"] = "DOEMO Studio — DIAGNOSTIC NON CONFORME POUR PRODUCTION"
        output.docinfo["/Subject"] = "Essai de composition de la page BAT complète. Tous les VEI restent visibles."
        report = {"schema_version": 1, "status": "diagnostic_nonconforming", "production_ready": False,
                  "application_origin": "https://studio.doemo.fr",
                  "application_url": "https://studio.doemo.fr/app/orientation",
                  "source": {"name": source_path.name, "sha256": hashes[str(source_path)], "page": source_page+1},
                  "template": {"name": template_path.name, "sha256": hashes[str(template_path)]},
                  "selection": "full_source_page_no_object_exclusion",
                  "zone": list(zone.values), "zone_confirmed": False, "margin_pt": margin,
                  "source_bounds": list(page_bounds.values), "placed_bounds": list(matrix.bounds(page_bounds).values),
                  "matrix": list(matrix.values), "rotation_degrees_ccw": angle, "scale": scale,
                  "scale_percent": scale*100, "direction_declared": list(direction),
                  "direction_after": list(matrix.vector(direction)),
                  "label_candidate_count": len(source_info["pages"][source_page]["label_candidates"]),
                  "checks": {},
                  "blockers": ["FULL_BAT_PAGE_WITH_SOURCE_PRESENTATION", "OTHER_VEI_NOT_EXCLUDED",
                               "COUNTER_ROTATIONS_NOT_VALIDATED", "ZONE_AND_MARGINS_NOT_APPROVED",
                               "TEMPLATE_PRODUCTION_CONTENT_NOT_APPROVED", "VISUAL_BUSINESS_REVIEW_REQUIRED"]}
        output_path.parent.mkdir(parents=True, exist_ok=True)
        created_pdf = False
        created_report = False
        try:
            with output_path.open("xb") as f:
                created_pdf = True
                output.save(f)
            with open_pdf(output_path) as check:
                saved_page = check.pages[0]
                saved_form = saved_page.Resources.XObject[key]
                stream_kept = digest(saved_form.read_bytes()) == source_stream
                resources_kept = resources_fingerprint(saved_form) == resources_before
                if not stream_kept or not resources_kept:
                    raise ValueError("Flux ou ressources vectorielles modifiés pendant la composition.")
                if list(saved_page.mediabox) != list(target.mediabox):
                    raise ValueError("Dimensions de la trame modifiées.")
            for name, expected in hashes.items():
                if file_hash(name) != expected:
                    raise ValueError("Une source a changé pendant la composition.")
            report["checks"] = {"pdf_reopens_without_syntax_errors": "passed", "page_dimensions": "passed",
                                "source_stream_unchanged": "passed", "embedded_resource_streams_unchanged": "passed",
                                "uniform_scale_and_no_reflection": "passed", "declared_direction_up": "passed",
                                "full_source_page_inside_zone": "passed", "source_files_unchanged": "passed",
                                "single_active_vei": "not_satisfied", "individual_counter_rotations": "not_run",
                                "architectural_scope_approved": "not_run", "visual_fidelity": "not_run"}
            report["output_sha256"] = file_hash(output_path)
            with report_path.open("x", encoding="utf-8") as f:
                created_report = True
                json.dump(report, f, ensure_ascii=False, indent=2, allow_nan=False)
                f.write("\n")
        except Exception:
            if created_pdf:
                output_path.unlink(missing_ok=True)
            if created_report:
                report_path.unlink(missing_ok=True)
            raise
    return report
