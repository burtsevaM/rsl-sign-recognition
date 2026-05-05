from __future__ import annotations

import numpy as np
import pytest

from rsl_sign_recognition.segmentation import BioSegment, decode_segments


def _bio(labels: str) -> np.ndarray:
    rows: list[list[float]] = []
    for label in labels:
        if label == "B":
            rows.append([0.9, 0.05, 0.05])
        elif label == "I":
            rows.append([0.05, 0.9, 0.05])
        elif label == "O":
            rows.append([0.05, 0.05, 0.9])
        else:
            raise ValueError(label)
    return np.asarray(rows, dtype=np.float32)


@pytest.mark.parametrize(
    "probs",
    [
        np.zeros((3,), dtype=np.float32),
        np.zeros((2, 4), dtype=np.float32),
        np.zeros((1, 2, 3), dtype=np.float32),
    ],
)
def test_decode_segments_rejects_input_not_t3(probs: np.ndarray) -> None:
    with pytest.raises(ValueError, match=r"\[T, 3\]"):
        decode_segments(probs, th_B=0.5, th_O=0.5)


def test_decode_segments_empty_input_returns_no_segments() -> None:
    assert decode_segments(np.zeros((0, 3), dtype=np.float32), th_B=0.5, th_O=0.5) == []


def test_decode_segments_sanitizes_nan_and_inf_without_crashing() -> None:
    probs = np.asarray(
        [
            [0.9, 0.1, 0.0],
            [np.nan, np.inf, -np.inf],
            [0.0, 0.0, 0.9],
        ],
        dtype=np.float32,
    )

    segments = decode_segments(probs, th_B=0.5, th_O=0.5)

    assert len(segments) == 1
    assert segments[0].start == 0
    assert segments[0].end == 1
    assert segments[0].score == pytest.approx(0.45)


def test_decode_segments_b_starts_segment() -> None:
    segments = decode_segments(_bio("OBI"), th_B=0.5, th_O=0.5)

    assert [(segment.start, segment.end) for segment in segments] == [(1, 2)]
    assert segments[0].score == pytest.approx(0.9)


def test_decode_segments_o_closes_segment_before_o_frame() -> None:
    segments = decode_segments(_bio("BIOI"), th_B=0.5, th_O=0.5)

    assert [(segment.start, segment.end) for segment in segments] == [(0, 1)]
    assert segments[0].score == pytest.approx(0.9)


def test_decode_segments_new_b_closes_previous_segment() -> None:
    segments = decode_segments(_bio("BIBI"), th_B=0.5, th_O=0.5)

    assert [(segment.start, segment.end) for segment in segments] == [(0, 1), (2, 3)]
    assert [segment.score for segment in segments] == pytest.approx([0.9, 0.9])


def test_decode_segments_merge_gap_merges_close_segments() -> None:
    segments = decode_segments(_bio("BIOBI"), th_B=0.5, th_O=0.5, merge_gap=1)

    assert len(segments) == 1
    assert segments[0].start == 0
    assert segments[0].end == 4


def test_decode_segments_min_len_filters_short_segments() -> None:
    segments = decode_segments(_bio("BOBI"), th_B=0.5, th_O=0.5, min_len=2)

    assert [(segment.start, segment.end) for segment in segments] == [(2, 3)]
    assert segments[0].score == pytest.approx(0.9)


def test_decode_segments_max_len_keeps_trailing_window_predictably() -> None:
    segments = decode_segments(_bio("BIIII"), th_B=0.5, th_O=0.5, max_len=3)

    assert [(segment.start, segment.end) for segment in segments] == [(2, 4)]
    assert segments[0].score == pytest.approx(0.9)


def test_decode_segments_score_is_mean_max_b_or_i_inside_segment() -> None:
    probs = np.asarray(
        [
            [0.8, 0.1, 0.1],
            [0.2, 0.7, 0.1],
            [0.05, 0.05, 0.9],
        ],
        dtype=np.float32,
    )

    segments = decode_segments(probs, th_B=0.5, th_O=0.5)

    assert len(segments) == 1
    assert segments[0].start == 0
    assert segments[0].end == 1
    assert segments[0].score == pytest.approx(0.75)
