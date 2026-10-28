"""Find potentially duplicated median axes for explicit human interpretation.

Proximity is not evidence that two traces describe the same wall. This module
never merges, snaps, closes a gap, or changes the user's geometry. Tolerances
are document units, not metres. Openings are subtracted before comparing spans.
"""
import copy
import math

from .geometry import axis_points, distance, solid_intervals

MAX_SEPARATION = 24.
MIN_OVERLAP = 6.
ANGLE = math.sin(math.radians(1))


def snapshot(wall):
    return [wall['id'], list(wall['a']), list(wall['b']), wall['thickness'],
            sorted([[o['kind'], o['start'], o['end']] for o in wall['openings']])]


def close_axes(first, second):
    """Return overlapping solid spans; endpoint contact alone is never a double."""
    if first['id'] == second['id'] or any(w['status'] == 'rejected' for w in (first, second)):
        return None
    # Canonical direction and order make the report independent of wall order.
    first, second = sorted((first, second), key=lambda w: w['id'])
    a, b = sorted((first['a'], first['b']))
    c, d = second['a'], second['b']
    length, other = distance(a, b), distance(c, d)
    ux, uy = (b[0]-a[0])/length, (b[1]-a[1])/length
    if abs(ux*(d[1]-c[1])-uy*(d[0]-c[0]))/other > ANGLE:
        return None
    projected = [(p[0]-a[0])*ux+(p[1]-a[1])*uy for p in (c, d)]
    spans = []
    for w in (first, second):
        spans.append([sorted((p[0]-a[0])*ux+(p[1]-a[1])*uy for p in axis_points(w, lo, hi))
                      for lo, hi in solid_intervals(w)])
    overlaps = []
    for start, end in spans[0]:
        for other_start, other_end in spans[1]:
            lo, hi = max(start, other_start), min(end, other_end)
            if hi-lo < MIN_OVERLAP:
                continue
            offsets = []
            for t in (lo, hi):
                fraction = (t-projected[0])/(projected[1]-projected[0])
                q = [c[k]+(d[k]-c[k])*fraction for k in (0, 1)]
                offsets.append(ux*(q[1]-a[1])-uy*(q[0]-a[0]))
            separation = max(map(abs, offsets))
            if separation > MAX_SEPARATION or (offsets[0]*offsets[1] < 0 and separation > 1e-6):
                continue
            overlaps.append({'first': [[a[0]+ux*t, a[1]+uy*t] for t in (lo, hi)],
                             'length': hi-lo, 'separation': separation})
    if not overlaps:
        return None
    separation = max(o['separation'] for o in overlaps)
    return {'wall_ids': [first['id'], second['id']], 'spans': overlaps,
            'overlap': sum(o['length'] for o in overlaps), 'separation': separation,
            'relation': 'coincident' if separation <= 1e-6 else 'parallel',
            'snapshots': [snapshot(first), snapshot(second)]}


def valid_reviews(level):
    validate_reviews(level)
    walls = {w['id']: w for w in level['walls'] if w['status'] != 'rejected'}
    valid = []
    for review in level.get('axis_reviews', []):
        ids = review['wall_ids']
        if all(i in walls for i in ids) and review['snapshots'] == [snapshot(walls[i]) for i in ids]:
            valid.append(review)
    return valid


def review_axes(level, *, approved_only=False):
    walls = [w for w in level['walls'] if w['status'] != 'rejected'
             and (not approved_only or w['status'] == 'approved')]
    boxes = sorted([(min(w['a'][0], w['b'][0]), max(w['a'][0], w['b'][0]),
                     min(w['a'][1], w['b'][1]), max(w['a'][1], w['b'][1]), w) for w in walls],
                   key=lambda entry: (entry[0], entry[4]['id']))
    decisions = {tuple(r['wall_ids']) for r in valid_reviews(level)}
    pairs = []
    for i, (_, right, top, bottom, first) in enumerate(boxes):
        for left, _, other_top, other_bottom, second in boxes[i+1:]:
            if left > right+MAX_SEPARATION:
                break
            if other_top > bottom+MAX_SEPARATION or top > other_bottom+MAX_SEPARATION:
                continue
            pair = close_axes(first, second)
            if pair:
                pair['resolved'] = pair['relation'] != 'coincident' and tuple(pair['wall_ids']) in decisions
                pairs.append(pair)
    return sorted(pairs, key=lambda p: (p['resolved'], -p['overlap'], p['wall_ids']))


def distinct_review(level, first_id, second_id, actor, note):
    if not isinstance(note, str) or not 1 <= len(note.strip()) <= 500:
        raise ValueError('Indiquer pourquoi il s’agit de deux murs distincts (500 caractères maximum)')
    walls = {w['id']: w for w in level['walls']}
    pair = close_axes(walls[first_id], walls[second_id])
    if not pair or pair['relation'] == 'coincident':
        raise ValueError('Deux axes superposés doivent être corrigés ; ils ne peuvent pas être confirmés distincts')
    return {'decision': 'distinct_walls', 'wall_ids': pair['wall_ids'],
            'snapshots': copy.deepcopy(pair['snapshots']), 'validated_by': actor, 'note': note.strip()}


def require_reviewed_axes(level):
    if any(not pair['resolved'] for pair in review_axes(level, approved_only=True)):
        raise ValueError('Doubles axes possibles parmi les murs validés : corriger ou confirmer deux murs distincts avant l’export')


def validate_reviews(level):
    reviews = level.get('axis_reviews', [])
    if not isinstance(reviews, list) or len(reviews) > 10000:
        raise ValueError('Contrôles des axes invalides')
    seen = set()
    for review in reviews:
        if not isinstance(review, dict) or set(review) != {'decision', 'wall_ids', 'snapshots', 'validated_by', 'note'}:
            raise ValueError('Contrôle des axes incomplet')
        ids = review['wall_ids']
        if (not isinstance(ids, list) or len(ids) != 2 or not all(isinstance(i, str) for i in ids)
                or ids != sorted(set(ids)) or tuple(ids) in seen):
            raise ValueError('Paire d’axes invalide')
        seen.add(tuple(ids))
        if (review['decision'] != 'distinct_walls' or not isinstance(review['validated_by'], str)
                or not review['validated_by'].strip() or not isinstance(review['note'], str)
                or not 1 <= len(review['note'].strip()) <= 500):
            raise ValueError('Décision humaine et motif requis')
        snaps = review['snapshots']
        if (not isinstance(snaps, list) or len(snaps) != 2
                or any(not isinstance(s, list) or len(s) != 5 or s[0] != i for s, i in zip(snaps, ids))):
            raise ValueError('Géométrie de contrôle absente')
