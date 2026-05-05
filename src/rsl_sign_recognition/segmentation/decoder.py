"""BIO probability decoder for sign and phrase segmentation."""

from __future__ import annotations

from collections.abc import Iterable

import numpy as np

from rsl_sign_recognition.segmentation.types import BioSegment

BIO_B = 0
BIO_I = 1
BIO_O = 2


def _validate_probs(probs: np.ndarray) -> np.ndarray:
    arr = np.asarray(probs, dtype=np.float32)
    if arr.ndim != 2 or arr.shape[1] != 3:
        raise ValueError(f"probs must have shape [T, 3], got {arr.shape}")
    if arr.shape[0] == 0:
        return np.zeros((0, 3), dtype=np.float32)
    if not np.all(np.isfinite(arr)):
        arr = np.nan_to_num(
            arr,
            nan=0.0,
            posinf=0.0,
            neginf=0.0,
        ).astype(np.float32)
    return np.ascontiguousarray(arr, dtype=np.float32)


def _segment_score(probs: np.ndarray, start: int, end: int) -> float:
    if end < start or probs.shape[0] == 0:
        return 0.0
    segment = probs[int(start) : int(end) + 1]
    if segment.size == 0:
        return 0.0
    confidence = np.maximum(segment[:, BIO_B], segment[:, BIO_I])
    return float(np.mean(confidence))


def _merge_with_gap(
    segments: Iterable[tuple[int, int]],
    merge_gap: int,
) -> list[tuple[int, int]]:
    items = sorted((int(start), int(end)) for start, end in segments if end >= start)
    if not items:
        return []
    if merge_gap <= 0:
        return items

    merged: list[tuple[int, int]] = [items[0]]
    for start, end in items[1:]:
        prev_start, prev_end = merged[-1]
        gap = int(start - prev_end - 1)
        if gap <= merge_gap:
            merged[-1] = (prev_start, max(prev_end, end))
            continue
        merged.append((start, end))
    return merged


def decode_segments(
    probs: np.ndarray,
    *,
    th_B: float,
    th_O: float,
    min_len: int = 1,
    max_len: int | None = None,
    merge_gap: int = 0,
) -> list[BioSegment]:
    """Decode per-frame BIO probabilities to inclusive segment boundaries."""

    p = _validate_probs(probs)
    if p.shape[0] == 0:
        return []

    th_b = float(th_B)
    th_o = float(th_O)
    min_length = max(1, int(min_len))
    max_length = max(1, int(max_len)) if max_len is not None else None
    gap = max(0, int(merge_gap))

    raw_segments: list[tuple[int, int]] = []
    active = False
    start = 0

    for idx in range(int(p.shape[0])):
        p_b = float(p[idx, BIO_B])
        p_o = float(p[idx, BIO_O])

        if not active:
            if p_b >= th_b:
                active = True
                start = idx
            continue

        if p_b >= th_b:
            raw_segments.append((start, idx - 1))
            start = idx
            continue

        if p_o >= th_o:
            raw_segments.append((start, idx - 1))
            active = False

    if active:
        raw_segments.append((start, int(p.shape[0]) - 1))

    output: list[BioSegment] = []
    for seg_start, seg_end in _merge_with_gap(raw_segments, gap):
        seg_len = int(seg_end - seg_start + 1)
        if seg_len < min_length:
            continue
        if max_length is not None and seg_len > max_length:
            seg_start = int(seg_end - max_length + 1)
            seg_len = max_length
        if seg_len < min_length:
            continue
        output.append(
            BioSegment(
                start=int(seg_start),
                end=int(seg_end),
                score=_segment_score(p, seg_start, seg_end),
            )
        )
    return output


__all__ = ["BIO_B", "BIO_I", "BIO_O", "decode_segments"]
