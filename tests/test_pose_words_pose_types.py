from __future__ import annotations

import numpy as np
import pytest

from rsl_sign_recognition.pipelines.pose_words.pose_types import (
    BODY_LANDMARK_COUNT,
    FACE_LANDMARK_COUNT,
    HAND_LANDMARK_COUNT,
    PoseFrame,
    PoseLandmarksGroup,
    validate_pose_frame,
)


def test_pose_frame_accepts_expected_landmark_shapes_and_exports_jsonable() -> None:
    frame = PoseFrame(
        timestamp=1.25,
        body=PoseLandmarksGroup(
            points=np.zeros((BODY_LANDMARK_COUNT, 3), dtype=np.float64),
            confidence=np.ones((BODY_LANDMARK_COUNT,), dtype=np.float64),
        ),
        left_hand=PoseLandmarksGroup(
            points=np.zeros((HAND_LANDMARK_COUNT, 3), dtype=np.float32),
        ),
        right_hand=PoseLandmarksGroup(
            points=np.zeros((HAND_LANDMARK_COUNT, 3), dtype=np.float32),
        ),
        face=PoseLandmarksGroup(
            points=np.zeros((FACE_LANDMARK_COUNT, 3), dtype=np.float32),
        ),
        meta={"source": "test"},
    )

    assert validate_pose_frame(frame) is frame
    assert frame.body is not None
    assert frame.body.points.dtype == np.float32
    assert frame.body.confidence is not None
    assert frame.body.confidence.dtype == np.float32

    payload = frame.to_jsonable()
    assert payload["timestamp"] == 1.25
    assert payload["meta"] == {"source": "test"}
    assert len(payload["body"]["points"]) == BODY_LANDMARK_COUNT
    assert len(payload["left_hand"]["points"]) == HAND_LANDMARK_COUNT
    assert len(payload["face"]["points"]) == FACE_LANDMARK_COUNT


@pytest.mark.parametrize(
    ("field_name", "points", "expected"),
    [
        ("body", np.zeros((BODY_LANDMARK_COUNT - 1, 3), dtype=np.float32), 33),
        ("left_hand", np.zeros((HAND_LANDMARK_COUNT - 1, 3), dtype=np.float32), 21),
        ("right_hand", np.zeros((HAND_LANDMARK_COUNT + 1, 3), dtype=np.float32), 21),
        ("face", np.zeros((FACE_LANDMARK_COUNT - 1, 3), dtype=np.float32), 468),
    ],
)
def test_pose_frame_rejects_invalid_landmark_counts(
    field_name: str,
    points: np.ndarray,
    expected: int,
) -> None:
    with pytest.raises(ValueError, match=f"expected {expected} landmarks"):
        PoseFrame(
            timestamp=0.0,
            **{field_name: PoseLandmarksGroup(points=points)},
        )


def test_pose_group_rejects_invalid_coordinate_shape() -> None:
    with pytest.raises(ValueError, match=r"shape \[N, 3\]"):
        PoseLandmarksGroup(points=np.zeros((21, 2), dtype=np.float32))


def test_pose_group_rejects_nan_and_inf_values() -> None:
    points = np.zeros((HAND_LANDMARK_COUNT, 3), dtype=np.float32)
    points[0, 0] = np.nan
    with pytest.raises(ValueError, match="NaN/Inf"):
        PoseLandmarksGroup(points=points)

    confidence = np.ones((HAND_LANDMARK_COUNT,), dtype=np.float32)
    confidence[0] = np.inf
    with pytest.raises(ValueError, match="confidence contains NaN/Inf"):
        PoseLandmarksGroup(
            points=np.zeros((HAND_LANDMARK_COUNT, 3), dtype=np.float32),
            confidence=confidence,
        )


def test_pose_frame_rejects_non_finite_timestamp() -> None:
    with pytest.raises(ValueError, match="timestamp must be a finite float"):
        PoseFrame(timestamp=float("inf"))


def test_validate_pose_frame_catches_mutated_invalid_group_shape() -> None:
    frame = PoseFrame(
        timestamp=0.0,
        body=PoseLandmarksGroup(
            points=np.zeros((BODY_LANDMARK_COUNT, 3), dtype=np.float32),
        ),
    )
    assert frame.body is not None
    frame.body.points = np.zeros((BODY_LANDMARK_COUNT, 2), dtype=np.float32)

    with pytest.raises(ValueError, match=r"shape \[N, 3\]"):
        validate_pose_frame(frame)

