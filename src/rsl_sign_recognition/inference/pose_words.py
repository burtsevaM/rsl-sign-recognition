"""ONNXRuntime wrapper for the pose_words classifier."""

from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass
from numbers import Integral, Real
from pathlib import Path
from typing import Any, Sequence

import numpy as np


@dataclass(frozen=True, slots=True)
class PoseWordPrediction:
    """Top prediction plus the full probability vector for a feature clip."""

    index: int
    label: str
    probability: float
    probabilities: np.ndarray
    latency_ms: float


def _static_positive_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, Integral):
        parsed = int(value)
        return parsed if parsed > 0 else None
    if isinstance(value, Real):
        parsed_float = float(value)
        if parsed_float.is_integer() and parsed_float > 0:
            return int(parsed_float)
    return None


def _config_positive_int(payload: dict[str, Any], key: str) -> int | None:
    if key not in payload:
        return None
    parsed = _static_positive_int(payload[key])
    if parsed is None:
        raise ValueError(f"pose word config {key} must be a positive integer")
    return parsed


def _nested_dict(payload: dict[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key)
    return value if isinstance(value, dict) else {}


def _label_key(value: str) -> str:
    return (
        str(value)
        .strip()
        .lower()
        .replace(" ", "_")
        .replace("-", "_")
    )


def find_no_event_index(
    labels: Sequence[str],
    label_name: str = "no_event",
) -> int | None:
    """Return the first label index matching common no-event aliases."""

    wanted = str(label_name).strip().lower()
    aliases = {
        wanted,
        wanted.replace("-", "_"),
        wanted.replace("_", "-"),
        _label_key(wanted),
        "_no_event",
        "no_event",
        "no-event",
        "no event",
        "noevent",
        "none",
        "---",
        "background",
    }
    normalized_aliases = {_label_key(alias) for alias in aliases}

    for idx, label in enumerate(labels):
        raw = str(label).strip().lower()
        if raw in aliases or _label_key(raw) in normalized_aliases:
            return int(idx)
    return None


def _load_labels(path: Path) -> list[str]:
    labels: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if text:
            labels.append(text)
    return labels


def _to_probs(logits_or_probs: np.ndarray) -> np.ndarray:
    values = np.asarray(logits_or_probs, dtype=np.float32).reshape(-1)
    if values.size == 0:
        raise ValueError("pose word output must contain at least one class")
    if not np.all(np.isfinite(values)):
        values = np.nan_to_num(
            values,
            nan=0.0,
            posinf=0.0,
            neginf=0.0,
        ).astype(np.float32)

    total = float(values.sum())
    if (
        float(values.min()) >= 0.0
        and float(values.max()) <= 1.0
        and math.isclose(total, 1.0, rel_tol=1e-2, abs_tol=1e-2)
    ):
        return np.ascontiguousarray(values, dtype=np.float32)

    max_value = float(np.max(values))
    exp = np.exp(values - max_value)
    denom = float(exp.sum())
    if denom <= 0.0:
        probs = np.full_like(values, 1.0 / float(values.size), dtype=np.float32)
    else:
        probs = (exp / denom).astype(np.float32)
    if not np.all(np.isfinite(probs)):
        probs = np.nan_to_num(
            probs,
            nan=0.0,
            posinf=0.0,
            neginf=0.0,
        ).astype(np.float32)
    return np.ascontiguousarray(probs, dtype=np.float32)


class PoseWordOnnxModel:
    """Classifier wrapper for already prepared pose_words feature clips."""

    def __init__(
        self,
        *,
        model_path: str | Path,
        labels_path: str | Path,
        config_path: str | Path | None = None,
        ort_num_threads: int = 1,
        providers: Sequence[str] = ("CPUExecutionProvider",),
    ) -> None:
        self.model_path = Path(model_path)
        self.labels_path = Path(labels_path)
        self.config_path = Path(config_path) if config_path is not None else None
        if not self.model_path.is_file():
            raise FileNotFoundError(f"pose word ONNX model not found: {self.model_path}")
        if not self.labels_path.is_file():
            raise FileNotFoundError(f"pose word labels not found: {self.labels_path}")
        if self.config_path is not None and not self.config_path.is_file():
            raise FileNotFoundError(f"pose word config not found: {self.config_path}")

        self.labels = _load_labels(self.labels_path)
        if not self.labels:
            raise ValueError(f"pose word labels file is empty: {self.labels_path}")

        self.ort_num_threads = max(1, int(ort_num_threads))
        self.providers = tuple(providers)
        self.runtime_config: dict[str, Any] = {}
        self.config_labels_total: int | None = None
        self.config_clip_frames: int | None = None
        self.config_feature_dim: int | None = None
        self.input_clip_frames: int | None = None
        self.input_feature_dim: int | None = None
        self._session: Any = None
        self._input_name = ""
        self._output_name = ""

        if self.config_path is not None:
            self.runtime_config = self._load_runtime_config(self.config_path)
        self._validate_against_runtime_config()
        self._init_session()
        self._validate_against_runtime_config()

    def _load_runtime_config(self, path: Path) -> dict[str, Any]:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"pose word config must be valid JSON: {path}") from exc
        if not isinstance(payload, dict):
            raise ValueError(f"pose word config must be a JSON object: {path}")

        model_cfg = _nested_dict(payload, "model")
        input_cfg = _nested_dict(payload, "input")

        labels_total = _config_positive_int(payload, "labels_total")
        if labels_total is None:
            labels_total = _config_positive_int(model_cfg, "labels_total")

        clip_frames = _config_positive_int(payload, "clip_frames")
        if clip_frames is None:
            clip_frames = _config_positive_int(model_cfg, "clip_frames")

        input_dim = _config_positive_int(payload, "input_dim")
        if input_dim is None:
            input_dim = _config_positive_int(model_cfg, "input_dim")

        shape = input_cfg.get("shape")
        if isinstance(shape, list) and len(shape) >= 3:
            if clip_frames is None:
                clip_frames = _static_positive_int(shape[1])
            if input_dim is None:
                input_dim = _static_positive_int(shape[2])

        self.config_labels_total = labels_total
        self.config_clip_frames = clip_frames
        self.config_feature_dim = input_dim
        return payload

    def _init_session(self) -> None:
        try:
            import onnxruntime as ort
        except Exception as exc:  # pragma: no cover - optional runtime dependency
            raise ImportError(
                "onnxruntime is required for pose_words inference; "
                "install the pose-words-inference extra"
            ) from exc

        options = ort.SessionOptions()
        options.intra_op_num_threads = self.ort_num_threads
        options.inter_op_num_threads = 1
        if hasattr(ort, "ExecutionMode"):
            options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        if hasattr(ort, "GraphOptimizationLevel"):
            options.graph_optimization_level = (
                ort.GraphOptimizationLevel.ORT_ENABLE_ALL
            )
        options.log_severity_level = 3

        self._session = ort.InferenceSession(
            str(self.model_path),
            sess_options=options,
            providers=list(self.providers),
        )

        inputs = self._session.get_inputs()
        if not inputs:
            raise ValueError("pose word ONNX must define one rank-3 input")
        model_input = inputs[0]
        self._input_name = str(model_input.name)
        shape = tuple(model_input.shape)
        if len(shape) != 3:
            raise ValueError(f"pose word ONNX input must be rank-3 [B,T,F], got {shape}")
        self.input_clip_frames = _static_positive_int(shape[1])
        self.input_feature_dim = _static_positive_int(shape[2])

        outputs = self._session.get_outputs()
        if not outputs:
            raise ValueError("pose word ONNX must define one classifier output")
        self._output_name = str(outputs[0].name)

    def _validate_against_runtime_config(self) -> None:
        if (
            self.config_labels_total is not None
            and self.config_labels_total != len(self.labels)
        ):
            raise ValueError(
                "pose word labels size mismatch: "
                f"config={self.config_labels_total}, file={len(self.labels)}"
            )

        if (
            self.config_clip_frames is not None
            and self.input_clip_frames is not None
            and self.config_clip_frames != self.input_clip_frames
        ):
            raise ValueError(
                "pose word clip length mismatch between config and ONNX: "
                f"config={self.config_clip_frames}, onnx={self.input_clip_frames}"
            )

        if (
            self.config_feature_dim is not None
            and self.input_feature_dim is not None
            and self.config_feature_dim != self.input_feature_dim
        ):
            raise ValueError(
                "pose word feature dim mismatch between config and ONNX: "
                f"config={self.config_feature_dim}, onnx={self.input_feature_dim}"
            )

    def _sanitize_features(self, features_tf: np.ndarray) -> np.ndarray:
        features = np.asarray(features_tf, dtype=np.float32)
        if features.ndim != 2:
            raise ValueError(f"features must have shape [T, F], got {features.shape}")
        if features.shape[0] < 1:
            raise ValueError("features must contain at least one frame")
        if (
            self.input_clip_frames is not None
            and features.shape[0] != self.input_clip_frames
        ):
            raise ValueError(
                "pose word clip length mismatch: "
                f"expected {self.input_clip_frames}, got {features.shape[0]}"
            )
        if (
            self.input_feature_dim is not None
            and features.shape[1] != self.input_feature_dim
        ):
            raise ValueError(
                "pose word feature dim mismatch: "
                f"expected {self.input_feature_dim}, got {features.shape[1]}"
            )

        if not np.all(np.isfinite(features)):
            features = np.nan_to_num(
                features,
                nan=0.0,
                posinf=0.0,
                neginf=0.0,
            ).astype(np.float32)
        return np.ascontiguousarray(features, dtype=np.float32)

    def _normalize_output(self, raw_output: np.ndarray) -> np.ndarray:
        raw_shape = np.asarray(raw_output).shape
        output = np.asarray(raw_output, dtype=np.float32)
        if not np.all(np.isfinite(output)):
            output = np.nan_to_num(
                output,
                nan=0.0,
                posinf=0.0,
                neginf=0.0,
            ).astype(np.float32)

        if output.ndim == 3:
            if output.shape[0] != 1:
                raise ValueError(
                    f"pose word output batch dimension must be 1, got {raw_shape}"
                )
            if output.shape[1] < 1:
                raise ValueError(
                    f"pose word output temporal dimension is empty: {raw_shape}"
                )
            output = output[0].mean(axis=0)
        elif output.ndim == 2:
            if output.shape[0] != 1:
                raise ValueError(
                    f"pose word output batch dimension must be 1, got {raw_shape}"
                )
            output = output[0]
        elif output.ndim != 1:
            raise ValueError(f"unsupported pose word output shape: {raw_shape}")

        if output.shape[0] != len(self.labels):
            raise ValueError(
                f"pose word output size {output.shape[0]} does not match "
                f"labels size {len(self.labels)}"
            )
        return _to_probs(output)

    def find_no_event_index(self, label_name: str = "no_event") -> int | None:
        return find_no_event_index(self.labels, label_name)

    def infer_probs(self, features_tf: np.ndarray) -> tuple[np.ndarray, float]:
        features = self._sanitize_features(features_tf)
        x = np.expand_dims(features, axis=0).astype(np.float32, copy=False)
        x = np.ascontiguousarray(x, dtype=np.float32)

        started = time.perf_counter()
        outputs = self._session.run([self._output_name], {self._input_name: x})
        latency_ms = float((time.perf_counter() - started) * 1000.0)
        if not outputs:
            raise ValueError("pose word ONNX returned no outputs")

        probs = self._normalize_output(outputs[0])
        return probs, latency_ms

    def predict(self, features_tf: np.ndarray) -> PoseWordPrediction:
        probs, latency_ms = self.infer_probs(features_tf)
        index = int(np.argmax(probs))
        return PoseWordPrediction(
            index=index,
            label=self.labels[index],
            probability=float(probs[index]),
            probabilities=probs,
            latency_ms=float(latency_ms),
        )


__all__ = [
    "PoseWordOnnxModel",
    "PoseWordPrediction",
    "find_no_event_index",
]
