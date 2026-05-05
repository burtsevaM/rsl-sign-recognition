"""ONNXRuntime wrapper for BIO segmentation models."""

from __future__ import annotations

import json
from dataclasses import dataclass
from numbers import Integral
from pathlib import Path
from typing import Any, Sequence
import time

import numpy as np


@dataclass(frozen=True, slots=True)
class BioThresholdConfig:
    sign_th_b: float = 0.5
    sign_th_o: float = 0.5
    phrase_th_b: float = 0.5
    phrase_th_o: float = 0.5

    def to_dict(self) -> dict[str, float]:
        return {
            "sign_th_b": float(self.sign_th_b),
            "sign_th_o": float(self.sign_th_o),
            "phrase_th_b": float(self.phrase_th_b),
            "phrase_th_o": float(self.phrase_th_o),
        }


def _to_probs(logits_or_probs: np.ndarray) -> np.ndarray:
    arr = np.asarray(logits_or_probs, dtype=np.float32)
    if arr.ndim != 2 or arr.shape[1] != 3:
        raise ValueError(f"BIO output must have shape [T, 3], got {arr.shape}")
    if not np.all(np.isfinite(arr)):
        arr = np.nan_to_num(
            arr,
            nan=0.0,
            posinf=0.0,
            neginf=0.0,
        ).astype(np.float32)

    row_sums = arr.sum(axis=1)
    if np.all((arr >= 0.0) & (arr <= 1.0)) and np.allclose(
        row_sums,
        1.0,
        atol=1e-2,
    ):
        return np.ascontiguousarray(arr, dtype=np.float32)

    max_value = np.max(arr, axis=1, keepdims=True)
    exp = np.exp(arr - max_value)
    denom = np.maximum(exp.sum(axis=1, keepdims=True), 1e-9)
    probs = (exp / denom).astype(np.float32)
    if not np.all(np.isfinite(probs)):
        probs = np.nan_to_num(
            probs,
            nan=0.0,
            posinf=0.0,
            neginf=0.0,
        ).astype(np.float32)
    return np.ascontiguousarray(probs, dtype=np.float32)


def _static_positive_int(value: object) -> int | None:
    if isinstance(value, Integral):
        parsed = int(value)
        return parsed if parsed > 0 else None
    return None


class BioSegmenterOnnxModel:
    """Segmentation-specific ONNX wrapper returning BIO probabilities."""

    def __init__(
        self,
        *,
        model_path: str | Path,
        config_path: str | Path | None = None,
        ort_num_threads: int = 1,
        providers: Sequence[str] = ("CPUExecutionProvider",),
    ) -> None:
        self.model_path = Path(model_path)
        self.config_path = Path(config_path) if config_path is not None else None
        if not self.model_path.is_file():
            raise FileNotFoundError(
                f"BIO segmenter ONNX model not found: {self.model_path}"
            )
        if self.config_path is not None and not self.config_path.is_file():
            raise FileNotFoundError(
                f"BIO segmenter config not found: {self.config_path}"
            )

        self.ort_num_threads = max(1, int(ort_num_threads))
        self.providers = tuple(providers)
        self.runtime_config: dict[str, Any] = {}
        self.config_feature_dim: int | None = None
        self.input_feature_dim: int | None = None
        self._session: Any = None
        self._input_name = ""
        self._sign_output_name = ""
        self._phrase_output_name = ""

        if self.config_path is not None:
            self.runtime_config = self._load_runtime_config(self.config_path)
        self._init_session()
        self._validate_against_runtime_config()

    def _load_runtime_config(self, path: Path) -> dict[str, Any]:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"BIO config must be valid JSON: {path}") from exc
        if not isinstance(payload, dict):
            raise ValueError(f"BIO config must be a JSON object: {path}")

        input_dim = payload.get("input_dim")
        if input_dim is not None:
            parsed = _static_positive_int(input_dim)
            if parsed is None:
                raise ValueError("BIO config input_dim must be a positive integer")
            self.config_feature_dim = parsed
        return payload

    def _init_session(self) -> None:
        try:
            import onnxruntime as ort
        except Exception as exc:  # pragma: no cover - optional runtime dependency
            raise ImportError(
                "onnxruntime is required for BIO segmenter inference; "
                "install the segmentation extra"
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
            raise ValueError("BIO segmenter ONNX must define one rank-3 input")
        model_input = inputs[0]
        self._input_name = str(model_input.name)
        shape = tuple(model_input.shape)
        if len(shape) != 3:
            raise ValueError(f"BIO segmenter input must be rank-3 [B,T,F], got {shape}")
        self.input_feature_dim = _static_positive_int(shape[-1])

        outputs = self._session.get_outputs()
        if len(outputs) < 2:
            raise ValueError(
                "BIO segmenter ONNX must have two outputs: sign_probs, phrase_probs"
            )
        self._sign_output_name = str(outputs[0].name)
        self._phrase_output_name = str(outputs[1].name)

    def _validate_against_runtime_config(self) -> None:
        if self.config_feature_dim is None or self.input_feature_dim is None:
            return
        if int(self.config_feature_dim) != int(self.input_feature_dim):
            raise ValueError(
                "BIO feature dim mismatch between config and ONNX: "
                f"config={self.config_feature_dim}, onnx={self.input_feature_dim}"
            )

    def _sanitize_features(self, features_tf: np.ndarray) -> np.ndarray:
        features = np.asarray(features_tf, dtype=np.float32)
        if features.ndim != 2:
            raise ValueError(f"features must have shape [T, F], got {features.shape}")
        if features.shape[0] < 1:
            raise ValueError("features must contain at least one frame")
        if self.input_feature_dim is not None and features.shape[1] != self.input_feature_dim:
            raise ValueError(
                "BIO segmenter feature dim mismatch: "
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

    def _squeeze_output(self, output: np.ndarray, *, expected_t: int) -> np.ndarray:
        arr = np.asarray(output, dtype=np.float32)
        if arr.ndim == 3:
            if arr.shape[0] != 1:
                raise ValueError(
                    f"BIO output batch dimension must be 1, got {arr.shape}"
                )
            arr = arr[0]
        probs = _to_probs(arr)
        if probs.shape[0] != expected_t:
            raise ValueError(
                f"BIO output frame count mismatch: expected {expected_t}, "
                f"got {probs.shape[0]}"
            )
        return probs

    def infer(self, features_tf: np.ndarray) -> tuple[np.ndarray, np.ndarray, float]:
        features = self._sanitize_features(features_tf)
        x = np.expand_dims(features, axis=0).astype(np.float32, copy=False)
        x = np.ascontiguousarray(x, dtype=np.float32)

        started = time.perf_counter()
        outputs = self._session.run(
            [self._sign_output_name, self._phrase_output_name],
            {self._input_name: x},
        )
        latency_ms = float((time.perf_counter() - started) * 1000.0)
        if len(outputs) < 2:
            raise ValueError("BIO segmenter ONNX returned fewer than two outputs")

        expected_t = int(features.shape[0])
        sign_probs = self._squeeze_output(outputs[0], expected_t=expected_t)
        phrase_probs = self._squeeze_output(outputs[1], expected_t=expected_t)
        return sign_probs, phrase_probs, latency_ms


def load_bio_thresholds(path: str | Path | None) -> BioThresholdConfig:
    if path is None:
        return BioThresholdConfig()

    threshold_path = Path(path)
    if not threshold_path.is_file():
        return BioThresholdConfig()

    try:
        payload = json.loads(threshold_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"BIO thresholds must be valid JSON: {threshold_path}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"BIO thresholds must be a JSON object: {threshold_path}")

    sign = payload.get("sign", {})
    phrase = payload.get("phrase", {})
    if not isinstance(sign, dict):
        sign = {}
    if not isinstance(phrase, dict):
        phrase = {}

    return BioThresholdConfig(
        sign_th_b=float(sign.get("th_b", 0.5)),
        sign_th_o=float(sign.get("th_o", 0.5)),
        phrase_th_b=float(phrase.get("th_b", 0.5)),
        phrase_th_o=float(phrase.get("th_o", 0.5)),
    )


__all__ = [
    "BioSegmenterOnnxModel",
    "BioThresholdConfig",
    "_to_probs",
    "load_bio_thresholds",
]
