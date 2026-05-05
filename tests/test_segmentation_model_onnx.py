from __future__ import annotations

import json
import sys
import types
from pathlib import Path
from typing import Callable

import numpy as np
import pytest


class _FakeNode:
    def __init__(self, name: str, shape: tuple[object, ...] | None = None) -> None:
        self.name = name
        self.shape = shape or ()


class _FakeOptions:
    pass


def _install_fake_ort(
    monkeypatch: pytest.MonkeyPatch,
    *,
    input_shape: tuple[object, ...] = (1, None, 5),
    output_factory: Callable[[np.ndarray], list[np.ndarray]] | None = None,
) -> types.SimpleNamespace:
    fake_ort = types.SimpleNamespace()

    class FakeSession:
        def __init__(
            self,
            model_path: str,
            *,
            sess_options: object,
            providers: list[str],
        ) -> None:
            self.model_path = model_path
            self.sess_options = sess_options
            self.providers = providers
            self.last_input: np.ndarray | None = None
            fake_ort.last_session = self

        def get_inputs(self) -> list[_FakeNode]:
            return [_FakeNode("features", input_shape)]

        def get_outputs(self) -> list[_FakeNode]:
            return [_FakeNode("sign_probs"), _FakeNode("phrase_probs")]

        def run(
            self,
            output_names: list[str],
            inputs: dict[str, np.ndarray],
        ) -> list[np.ndarray]:
            del output_names
            self.last_input = inputs["features"]
            if output_factory is not None:
                return output_factory(self.last_input)
            t_frames = int(self.last_input.shape[1])
            sign = np.zeros((1, t_frames, 3), dtype=np.float32)
            sign[:, :, 2] = 1.0
            phrase = np.zeros((t_frames, 3), dtype=np.float32)
            phrase[:, 2] = 1.0
            return [sign, phrase]

    fake_ort.SessionOptions = _FakeOptions
    fake_ort.ExecutionMode = types.SimpleNamespace(ORT_SEQUENTIAL="sequential")
    fake_ort.GraphOptimizationLevel = types.SimpleNamespace(ORT_ENABLE_ALL="all")
    fake_ort.InferenceSession = FakeSession
    fake_ort.last_session = None
    monkeypatch.setitem(sys.modules, "onnxruntime", fake_ort)
    return fake_ort


def _write_model(path: Path) -> Path:
    path.write_bytes(b"fake-onnx")
    return path


def test_segmentation_package_import_does_not_require_onnxruntime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(sys.modules, "onnxruntime", None)

    import rsl_sign_recognition.segmentation as segmentation

    assert segmentation.BIO_B == 0


def test_bio_segmenter_onnx_missing_model_file_gives_clear_error(tmp_path: Path) -> None:
    from rsl_sign_recognition.segmentation.model_onnx import BioSegmenterOnnxModel

    with pytest.raises(FileNotFoundError, match="BIO segmenter ONNX model not found"):
        BioSegmenterOnnxModel(model_path=tmp_path / "missing.onnx")


def test_bio_segmenter_onnx_invalid_config_json_gives_clear_error(
    tmp_path: Path,
) -> None:
    from rsl_sign_recognition.segmentation.model_onnx import BioSegmenterOnnxModel

    model_path = _write_model(tmp_path / "model.onnx")
    config_path = tmp_path / "config.json"
    config_path.write_text("{", encoding="utf-8")

    with pytest.raises(ValueError, match="BIO config must be valid JSON"):
        BioSegmenterOnnxModel(model_path=model_path, config_path=config_path)


def test_bio_segmenter_onnx_config_input_dim_mismatch_gives_clear_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from rsl_sign_recognition.segmentation.model_onnx import BioSegmenterOnnxModel

    _install_fake_ort(monkeypatch, input_shape=(1, None, 5))
    model_path = _write_model(tmp_path / "model.onnx")
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({"input_dim": 4}), encoding="utf-8")

    with pytest.raises(ValueError, match="config=4, onnx=5"):
        BioSegmenterOnnxModel(model_path=model_path, config_path=config_path)


def test_bio_segmenter_onnx_fake_session_infer_shape_and_outputs(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from rsl_sign_recognition.segmentation.model_onnx import BioSegmenterOnnxModel

    def outputs(x: np.ndarray) -> list[np.ndarray]:
        t_frames = int(x.shape[1])
        sign_logits = np.tile(
            np.asarray([[[2.0, 1.0, -1.0]]], dtype=np.float32),
            (1, t_frames, 1),
        )
        phrase_probs = np.tile(
            np.asarray([[0.1, 0.2, 0.7]], dtype=np.float32),
            (t_frames, 1),
        )
        return [sign_logits, phrase_probs]

    fake_ort = _install_fake_ort(monkeypatch, output_factory=outputs)
    model_path = _write_model(tmp_path / "model.onnx")
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({"input_dim": 5}), encoding="utf-8")
    model = BioSegmenterOnnxModel(model_path=model_path, config_path=config_path)
    features = np.ones((4, 5), dtype=np.float32)
    features[1, 2] = np.nan

    sign_probs, phrase_probs, latency_ms = model.infer(features)

    assert sign_probs.shape == (4, 3)
    assert phrase_probs.shape == (4, 3)
    assert sign_probs.dtype == np.float32
    assert phrase_probs.dtype == np.float32
    assert np.allclose(sign_probs.sum(axis=1), 1.0)
    assert np.allclose(phrase_probs[0], [0.1, 0.2, 0.7])
    assert latency_ms >= 0.0
    assert fake_ort.last_session is not None
    assert fake_ort.last_session.last_input.shape == (1, 4, 5)
    assert np.all(np.isfinite(fake_ort.last_session.last_input))


def test_to_probs_handles_logits_probs_and_nan_inf() -> None:
    from rsl_sign_recognition.segmentation.model_onnx import _to_probs

    probs = _to_probs(np.asarray([[0.2, 0.3, 0.5]], dtype=np.float32))
    logits = _to_probs(np.asarray([[2.0, 1.0, -1.0]], dtype=np.float32))
    dirty = _to_probs(np.asarray([[np.nan, np.inf, -np.inf]], dtype=np.float32))

    assert np.allclose(probs, [[0.2, 0.3, 0.5]])
    assert np.allclose(logits.sum(axis=1), [1.0])
    assert dirty.shape == (1, 3)
    assert np.all(np.isfinite(dirty))
    assert np.allclose(dirty.sum(axis=1), [1.0])
