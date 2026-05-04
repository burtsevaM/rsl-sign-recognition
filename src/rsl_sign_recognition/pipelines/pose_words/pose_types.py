"""Pose runtime datatypes for the pose_words pipeline layer."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

ArrayF32 = np.ndarray

BODY_LANDMARK_COUNT = 33
HAND_LANDMARK_COUNT = 21
FACE_LANDMARK_COUNT = 468


def _as_float32_points(
    points: np.ndarray,
    *,
    expected_points: int | None = None,
) -> ArrayF32:
    arr = np.asarray(points, dtype=np.float32)
    if arr.ndim != 2 or arr.shape[1] != 3:
        raise ValueError(f"landmarks must have shape [N, 3], got {arr.shape}")
    if expected_points is not None and arr.shape[0] != expected_points:
        raise ValueError(f"expected {expected_points} landmarks, got {arr.shape[0]}")
    if not np.all(np.isfinite(arr)):
        raise ValueError("landmarks contain NaN/Inf values")
    return np.ascontiguousarray(arr, dtype=np.float32)


def _as_confidence(
    confidence: np.ndarray | None,
    *,
    expected_points: int,
) -> ArrayF32 | None:
    if confidence is None:
        return None

    arr = np.asarray(confidence, dtype=np.float32).reshape(-1)
    if arr.shape[0] != expected_points:
        raise ValueError(f"confidence must have shape [N], got {arr.shape}")
    if not np.all(np.isfinite(arr)):
        raise ValueError("confidence contains NaN/Inf values")
    return np.ascontiguousarray(arr, dtype=np.float32)


@dataclass(slots=True)
class PoseLandmarksGroup:
    """A single landmark group stored as finite float32 [N, 3] coordinates."""

    points: ArrayF32
    confidence: ArrayF32 | None = None

    def __post_init__(self) -> None:
        self.validate()

    def validate(self, *, expected_points: int | None = None) -> "PoseLandmarksGroup":
        self.points = _as_float32_points(
            self.points,
            expected_points=expected_points,
        )
        self.confidence = _as_confidence(
            self.confidence,
            expected_points=self.points.shape[0],
        )
        return self

    def copy(self) -> "PoseLandmarksGroup":
        confidence = None if self.confidence is None else self.confidence.copy()
        return PoseLandmarksGroup(points=self.points.copy(), confidence=confidence)

    def to_jsonable(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "points": self.points.astype(np.float32, copy=False).tolist(),
        }
        if self.confidence is not None:
            payload["confidence"] = self.confidence.astype(
                np.float32,
                copy=False,
            ).tolist()
        return payload

    def to_debug_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "shape": list(self.points.shape),
            "dtype": str(self.points.dtype),
            "has_confidence": self.confidence is not None,
        }
        if self.confidence is not None:
            payload["confidence_shape"] = list(self.confidence.shape)
        return payload


@dataclass(slots=True)
class PoseFrame:
    """A decoded pose frame with MediaPipe-compatible landmark groups."""

    timestamp: float
    body: PoseLandmarksGroup | None = None
    left_hand: PoseLandmarksGroup | None = None
    right_hand: PoseLandmarksGroup | None = None
    face: PoseLandmarksGroup | None = None
    meta: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.validate()

    def validate(self) -> "PoseFrame":
        try:
            timestamp = float(self.timestamp)
        except (TypeError, ValueError) as exc:
            raise ValueError("timestamp must be a finite float") from exc

        if not np.isfinite(timestamp):
            raise ValueError("timestamp must be a finite float")
        self.timestamp = timestamp

        if self.body is not None:
            self.body.validate(expected_points=BODY_LANDMARK_COUNT)
        if self.left_hand is not None:
            self.left_hand.validate(expected_points=HAND_LANDMARK_COUNT)
        if self.right_hand is not None:
            self.right_hand.validate(expected_points=HAND_LANDMARK_COUNT)
        if self.face is not None:
            self.face.validate(expected_points=FACE_LANDMARK_COUNT)

        self.meta = dict(self.meta)
        return self

    def copy(self) -> "PoseFrame":
        return PoseFrame(
            timestamp=float(self.timestamp),
            body=None if self.body is None else self.body.copy(),
            left_hand=None if self.left_hand is None else self.left_hand.copy(),
            right_hand=None if self.right_hand is None else self.right_hand.copy(),
            face=None if self.face is None else self.face.copy(),
            meta=dict(self.meta),
        )

    def to_jsonable(self) -> dict[str, Any]:
        return {
            "timestamp": float(self.timestamp),
            "body": None if self.body is None else self.body.to_jsonable(),
            "left_hand": (
                None if self.left_hand is None else self.left_hand.to_jsonable()
            ),
            "right_hand": (
                None if self.right_hand is None else self.right_hand.to_jsonable()
            ),
            "face": None if self.face is None else self.face.to_jsonable(),
            "meta": dict(self.meta),
        }

    def to_debug_dict(self) -> dict[str, Any]:
        return {
            "timestamp": float(self.timestamp),
            "body": None if self.body is None else self.body.to_debug_dict(),
            "left_hand": (
                None if self.left_hand is None else self.left_hand.to_debug_dict()
            ),
            "right_hand": (
                None if self.right_hand is None else self.right_hand.to_debug_dict()
            ),
            "face": None if self.face is None else self.face.to_debug_dict(),
            "meta": dict(self.meta),
        }


def validate_pose_frame(frame: PoseFrame) -> PoseFrame:
    if not isinstance(frame, PoseFrame):
        raise ValueError("frame must be PoseFrame")
    return frame.validate()


__all__ = [
    "ArrayF32",
    "BODY_LANDMARK_COUNT",
    "FACE_LANDMARK_COUNT",
    "HAND_LANDMARK_COUNT",
    "PoseFrame",
    "PoseLandmarksGroup",
    "validate_pose_frame",
]

