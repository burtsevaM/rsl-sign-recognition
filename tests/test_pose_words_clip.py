from __future__ import annotations

import numpy as np
import pytest

from rsl_sign_recognition.pipelines.pose_words.clip import resample_to_fixed_T


def test_resample_to_fixed_t_rejects_non_2d_input() -> None:
    with pytest.raises(ValueError, match=r"\[Tseg, F\]"):
        resample_to_fixed_T(np.zeros((2, 3, 4), dtype=np.float32), T=4)


def test_resample_to_fixed_t_empty_segment_returns_zeros() -> None:
    out = resample_to_fixed_T(np.zeros((0, 3), dtype=np.float32), T=4)

    assert out.shape == (4, 3)
    assert out.dtype == np.float32
    assert np.allclose(out, 0.0)


def test_resample_to_fixed_t_short_segment_repeats_last_frame() -> None:
    seg = np.asarray([[1.0, 2.0], [3.0, 4.0]], dtype=np.float32)

    out = resample_to_fixed_T(seg, T=4)

    assert out.dtype == np.float32
    assert np.allclose(
        out,
        [[1.0, 2.0], [3.0, 4.0], [3.0, 4.0], [3.0, 4.0]],
    )


def test_resample_to_fixed_t_long_segment_linear_resampling() -> None:
    seg = np.asarray([[0.0], [10.0], [20.0], [30.0], [40.0]], dtype=np.float32)

    out = resample_to_fixed_T(seg, T=3, method="linear")

    assert out.dtype == np.float32
    assert out.shape == (3, 1)
    assert np.allclose(out[:, 0], [0.0, 20.0, 40.0])


def test_resample_to_fixed_t_index_method_uses_nearest_indices() -> None:
    seg = np.asarray([[0.0], [10.0], [20.0], [30.0], [40.0]], dtype=np.float32)

    out = resample_to_fixed_T(seg, T=3, method="index")

    assert out.dtype == np.float32
    assert np.allclose(out[:, 0], [0.0, 20.0, 40.0])


def test_resample_to_fixed_t_sanitizes_nan_inf() -> None:
    seg = np.asarray(
        [[np.nan, np.inf], [1.0, -np.inf], [2.0, 3.0]],
        dtype=np.float32,
    )

    out = resample_to_fixed_T(seg, T=3)

    assert out.dtype == np.float32
    assert np.all(np.isfinite(out))
    assert np.allclose(out, [[0.0, 0.0], [1.0, 0.0], [2.0, 3.0]])


def test_resample_to_fixed_t_output_dtype_float32_when_input_is_float64() -> None:
    seg = np.asarray([[0.0, 1.0], [2.0, 3.0]], dtype=np.float64)

    out = resample_to_fixed_T(seg, T=2)

    assert out.dtype == np.float32
