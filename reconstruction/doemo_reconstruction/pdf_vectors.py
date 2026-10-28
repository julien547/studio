"""Recover conservative native axes, without pairing independent PDF strokes.

This is geometric recovery, not architectural classification. Unsupported paint,
clips and Form XObjects remain in raw vectors and in the rendered reference.
"""
import ctypes
import math

from pypdfium2 import raw

from .geometry import distance, wall


def transform(point, matrix):
    x, y = point
    a, b, c, d, e, f = matrix
    return [a*x+c*y+e, b*x+d*y+f]


def _rgba(obj, getter):
    channels = [ctypes.c_uint() for _ in range(4)]
    return [v.value for v in channels] if getter(obj, *channels) else None


def _dark_opaque(color):
    return (color is not None and color[3] == 255
            and max(color[:3])-min(color[:3]) < 30 and max(color[:3]) < 180)


def _rectangle_axis(points):
    """One median for an elongated rectangle, never its four outline edges."""
    points = list(points)
    if len(points) > 1 and distance(points[0], points[-1]) < 1e-6:
        points.pop()
    if len(points) != 4:
        return None
    edges = [[points[(i+1) % 4][k]-p[k] for k in (0, 1)] for i, p in enumerate(points)]
    lengths = [math.hypot(*edge) for edge in edges]
    if min(lengths) < 1e-6:
        return None
    # Relative tolerances only compensate PDF float representation, not skew.
    if any(abs(sum(edges[i][k]*edges[(i+1) % 4][k] for k in (0, 1)))
           > 1e-5*lengths[i]*lengths[(i+1) % 4] for i in range(4)):
        return None
    if any(math.hypot(*(edges[i][k]+edges[i+2][k] for k in (0, 1)))
           > 1e-5*max(lengths) for i in (0, 1)):
        return None
    short = min(range(4), key=lengths.__getitem__)
    thickness, length = lengths[short], lengths[(short+1) % 4]
    if length < 12 or length < 4*thickness or thickness > 24:
        return None
    midpoint = lambda i: [(points[i % 4][k]+points[(i+1) % 4][k])/2 for k in (0, 1)]
    return midpoint(short), midpoint(short+2), thickness


def _axes(path, subpaths):
    reason = path['deferred_reason']
    if reason:
        return []
    evidence = {'type': 'native_pdf', 'raw_path_id': path['id'], 'semantic_status': 'unknown',
                'stroke_width_pdf_local': path['stroke_width_pdf_local']}
    fill, stroke = path['fill_mode'] != 0, path['stroked']
    if fill or any(part['closed'] for part in subpaths):
        # A compound path may contain a hole/opening: never collapse its envelope.
        rectangle = _rectangle_axis(subpaths[0]['points']) if len(subpaths) == 1 else None
        if rectangle:
            a, b, thickness = rectangle
            path['recovery'] = 'rectangle_median'
            return [wall(a, b, thickness, method='native_pdf_rectangle', evidence=[{
                **evidence, 'geometry': 'rectangle_median',
                'source_polygon': subpaths[0]['points'], 'thickness_unit': 'document'}])]
        path['deferred_reason'] = 'complex_closed_or_filled_path'
        return []
    if stroke:
        walls = []
        for part_index, part in enumerate(subpaths):
            for segment_index, (a, b) in enumerate(zip(part['points'], part['points'][1:])):
                if distance(a, b) >= 12:
                    walls.append(wall(a, b, None, method='native_pdf_stroke', evidence=[{
                        **evidence, 'geometry': 'stroke_axis', 'subpath': part_index,
                        'segment': segment_index}]))
        path['recovery'] = 'stroke_axes' if walls else None
        if not walls:
            path['deferred_reason'] = 'segments_below_minimum'
        return walls
    return []


def recover_vectors(page, page_matrix):
    paths, walls, texts = [], [], []
    has_images = False
    for obj in page.get_objects():
        if obj.type == raw.FPDF_PAGEOBJ_IMAGE:
            has_images = True
        if obj.type == raw.FPDF_PAGEOBJ_TEXT:
            texts.append(list(obj.get_bounds()))
        if obj.type != raw.FPDF_PAGEOBJ_PATH:
            continue
        matrix = obj.get_matrix()
        parent = obj.container
        while parent is not None:
            matrix = matrix.multiply(parent.get_matrix())
            parent = parent.container
        segments, subpaths = [], []
        curved = False
        for i in range(raw.FPDFPath_CountSegments(obj)):
            seg = raw.FPDFPath_GetPathSegment(obj, i)
            x, y = ctypes.c_float(), ctypes.c_float()
            if not raw.FPDFPathSegment_GetPoint(seg, x, y):
                raise ValueError('Segment PDF illisible')
            point = transform(matrix.on_point(x.value, y.value), page_matrix)
            if not all(math.isfinite(v) for v in point):
                raise ValueError('Coordonnées PDF non finies')
            kind = raw.FPDFPathSegment_GetType(seg)
            closed = bool(raw.FPDFPathSegment_GetClose(seg))
            segments.append({'type': kind, 'point': point, 'close': closed})
            if kind == raw.FPDF_SEGMENT_MOVETO:
                subpaths.append({'points': [point], 'closed': closed})
            elif subpaths:
                subpaths[-1]['points'].append(point)
                subpaths[-1]['closed'] |= closed
            if kind not in (raw.FPDF_SEGMENT_MOVETO, raw.FPDF_SEGMENT_LINETO):
                curved = True
        fill, stroke = ctypes.c_int(), ctypes.c_int()
        draw_ok = raw.FPDFPath_GetDrawMode(obj, fill, stroke)
        width = ctypes.c_float()
        width_ok = raw.FPDFPageObj_GetStrokeWidth(obj, width)
        stroke_rgba = _rgba(obj, raw.FPDFPageObj_GetStrokeColor)
        fill_rgba = _rgba(obj, raw.FPDFPageObj_GetFillColor)
        dash_count = raw.FPDFPageObj_GetDashCount(obj)
        clip = raw.FPDFPageObj_GetClipPath(obj)
        clip_count = raw.FPDFClipPath_CountPaths(clip) if clip else 0
        reason = None
        if not draw_ok or not (fill.value or stroke.value):
            reason = 'unpainted_or_unknown'
        elif obj.container is not None:
            # PDFium's child clip accessor does not expose the Form's /BBox clip.
            reason = 'form_visibility_requires_review'
        elif clip_count > 0:
            reason = 'clipped_path'
        elif curved:
            reason = 'curved_path'
        elif stroke.value and dash_count != 0:
            reason = 'dashed_or_unknown_stroke'
        elif ((stroke.value and not _dark_opaque(stroke_rgba))
              or (fill.value and not _dark_opaque(fill_rgba))):
            reason = 'non_dark_or_transparent_paint'
        path = {'id': f'pdf-path-{len(paths)+1}', 'segments': segments,
                'stroke_rgb': stroke_rgba[:3] if stroke_rgba else None,
                'stroke_rgba': stroke_rgba, 'fill_rgba': fill_rgba,
                'stroked': bool(stroke.value), 'fill_mode': fill.value,
                'stroke_width_pdf_local': width.value if width_ok else None,
                'dash_count': dash_count, 'clip_count': max(0, clip_count),
                'in_form': obj.container is not None, 'contains_curves': curved,
                'status': 'unclassified', 'deferred_reason': reason, 'recovery': None}
        walls.extend(_axes(path, subpaths))
        paths.append(path)
    # Repeated paint of exactly the same axis is one geometric candidate. This
    # never averages nearby lines, joins intervals, or removes an opening.
    unique = {}
    for candidate in walls:
        key = (tuple(sorted(tuple(p) for p in (candidate['a'], candidate['b']))), candidate['thickness'])
        if key in unique:
            unique[key]['evidence'].extend(candidate['evidence'])
        else:
            unique[key] = candidate
    return paths, list(unique.values()), texts, has_images
