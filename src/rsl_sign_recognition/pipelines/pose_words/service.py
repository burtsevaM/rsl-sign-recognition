"""Synchronous pose feature service boundary for future runtime wiring."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

import numpy as np

from rsl_sign_recognition.pipelines.pose_words.features import (
    DEFAULT_UPPER_BODY_INDICES,
    compose_features,
)
from rsl_sign_recognition.pipelines.pose_words.pose_extraction import validate_rgb_frame
from rsl_sign_recognition.pipelines.pose_words.pose_types import PoseFrame


class PoseFrameExtractor(Protocol):
    def process(self, rgb_frame: np.ndarray) -> PoseFrame | None:
        ...


@dataclass(frozen=True, slots=True)
class PoseFeatureServiceConfig:
    upper_body_indices: tuple[int, ...] = DEFAULT_UPPER_BODY_INDICES
    apply_shoulder_norm: bool = True
    hide_legs_before_body: bool = True
    canonical_hands_3d: bool = True


@dataclass(frozen=True, slots=True)
class PoseFeatureResult:
    pose_frame: PoseFrame | None
    feature_vector: np.ndarray | None
    aux: dict[str, Any]

    @property
    def hand_present(self) -> bool:
        if self.pose_frame is None:
            return False
        return self.pose_frame.left_hand is not None or self.pose_frame.right_hand is not None


class PoseFeatureService:
    """Dependency-injected synchronous boundary: decoded RGB -> pose -> features."""

    def __init__(
        self,
        *,
        extractor: PoseFrameExtractor,
        config: PoseFeatureServiceConfig | None = None,
    ) -> None:
        self.extractor = extractor
        self.config = config or PoseFeatureServiceConfig()

    def process_rgb_frame(self, rgb_frame: np.ndarray) -> PoseFeatureResult:
        frame = validate_rgb_frame(rgb_frame)
        pose_frame = self.extractor.process(frame)
        if pose_frame is None:
            return PoseFeatureResult(
                pose_frame=None,
                feature_vector=None,
                aux={"reason": "pose_not_detected"},
            )

        feature_vector, aux = compose_features(
            pose_frame,
            upper_body_indices=self.config.upper_body_indices,
            apply_shoulder_norm=self.config.apply_shoulder_norm,
            hide_legs_before_body=self.config.hide_legs_before_body,
            canonical_hands_3d=self.config.canonical_hands_3d,
        )
        return PoseFeatureResult(
            pose_frame=pose_frame,
            feature_vector=feature_vector,
            aux=aux,
        )


__all__ = [
    "PoseFeatureResult",
    "PoseFeatureService",
    "PoseFeatureServiceConfig",
    "PoseFrameExtractor",
]
