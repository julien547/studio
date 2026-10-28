import cv2
import numpy as np


def project(matrix, points):
    m = np.asarray(matrix, dtype=float)
    p = np.asarray(points, dtype=float)
    if m.shape != (3, 3) or p.ndim != 2 or p.shape[1] != 2 or not np.isfinite(m).all() or not np.isfinite(p).all():
        raise ValueError("Coordonnées ou matrice invalides")
    q = np.c_[p, np.ones(len(p))] @ m.T
    if np.any(np.abs(q[:, 2]) < 1e-9):
        raise ValueError("Transformation singulière")
    result = q[:, :2] / q[:, 2, None]
    if not np.isfinite(result).all():
        raise ValueError("Transformation non finie")
    return result


def error_px(matrix, source, target, width, height):
    residual = (project(matrix, source) - np.asarray(target)) * [width, height]
    return float(np.sqrt(np.mean(np.sum(residual ** 2, axis=1))))


def solve(source, target, model, width, height, checks_source, checks_target):
    a, b = np.asarray(source, dtype=float), np.asarray(target, dtype=float)
    minimum = 3 if model == "affine" else 4
    if model not in ("affine", "homography") or a.shape != b.shape or a.ndim != 2 or a.shape[1] != 2 or len(a) < minimum:
        raise ValueError("Au moins trois paires pour affine, quatre pour perspective")
    if not np.isfinite(a).all() or not np.isfinite(b).all() or np.any(a < 0) or np.any(a > 1) or np.any(b < 0) or np.any(b > 1):
        raise ValueError("Points hors page")
    if np.linalg.matrix_rank(np.c_[a, np.ones(len(a))]) < 3 or np.linalg.matrix_rank(np.c_[b, np.ones(len(b))]) < 3:
        raise ValueError("Points colinéaires")
    if model == "affine":
        x, *_ = np.linalg.lstsq(np.c_[a, np.ones(len(a))], b, rcond=None)
        matrix = np.vstack([x.T, [0, 0, 1]])
    else:
        matrix, _ = cv2.findHomography(a, b, 0)
        if matrix is None:
            raise ValueError("Recalage impossible")
    if abs(np.linalg.det(matrix)) < 1e-10 or np.linalg.cond(matrix) > 1e8:
        raise ValueError("Transformation dégénérée")
    if len(checks_source) < 1 or len(checks_source) != len(checks_target):
        raise ValueError("Un point de contrôle indépendant est requis")
    for p in checks_source:
        if any(np.linalg.norm(np.array(p) - q) < 1e-4 for q in a):
            raise ValueError("Le point de contrôle doit être indépendant des points de calcul")
    return {"matrix": matrix.tolist(), "fit_error_px": error_px(matrix, a, b, width, height),
            "check_error_px": error_px(matrix, checks_source, checks_target, width, height)}


def automatic(source_rgb, target_rgb):
    # Architectural luminance edges, tentative feature matches only. No auto-acceptance.
    source, target = [cv2.cvtColor(x, cv2.COLOR_RGB2GRAY) for x in (source_rgb, target_rgb)]
    detector = cv2.SIFT_create(nfeatures=4000)
    ka, da = detector.detectAndCompute(source, None)
    kb, db = detector.detectAndCompute(target, None)
    if da is None or db is None:
        raise ValueError("Pas assez de détails communs")
    pairs = cv2.BFMatcher().knnMatch(da, db, k=2)
    good = [p[0] for p in pairs if len(p) == 2 and p[0].distance < .65 * p[1].distance]
    if len(good) < 8:
        raise ValueError("Correspondances insuffisantes : utiliser les points manuels")
    a = np.float32([ka[m.queryIdx].pt for m in good])
    b = np.float32([kb[m.trainIdx].pt for m in good])
    matrix, mask = cv2.findHomography(a, b, cv2.RANSAC, 4)
    if matrix is None or int(mask.sum()) < 8 or float(mask.mean()) < .4:
        raise ValueError("Alignement automatique non fiable")
    a, b = a[mask.ravel() == 1], b[mask.ravel() == 1]
    # Keep a bounded, spread sample; manual independent checks remain obligatory.
    idx = np.linspace(0, len(a) - 1, min(12, len(a)), dtype=int)
    return {"source_points": (a[idx] / [source.shape[1], source.shape[0]]).tolist(),
            "target_points": (b[idx] / [target.shape[1], target.shape[0]]).tolist(),
            "inliers": len(a), "tentative_matches": len(good), "confirmed": False}
