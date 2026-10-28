from pathlib import Path
import hashlib
import warnings
import numpy as np
from PIL import Image, ImageOps
import pypdfium2 as pdfium

MAX_PAGES = 50
MAX_PIXELS = 40_000_000
Image.MAX_IMAGE_PIXELS = MAX_PIXELS


def is_pdf(path):
    with open(path, "rb") as f:
        return f.read(5) == b"%PDF-"


def render_page(path, page, output=None, max_side=2400):
    path = Path(path)
    if is_pdf(path):
        try:
            with pdfium.PdfDocument(path) as doc:
                if len(doc) > MAX_PAGES or not 1 <= page <= len(doc):
                    raise ValueError("Nombre de pages refusé")
                p = doc[page - 1]
                w, h = p.get_size()
                if not 0 < w < 100000 or not 0 < h < 100000:
                    raise ValueError("Dimensions PDF refusées")
                bitmap = p.render(scale=max_side / max(w, h))
                image = bitmap.to_pil().convert("RGB")
                bitmap.close()
                p.close()
        except pdfium.PdfiumError as e:
            raise ValueError("PDF illisible ou chiffré") from e
    else:
        if page != 1:
            raise ValueError("Page d'image invalide")
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(path) as im:
                    if im.format not in ("JPEG", "PNG") or im.width * im.height > MAX_PIXELS:
                        raise ValueError("Image refusée")
                    image = ImageOps.exif_transpose(im).convert("RGB")
                    image.thumbnail((max_side, max_side))
        except (OSError, Image.DecompressionBombWarning, Image.DecompressionBombError) as e:
            raise ValueError("Image invalide ou trop grande") from e
    if output:
        image.save(output, "PNG")
    return image


def prepare_document(path, directory, original_name, role):
    """Keep exact original bytes. All proposals use the rendered, upright page frame."""
    directory = Path(directory)
    if role == "target" and Path(original_name).suffix.lower() != ".ai":
        raise ValueError("Le BAT de référence doit être un fichier .ai avec aperçu PDF")
    if role == "target" and not is_pdf(path):
        raise ValueError("BAT AI sans compatibilité PDF : exporter un aperçu PDF depuis Illustrator")
    native_present = False
    original_image_size = None
    exif_orientation = None
    pdf_frames = []
    if role == "target":
        from pypdf import PdfReader
        try:
            reader = PdfReader(path)
            for page in reader.pages:
                piece = page.get("/PieceInfo", {})
                piece = piece.get_object() if hasattr(piece, "get_object") else piece
                illustrator = piece.get("/Illustrator", {})
                illustrator = illustrator.get_object() if hasattr(illustrator, "get_object") else illustrator
                private = illustrator.get("/Private", {})
                private = private.get_object() if hasattr(private, "get_object") else private
                if any(str(key).startswith("/AIPrivateData") for key in private):
                    native_present = True
        except Exception as e:
            raise ValueError("Métadonnées natives du BAT illisibles") from e
        if not native_present:
            raise ValueError("Le BAT ne contient pas de données Illustrator natives ; un PDF renommé .ai n'est pas accepté")
    digest = hashlib.sha256(Path(path).read_bytes()).hexdigest()
    if is_pdf(path):
        try:
            with pdfium.PdfDocument(path) as doc:
                count = len(doc)
                sizes = [list(doc[i].get_size()) for i in range(min(count, MAX_PAGES))]
                for i in range(min(count, MAX_PAGES)):
                    pdf_page = doc[i]
                    pdf_frames.append({"crop_box_pt": list(pdf_page.get_bbox()), "rotation_deg": pdf_page.get_rotation()})
                    pdf_page.close()
        except pdfium.PdfiumError as e:
            raise ValueError("PDF illisible") from e
        if not 1 <= count <= MAX_PAGES:
            raise ValueError("Document limité à 50 pages")
    else:
        sizes = [None]
        with Image.open(path) as original:
            original_image_size = list(original.size)
            exif_orientation = int(original.getexif().get(274, 1))
    pages = []
    for i, points in enumerate(sizes, 1):
        image = render_page(path, i, directory / f"page-{i}.png")
        pages.append({"number": i, "width": image.width, "height": image.height,
                      "pdf_size_pt": points, "coordinate_frame": "rendered_upright_normalized_top_left",
                      "original_image_size_px": original_image_size, "exif_orientation": exif_orientation,
                      "pdf_source_frame": pdf_frames[i-1] if pdf_frames else None})
    return {"name": Path(original_name).name, "sha256": digest, "role": role, "pages": pages,
            "native_ai_data_present": native_present, "native_ai_runtime_verified": False}


def rgb(path):
    with Image.open(path) as im:
        return np.asarray(im.convert("RGB"))
