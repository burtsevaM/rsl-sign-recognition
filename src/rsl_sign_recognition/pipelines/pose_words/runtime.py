"""Runtime assembly for the live pose_words path."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import numpy as np

from rsl_sign_recognition.inference.pose_words import (
    PoseWordOnnxModel,
    find_no_event_index,
)
from rsl_sign_recognition.pipelines.pose_words.pose_extraction import PoseExtractor
from rsl_sign_recognition.pipelines.pose_words.service import (
    PoseFeatureService,
    PoseFrameExtractor,
)
from rsl_sign_recognition.runtime.artifacts import ResolvedActiveArtifacts
from rsl_sign_recognition.segmentation.model_onnx import (
    BioSegmenterOnnxModel,
    load_bio_thresholds,
)
from rsl_sign_recognition.segmentation.streaming import (
    BioSegmentationModel,
    StreamingBioSegmenter,
)


class PoseWordsClassifier(Protocol):
    labels: list[str]
    input_clip_frames: int | None
    config_clip_frames: int | None
    input_feature_dim: int | None
    config_feature_dim: int | None

    def infer_probs(self, features_tf: np.ndarray) -> tuple[np.ndarray, float]:
        ...

    def find_no_event_index(self, label_name: str = "no_event") -> int | None:
        ...


ClassifierFactory = Callable[..., PoseWordsClassifier]
ExtractorFactory = Callable[[], PoseFrameExtractor]
SegmenterModelFactory = Callable[..., BioSegmentationModel]


@dataclass(frozen=True, slots=True)
class PoseWordsRuntimePipeline:
    """Layer wiring for pose_words without transport/session ownership."""

    artifacts: ResolvedActiveArtifacts
    pose_features: PoseFeatureService
    segmentation_model: BioSegmentationModel
    segmenter: StreamingBioSegmenter
    classifier: PoseWordsClassifier
    clip_frames: int
    feature_dim: int
    no_event_index: int | None

    @property
    def profile_id(self) -> str:
        return self.artifacts.profile_id

    @property
    def manifest_path(self) -> Path:
        return self.artifacts.manifest_path


def build_pose_words_runtime_pipeline(
    artifacts: ResolvedActiveArtifacts,
    *,
    extractor_factory: ExtractorFactory | None = None,
    classifier_factory: ClassifierFactory | None = None,
    segmenter_model_factory: SegmenterModelFactory | None = None,
) -> PoseWordsRuntimePipeline:
    """Build the clean pose_words path from manifest-resolved artifacts."""

    extractor_factory = extractor_factory or PoseExtractor
    classifier_factory = classifier_factory or PoseWordOnnxModel
    segmenter_model_factory = segmenter_model_factory or BioSegmenterOnnxModel

    classifier = classifier_factory(
        model_path=artifacts.classifier_model_path,
        labels_path=artifacts.classifier_labels_path,
        config_path=artifacts.classifier_config_path,
        ort_num_threads=1,
    )
    segmentation_model = segmenter_model_factory(
        model_path=artifacts.segmentation_model_path,
        config_path=artifacts.segmentation_config_path,
        ort_num_threads=1,
    )
    extractor = extractor_factory()
    pose_features = PoseFeatureService(extractor=extractor)

    feature_dim = _resolve_feature_dim(classifier, segmentation_model)
    clip_frames = _resolve_clip_frames(classifier)
    thresholds = load_bio_thresholds(artifacts.segmentation_thresholds_path)
    segmentation_config = _read_optional_json(artifacts.segmentation_config_path)
    window = _positive_int(segmentation_config.get("window_size"), default=64)

    segmenter = StreamingBioSegmenter(
        model=segmentation_model,
        window=window,
        step=_positive_int(segmentation_config.get("step"), default=8),
        min_len=_positive_int(
            segmentation_config.get("min_segment_len"),
            default=1,
        ),
        sign_th_b=thresholds.sign_th_b,
        sign_th_o=thresholds.sign_th_o,
        phrase_th_b=thresholds.phrase_th_b,
        phrase_th_o=thresholds.phrase_th_o,
        feature_dim=feature_dim,
    )

    return PoseWordsRuntimePipeline(
        artifacts=artifacts,
        pose_features=pose_features,
        segmentation_model=segmentation_model,
        segmenter=segmenter,
        classifier=classifier,
        clip_frames=clip_frames,
        feature_dim=feature_dim,
        no_event_index=_resolve_no_event_index(classifier),
    )


def _resolve_feature_dim(
    classifier: PoseWordsClassifier,
    segmentation_model: BioSegmentationModel,
) -> int:
    candidates = (
        getattr(classifier, "input_feature_dim", None),
        getattr(classifier, "config_feature_dim", None),
        getattr(segmentation_model, "input_feature_dim", None),
        getattr(segmentation_model, "config_feature_dim", None),
    )
    for value in candidates:
        parsed = _positive_int(value, default=0)
        if parsed > 0:
            return parsed
    raise ValueError("pose_words runtime feature_dim is unavailable")


def _resolve_clip_frames(classifier: PoseWordsClassifier) -> int:
    candidates = (
        getattr(classifier, "input_clip_frames", None),
        getattr(classifier, "config_clip_frames", None),
    )
    for value in candidates:
        parsed = _positive_int(value, default=0)
        if parsed > 0:
            return parsed
    raise ValueError("pose_words runtime clip_frames is unavailable")


def _resolve_no_event_index(classifier: PoseWordsClassifier) -> int | None:
    method = getattr(classifier, "find_no_event_index", None)
    if callable(method):
        return method()
    return find_no_event_index(getattr(classifier, "labels", ()))


def _read_optional_json(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _positive_int(value: object, *, default: int) -> int:
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value if value > 0 else default
    return default


__all__ = [
    "ClassifierFactory",
    "ExtractorFactory",
    "PoseWordsClassifier",
    "PoseWordsRuntimePipeline",
    "SegmenterModelFactory",
    "build_pose_words_runtime_pipeline",
]
