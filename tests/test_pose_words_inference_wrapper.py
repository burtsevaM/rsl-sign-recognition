from __future__ import annotations

import importlib
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
    input_shape: tuple[object, ...] = (1, 4, 5),
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
            return [_FakeNode("logits")]

        def run(
            self,
            output_names: list[str],
            inputs: dict[str, np.ndarray],
        ) -> list[np.ndarray]:
            assert output_names == ["logits"]
            self.last_input = inputs["features"]
            if output_factory is not None:
                return output_factory(self.last_input)
            return [np.asarray([[0.1, 0.2, 0.7]], dtype=np.float32)]

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


def _write_labels(path: Path, labels: list[str] | None = None) -> Path:
    path.write_text(
        "\n".join(labels or ["hello", "thanks", "background"]),
        encoding="utf-8",
    )
    return path


def _write_config(path: Path, payload: object) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _build_model(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    input_shape: tuple[object, ...] = (1, 4, 5),
    labels: list[str] | None = None,
    config: object | None = None,
    output_factory: Callable[[np.ndarray], list[np.ndarray]] | None = None,
):
    from rsl_sign_recognition.inference.pose_words import PoseWordOnnxModel

    _install_fake_ort(
        monkeypatch,
        input_shape=input_shape,
        output_factory=output_factory,
    )
    model_path = _write_model(tmp_path / "model.onnx")
    labels_path = _write_labels(tmp_path / "labels.txt", labels)
    config_path = (
        _write_config(tmp_path / "config.json", config)
        if config is not None
        else None
    )
    return PoseWordOnnxModel(
        model_path=model_path,
        labels_path=labels_path,
        config_path=config_path,
    )


def test_inference_package_import_does_not_require_onnxruntime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(sys.modules, "onnxruntime", None)
    sys.modules.pop("rsl_sign_recognition.inference", None)
    sys.modules.pop("rsl_sign_recognition.inference.pose_words", None)

    inference = importlib.import_module("rsl_sign_recognition.inference")

    assert inference.PoseWordOnnxModel.__name__ == "PoseWordOnnxModel"


def test_pose_word_onnx_missing_model_file_gives_clear_error(tmp_path: Path) -> None:
    from rsl_sign_recognition.inference.pose_words import PoseWordOnnxModel

    labels_path = _write_labels(tmp_path / "labels.txt")

    with pytest.raises(FileNotFoundError, match="pose word ONNX model not found"):
        PoseWordOnnxModel(model_path=tmp_path / "missing.onnx", labels_path=labels_path)


def test_pose_word_onnx_missing_labels_file_gives_clear_error(tmp_path: Path) -> None:
    from rsl_sign_recognition.inference.pose_words import PoseWordOnnxModel

    model_path = _write_model(tmp_path / "model.onnx")

    with pytest.raises(FileNotFoundError, match="pose word labels not found"):
        PoseWordOnnxModel(model_path=model_path, labels_path=tmp_path / "missing.txt")


def test_pose_word_onnx_missing_config_file_gives_clear_error(tmp_path: Path) -> None:
    from rsl_sign_recognition.inference.pose_words import PoseWordOnnxModel

    model_path = _write_model(tmp_path / "model.onnx")
    labels_path = _write_labels(tmp_path / "labels.txt")

    with pytest.raises(FileNotFoundError, match="pose word config not found"):
        PoseWordOnnxModel(
            model_path=model_path,
            labels_path=labels_path,
            config_path=tmp_path / "missing.json",
        )


def test_pose_word_onnx_empty_labels_file_gives_clear_error(tmp_path: Path) -> None:
    from rsl_sign_recognition.inference.pose_words import PoseWordOnnxModel

    model_path = _write_model(tmp_path / "model.onnx")
    labels_path = tmp_path / "labels.txt"
    labels_path.write_text("\n", encoding="utf-8")

    with pytest.raises(ValueError, match="pose word labels file is empty"):
        PoseWordOnnxModel(model_path=model_path, labels_path=labels_path)


def test_pose_word_onnx_invalid_config_json_gives_clear_error(tmp_path: Path) -> None:
    from rsl_sign_recognition.inference.pose_words import PoseWordOnnxModel

    model_path = _write_model(tmp_path / "model.onnx")
    labels_path = _write_labels(tmp_path / "labels.txt")
    config_path = tmp_path / "config.json"
    config_path.write_text("{", encoding="utf-8")

    with pytest.raises(ValueError, match="pose word config must be valid JSON"):
        PoseWordOnnxModel(
            model_path=model_path,
            labels_path=labels_path,
            config_path=config_path,
        )


def test_pose_word_onnx_config_must_be_json_object(tmp_path: Path) -> None:
    from rsl_sign_recognition.inference.pose_words import PoseWordOnnxModel

    model_path = _write_model(tmp_path / "model.onnx")
    labels_path = _write_labels(tmp_path / "labels.txt")
    config_path = _write_config(tmp_path / "config.json", [])

    with pytest.raises(ValueError, match="pose word config must be a JSON object"):
        PoseWordOnnxModel(
            model_path=model_path,
            labels_path=labels_path,
            config_path=config_path,
        )


def test_pose_word_onnx_labels_total_mismatch_gives_clear_error(
    tmp_path: Path,
) -> None:
    from rsl_sign_recognition.inference.pose_words import PoseWordOnnxModel

    model_path = _write_model(tmp_path / "model.onnx")
    labels_path = _write_labels(tmp_path / "labels.txt", ["a", "b"])
    config_path = _write_config(tmp_path / "config.json", {"labels_total": 3})

    with pytest.raises(ValueError, match="config=3, file=2"):
        PoseWordOnnxModel(
            model_path=model_path,
            labels_path=labels_path,
            config_path=config_path,
        )


def test_pose_word_onnx_config_clip_frames_mismatch_gives_clear_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from rsl_sign_recognition.inference.pose_words import PoseWordOnnxModel

    _install_fake_ort(monkeypatch, input_shape=(1, 5, 5))
    model_path = _write_model(tmp_path / "model.onnx")
    labels_path = _write_labels(tmp_path / "labels.txt")
    config_path = _write_config(tmp_path / "config.json", {"clip_frames": 4})

    with pytest.raises(ValueError, match="config=4, onnx=5"):
        PoseWordOnnxModel(
            model_path=model_path,
            labels_path=labels_path,
            config_path=config_path,
        )


def test_pose_word_onnx_config_input_dim_mismatch_gives_clear_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from rsl_sign_recognition.inference.pose_words import PoseWordOnnxModel

    _install_fake_ort(monkeypatch, input_shape=(1, 4, 5))
    model_path = _write_model(tmp_path / "model.onnx")
    labels_path = _write_labels(tmp_path / "labels.txt")
    config_path = _write_config(tmp_path / "config.json", {"input_dim": 4})

    with pytest.raises(ValueError, match="config=4, onnx=5"):
        PoseWordOnnxModel(
            model_path=model_path,
            labels_path=labels_path,
            config_path=config_path,
        )


def test_pose_word_onnx_input_rank_must_be_btf(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from rsl_sign_recognition.inference.pose_words import PoseWordOnnxModel

    _install_fake_ort(monkeypatch, input_shape=(1, 5))
    model_path = _write_model(tmp_path / "model.onnx")
    labels_path = _write_labels(tmp_path / "labels.txt")

    with pytest.raises(ValueError, match=r"rank-3 \[B,T,F\]"):
        PoseWordOnnxModel(model_path=model_path, labels_path=labels_path)


def test_pose_word_infer_probs_rejects_wrong_rank(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    model = _build_model(monkeypatch, tmp_path)

    with pytest.raises(ValueError, match=r"\[T, F\]"):
        model.infer_probs(np.zeros((4, 5, 1), dtype=np.float32))


def test_pose_word_infer_probs_rejects_empty_clip(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    model = _build_model(monkeypatch, tmp_path)

    with pytest.raises(ValueError, match="at least one frame"):
        model.infer_probs(np.zeros((0, 5), dtype=np.float32))


def test_pose_word_infer_probs_rejects_wrong_static_t_or_f(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    model = _build_model(monkeypatch, tmp_path, input_shape=(1, 4, 5))

    with pytest.raises(ValueError, match="clip length mismatch"):
        model.infer_probs(np.zeros((3, 5), dtype=np.float32))
    with pytest.raises(ValueError, match="feature dim mismatch"):
        model.infer_probs(np.zeros((4, 4), dtype=np.float32))


def test_pose_word_infer_probs_sanitizes_nan_inf_before_session(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    fake_ort = _install_fake_ort(monkeypatch, input_shape=(1, 4, 5))
    from rsl_sign_recognition.inference.pose_words import PoseWordOnnxModel

    model_path = _write_model(tmp_path / "model.onnx")
    labels_path = _write_labels(tmp_path / "labels.txt")
    model = PoseWordOnnxModel(model_path=model_path, labels_path=labels_path)
    features = np.ones((4, 5), dtype=np.float32)
    features[0, 0] = np.nan
    features[1, 1] = np.inf
    features[2, 2] = -np.inf

    probs, latency_ms = model.infer_probs(features)

    assert np.allclose(probs, [0.1, 0.2, 0.7])
    assert latency_ms >= 0.0
    assert fake_ort.last_session is not None
    assert fake_ort.last_session.last_input.shape == (1, 4, 5)
    assert np.all(np.isfinite(fake_ort.last_session.last_input))
    assert fake_ort.last_session.last_input[0, 0, 0] == 0.0
    assert fake_ort.last_session.last_input[0, 1, 1] == 0.0
    assert fake_ort.last_session.last_input[0, 2, 2] == 0.0


def test_pose_word_infer_probs_output_size_mismatch_gives_clear_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    def outputs(_: np.ndarray) -> list[np.ndarray]:
        return [np.asarray([[0.2, 0.3, 0.5]], dtype=np.float32)]

    model = _build_model(
        monkeypatch,
        tmp_path,
        labels=["a", "b"],
        output_factory=outputs,
    )

    with pytest.raises(ValueError, match="does not match labels size 2"):
        model.infer_probs(np.zeros((4, 5), dtype=np.float32))


def test_pose_word_infer_probs_logits_output_becomes_probabilities(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    def outputs(_: np.ndarray) -> list[np.ndarray]:
        return [np.asarray([[2.0, 1.0, -1.0]], dtype=np.float32)]

    model = _build_model(monkeypatch, tmp_path, output_factory=outputs)

    probs, _ = model.infer_probs(np.zeros((4, 5), dtype=np.float32))

    assert probs.dtype == np.float32
    assert np.allclose(probs.sum(), 1.0)
    assert probs[0] > probs[1] > probs[2]


def test_pose_word_infer_probs_probability_like_output_is_preserved(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    def outputs(_: np.ndarray) -> list[np.ndarray]:
        return [np.asarray([[0.1, 0.2, 0.7]], dtype=np.float32)]

    model = _build_model(monkeypatch, tmp_path, output_factory=outputs)

    probs, _ = model.infer_probs(np.zeros((4, 5), dtype=np.float32))

    assert np.allclose(probs, [0.1, 0.2, 0.7])


def test_pose_word_infer_probs_normalizes_temporal_output_rank(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    def outputs(_: np.ndarray) -> list[np.ndarray]:
        return [
            np.asarray(
                [[[0.2, 0.8, 0.0], [0.4, 0.6, 0.0]]],
                dtype=np.float32,
            )
        ]

    model = _build_model(monkeypatch, tmp_path, output_factory=outputs)

    probs, _ = model.infer_probs(np.zeros((4, 5), dtype=np.float32))

    assert np.allclose(probs, [0.3, 0.7, 0.0])


def test_pose_word_infer_probs_unsupported_output_rank_gives_clear_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    def outputs(_: np.ndarray) -> list[np.ndarray]:
        return [np.zeros((1, 1, 1, 3), dtype=np.float32)]

    model = _build_model(monkeypatch, tmp_path, output_factory=outputs)

    with pytest.raises(ValueError, match="unsupported pose word output shape"):
        model.infer_probs(np.zeros((4, 5), dtype=np.float32))


def test_pose_word_find_no_event_index_handles_aliases(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from rsl_sign_recognition.inference.pose_words import find_no_event_index

    assert find_no_event_index(["hello", "background"]) == 1
    assert find_no_event_index(["hello", "NO-EVENT"]) == 1
    assert find_no_event_index(["---", "hello"]) == 0
    assert find_no_event_index(["hello", "none"]) == 1
    assert find_no_event_index(["hello", "thanks"]) is None

    model = _build_model(
        monkeypatch,
        tmp_path,
        labels=["hello", "_no_event", "thanks"],
    )
    assert model.find_no_event_index("no-event") == 1


def test_pose_word_predict_returns_top_label(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    model = _build_model(monkeypatch, tmp_path)

    prediction = model.predict(np.zeros((4, 5), dtype=np.float32))

    assert prediction.index == 2
    assert prediction.label == "background"
    assert prediction.probability == pytest.approx(0.7)
    assert np.allclose(prediction.probabilities, [0.1, 0.2, 0.7])
