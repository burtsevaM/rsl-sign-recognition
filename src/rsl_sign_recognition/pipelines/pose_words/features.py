"""Pose normalization and feature composition for pose_words."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Sequence

import numpy as np

from rsl_sign_recognition.pipelines.pose_words.pose_types import (
    PoseFrame,
    PoseLandmarksGroup,
    validate_pose_frame,
)

POSE_LEFT_SHOULDER = 11
POSE_RIGHT_SHOULDER = 12
POSE_LEFT_HIP = 23
POSE_RIGHT_HIP = 24
POSE_LEFT_KNEE = 25
POSE_RIGHT_KNEE = 26
POSE_LEFT_ANKLE = 27
POSE_RIGHT_ANKLE = 28
POSE_LEFT_HEEL = 29
POSE_RIGHT_HEEL = 30
POSE_LEFT_FOOT_INDEX = 31
POSE_RIGHT_FOOT_INDEX = 32

HAND_WRIST = 0
HAND_INDEX_MCP = 5
HAND_MIDDLE_MCP = 9
HAND_PINKY_MCP = 17

POSE_LEG_INDICES: tuple[int, ...] = (
    POSE_LEFT_HIP,
    POSE_RIGHT_HIP,
    POSE_LEFT_KNEE,
    POSE_RIGHT_KNEE,
    POSE_LEFT_ANKLE,
    POSE_RIGHT_ANKLE,
    POSE_LEFT_HEEL,
    POSE_RIGHT_HEEL,
    POSE_LEFT_FOOT_INDEX,
    POSE_RIGHT_FOOT_INDEX,
)

DEFAULT_UPPER_BODY_INDICES: tuple[int, ...] = (
    0,
    9,
    10,
    POSE_LEFT_SHOULDER,
    POSE_RIGHT_SHOULDER,
    13,
    14,
    15,
    16,
    POSE_LEFT_HIP,
    POSE_RIGHT_HIP,
)

DEFAULT_FEATURE_POINT_COUNT = len(DEFAULT_UPPER_BODY_INDICES) + 21 + 21
DEFAULT_FEATURE_DIM = DEFAULT_FEATURE_POINT_COUNT * 3


@dataclass(slots=True)
class ShoulderNormInfo:
    normalized: bool
    center: np.ndarray
    scale: float
    valid_frames: int
    reason: str = ""

    def to_debug_dict(self) -> dict[str, object]:
        return {
            "normalized": bool(self.normalized),
            "center": np.asarray(self.center, dtype=np.float32).reshape(3).tolist(),
            "scale": float(self.scale),
            "valid_frames": int(self.valid_frames),
            "reason": str(self.reason),
        }


def _copy_group(group: PoseLandmarksGroup | None) -> PoseLandmarksGroup | None:
    return None if group is None else group.copy()


def _copy_frame(frame: PoseFrame) -> PoseFrame:
    return PoseFrame(
        timestamp=float(frame.timestamp),
        body=_copy_group(frame.body),
        left_hand=_copy_group(frame.left_hand),
        right_hand=_copy_group(frame.right_hand),
        face=_copy_group(frame.face),
        meta=dict(frame.meta),
    )


def _norm_info(
    normalized: bool,
    *,
    scale: float = 1.0,
    valid_frames: int = 0,
    reason: str = "",
    center: np.ndarray | None = None,
) -> ShoulderNormInfo:
    return ShoulderNormInfo(
        normalized=bool(normalized),
        center=(
            np.zeros(3, dtype=np.float32)
            if center is None
            else np.asarray(center, dtype=np.float32).reshape(3)
        ),
        scale=float(scale),
        valid_frames=int(valid_frames),
        reason=str(reason),
    )


def _iter_shoulder_stats(
    frames: Sequence[PoseFrame],
    *,
    min_shoulder_confidence: float,
) -> Iterable[tuple[np.ndarray, float]]:
    for frame in frames:
        validate_pose_frame(frame)
        body = frame.body
        if body is None:
            continue

        left = body.points[POSE_LEFT_SHOULDER]
        right = body.points[POSE_RIGHT_SHOULDER]
        if body.confidence is not None:
            left_confidence = float(body.confidence[POSE_LEFT_SHOULDER])
            right_confidence = float(body.confidence[POSE_RIGHT_SHOULDER])
            if (
                left_confidence < min_shoulder_confidence
                or right_confidence < min_shoulder_confidence
            ):
                continue

        midpoint = (left + right) * 0.5
        distance = float(np.linalg.norm(left - right))
        if distance <= 0.0:
            continue
        yield midpoint.astype(np.float32), distance


def shoulder_normalize(
    sequence: Sequence[PoseFrame] | np.ndarray,
    *,
    window: int | None = None,
    safe_mode: bool = True,
    min_shoulder_confidence: float = 0.0,
    eps: float = 1e-6,
) -> tuple[Sequence[PoseFrame] | np.ndarray, ShoulderNormInfo]:
    """Normalize landmarks by mean shoulder midpoint and shoulder distance."""

    if isinstance(sequence, np.ndarray):
        points = np.asarray(sequence, dtype=np.float32)
        squeeze_back = False
        if points.ndim == 2 and points.shape[1] == 3:
            points = points[None, ...]
            squeeze_back = True
        if points.ndim != 3 or points.shape[2] != 3:
            raise ValueError("numpy input must have shape [T, N, 3] or [N, 3]")

        output = points.copy()
        if output.shape[1] <= max(POSE_LEFT_SHOULDER, POSE_RIGHT_SHOULDER):
            info = _norm_info(False, reason="body_has_no_shoulders")
            if safe_mode:
                return (output[0] if squeeze_back else output), info
            raise ValueError("cannot normalize: body landmarks do not include shoulders")

        stats_points = output
        if window is not None:
            stats_points = stats_points[-max(1, int(window)) :]

        left = stats_points[:, POSE_LEFT_SHOULDER, :]
        right = stats_points[:, POSE_RIGHT_SHOULDER, :]
        valid = np.isfinite(left).all(axis=1) & np.isfinite(right).all(axis=1)
        if not np.any(valid):
            info = _norm_info(False, reason="no_valid_shoulders")
            if safe_mode:
                return (output[0] if squeeze_back else output), info
            raise ValueError("cannot normalize: no valid shoulders")

        midpoints = (left[valid] + right[valid]) * 0.5
        distances = np.linalg.norm(left[valid] - right[valid], axis=1)
        mean_distance = float(np.mean(distances)) if distances.size else 0.0
        if mean_distance <= eps:
            info = _norm_info(
                False,
                valid_frames=int(valid.sum()),
                reason="shoulder_distance_too_small",
            )
            if safe_mode:
                return (output[0] if squeeze_back else output), info
            raise ValueError("cannot normalize: shoulder distance too small")

        center = np.mean(midpoints, axis=0).astype(np.float32)
        scale = float(1.0 / mean_distance)
        output = ((output - center.reshape(1, 1, 3)) * scale).astype(np.float32)
        info = _norm_info(
            True,
            center=center,
            scale=scale,
            valid_frames=int(valid.sum()),
        )
        return (output[0] if squeeze_back else output), info

    frames = [_copy_frame(frame) for frame in sequence]
    if not frames:
        return frames, _norm_info(False, reason="empty_sequence")

    frames_for_stats = frames
    if window is not None:
        frames_for_stats = frames[-max(1, int(window)) :]

    stats = list(
        _iter_shoulder_stats(
            frames_for_stats,
            min_shoulder_confidence=float(min_shoulder_confidence),
        )
    )
    if not stats:
        info = _norm_info(False, reason="no_valid_shoulders")
        if safe_mode:
            return frames, info
        raise ValueError("cannot normalize: no reliable shoulders in sequence")

    midpoints = np.stack([item[0] for item in stats], axis=0)
    distances = np.asarray([item[1] for item in stats], dtype=np.float32)
    mean_distance = float(np.mean(distances))
    if mean_distance <= eps:
        info = _norm_info(
            False,
            valid_frames=len(stats),
            reason="shoulder_distance_too_small",
        )
        if safe_mode:
            return frames, info
        raise ValueError("cannot normalize: shoulder distance too small")

    center = np.mean(midpoints, axis=0).astype(np.float32)
    scale = float(1.0 / mean_distance)

    for frame in frames:
        for group_name in ("body", "left_hand", "right_hand", "face"):
            group = getattr(frame, group_name)
            if group is None:
                continue
            group.points = ((group.points - center.reshape(1, 3)) * scale).astype(
                np.float32
            )

    return frames, _norm_info(
        True,
        center=center,
        scale=scale,
        valid_frames=len(stats),
    )


def hide_legs(sequence: Sequence[PoseFrame] | np.ndarray) -> Sequence[PoseFrame] | np.ndarray:
    if isinstance(sequence, np.ndarray):
        points = np.asarray(sequence, dtype=np.float32)
        squeeze_back = False
        if points.ndim == 2 and points.shape[1] == 3:
            points = points[None, ...]
            squeeze_back = True
        if points.ndim != 3 or points.shape[2] != 3:
            raise ValueError("numpy input must have shape [T, N, 3] or [N, 3]")

        output = points.copy()
        valid_indices = [idx for idx in POSE_LEG_INDICES if idx < output.shape[1]]
        if valid_indices:
            output[:, valid_indices, :] = 0.0
        return output[0] if squeeze_back else output

    frames = [_copy_frame(frame) for frame in sequence]
    for frame in frames:
        body = frame.body
        if body is None:
            continue
        for idx in POSE_LEG_INDICES:
            body.points[idx, :] = 0.0
            if body.confidence is not None:
                body.confidence[idx] = 0.0
    return frames


def _skew(vector: np.ndarray) -> np.ndarray:
    return np.array(
        [
            [0.0, -vector[2], vector[1]],
            [vector[2], 0.0, -vector[0]],
            [-vector[1], vector[0], 0.0],
        ],
        dtype=np.float32,
    )


def _rotation_matrix_from_vectors(
    source: np.ndarray,
    target: np.ndarray,
    eps: float = 1e-6,
) -> np.ndarray:
    source = np.asarray(source, dtype=np.float32)
    target = np.asarray(target, dtype=np.float32)
    source_norm = float(np.linalg.norm(source))
    target_norm = float(np.linalg.norm(target))
    if source_norm <= eps or target_norm <= eps:
        return np.eye(3, dtype=np.float32)

    source = source / source_norm
    target = target / target_norm
    cross = np.cross(source, target)
    dot = float(np.dot(source, target))
    cross_norm = float(np.linalg.norm(cross))

    if cross_norm <= eps:
        if dot > 0.0:
            return np.eye(3, dtype=np.float32)

        axis = np.array([1.0, 0.0, 0.0], dtype=np.float32)
        if abs(float(np.dot(axis, source))) > 0.9:
            axis = np.array([0.0, 1.0, 0.0], dtype=np.float32)
        axis = axis - float(np.dot(axis, source)) * source
        axis_norm = float(np.linalg.norm(axis))
        if axis_norm <= eps:
            return np.eye(3, dtype=np.float32)
        axis = axis / axis_norm
        skew = _skew(axis)
        return (np.eye(3, dtype=np.float32) + 2.0 * (skew @ skew)).astype(
            np.float32
        )

    skew = _skew(cross)
    rotation = (
        np.eye(3, dtype=np.float32)
        + skew
        + (skew @ skew) * ((1.0 - dot) / (cross_norm * cross_norm))
    )
    return rotation.astype(np.float32)


def _rotation_z(theta: float) -> np.ndarray:
    cosine = float(np.cos(theta))
    sine = float(np.sin(theta))
    return np.array(
        [
            [cosine, -sine, 0.0],
            [sine, cosine, 0.0],
            [0.0, 0.0, 1.0],
        ],
        dtype=np.float32,
    )


def hand_normalize_3d(hand_21x3: np.ndarray, *, eps: float = 1e-6) -> np.ndarray:
    hand = np.asarray(hand_21x3, dtype=np.float32)
    if hand.shape != (21, 3):
        raise ValueError(f"hand landmarks must have shape [21, 3], got {hand.shape}")
    if not np.all(np.isfinite(hand)):
        hand = np.nan_to_num(
            hand,
            nan=0.0,
            posinf=0.0,
            neginf=0.0,
        ).astype(np.float32)

    wrist = hand[HAND_WRIST].copy()
    centered = hand - wrist.reshape(1, 3)

    index_vector = centered[HAND_INDEX_MCP]
    pinky_vector = centered[HAND_PINKY_MCP]
    palm_normal = np.cross(index_vector, pinky_vector)

    if float(np.linalg.norm(palm_normal)) > eps:
        rotation = _rotation_matrix_from_vectors(
            palm_normal,
            np.array([0.0, 0.0, 1.0], dtype=np.float32),
            eps=eps,
        )
        centered = (rotation @ centered.T).T.astype(np.float32)

    middle_vector = centered[HAND_MIDDLE_MCP]
    middle_xy = np.array([middle_vector[0], middle_vector[1]], dtype=np.float32)
    if float(np.linalg.norm(middle_xy)) > eps:
        theta = float(np.arctan2(middle_vector[0], middle_vector[1]))
        centered = (_rotation_z(theta) @ centered.T).T.astype(np.float32)

    axis_length = float(np.linalg.norm(centered[HAND_MIDDLE_MCP]))
    if axis_length > eps:
        centered = centered * float(1.0 / axis_length)

    if not np.all(np.isfinite(centered)):
        centered = np.nan_to_num(
            centered,
            nan=0.0,
            posinf=0.0,
            neginf=0.0,
        ).astype(np.float32)

    centered[HAND_WRIST] = 0.0
    return centered.astype(np.float32)


def feature_point_count(
    *,
    upper_body_indices: Sequence[int] = DEFAULT_UPPER_BODY_INDICES,
) -> int:
    return len(tuple(upper_body_indices)) + 21 + 21


def feature_dim(
    *,
    upper_body_indices: Sequence[int] = DEFAULT_UPPER_BODY_INDICES,
    include_velocity: bool = False,
) -> int:
    base_dim = feature_point_count(upper_body_indices=upper_body_indices) * 3
    return base_dim * (2 if include_velocity else 1)


def _extract_body_subset(
    frame: PoseFrame,
    *,
    upper_body_indices: Sequence[int],
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    count = len(tuple(upper_body_indices))
    body = np.zeros((count, 3), dtype=np.float32)
    mask = np.zeros((count,), dtype=np.float32)
    confidence = np.zeros((count,), dtype=np.float32)

    if frame.body is None:
        return body, mask, confidence

    for output_idx, landmark_idx in enumerate(upper_body_indices):
        if landmark_idx < 0 or landmark_idx >= frame.body.points.shape[0]:
            continue
        body[output_idx] = frame.body.points[landmark_idx].astype(np.float32)
        mask[output_idx] = 1.0
        if frame.body.confidence is None:
            confidence[output_idx] = 1.0
        else:
            confidence[output_idx] = float(frame.body.confidence[landmark_idx])
    return body, mask, confidence


def _extract_hand_group(
    group: PoseLandmarksGroup | None,
    *,
    canonical_3d: bool,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    points = np.zeros((21, 3), dtype=np.float32)
    mask = np.zeros((21,), dtype=np.float32)
    confidence = np.zeros((21,), dtype=np.float32)

    if group is None:
        return points, mask, confidence

    hand_points = group.points.astype(np.float32, copy=True)
    if canonical_3d:
        hand_points = hand_normalize_3d(hand_points)

    points[:] = hand_points
    mask[:] = 1.0
    if group.confidence is None:
        confidence[:] = 1.0
    else:
        confidence[:] = group.confidence.astype(np.float32)
    return points, mask, confidence


def _feature_layout(
    upper_body_indices: Sequence[int],
    *,
    include_velocity: bool = False,
) -> dict[str, object]:
    return {
        "body_indices": list(upper_body_indices),
        "body_points": len(tuple(upper_body_indices)),
        "left_hand_points": 21,
        "right_hand_points": 21,
        "point_count": feature_point_count(upper_body_indices=upper_body_indices),
        "feature_dim": feature_dim(
            upper_body_indices=upper_body_indices,
            include_velocity=include_velocity,
        ),
        "includes_face": False,
        "include_velocity": bool(include_velocity),
    }


def _finalize_feature(feature: np.ndarray) -> np.ndarray:
    feature = np.asarray(feature, dtype=np.float32).reshape(-1)
    if not np.all(np.isfinite(feature)):
        raise ValueError("feature vector contains NaN/Inf values")
    return np.ascontiguousarray(feature, dtype=np.float32)


def compose_features(
    frame: PoseFrame,
    *,
    upper_body_indices: Sequence[int] = DEFAULT_UPPER_BODY_INDICES,
    apply_shoulder_norm: bool = True,
    hide_legs_before_body: bool = True,
    canonical_hands_3d: bool = True,
) -> tuple[np.ndarray, dict[str, Any]]:
    """Compose one deterministic feature vector without masks or confidences."""

    validate_pose_frame(frame)
    frames: list[PoseFrame] = [_copy_frame(frame)]
    norm_info = _norm_info(False, reason="not_requested")

    if apply_shoulder_norm:
        normalized, norm_info = shoulder_normalize(frames, safe_mode=True)
        frames = list(normalized)

    if hide_legs_before_body:
        frames = list(hide_legs(frames))

    body_points, body_mask, body_confidence = _extract_body_subset(
        frames[0],
        upper_body_indices=upper_body_indices,
    )
    left_points, left_mask, left_confidence = _extract_hand_group(
        frames[0].left_hand,
        canonical_3d=canonical_hands_3d,
    )
    right_points, right_mask, right_confidence = _extract_hand_group(
        frames[0].right_hand,
        canonical_3d=canonical_hands_3d,
    )

    feature = _finalize_feature(
        np.concatenate(
            [
                body_points.reshape(-1),
                left_points.reshape(-1),
                right_points.reshape(-1),
            ],
            axis=0,
        )
    )

    point_mask = np.concatenate([body_mask, left_mask, right_mask], axis=0).astype(
        np.float32
    )
    point_confidence = np.concatenate(
        [body_confidence, left_confidence, right_confidence],
        axis=0,
    ).astype(np.float32)
    if not np.all(np.isfinite(point_mask)) or not np.all(np.isfinite(point_confidence)):
        raise ValueError("feature aux contains NaN/Inf values")

    aux = {
        "point_mask": point_mask,
        "point_confidence": point_confidence,
        "normalization": norm_info.to_debug_dict(),
        "feature_layout": _feature_layout(upper_body_indices),
    }
    return feature, aux


def _empty_sequence_result(
    upper_body_indices: Sequence[int],
    *,
    include_velocity: bool,
) -> tuple[np.ndarray, dict[str, Any]]:
    point_count = feature_point_count(upper_body_indices=upper_body_indices)
    return np.zeros(
        (
            0,
            feature_dim(
                upper_body_indices=upper_body_indices,
                include_velocity=include_velocity,
            ),
        ),
        dtype=np.float32,
    ), {
        "point_mask": np.zeros((0, point_count), dtype=np.float32),
        "point_confidence": np.zeros((0, point_count), dtype=np.float32),
        "normalization": _norm_info(False, reason="empty_sequence").to_debug_dict(),
        "feature_layout": _feature_layout(
            upper_body_indices,
            include_velocity=include_velocity,
        ),
    }


def compose_features_sequence(
    sequence: Sequence[PoseFrame],
    *,
    upper_body_indices: Sequence[int] = DEFAULT_UPPER_BODY_INDICES,
    apply_shoulder_norm: bool = True,
    shoulder_window: int | None = None,
    hide_legs_before_body: bool = True,
    canonical_hands_3d: bool = True,
    include_velocity: bool = False,
) -> tuple[np.ndarray, dict[str, Any]]:
    frames = [_copy_frame(frame) for frame in sequence]
    if not frames:
        return _empty_sequence_result(
            upper_body_indices,
            include_velocity=include_velocity,
        )

    norm_info = _norm_info(False, reason="not_requested")
    if apply_shoulder_norm:
        normalized, norm_info = shoulder_normalize(
            frames,
            safe_mode=True,
            window=shoulder_window,
        )
        frames = list(normalized)

    if hide_legs_before_body:
        frames = list(hide_legs(frames))

    features: list[np.ndarray] = []
    masks: list[np.ndarray] = []
    confidences: list[np.ndarray] = []

    for frame in frames:
        feature, aux = compose_features(
            frame,
            upper_body_indices=upper_body_indices,
            apply_shoulder_norm=False,
            hide_legs_before_body=False,
            canonical_hands_3d=canonical_hands_3d,
        )
        features.append(feature)
        masks.append(np.asarray(aux["point_mask"], dtype=np.float32))
        confidences.append(np.asarray(aux["point_confidence"], dtype=np.float32))

    feature_matrix = np.stack(features, axis=0).astype(np.float32)
    if include_velocity:
        velocity = np.zeros_like(feature_matrix)
        if feature_matrix.shape[0] > 1:
            velocity[1:] = feature_matrix[1:] - feature_matrix[:-1]
        feature_matrix = np.concatenate([feature_matrix, velocity], axis=1)

    if not np.all(np.isfinite(feature_matrix)):
        raise ValueError("feature sequence contains NaN/Inf values")

    return np.ascontiguousarray(feature_matrix, dtype=np.float32), {
        "point_mask": np.stack(masks, axis=0).astype(np.float32),
        "point_confidence": np.stack(confidences, axis=0).astype(np.float32),
        "normalization": norm_info.to_debug_dict(),
        "feature_layout": _feature_layout(
            upper_body_indices,
            include_velocity=include_velocity,
        ),
    }


__all__ = [
    "DEFAULT_FEATURE_DIM",
    "DEFAULT_FEATURE_POINT_COUNT",
    "DEFAULT_UPPER_BODY_INDICES",
    "HAND_INDEX_MCP",
    "HAND_MIDDLE_MCP",
    "HAND_PINKY_MCP",
    "HAND_WRIST",
    "POSE_LEFT_SHOULDER",
    "POSE_LEG_INDICES",
    "POSE_RIGHT_SHOULDER",
    "ShoulderNormInfo",
    "compose_features",
    "compose_features_sequence",
    "feature_dim",
    "feature_point_count",
    "hand_normalize_3d",
    "hide_legs",
    "shoulder_normalize",
]

