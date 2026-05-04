"""MediaPipe pose extraction boundary for decoded RGB frames."""

from __future__ import annotations

from dataclasses import dataclass, replace
import importlib
import time
from typing import Any

import numpy as np

from rsl_sign_recognition.pipelines.pose_words.pose_types import (
    PoseFrame,
    PoseLandmarksGroup,
)


def validate_rgb_frame(rgb_frame: np.ndarray) -> np.ndarray:
    """Validate decoded RGB input and return a contiguous uint8 view/copy."""

    if not isinstance(rgb_frame, np.ndarray):
        raise ValueError("rgb_frame must be numpy.ndarray")
    if rgb_frame.dtype != np.uint8:
        raise ValueError(f"rgb_frame must have dtype uint8, got {rgb_frame.dtype}")
    if rgb_frame.ndim != 3 or rgb_frame.shape[2] != 3:
        raise ValueError(
            f"rgb_frame must have shape [H, W, 3], got {rgb_frame.shape}"
        )
    if rgb_frame.shape[0] < 1 or rgb_frame.shape[1] < 1:
        raise ValueError("rgb_frame must have non-zero width and height")
    return np.ascontiguousarray(rgb_frame)


@dataclass(frozen=True, slots=True)
class PoseExtractorConfig:
    include_face: bool = False
    model_complexity: int = 1
    min_detection_confidence: float = 0.5
    min_tracking_confidence: float = 0.5

    def __post_init__(self) -> None:
        model_complexity = int(self.model_complexity)
        if model_complexity < 0:
            raise ValueError("model_complexity must be non-negative")

        detection = float(self.min_detection_confidence)
        tracking = float(self.min_tracking_confidence)
        for name, value in (
            ("min_detection_confidence", detection),
            ("min_tracking_confidence", tracking),
        ):
            if not np.isfinite(value) or value < 0.0 or value > 1.0:
                raise ValueError(f"{name} must be a finite float in [0, 1]")

        object.__setattr__(self, "include_face", bool(self.include_face))
        object.__setattr__(self, "model_complexity", model_complexity)
        object.__setattr__(self, "min_detection_confidence", detection)
        object.__setattr__(self, "min_tracking_confidence", tracking)


class PoseExtractor:
    """Lazy MediaPipe Holistic wrapper for decoded RGB input."""

    def __init__(
        self,
        config: PoseExtractorConfig | None = None,
        *,
        include_face: bool | None = None,
        model_complexity: int | None = None,
        min_detection_confidence: float | None = None,
        min_tracking_confidence: float | None = None,
    ) -> None:
        resolved_config = config or PoseExtractorConfig()
        updates: dict[str, object] = {}
        if include_face is not None:
            updates["include_face"] = include_face
        if model_complexity is not None:
            updates["model_complexity"] = model_complexity
        if min_detection_confidence is not None:
            updates["min_detection_confidence"] = min_detection_confidence
        if min_tracking_confidence is not None:
            updates["min_tracking_confidence"] = min_tracking_confidence
        if updates:
            resolved_config = replace(resolved_config, **updates)

        self.config = resolved_config
        self._mp = self._load_mediapipe()
        self._holistic = self._mp.solutions.holistic.Holistic(
            static_image_mode=False,
            model_complexity=self.config.model_complexity,
            smooth_landmarks=True,
            enable_segmentation=False,
            smooth_segmentation=False,
            refine_face_landmarks=False,
            min_detection_confidence=self.config.min_detection_confidence,
            min_tracking_confidence=self.config.min_tracking_confidence,
        )

    @staticmethod
    def _load_mediapipe() -> Any:
        try:
            return importlib.import_module("mediapipe")
        except ModuleNotFoundError as exc:  # pragma: no cover - environment dependent
            if exc.name != "mediapipe":
                raise
            raise ImportError(
                "mediapipe is required for PoseExtractor. Install the optional "
                "pose extraction dependencies, for example "
                "`pip install rsl-sign-recognition[pose-extraction]`."
            ) from exc
        except Exception as exc:  # pragma: no cover - environment dependent
            raise ImportError("failed to import mediapipe for PoseExtractor") from exc

    def close(self) -> None:
        holistic = getattr(self, "_holistic", None)
        if holistic is not None:
            holistic.close()

    def __enter__(self) -> "PoseExtractor":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # type: ignore[override]
        self.close()

    @staticmethod
    def _landmarks_to_group(
        landmarks: Any,
        *,
        with_visibility: bool = False,
    ) -> PoseLandmarksGroup | None:
        if landmarks is None:
            return None

        landmark_list = getattr(landmarks, "landmark", None)
        if not landmark_list:
            return None

        points = np.asarray(
            [[lm.x, lm.y, lm.z] for lm in landmark_list],
            dtype=np.float32,
        )
        confidence: np.ndarray | None = None

        if with_visibility:
            values: list[float] = []
            all_present = True
            for landmark in landmark_list:
                if not hasattr(landmark, "visibility"):
                    all_present = False
                    break
                values.append(float(landmark.visibility))
            if all_present:
                confidence = np.asarray(values, dtype=np.float32)

        return PoseLandmarksGroup(points=points, confidence=confidence)

    def process(
        self,
        rgb_frame: np.ndarray,
        *,
        timestamp: float | None = None,
    ) -> PoseFrame | None:
        frame = validate_rgb_frame(rgb_frame)
        height, width = frame.shape[:2]

        results = self._holistic.process(frame)

        body = self._landmarks_to_group(
            getattr(results, "pose_landmarks", None),
            with_visibility=True,
        )
        left_hand = self._landmarks_to_group(
            getattr(results, "left_hand_landmarks", None),
        )
        right_hand = self._landmarks_to_group(
            getattr(results, "right_hand_landmarks", None),
        )
        face = None
        if self.config.include_face:
            face = self._landmarks_to_group(getattr(results, "face_landmarks", None))

        if body is None and left_hand is None and right_hand is None and face is None:
            return None

        return PoseFrame(
            timestamp=float(time.time() if timestamp is None else timestamp),
            body=body,
            left_hand=left_hand,
            right_hand=right_hand,
            face=face,
            meta={
                "image_size": [int(height), int(width)],
                "include_face": bool(self.config.include_face),
                "source": "mediapipe_holistic",
            },
        )


__all__ = ["PoseExtractor", "PoseExtractorConfig", "validate_rgb_frame"]

