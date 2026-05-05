"""Feature clip helpers for the pose_words classifier boundary."""

from __future__ import annotations

import numpy as np


def resample_to_fixed_T(
    seg: np.ndarray,
    T: int = 32,
    method: str = "linear",
) -> np.ndarray:
    """Resample an already extracted segment clip [Tseg, F] to [T, F]."""

    target = max(1, int(T))
    arr = np.asarray(seg, dtype=np.float32)
    if arr.ndim != 2:
        raise ValueError(f"seg must have shape [Tseg, F], got {arr.shape}")

    if arr.shape[0] == 0:
        return np.zeros((target, arr.shape[1]), dtype=np.float32)

    if not np.all(np.isfinite(arr)):
        arr = np.nan_to_num(
            arr,
            nan=0.0,
            posinf=0.0,
            neginf=0.0,
        ).astype(np.float32)

    tseg = int(arr.shape[0])
    feature_dim = int(arr.shape[1])
    if tseg == target:
        return np.ascontiguousarray(arr, dtype=np.float32).copy()

    if tseg < target:
        output = np.zeros((target, feature_dim), dtype=np.float32)
        output[:tseg] = arr
        output[tseg:] = arr[-1]
        return output

    mode = str(method).strip().lower()
    if mode == "index":
        idx = np.linspace(0, tseg - 1, num=target, dtype=np.float32)
        idx = np.clip(np.round(idx).astype(np.int32), 0, tseg - 1)
        return np.ascontiguousarray(arr[idx], dtype=np.float32)

    source_x = np.linspace(0, tseg - 1, num=tseg, dtype=np.float32)
    target_x = np.linspace(0, tseg - 1, num=target, dtype=np.float32)
    output = np.zeros((target, feature_dim), dtype=np.float32)
    for col in range(feature_dim):
        output[:, col] = np.interp(target_x, source_x, arr[:, col])
    if not np.all(np.isfinite(output)):
        output = np.nan_to_num(
            output,
            nan=0.0,
            posinf=0.0,
            neginf=0.0,
        ).astype(np.float32)
    return np.ascontiguousarray(output, dtype=np.float32)


__all__ = ["resample_to_fixed_T"]
