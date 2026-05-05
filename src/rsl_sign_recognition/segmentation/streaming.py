"""Streaming BIO segmentation over pose feature vectors."""

from __future__ import annotations

from collections import deque
from typing import Protocol
import time

import numpy as np

from rsl_sign_recognition.segmentation.decoder import decode_segments
from rsl_sign_recognition.segmentation.types import BioSegment, StreamingBioResult


class BioSegmentationModel(Protocol):
    def infer(self, features_tf: np.ndarray) -> tuple[np.ndarray, np.ndarray, float]:
        ...


class StreamingBioSegmenter:
    """Stateful streaming segmenter using global monotonic frame indices."""

    def __init__(
        self,
        *,
        model: BioSegmentationModel,
        window: int = 256,
        step: int = 8,
        min_len: int = 6,
        max_len: int | None = 150,
        merge_gap: int = 2,
        cool_off_frames: int = 0,
        sign_th_b: float = 0.5,
        sign_th_o: float = 0.5,
        phrase_th_b: float = 0.5,
        phrase_th_o: float = 0.5,
        max_buffer: int | None = None,
        feature_dim: int | None = None,
    ) -> None:
        self.model = model
        self.window = max(1, int(window))
        self.step = max(1, int(step))
        self.min_len = max(1, int(min_len))
        self.max_len = (
            max(self.min_len, int(max_len)) if max_len is not None else None
        )
        self.merge_gap = max(0, int(merge_gap))
        self.cool_off_frames = max(0, int(cool_off_frames))
        self.sign_th_b = float(sign_th_b)
        self.sign_th_o = float(sign_th_o)
        self.phrase_th_b = float(phrase_th_b)
        self.phrase_th_o = float(phrase_th_o)
        self.feature_dim = int(feature_dim) if feature_dim is not None else None
        if self.feature_dim is not None and self.feature_dim < 1:
            raise ValueError("feature_dim must be a positive integer")

        resolved_max_buffer = (
            self.window * 2 if max_buffer is None else max(1, int(max_buffer))
        )
        self.max_buffer = max(self.window, resolved_max_buffer)
        self._features: deque[np.ndarray] = deque(maxlen=self.max_buffer)
        self._frame_indices: deque[int] = deque(maxlen=self.max_buffer)
        self._next_frame_idx = 0
        self._frames_since_infer = 0
        self._has_run_inference = False

        self._sign_sum: dict[int, np.ndarray] = {}
        self._phrase_sum: dict[int, np.ndarray] = {}
        self._counts: dict[int, int] = {}

        self._latest_sign_segments: list[BioSegment] = []
        self._latest_phrase_segments: list[BioSegment] = []
        self._latest_active_sign = False
        self._latest_active_phrase = False
        self._latest_active_sign_progress = 0.0
        self._latest_active_phrase_progress = 0.0
        self._last_emitted_sign_end = -1
        self._last_emitted_phrase_end = -1
        self._emitted_sign_keys: set[tuple[int, int]] = set()
        self._emitted_phrase_keys: set[tuple[int, int]] = set()

    @property
    def has_enough_frames(self) -> bool:
        return len(self._features) >= self.window

    @property
    def next_frame_index(self) -> int:
        return int(self._next_frame_idx)

    def _append_feature(self, feature: np.ndarray) -> None:
        arr = np.asarray(feature, dtype=np.float32)
        if arr.size == 0:
            raise ValueError("feature vector must contain at least one value")
        feat = arr.reshape(-1).astype(np.float32, copy=False)
        if not np.all(np.isfinite(feat)):
            feat = np.nan_to_num(
                feat,
                nan=0.0,
                posinf=0.0,
                neginf=0.0,
            ).astype(np.float32)

        if self.feature_dim is None:
            self.feature_dim = int(feat.shape[0])
        elif int(feat.shape[0]) != int(self.feature_dim):
            raise ValueError(
                f"feature vector dim mismatch: expected {self.feature_dim}, "
                f"got {feat.shape[0]}"
            )

        frame_idx = int(self._next_frame_idx)
        self._next_frame_idx += 1
        self._features.append(np.ascontiguousarray(feat, dtype=np.float32))
        self._frame_indices.append(frame_idx)
        self._frames_since_infer += 1

    def _result(self, *, ran_inference: bool) -> StreamingBioResult:
        start = int(self._frame_indices[0]) if self._frame_indices else 0
        end = int(self._frame_indices[-1]) if self._frame_indices else -1
        return StreamingBioResult(
            ran_inference=ran_inference,
            recent_sign_segments=list(self._latest_sign_segments),
            recent_phrase_segments=list(self._latest_phrase_segments),
            active_sign=bool(self._latest_active_sign),
            active_phrase=bool(self._latest_active_phrase),
            active_sign_progress=float(self._latest_active_sign_progress),
            active_phrase_progress=float(self._latest_active_phrase_progress),
            buffer_len=len(self._frame_indices),
            buffer_start=start,
            buffer_end=end,
            index_mode="global",
        )

    def _prune_aggregation(self) -> None:
        if not self._frame_indices:
            self._sign_sum.clear()
            self._phrase_sum.clear()
            self._counts.clear()
            return

        min_idx = int(self._frame_indices[0])
        drop_keys = [frame_idx for frame_idx in self._counts if frame_idx < min_idx]
        for frame_idx in drop_keys:
            self._counts.pop(frame_idx, None)
            self._sign_sum.pop(frame_idx, None)
            self._phrase_sum.pop(frame_idx, None)

    def _coerce_window_probs(self, probs: np.ndarray, *, expected_len: int) -> np.ndarray:
        arr = np.asarray(probs, dtype=np.float32)
        if arr.ndim != 2 or arr.shape != (expected_len, 3):
            raise ValueError(
                f"BIO model output must have shape [{expected_len}, 3], got {arr.shape}"
            )
        if not np.all(np.isfinite(arr)):
            arr = np.nan_to_num(
                arr,
                nan=0.0,
                posinf=0.0,
                neginf=0.0,
            ).astype(np.float32)
        return np.ascontiguousarray(arr, dtype=np.float32)

    def _update_aggregation(
        self,
        frame_indices: list[int],
        sign_probs: np.ndarray,
        phrase_probs: np.ndarray,
    ) -> None:
        expected_len = len(frame_indices)
        sign = self._coerce_window_probs(sign_probs, expected_len=expected_len)
        phrase = self._coerce_window_probs(phrase_probs, expected_len=expected_len)

        for offset, frame_idx in enumerate(frame_indices):
            if frame_idx not in self._counts:
                self._counts[frame_idx] = 0
                self._sign_sum[frame_idx] = np.zeros((3,), dtype=np.float32)
                self._phrase_sum[frame_idx] = np.zeros((3,), dtype=np.float32)
            self._counts[frame_idx] += 1
            self._sign_sum[frame_idx] += sign[offset]
            self._phrase_sum[frame_idx] += phrase[offset]

    def _averaged_probs(self) -> tuple[list[int], np.ndarray, np.ndarray]:
        if not self._frame_indices:
            empty = np.zeros((0, 3), dtype=np.float32)
            return [], empty, empty.copy()

        indices = list(self._frame_indices)
        sign = np.zeros((len(indices), 3), dtype=np.float32)
        phrase = np.zeros((len(indices), 3), dtype=np.float32)
        for offset, frame_idx in enumerate(indices):
            count = int(self._counts.get(frame_idx, 0))
            if count <= 0:
                sign[offset, 2] = 1.0
                phrase[offset, 2] = 1.0
                continue
            sign[offset] = (self._sign_sum[frame_idx] / float(count)).astype(np.float32)
            phrase[offset] = (self._phrase_sum[frame_idx] / float(count)).astype(
                np.float32
            )
        return indices, sign, phrase

    def _segments_to_global(
        self,
        indices: list[int],
        local_segments: list[BioSegment],
    ) -> list[BioSegment]:
        return [
            BioSegment(
                start=indices[segment.start],
                end=indices[segment.end],
                score=float(segment.score),
            )
            for segment in local_segments
        ]

    def _active_state(
        self,
        indices: list[int],
        probs: np.ndarray,
        *,
        th_b: float,
        th_o: float,
    ) -> tuple[bool, float]:
        active_candidates = decode_segments(
            probs,
            th_B=th_b,
            th_O=th_o,
            min_len=1,
            max_len=self.max_len,
            merge_gap=self.merge_gap,
        )
        if not active_candidates:
            return False, 0.0
        latest_local_idx = len(indices) - 1
        active = active_candidates[-1].end >= latest_local_idx
        if not active:
            return False, 0.0
        active_length = int(active_candidates[-1].end - active_candidates[-1].start + 1)
        progress = min(1.0, active_length / float(self.min_len))
        return True, float(progress)

    def _decode_segments_for_buffer(
        self,
    ) -> tuple[list[BioSegment], list[BioSegment], bool, bool, float, float]:
        indices, sign_probs, phrase_probs = self._averaged_probs()
        if not indices:
            return [], [], False, False, 0.0, 0.0

        sign_local = decode_segments(
            sign_probs,
            th_B=self.sign_th_b,
            th_O=self.sign_th_o,
            min_len=self.min_len,
            max_len=self.max_len,
            merge_gap=self.merge_gap,
        )
        phrase_local = decode_segments(
            phrase_probs,
            th_B=self.phrase_th_b,
            th_O=self.phrase_th_o,
            min_len=self.min_len,
            max_len=self.max_len,
            merge_gap=self.merge_gap,
        )
        active_sign, active_sign_progress = self._active_state(
            indices,
            sign_probs,
            th_b=self.sign_th_b,
            th_o=self.sign_th_o,
        )
        active_phrase, active_phrase_progress = self._active_state(
            indices,
            phrase_probs,
            th_b=self.phrase_th_b,
            th_o=self.phrase_th_o,
        )
        return (
            self._segments_to_global(indices, sign_local),
            self._segments_to_global(indices, phrase_local),
            active_sign,
            active_phrase,
            active_sign_progress,
            active_phrase_progress,
        )

    def _apply_cool_off(
        self,
        segments: list[BioSegment],
        *,
        last_end: int,
        emitted_keys: set[tuple[int, int]],
    ) -> tuple[list[BioSegment], int]:
        if not segments:
            return [], int(last_end)

        output: list[BioSegment] = []
        cursor_end = int(last_end)
        for segment in sorted(segments, key=lambda item: (item.end, item.start)):
            key = (int(segment.start), int(segment.end))
            if key in emitted_keys:
                continue
            if segment.end <= cursor_end:
                continue
            if cursor_end >= 0:
                gap = int(segment.start - cursor_end - 1)
                if gap < self.cool_off_frames:
                    continue
            output.append(segment)
            emitted_keys.add(key)
            cursor_end = int(segment.end)
        return output, cursor_end

    def get_feature_span(self, start: int, end: int) -> np.ndarray | None:
        if not self._frame_indices:
            return None

        start_i = int(start)
        end_i = int(end)
        if end_i < start_i:
            return None

        min_idx = int(self._frame_indices[0])
        max_idx = int(self._frame_indices[-1])
        if start_i < min_idx or end_i > max_idx:
            return None

        local_start = start_i - min_idx
        local_end = end_i - min_idx
        if local_start < 0 or local_end >= len(self._features):
            return None

        features = np.stack(list(self._features), axis=0).astype(np.float32)
        span = features[local_start : local_end + 1]
        if span.shape[0] != end_i - start_i + 1:
            return None
        return np.ascontiguousarray(span, dtype=np.float32).copy()

    def update(self, feature: np.ndarray) -> StreamingBioResult:
        self._append_feature(feature)
        self._prune_aggregation()

        if not self.has_enough_frames:
            return self._result(ran_inference=False)

        should_run = (
            not self._has_run_inference or self._frames_since_infer >= self.step
        )
        if not should_run:
            return self._result(ran_inference=False)

        window_features = np.stack(list(self._features)[-self.window :], axis=0).astype(
            np.float32
        )
        window_indices = list(self._frame_indices)[-self.window :]
        self._frames_since_infer = 0
        self._has_run_inference = True

        sign_probs, phrase_probs, latency_ms = self.model.infer(window_features)
        self._update_aggregation(window_indices, sign_probs, phrase_probs)
        self._prune_aggregation()

        decode_started = time.perf_counter()
        (
            all_sign,
            all_phrase,
            active_sign,
            active_phrase,
            active_sign_progress,
            active_phrase_progress,
        ) = self._decode_segments_for_buffer()
        decode_latency_ms = float((time.perf_counter() - decode_started) * 1000.0)

        self._latest_sign_segments = list(all_sign)
        self._latest_phrase_segments = list(all_phrase)
        self._latest_active_sign = bool(active_sign)
        self._latest_active_phrase = bool(active_phrase)
        self._latest_active_sign_progress = float(active_sign_progress)
        self._latest_active_phrase_progress = float(active_phrase_progress)

        latest_idx = int(self._frame_indices[-1])
        completed_sign = [segment for segment in all_sign if segment.end < latest_idx]
        completed_phrase = [
            segment for segment in all_phrase if segment.end < latest_idx
        ]

        new_sign, self._last_emitted_sign_end = self._apply_cool_off(
            [
                segment
                for segment in completed_sign
                if segment.end > self._last_emitted_sign_end
            ],
            last_end=self._last_emitted_sign_end,
            emitted_keys=self._emitted_sign_keys,
        )
        new_phrase, self._last_emitted_phrase_end = self._apply_cool_off(
            [
                segment
                for segment in completed_phrase
                if segment.end > self._last_emitted_phrase_end
            ],
            last_end=self._last_emitted_phrase_end,
            emitted_keys=self._emitted_phrase_keys,
        )

        result = self._result(ran_inference=True)
        result.sign_segments = new_sign
        result.phrase_segments = new_phrase
        result.latency_ms = float(latency_ms)
        result.decode_latency_ms = decode_latency_ms
        return result


__all__ = ["BioSegmentationModel", "StreamingBioSegmenter"]
