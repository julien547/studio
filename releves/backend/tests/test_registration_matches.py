from types import SimpleNamespace

import numpy as np
import pytest

from doemo_releves import registration


def test_repeated_features_cannot_all_match_one_target_corner(monkeypatch):
    # Multiple descriptors at the same target point made real repetitive plans
    # appear to have many RANSAC inliers despite a collapsing transformation.
    source = [SimpleNamespace(pt=(float(i*10), float(i*i))) for i in range(12)]
    target = [SimpleNamespace(pt=(20., 20.)) for _ in range(12)]
    keypoints = iter([source, target])
    detector = SimpleNamespace(detectAndCompute=lambda *_: (next(keypoints), np.ones((12,128), np.float32)))
    pairs = [[SimpleNamespace(queryIdx=i, trainIdx=i, distance=1.),
              SimpleNamespace(queryIdx=i, trainIdx=(i+1)%12, distance=10.)] for i in range(12)]
    monkeypatch.setattr(registration.cv2, "SIFT_create", lambda **_: detector)
    monkeypatch.setattr(registration.cv2, "BFMatcher", lambda: SimpleNamespace(knnMatch=lambda *a, **kw: pairs))
    with pytest.raises(ValueError, match="Correspondances insuffisantes"):
        registration.automatic(np.zeros((150,150,3), np.uint8), np.zeros((150,150,3), np.uint8))
