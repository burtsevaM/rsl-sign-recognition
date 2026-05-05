from __future__ import annotations

import inspect

import numpy as np

from rsl_sign_recognition.pipelines.pose_words.features import DEFAULT_FEATURE_DIM
from rsl_sign_recognition.segmentation.streaming import StreamingBioSegmenter
import rsl_sign_recognition.segmentation.streaming as streaming_module


def _probs_for_label(label: str) -> np.ndarray:
    if label == "B":
        return np.asarray([0.9, 0.05, 0.05], dtype=np.float32)
    if label == "I":
        return np.asarray([0.05, 0.9, 0.05], dtype=np.float32)
    return np.asarray([0.05, 0.05, 0.9], dtype=np.float32)


class IndexPatternModel:
    def __init__(
        self,
        *,
        sign: dict[int, str] | None = None,
        phrase: dict[int, str] | None = None,
    ) -> None:
        self.sign = sign or {}
        self.phrase = phrase or {}
        self.calls: list[np.ndarray] = []

    def infer(self, features_tf: np.ndarray) -> tuple[np.ndarray, np.ndarray, float]:
        features = np.asarray(features_tf, dtype=np.float32)
        self.calls.append(features.copy())
        indices = [int(value) for value in features[:, 0]]
        sign = np.stack(
            [_probs_for_label(self.sign.get(frame_idx, "O")) for frame_idx in indices],
            axis=0,
        )
        phrase = np.stack(
            [_probs_for_label(self.phrase.get(frame_idx, "O")) for frame_idx in indices],
            axis=0,
        )
        return sign.astype(np.float32), phrase.astype(np.float32), 1.25


def _feature(frame_idx: int, *, dim: int = 4) -> np.ndarray:
    feature = np.full((dim,), float(frame_idx), dtype=np.float32)
    feature[0] = float(frame_idx)
    return feature


def test_streaming_does_not_run_inference_before_window() -> None:
    model = IndexPatternModel()
    segmenter = StreamingBioSegmenter(model=model, window=3, step=1)

    first = segmenter.update(_feature(0))
    second = segmenter.update(_feature(1))

    assert first.ran_inference is False
    assert second.ran_inference is False
    assert len(model.calls) == 0


def test_streaming_runs_after_window_and_then_by_step_cadence() -> None:
    model = IndexPatternModel()
    segmenter = StreamingBioSegmenter(model=model, window=3, step=2)

    results = [segmenter.update(_feature(idx)) for idx in range(5)]

    assert [result.ran_inference for result in results] == [
        False,
        False,
        True,
        False,
        True,
    ]
    assert len(model.calls) == 2
    assert model.calls[0].shape == (3, 4)
    assert [int(value) for value in model.calls[1][:, 0]] == [2, 3, 4]


def test_streaming_reports_global_monotonic_buffer_indices() -> None:
    model = IndexPatternModel()
    segmenter = StreamingBioSegmenter(model=model, window=2, step=1, max_buffer=3)

    results = [segmenter.update(_feature(idx)) for idx in range(5)]

    assert [result.buffer_end for result in results] == [0, 1, 2, 3, 4]
    assert results[-1].buffer_start == 2
    assert results[-1].buffer_end == 4
    assert segmenter.next_frame_index == 5


def test_streaming_emits_completed_sign_segment_once() -> None:
    model = IndexPatternModel(sign={0: "B", 1: "I", 2: "O"})
    segmenter = StreamingBioSegmenter(model=model, window=3, step=1, min_len=1)

    first_completed = None
    for idx in range(3):
        first_completed = segmenter.update(_feature(idx))

    assert first_completed is not None
    assert [(segment.start, segment.end) for segment in first_completed.sign_segments] == [
        (0, 1)
    ]
    assert np.isclose(first_completed.sign_segments[0].score, 0.9)

    repeated = segmenter.update(_feature(3))

    assert repeated.ran_inference is True
    assert repeated.sign_segments == []
    assert [(segment.start, segment.end) for segment in repeated.recent_sign_segments] == [
        (0, 1)
    ]


def test_streaming_active_sign_progress_can_exist_without_completed_segment() -> None:
    model = IndexPatternModel(sign={0: "B", 1: "I"})
    segmenter = StreamingBioSegmenter(model=model, window=2, step=1, min_len=4)

    segmenter.update(_feature(0))
    result = segmenter.update(_feature(1))

    assert result.ran_inference is True
    assert result.sign_segments == []
    assert result.active_sign is True
    assert result.active_sign_progress == 0.5


def test_streaming_cool_off_suppresses_close_duplicate_segments() -> None:
    model = IndexPatternModel(
        sign={0: "B", 1: "I", 2: "O", 3: "B", 4: "I", 5: "O"}
    )
    segmenter = StreamingBioSegmenter(
        model=model,
        window=3,
        step=1,
        min_len=1,
        cool_off_frames=2,
    )

    emitted: list[tuple[int, int]] = []
    for idx in range(6):
        result = segmenter.update(_feature(idx))
        emitted.extend((segment.start, segment.end) for segment in result.sign_segments)

    assert emitted == [(0, 1)]
    assert segmenter.update(_feature(6)).sign_segments == []


def test_streaming_get_feature_span_returns_exact_valid_global_range() -> None:
    model = IndexPatternModel()
    segmenter = StreamingBioSegmenter(model=model, window=10, max_buffer=10)
    features = [_feature(idx, dim=3) for idx in range(5)]
    for feature in features:
        segmenter.update(feature)

    span = segmenter.get_feature_span(1, 3)

    assert span is not None
    assert span.shape == (3, 3)
    assert np.allclose(span, np.stack(features[1:4], axis=0))


def test_streaming_get_feature_span_returns_none_for_invalid_or_out_of_buffer_range() -> None:
    model = IndexPatternModel()
    segmenter = StreamingBioSegmenter(model=model, window=1, max_buffer=3)
    for idx in range(5):
        segmenter.update(_feature(idx, dim=3))

    assert segmenter.get_feature_span(3, 2) is None
    assert segmenter.get_feature_span(0, 1) is None
    assert segmenter.get_feature_span(3, 10) is None


def test_streaming_accepts_pw05_default_dim_without_pose_words_import_boundary() -> None:
    model = IndexPatternModel()
    segmenter = StreamingBioSegmenter(model=model, window=2, feature_dim=DEFAULT_FEATURE_DIM)

    segmenter.update(np.zeros((DEFAULT_FEATURE_DIM,), dtype=np.float32))
    result = segmenter.update(np.ones((DEFAULT_FEATURE_DIM,), dtype=np.float32))

    assert result.ran_inference is True
    assert "pose_words" not in inspect.getsource(streaming_module)
