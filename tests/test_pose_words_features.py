from __future__ import annotations

import numpy as np

from rsl_sign_recognition.pipelines.pose_words.features import (
    DEFAULT_FEATURE_DIM,
    DEFAULT_FEATURE_POINT_COUNT,
    HAND_MIDDLE_MCP,
    HAND_WRIST,
    POSE_LEFT_ANKLE,
    POSE_LEFT_SHOULDER,
    POSE_RIGHT_SHOULDER,
    compose_features,
    compose_features_sequence,
    hand_normalize_3d,
    hide_legs,
    shoulder_normalize,
)
from rsl_sign_recognition.pipelines.pose_words.pose_types import (
    BODY_LANDMARK_COUNT,
    HAND_LANDMARK_COUNT,
    PoseFrame,
    PoseLandmarksGroup,
)


def _synthetic_hand(offset: float = 0.0) -> np.ndarray:
    hand = np.zeros((HAND_LANDMARK_COUNT, 3), dtype=np.float32)
    hand[0] = [offset, 0.0, 0.0]
    hand[5] = [offset + 0.35, 0.20, 0.04]
    hand[9] = [offset, 0.65, 0.03]
    hand[13] = [offset - 0.28, 0.52, 0.01]
    hand[17] = [offset - 0.45, 0.18, -0.02]
    for idx in range(HAND_LANDMARK_COUNT):
        if idx != 0 and np.allclose(hand[idx], 0.0):
            hand[idx] = [
                offset + 0.02 * ((idx % 4) - 1.5),
                0.12 + 0.03 * idx,
                0.01 * ((idx % 3) - 1.0),
            ]
    return hand


def _pose_frame(*, timestamp: float = 0.0, offset: float = 0.0) -> PoseFrame:
    body = np.zeros((BODY_LANDMARK_COUNT, 3), dtype=np.float32)
    for idx in range(BODY_LANDMARK_COUNT):
        body[idx] = [offset + idx * 0.01, idx * 0.005, idx * 0.002]
    body[POSE_LEFT_SHOULDER] = [offset - 0.4, 0.2, 0.0]
    body[POSE_RIGHT_SHOULDER] = [offset + 0.4, 0.2, 0.0]

    return PoseFrame(
        timestamp=timestamp,
        body=PoseLandmarksGroup(
            points=body,
            confidence=np.ones((BODY_LANDMARK_COUNT,), dtype=np.float32),
        ),
        left_hand=PoseLandmarksGroup(points=_synthetic_hand(offset=offset)),
        right_hand=PoseLandmarksGroup(points=_synthetic_hand(offset=offset + 0.2)),
    )


def test_shoulder_normalize_safe_fallback_without_shoulders() -> None:
    normalized, info = shoulder_normalize([PoseFrame(timestamp=0.0)], safe_mode=True)

    assert len(normalized) == 1
    assert info.normalized is False
    assert info.reason == "no_valid_shoulders"
    assert info.scale == 1.0
    assert np.allclose(info.center, np.zeros(3, dtype=np.float32))


def test_hand_normalize_3d_returns_finite_float32_and_zero_wrist() -> None:
    normalized = hand_normalize_3d(_synthetic_hand(offset=2.0))

    assert normalized.dtype == np.float32
    assert normalized.shape == (HAND_LANDMARK_COUNT, 3)
    assert np.all(np.isfinite(normalized))
    assert np.allclose(normalized[HAND_WRIST], np.zeros(3, dtype=np.float32))
    assert np.isclose(float(np.linalg.norm(normalized[HAND_MIDDLE_MCP])), 1.0)


def test_hide_legs_zeroes_pose_leg_landmarks() -> None:
    frame = _pose_frame()
    hidden = hide_legs([frame])

    assert hidden[0].body is not None
    assert np.allclose(hidden[0].body.points[POSE_LEFT_ANKLE], 0.0)


def test_compose_features_returns_expected_shape_dtype_and_aux() -> None:
    feature, aux = compose_features(_pose_frame())

    assert feature.shape == (DEFAULT_FEATURE_DIM,)
    assert feature.dtype == np.float32
    assert np.all(np.isfinite(feature))
    assert aux["point_mask"].shape == (DEFAULT_FEATURE_POINT_COUNT,)
    assert aux["point_confidence"].shape == (DEFAULT_FEATURE_POINT_COUNT,)
    assert aux["feature_layout"]["includes_face"] is False
    assert aux["feature_layout"]["feature_dim"] == DEFAULT_FEATURE_DIM


def test_compose_features_sequence_handles_empty_sequence_with_stable_shape() -> None:
    features, aux = compose_features_sequence([])

    assert features.shape == (0, DEFAULT_FEATURE_DIM)
    assert features.dtype == np.float32
    assert aux["point_mask"].shape == (0, DEFAULT_FEATURE_POINT_COUNT)
    assert aux["point_confidence"].shape == (0, DEFAULT_FEATURE_POINT_COUNT)
    assert aux["normalization"]["reason"] == "empty_sequence"


def test_compose_features_sequence_velocity_doubles_feature_dimension() -> None:
    frames = [
        _pose_frame(timestamp=0.0, offset=0.0),
        _pose_frame(timestamp=1.0, offset=0.1),
    ]

    base_features, _ = compose_features_sequence(frames, include_velocity=False)
    velocity_features, aux = compose_features_sequence(frames, include_velocity=True)

    assert base_features.shape == (2, DEFAULT_FEATURE_DIM)
    assert velocity_features.shape == (2, DEFAULT_FEATURE_DIM * 2)
    assert aux["feature_layout"]["feature_dim"] == DEFAULT_FEATURE_DIM * 2
    assert np.allclose(velocity_features[0, DEFAULT_FEATURE_DIM:], 0.0)
    assert np.allclose(
        velocity_features[1, DEFAULT_FEATURE_DIM:],
        base_features[1] - base_features[0],
    )

