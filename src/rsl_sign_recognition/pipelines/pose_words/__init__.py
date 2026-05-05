"""Pose-first runtime layer for the future pose_words pipeline."""

from rsl_sign_recognition.pipelines.pose_words.features import (
    DEFAULT_FEATURE_DIM,
    DEFAULT_FEATURE_POINT_COUNT,
    DEFAULT_UPPER_BODY_INDICES,
    ShoulderNormInfo,
    compose_features,
    compose_features_sequence,
    hand_normalize_3d,
    hide_legs,
    shoulder_normalize,
)
from rsl_sign_recognition.pipelines.pose_words.clip import resample_to_fixed_T
from rsl_sign_recognition.pipelines.pose_words.pose_extraction import (
    PoseExtractor,
    PoseExtractorConfig,
    validate_rgb_frame,
)
from rsl_sign_recognition.pipelines.pose_words.pose_types import (
    BODY_LANDMARK_COUNT,
    FACE_LANDMARK_COUNT,
    HAND_LANDMARK_COUNT,
    PoseFrame,
    PoseLandmarksGroup,
    validate_pose_frame,
)
from rsl_sign_recognition.pipelines.pose_words.service import (
    PoseFeatureResult,
    PoseFeatureService,
    PoseFeatureServiceConfig,
)

__all__ = [
    "BODY_LANDMARK_COUNT",
    "DEFAULT_FEATURE_DIM",
    "DEFAULT_FEATURE_POINT_COUNT",
    "DEFAULT_UPPER_BODY_INDICES",
    "FACE_LANDMARK_COUNT",
    "HAND_LANDMARK_COUNT",
    "PoseExtractor",
    "PoseExtractorConfig",
    "PoseFeatureResult",
    "PoseFeatureService",
    "PoseFeatureServiceConfig",
    "PoseFrame",
    "PoseLandmarksGroup",
    "ShoulderNormInfo",
    "compose_features",
    "compose_features_sequence",
    "hand_normalize_3d",
    "hide_legs",
    "resample_to_fixed_T",
    "shoulder_normalize",
    "validate_pose_frame",
    "validate_rgb_frame",
]
