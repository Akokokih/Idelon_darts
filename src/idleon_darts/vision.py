"""Small calibrated image measurements. Optional vision dependencies only.

Scores are geometric/template quality measures, not probabilities of correctness.
All coordinates returned here are relative to the input image.
"""
from dataclasses import dataclass
import math
import cv2
import numpy as np
from .models import Rect


def crop(image, region: Rect):
    height, width = image.shape[:2]
    if not Rect(0, 0, width, height).contains(region):
        raise ValueError('Repere hors image')
    return image[region.top:region.top + region.height, region.left:region.left + region.width]


@dataclass(frozen=True)
class BladeLine:
    center: tuple[float, float]
    vector: tuple[float, float]
    angle: float
    ratio: float
    area: int


def find_blade(image, region: Rect, *, area_min=400, area_max=1400, ratio_min=15., length_min=50, length_max=180) -> BladeLine | None:
    patch = crop(image, region)
    neutral = ((patch.max(axis=2).astype('int16') - patch.min(axis=2) < 35)
               & (patch.min(axis=2) > 150)).astype('uint8')
    count, labels, stats, _ = cv2.connectedComponentsWithStats(neutral)
    candidates = []
    for label in range(1, count):
        area = int(stats[label, cv2.CC_STAT_AREA])
        if not area_min <= area <= area_max:
            continue
        yy, xx = np.where(labels == label)
        points = np.column_stack((xx + region.left, yy + region.top)).astype('float64')
        values, vectors = np.linalg.eigh(np.cov(points.T))
        ratio = float(values[-1] / max(float(values[0]), .001))
        vector = vectors[:, -1]
        if vector[0] < 0:
            vector = -vector
        angle = math.atan2(-float(vector[1]), float(vector[0]))
        length = float(np.ptp(points @ vector))
        if ratio < ratio_min or not length_min <= length <= length_max or not math.radians(-30) <= angle <= math.radians(80):
            continue
        candidates.append(BladeLine(tuple(points.mean(axis=0)), tuple(vector), angle, ratio, area))
    candidates.sort(key=lambda item: item.area, reverse=True)
    if not candidates or (len(candidates) > 1 and candidates[1].area > .7 * candidates[0].area):
        return None
    return candidates[0]


def fit_pivot(lines: list[BladeLine]):
    if len(lines) < 30:
        raise ValueError('Au moins 30 orientations detectees requises')
    angles = np.array([line.angle for line in lines])
    if np.ptp(angles) < math.radians(25):
        raise ValueError('Balayage angulaire insuffisant pour localiser le pivot')
    normals = np.array([[-line.vector[1], line.vector[0]] for line in lines])
    values = np.array([np.dot(normal, line.center) for normal, line in zip(normals, lines)])
    pivot, _, rank, _ = np.linalg.lstsq(normals, values, rcond=None)
    errors = np.abs(normals @ pivot - values)
    p95 = float(np.quantile(errors, .95))
    if rank != 2 or p95 > 8:
        raise ValueError('Pivot instable : ajustement des orientations refuse')
    return tuple(float(x) for x in pivot), dict(detected=len(lines),
        angle_min_degrees=float(np.degrees(angles.min())), angle_max_degrees=float(np.degrees(angles.max())),
        line_distance_p95_px=p95, line_distance_max_px=float(errors.max()))


def find_red_target(image, region: Rect, *, expected_size=None):
    patch = crop(image, region)
    blue, green, red = [patch[:, :, i].astype('int16') for i in range(3)]
    mask = ((red > 180) & (red > 1.9 * green) & (green < 120) & (blue < 100)).astype('uint8')
    count, _, stats, _ = cv2.connectedComponentsWithStats(mask)
    candidates = []
    for x, y, width, height, area in stats[1:]:
        if area < 300 or not 15 <= width <= 150 or not 15 <= height <= 200:
            continue
        fill = float(area / (width * height))
        if fill < .55:
            continue
        if expected_size is not None and any(not .9 * expected <= measured <= 1.1 * expected
                                            for measured, expected in zip((width, height), expected_size)):
            continue
        candidates.append((Rect(int(x + region.left), int(y + region.top), int(width), int(height)), fill))
    return candidates[0] if len(candidates) == 1 else None


def template_score(image, region: Rect, reference) -> float:
    patch = crop(image, region)
    if patch.shape != reference.shape:
        raise ValueError('Dimensions du modele visuel incoherentes')
    score = float(cv2.matchTemplate(patch, reference, cv2.TM_SQDIFF_NORMED)[0, 0])
    return max(0., min(1., 1. - score)) if math.isfinite(score) else 0.


def locate_template(image, reference, *, threshold):
    """Locate a translated anchor; exclude distant, similarly good matches."""
    scores = cv2.matchTemplate(image, reference, cv2.TM_SQDIFF_NORMED)
    minimum, _, location, _ = cv2.minMaxLoc(scores)
    quality = 1. - float(minimum)
    if quality < threshold:
        return None
    x, y = location
    # Nearby pixel aliases describe the same anchor, not a second object.
    scores[max(0, y - 20):y + 21, max(0, x - 20):x + 21] = 1.
    second = 1. - float(scores.min())
    if second >= threshold:
        return None
    return (x, y), quality
