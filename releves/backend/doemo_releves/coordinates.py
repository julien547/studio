"""Explicit homogeneous transforms. All persisted annotations use the upright page.

Cropping, viewer zoom and quarter-turn rotations never rewrite stored coordinates.
PDF points use a bottom-left origin; Illustrator placements use artboard top-left.
"""
import numpy as np


def apply(matrix, points):
    m = np.asarray(matrix, dtype=float)
    p = np.asarray(points, dtype=float)
    if m.shape != (3, 3) or p.ndim != 2 or p.shape[1] != 2 or not np.isfinite(m).all() or not np.isfinite(p).all():
        raise ValueError("Coordonnées ou matrice invalides")
    q = np.c_[p, np.ones(len(p))] @ m.T
    if np.any(np.abs(q[:, 2]) < 1e-12):
        raise ValueError("Transformation singulière")
    return (q[:, :2] / q[:, 2:]).tolist()


def inverse(matrix):
    try:
        value = np.linalg.inv(np.asarray(matrix, dtype=float))
    except np.linalg.LinAlgError as e:
        raise ValueError("Transformation non inversible") from e
    if not np.isfinite(value).all():
        raise ValueError("Transformation non finie")
    return value.tolist()


def frames(page, region=None, rotation=0):
    b = region or {"x": 0, "y": 0, "w": 1, "h": 1}
    crop = np.array([[b["w"], 0, b["x"]], [0, b["h"], b["y"]], [0, 0, 1]])
    # Rotated view normalized -> unrotated crop normalized.
    rotations = {0: np.eye(3), 90: [[0,1,0],[-1,0,1],[0,0,1]],
                 180: [[-1,0,1],[0,-1,1],[0,0,1]], 270: [[0,-1,1],[1,0,0],[0,0,1]]}
    view_to_page = (crop @ rotations[rotation]).tolist()
    result = {"page_normalized_to_raster": [[page["width"],0,0],[0,page["height"],0],[0,0,1]],
              "view_to_page": view_to_page, "page_to_view": inverse(view_to_page)}
    if page.get('original_image_size_px'):
        raw_w, raw_h = page['original_image_size_px']
        upright_to_raw = {
            1:[[1,0,0],[0,1,0],[0,0,1]], 2:[[-1,0,1],[0,1,0],[0,0,1]],
            3:[[-1,0,1],[0,-1,1],[0,0,1]], 4:[[1,0,0],[0,-1,1],[0,0,1]],
            5:[[0,1,0],[1,0,0],[0,0,1]], 6:[[0,1,0],[-1,0,1],[0,0,1]],
            7:[[0,-1,1],[-1,0,1],[0,0,1]], 8:[[0,-1,1],[1,0,0],[0,0,1]],
        }.get(page.get('exif_orientation'), np.eye(3))
        result['page_normalized_to_original_raster'] = (np.diag([raw_w,raw_h,1]) @ upright_to_raw).tolist()
    if page.get("pdf_size_pt"):
        w,h = page["pdf_size_pt"]
        result["page_normalized_to_pdf"] = [[w,0,0],[0,-h,h],[0,0,1]]
        result["page_normalized_to_illustrator_top_left"] = [[w,0,0],[0,h,0],[0,0,1]]
        source = page.get("pdf_source_frame")
        if source:
            left,bottom,right,top = source['crop_box_pt']
            bw,bh = right-left,top-bottom
            result['page_normalized_to_pdf'] = {
                0:[[bw,0,left],[0,-bh,top],[0,0,1]],
                90:[[0,bw,left],[bh,0,bottom],[0,0,1]],
                180:[[-bw,0,right],[0,bh,bottom],[0,0,1]],
                270:[[0,-bw,right],[-bh,0,top],[0,0,1]],
            }[source['rotation_deg']]
    return result
