#!/usr/bin/env python3
"""Train and export the MODEL-01 demo gesture active classifier pack."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import sys
import tempfile
import time
from typing import Any, Iterable, Sequence
import zipfile

import numpy as np


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from rsl_sign_recognition.pipelines.pose_words.clip import (  # noqa: E402
    resample_to_fixed_T,
)
from rsl_sign_recognition.pipelines.pose_words.pose_extraction import (  # noqa: E402
    PoseExtractor,
    PoseExtractorConfig,
)
from rsl_sign_recognition.pipelines.pose_words.service import (  # noqa: E402
    PoseFeatureService,
    PoseFeatureServiceConfig,
)


DEFAULT_CONFIG = Path("configs/demo_gestures_classifier.json")
DEFAULT_FEATURE_CACHE = Path(".cache/demo_gestures_classifier/features")
NO_EVENT_LABEL = "_no_event"
LIVE_SMOKE_SAMPLE_IDS = {
    "slovo_da_2b1b2857",
    "slovo_dom_524d6b8f",
    "slovo_horosho_43791c91",
    "slovo_ploho_27560a7e",
    "slovo_poka_8ba230dc",
    "slovo_privet_f17a6060",
    "slovo_rabotat_ffce2323",
    "slovo_ulica_908f133b",
    "slovo_utro_c1766b2e",
    "slovo_voda_90db4617",
}


@dataclass(frozen=True, slots=True)
class DemoSample:
    sample_id: str
    label: str
    source_label: str
    split: str
    source_path: str
    byte_size: int
    sha256: str


@dataclass(frozen=True, slots=True)
class FeatureRecord:
    sample: DemoSample
    features: np.ndarray
    frames_read: int
    feature_frames: int
    hand_frames: int
    cache_hit: bool


@dataclass(frozen=True, slots=True)
class PreparedClip:
    sample_id: str
    label: str
    split: str
    window_kind: str
    features: np.ndarray
    source_feature_frames: int


@dataclass(frozen=True, slots=True)
class LinearClassifier:
    labels: tuple[str, ...]
    feature_projection: str
    mean: np.ndarray
    scale: np.ndarray
    weights: np.ndarray
    bias: np.ndarray
    logit_scale: float


def repo_path(value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else (REPO_ROOT / path)


def repo_display(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return str(path)


def read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON payload must be an object: {path}")
    return payload


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Train/export the demo gestures pose_words active classifier pack."
    )
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG),
        help="Repo-relative JSON training config.",
    )
    parser.add_argument(
        "--slovo-root",
        default=None,
        help="Local Slovo root directory or slovo.zip. Defaults to config, env, or data/slovo.",
    )
    parser.add_argument(
        "--feature-cache",
        default=str(DEFAULT_FEATURE_CACHE),
        help="Repo-relative cache directory for extracted feature arrays.",
    )
    parser.add_argument(
        "--refresh-cache",
        action="store_true",
        help="Re-extract features even when cache entries exist.",
    )
    parser.add_argument(
        "--no-verify-source",
        action="store_true",
        help="Skip source byte_size/sha256 verification before feature extraction.",
    )
    parser.add_argument(
        "--output-root",
        default=None,
        help="Override active output root. Defaults to config active_output_root.",
    )
    parser.add_argument(
        "--report-json",
        default=None,
        help="Override report JSON path. Defaults to config report_json.",
    )
    return parser


def expected_labels(config: dict[str, Any]) -> list[str]:
    labels = config.get("labels")
    if not isinstance(labels, list) or not all(
        isinstance(label, str) and label for label in labels
    ):
        raise ValueError("config.labels must be a non-empty list of strings")
    if labels[0] != NO_EVENT_LABEL:
        raise ValueError("config.labels must start with _no_event")
    if len(set(labels)) != len(labels):
        raise ValueError("config.labels must not contain duplicates")
    return list(labels)


def load_materialized_samples(
    manifest_path: Path,
    *,
    labels: Sequence[str],
) -> tuple[list[DemoSample], dict[str, Any]]:
    manifest = read_json(manifest_path)
    samples_raw = manifest.get("samples")
    if not isinstance(samples_raw, list) or not samples_raw:
        raise ValueError(f"materialized manifest has no samples: {manifest_path}")

    target_labels = [label for label in labels if label != NO_EVENT_LABEL]
    if list(manifest.get("target_gestures", [])) != target_labels:
        raise ValueError("materialized target_gestures do not match config.labels")

    counts = manifest.get("materialized_counts")
    if not isinstance(counts, dict):
        raise ValueError("materialized manifest is missing materialized_counts")
    for label in labels:
        item = counts.get(label)
        if not isinstance(item, dict):
            raise ValueError(f"missing materialized count for label: {label}")
        if int(item.get("train", 0)) <= 0 or int(item.get("validation", 0)) <= 0:
            raise ValueError(f"label has no train/validation records: {label}")

    parsed: list[DemoSample] = []
    seen_ids: set[str] = set()
    for item in samples_raw:
        if not isinstance(item, dict):
            continue
        sample = DemoSample(
            sample_id=str(item["sample_id"]),
            label=str(item["label"]),
            source_label=str(item.get("source_label", item["label"])),
            split=str(item["split"]),
            source_path=str(item["source_path"]),
            byte_size=int(item["byte_size"]),
            sha256=str(item["sha256"]),
        )
        if sample.sample_id in LIVE_SMOKE_SAMPLE_IDS:
            raise ValueError(f"live smoke sample leaked into train/validation: {sample.sample_id}")
        if sample.sample_id in seen_ids:
            raise ValueError(f"duplicate sample_id in materialized manifest: {sample.sample_id}")
        if sample.label not in labels:
            raise ValueError(f"sample label is outside configured labels: {sample.label}")
        if sample.split not in {"train", "validation"}:
            raise ValueError(f"sample split must be train or validation: {sample.sample_id}")
        if len(sample.sha256) != 64:
            raise ValueError(f"sample sha256 is invalid: {sample.sample_id}")
        seen_ids.add(sample.sample_id)
        parsed.append(sample)
    return parsed, manifest


def resolve_slovo_archive(path_text: str | None, config: dict[str, Any]) -> Path:
    candidates: list[Path] = []
    if path_text:
        candidates.append(Path(path_text).expanduser())
    env_path = os.environ.get("SLOVO_DATA_ROOT")
    if env_path:
        candidates.append(Path(env_path).expanduser())
    config_root = config.get("slovo_root")
    if isinstance(config_root, str) and config_root:
        candidates.append(repo_path(config_root).expanduser())
    candidates.append(REPO_ROOT / "data/slovo")

    for candidate in candidates:
        resolved = candidate.resolve(strict=False)
        if resolved.is_file() and resolved.name.endswith(".zip"):
            return resolved
        archive = resolved / "slovo.zip"
        if archive.is_file():
            return archive.resolve()
    formatted = ", ".join(str(path) for path in candidates)
    raise FileNotFoundError(f"could not find local slovo.zip in: {formatted}")


def source_member_path(sample: DemoSample) -> str:
    if "::" not in sample.source_path:
        raise ValueError(f"sample source_path must point into slovo.zip: {sample.sample_id}")
    return sample.source_path.split("::", 1)[1].lstrip("/")


def verify_sources(samples: Sequence[DemoSample], archive_path: Path) -> dict[str, Any]:
    checked = 0
    with zipfile.ZipFile(archive_path) as archive:
        names = set(archive.namelist())
        for sample in samples:
            member = source_member_path(sample)
            if member not in names:
                raise FileNotFoundError(f"missing zip member for {sample.sample_id}: {member}")
            data = archive.read(member)
            if len(data) != sample.byte_size:
                raise ValueError(
                    f"byte_size mismatch for {sample.sample_id}: "
                    f"manifest={sample.byte_size}, actual={len(data)}"
                )
            digest = sha256_bytes(data)
            if digest != sample.sha256:
                raise ValueError(
                    f"sha256 mismatch for {sample.sample_id}: "
                    f"manifest={sample.sha256}, actual={digest}"
                )
            checked += 1
    return {"archive": str(archive_path), "checked_samples": checked}


def cache_key(sample: DemoSample, config: dict[str, Any]) -> str:
    feature_cfg = config["feature_extraction"]
    payload = {
        "sample_id": sample.sample_id,
        "sha256": sample.sha256,
        "feature_extraction": feature_cfg,
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:16]


def read_cached_features(path: Path, sample: DemoSample) -> FeatureRecord | None:
    if not path.is_file():
        return None
    data = np.load(path, allow_pickle=False)
    features = np.asarray(data["features"], dtype=np.float32)
    return FeatureRecord(
        sample=sample,
        features=np.ascontiguousarray(features, dtype=np.float32),
        frames_read=int(data["frames_read"]),
        feature_frames=int(data["feature_frames"]),
        hand_frames=int(data["hand_frames"]),
        cache_hit=True,
    )


def write_cached_features(path: Path, record: FeatureRecord) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        path,
        features=record.features.astype(np.float32),
        frames_read=np.asarray(record.frames_read, dtype=np.int64),
        feature_frames=np.asarray(record.feature_frames, dtype=np.int64),
        hand_frames=np.asarray(record.hand_frames, dtype=np.int64),
    )


def iter_video_frames(video_path: Path) -> Iterable[np.ndarray]:
    try:
        import imageio.v3 as imageio_v3
    except ImportError as exc:
        raise ImportError("imageio is required for video feature extraction") from exc
    yield from imageio_v3.imiter(video_path)


def extract_features_from_video(
    video_path: Path,
    sample: DemoSample,
    service: PoseFeatureService,
    *,
    gesture_requires_hand: bool,
) -> FeatureRecord:
    features: list[np.ndarray] = []
    frames_read = 0
    hand_frames = 0
    for frame in iter_video_frames(video_path):
        rgb = np.asarray(frame)
        if rgb.ndim == 3 and rgb.shape[2] == 4:
            rgb = rgb[:, :, :3]
        if rgb.dtype != np.uint8:
            rgb = rgb.astype(np.uint8)
        result = service.process_rgb_frame(rgb)
        frames_read += 1
        if result.feature_vector is None:
            continue
        if result.hand_present:
            hand_frames += 1
        if sample.label != NO_EVENT_LABEL and gesture_requires_hand and not result.hand_present:
            continue
        features.append(result.feature_vector.astype(np.float32))

    if features:
        matrix = np.stack(features, axis=0).astype(np.float32)
    else:
        feature_dim = int(service.config.upper_body_indices.__len__() + 42) * 3
        matrix = np.zeros((0, feature_dim), dtype=np.float32)
    return FeatureRecord(
        sample=sample,
        features=np.ascontiguousarray(matrix, dtype=np.float32),
        frames_read=frames_read,
        feature_frames=int(matrix.shape[0]),
        hand_frames=hand_frames,
        cache_hit=False,
    )


def extract_features(
    samples: Sequence[DemoSample],
    *,
    archive_path: Path,
    config: dict[str, Any],
    cache_dir: Path,
    refresh_cache: bool,
) -> tuple[list[FeatureRecord], list[dict[str, Any]]]:
    feature_cfg = config["feature_extraction"]
    extractor_config = PoseExtractorConfig(
        model_complexity=int(feature_cfg["model_complexity"]),
        min_detection_confidence=float(feature_cfg["min_detection_confidence"]),
        min_tracking_confidence=float(feature_cfg["min_tracking_confidence"]),
    )
    service_config = PoseFeatureServiceConfig(
        apply_shoulder_norm=bool(feature_cfg["apply_shoulder_norm"]),
        hide_legs_before_body=bool(feature_cfg["hide_legs_before_body"]),
        canonical_hands_3d=bool(feature_cfg["canonical_hands_3d"]),
    )
    gesture_requires_hand = bool(feature_cfg.get("gesture_requires_hand", True))
    failures: list[dict[str, Any]] = []
    records: list[FeatureRecord] = []

    with tempfile.TemporaryDirectory(prefix="rsl_demo_gestures_") as tmp_dir_text:
        tmp_dir = Path(tmp_dir_text)
        with zipfile.ZipFile(archive_path) as archive, PoseExtractor(extractor_config) as extractor:
            service = PoseFeatureService(extractor=extractor, config=service_config)
            for index, sample in enumerate(samples, start=1):
                key = cache_key(sample, config)
                cache_path = cache_dir / f"{sample.sample_id}-{key}.npz"
                cached = None if refresh_cache else read_cached_features(cache_path, sample)
                if cached is not None:
                    records.append(cached)
                    print(f"[features] {index}/{len(samples)} cache {sample.sample_id} frames={cached.feature_frames}")
                    continue

                member = source_member_path(sample)
                tmp_video = tmp_dir / f"{sample.sample_id}.mp4"
                with archive.open(member) as source, tmp_video.open("wb") as target:
                    shutil.copyfileobj(source, target)

                try:
                    record = extract_features_from_video(
                        tmp_video,
                        sample,
                        service,
                        gesture_requires_hand=gesture_requires_hand,
                    )
                except Exception as exc:
                    failures.append(
                        {
                            "sample_id": sample.sample_id,
                            "label": sample.label,
                            "split": sample.split,
                            "error": f"{type(exc).__name__}: {exc}",
                        }
                    )
                    print(f"[features] {index}/{len(samples)} ERROR {sample.sample_id}: {exc}", file=sys.stderr)
                    continue

                write_cached_features(cache_path, record)
                records.append(record)
                print(
                    f"[features] {index}/{len(samples)} extracted {sample.sample_id} "
                    f"features={record.feature_frames} hands={record.hand_frames}/{record.frames_read}"
                )
                tmp_video.unlink(missing_ok=True)
    return records, failures


def clip_from_features(
    features: np.ndarray,
    *,
    clip_frames: int,
    segment_len: int,
    window_kind: str,
) -> tuple[np.ndarray, int]:
    total = int(features.shape[0])
    source_len = min(total, int(segment_len))
    if window_kind == "prefix":
        start = 0
    elif window_kind == "middle":
        start = max(0, (total - source_len) // 2)
    elif window_kind == "tail":
        start = max(0, total - source_len)
    else:
        raise ValueError(f"unsupported training window kind: {window_kind}")
    span = features[start : start + source_len]
    clip = resample_to_fixed_T(span, T=int(clip_frames), method="linear")
    return np.ascontiguousarray(clip, dtype=np.float32), int(source_len)


def prepare_clips(
    records: Sequence[FeatureRecord],
    *,
    config: dict[str, Any],
) -> tuple[list[PreparedClip], list[dict[str, Any]]]:
    feature_cfg = config["feature_extraction"]
    training_cfg = config["training"]
    clip_frames = int(feature_cfg["clip_frames"])
    segment_len = int(feature_cfg["segment_window"]) - 1
    min_feature_frames = int(feature_cfg["min_feature_frames"])
    train_windows = [
        str(value)
        for value in training_cfg.get("windows", ["prefix"])
        if isinstance(value, str)
    ]
    clips: list[PreparedClip] = []
    rejected: list[dict[str, Any]] = []

    for record in records:
        if record.feature_frames < min_feature_frames:
            rejected.append(
                {
                    "sample_id": record.sample.sample_id,
                    "label": record.sample.label,
                    "split": record.sample.split,
                    "feature_frames": record.feature_frames,
                    "reason": "too_few_feature_frames",
                }
            )
            continue
        windows = train_windows if record.sample.split == "train" else ["prefix"]
        for window_kind in windows:
            clip, source_len = clip_from_features(
                record.features,
                clip_frames=clip_frames,
                segment_len=segment_len,
                window_kind=window_kind,
            )
            clips.append(
                PreparedClip(
                    sample_id=record.sample.sample_id,
                    label=record.sample.label,
                    split=record.sample.split,
                    window_kind=window_kind,
                    features=clip,
                    source_feature_frames=source_len,
                )
            )
    return clips, rejected


def flatten_clips(clips: Sequence[PreparedClip]) -> np.ndarray:
    if not clips:
        return np.zeros((0, 0), dtype=np.float32)
    return np.stack([clip.features.reshape(-1) for clip in clips], axis=0).astype(
        np.float32
    )


def summarize_clip_features(features: np.ndarray) -> np.ndarray:
    clip = np.asarray(features, dtype=np.float32)
    if clip.ndim != 2 or clip.shape[0] < 1:
        raise ValueError(f"clip must have shape [T, F], got {clip.shape}")
    mean = clip.mean(axis=0)
    std = clip.std(axis=0)
    delta = clip[-1] - clip[0]
    return np.concatenate([mean, std, delta], axis=0).astype(np.float32)


def model_features_for_clips(
    clips: Sequence[PreparedClip],
    *,
    projection: str,
) -> np.ndarray:
    if projection == "flatten":
        return flatten_clips(clips)
    if projection == "temporal_summary_mean_std_delta":
        if not clips:
            return np.zeros((0, 0), dtype=np.float32)
        return np.stack(
            [summarize_clip_features(clip.features) for clip in clips],
            axis=0,
        ).astype(np.float32)
    raise ValueError(f"unsupported feature projection: {projection}")


def train_linear_classifier(
    clips: Sequence[PreparedClip],
    *,
    labels: Sequence[str],
    config: dict[str, Any],
) -> LinearClassifier:
    train_clips = [clip for clip in clips if clip.split == "train"]
    if not train_clips:
        raise ValueError("no training clips were prepared")

    projection = str(config["training"].get("feature_projection", "flatten"))
    X_raw = model_features_for_clips(train_clips, projection=projection)
    mean = X_raw.mean(axis=0).astype(np.float32)
    scale = X_raw.std(axis=0).astype(np.float32)
    scale = np.where(scale < 1e-4, 1.0, scale).astype(np.float32)
    X = ((X_raw - mean.reshape(1, -1)) / scale.reshape(1, -1)).astype(np.float32)
    X_aug = np.concatenate(
        [X, np.ones((X.shape[0], 1), dtype=np.float32)],
        axis=1,
    )

    label_to_index = {label: idx for idx, label in enumerate(labels)}
    y_index = np.asarray([label_to_index[clip.label] for clip in train_clips], dtype=np.int64)
    Y = np.full((len(train_clips), len(labels)), -1.0, dtype=np.float32)
    Y[np.arange(len(train_clips)), y_index] = 1.0

    class_counts = np.bincount(y_index, minlength=len(labels)).astype(np.float32)
    sample_weights = np.ones((len(train_clips),), dtype=np.float32)
    if config["training"].get("class_weight") == "balanced":
        nonzero = np.maximum(class_counts, 1.0)
        weights_by_class = float(len(train_clips)) / (float(len(labels)) * nonzero)
        sample_weights = weights_by_class[y_index].astype(np.float32)

    sqrt_w = np.sqrt(sample_weights).reshape(-1, 1).astype(np.float32)
    Xw = X_aug * sqrt_w
    Yw = Y * sqrt_w
    alpha = float(config["training"]["ridge_alpha"])
    gram = Xw @ Xw.T
    gram += np.eye(gram.shape[0], dtype=np.float32) * alpha
    dual = np.linalg.solve(gram.astype(np.float64), Yw.astype(np.float64)).astype(np.float32)
    coef_aug = Xw.T @ dual
    weights = coef_aug[:-1].astype(np.float32)
    bias = coef_aug[-1].astype(np.float32)
    return LinearClassifier(
        labels=tuple(labels),
        feature_projection=projection,
        mean=mean,
        scale=scale,
        weights=weights,
        bias=bias,
        logit_scale=float(config["training"]["logit_scale"]),
    )


def predict_logits(model: LinearClassifier, clips: Sequence[PreparedClip]) -> np.ndarray:
    X_raw = model_features_for_clips(clips, projection=model.feature_projection)
    X = ((X_raw - model.mean.reshape(1, -1)) / model.scale.reshape(1, -1)).astype(
        np.float32
    )
    logits = (X @ model.weights + model.bias.reshape(1, -1)) * float(model.logit_scale)
    return logits.astype(np.float32)


def softmax(logits: np.ndarray) -> np.ndarray:
    values = logits.astype(np.float32)
    values = values - values.max(axis=1, keepdims=True)
    exp = np.exp(values).astype(np.float32)
    return exp / np.maximum(exp.sum(axis=1, keepdims=True), 1e-9)


def classification_metrics(
    clips: Sequence[PreparedClip],
    *,
    labels: Sequence[str],
    model: LinearClassifier,
) -> dict[str, Any]:
    if not clips:
        return {
            "sample_count": 0,
            "correct": 0,
            "accuracy": 0.0,
            "classes": [],
            "failed_cases": [],
            "confusion_matrix": [],
        }
    label_to_index = {label: idx for idx, label in enumerate(labels)}
    expected = np.asarray([label_to_index[clip.label] for clip in clips], dtype=np.int64)
    logits = predict_logits(model, clips)
    probs = softmax(logits)
    predicted = probs.argmax(axis=1).astype(np.int64)
    correct = predicted == expected

    matrix = np.zeros((len(labels), len(labels)), dtype=np.int64)
    for exp_idx, pred_idx in zip(expected, predicted, strict=True):
        matrix[int(exp_idx), int(pred_idx)] += 1

    classes: list[dict[str, Any]] = []
    weak_classes: list[str] = []
    for idx, label in enumerate(labels):
        tp = int(matrix[idx, idx])
        fp = int(matrix[:, idx].sum() - tp)
        fn = int(matrix[idx, :].sum() - tp)
        support = int(matrix[idx, :].sum())
        precision = tp / (tp + fp) if (tp + fp) else 0.0
        recall = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
        if support and f1 < 0.999:
            weak_classes.append(label)
        classes.append(
            {
                "label": label,
                "precision": round(float(precision), 6),
                "recall": round(float(recall), 6),
                "f1": round(float(f1), 6),
                "support": support,
            }
        )

    failed_cases: list[dict[str, Any]] = []
    for clip, exp_idx, pred_idx, ok, row_probs in zip(
        clips,
        expected,
        predicted,
        correct,
        probs,
        strict=True,
    ):
        if bool(ok):
            continue
        failed_cases.append(
            {
                "sample_id": clip.sample_id,
                "split": clip.split,
                "window_kind": clip.window_kind,
                "expected_label": labels[int(exp_idx)],
                "predicted_label": labels[int(pred_idx)],
                "confidence": round(float(row_probs[int(pred_idx)]), 6),
            }
        )

    return {
        "sample_count": len(clips),
        "correct": int(correct.sum()),
        "accuracy": round(float(correct.mean()), 6),
        "classes": classes,
        "weak_classes": weak_classes,
        "failed_cases": failed_cases,
        "confusion_matrix": matrix.tolist(),
    }


def export_linear_classifier_onnx(
    path: Path,
    *,
    model: LinearClassifier,
    clip_frames: int,
    feature_dim: int,
) -> None:
    import onnx
    from onnx import TensorProto, helper, numpy_helper

    if model.feature_projection not in {"flatten", "temporal_summary_mean_std_delta"}:
        raise ValueError(f"unsupported ONNX feature projection: {model.feature_projection}")
    model_input_dim = int(model.mean.shape[0])
    weights = (model.weights * float(model.logit_scale)).astype(np.float32)
    bias = (model.bias * float(model.logit_scale)).astype(np.float32)
    if model.feature_projection == "flatten":
        flat_dim = int(clip_frames) * int(feature_dim)
        projection_nodes = [
            helper.make_node("Reshape", ["features", "flat_shape"], ["flat"]),
        ]
        projection_output = "flat"
        initializers = [
            numpy_helper.from_array(np.asarray([1, flat_dim], dtype=np.int64), "flat_shape"),
        ]
    else:
        projection_nodes = [
            helper.make_node("ReduceMean", ["features"], ["clip_mean"], axes=[1], keepdims=0),
            helper.make_node("Unsqueeze", ["clip_mean", "unsqueeze_axes"], ["clip_mean_bt"]),
            helper.make_node("Sub", ["features", "clip_mean_bt"], ["clip_centered"]),
            helper.make_node("Mul", ["clip_centered", "clip_centered"], ["clip_centered_sq"]),
            helper.make_node("ReduceMean", ["clip_centered_sq"], ["clip_var"], axes=[1], keepdims=0),
            helper.make_node("Sqrt", ["clip_var"], ["clip_std"]),
            helper.make_node("Gather", ["features", "first_index"], ["first_frame"], axis=1),
            helper.make_node("Gather", ["features", "last_index"], ["last_frame"], axis=1),
            helper.make_node("Sub", ["last_frame", "first_frame"], ["clip_delta"]),
            helper.make_node("Concat", ["clip_mean", "clip_std", "clip_delta"], ["summary"], axis=1),
        ]
        projection_output = "summary"
        initializers = [
            numpy_helper.from_array(np.asarray([1], dtype=np.int64), "unsqueeze_axes"),
            numpy_helper.from_array(np.asarray(0, dtype=np.int64), "first_index"),
            numpy_helper.from_array(np.asarray(int(clip_frames) - 1, dtype=np.int64), "last_index"),
        ]

    graph = helper.make_graph(
        nodes=[
            *projection_nodes,
            helper.make_node("Sub", [projection_output, "mean"], ["centered"]),
            helper.make_node("Div", ["centered", "scale"], ["standardized"]),
            helper.make_node("MatMul", ["standardized", "weights"], ["linear"]),
            helper.make_node("Add", ["linear", "bias"], ["logits"]),
        ],
        name="demo_gestures_linear_pose_words_classifier",
        inputs=[
            helper.make_tensor_value_info(
                "features",
                TensorProto.FLOAT,
                [1, int(clip_frames), int(feature_dim)],
            )
        ],
        outputs=[
            helper.make_tensor_value_info(
                "logits",
                TensorProto.FLOAT,
                [1, len(model.labels)],
            )
        ],
        initializer=[
            *initializers,
            numpy_helper.from_array(model.mean.reshape(1, -1).astype(np.float32), "mean"),
            numpy_helper.from_array(model.scale.reshape(1, -1).astype(np.float32), "scale"),
            numpy_helper.from_array(weights.astype(np.float32), "weights"),
            numpy_helper.from_array(bias.reshape(1, -1).astype(np.float32), "bias"),
        ],
    )
    onnx_model = helper.make_model(
        graph,
        producer_name="scripts/train_demo_gestures_classifier.py",
        opset_imports=[helper.make_operatorsetid("", 13)],
    )
    onnx_model.ir_version = 10
    onnx.checker.check_model(onnx_model)
    path.parent.mkdir(parents=True, exist_ok=True)
    onnx.save(onnx_model, path)


def export_deterministic_segmenter_onnx(
    path: Path,
    *,
    window_size: int,
    feature_dim: int,
) -> None:
    import onnx
    from onnx import TensorProto, helper, numpy_helper

    sign = np.zeros((1, int(window_size), 3), dtype=np.float32)
    sign[:, :, 2] = 1.0
    sign[:, 0, :] = np.asarray([1.0, 0.0, 0.0], dtype=np.float32)
    if window_size > 2:
        sign[:, 1 : window_size - 1, :] = np.asarray([0.0, 1.0, 0.0], dtype=np.float32)
    sign[:, window_size - 1, :] = np.asarray([0.0, 0.0, 1.0], dtype=np.float32)
    phrase = sign.copy()

    graph = helper.make_graph(
        nodes=[
            helper.make_node(
                "Constant",
                [],
                ["sign_probs"],
                value=numpy_helper.from_array(sign, "sign_value"),
            ),
            helper.make_node(
                "Constant",
                [],
                ["phrase_probs"],
                value=numpy_helper.from_array(phrase, "phrase_value"),
            ),
        ],
        name="deterministic_isolated_gesture_bio_segmenter",
        inputs=[
            helper.make_tensor_value_info(
                "features",
                TensorProto.FLOAT,
                [1, int(window_size), int(feature_dim)],
            )
        ],
        outputs=[
            helper.make_tensor_value_info(
                "sign_probs",
                TensorProto.FLOAT,
                [1, int(window_size), 3],
            ),
            helper.make_tensor_value_info(
                "phrase_probs",
                TensorProto.FLOAT,
                [1, int(window_size), 3],
            ),
        ],
    )
    onnx_model = helper.make_model(
        graph,
        producer_name="scripts/train_demo_gestures_classifier.py",
        opset_imports=[helper.make_operatorsetid("", 13)],
    )
    onnx_model.ir_version = 10
    onnx.checker.check_model(onnx_model)
    path.parent.mkdir(parents=True, exist_ok=True)
    onnx.save(onnx_model, path)


def write_active_pack(
    output_root: Path,
    *,
    config: dict[str, Any],
    model: LinearClassifier,
    training_report_path: Path,
) -> dict[str, Any]:
    feature_cfg = config["feature_extraction"]
    segmentation_cfg = config["segmentation"]
    clip_frames = int(feature_cfg["clip_frames"])
    feature_dim = int(feature_cfg["feature_dim"])
    window_size = int(segmentation_cfg["window_size"])

    classifier_model = output_root / "classifier/model.onnx"
    segmentation_model = output_root / "segmentation/model.onnx"
    labels_path = output_root / "classifier/labels.txt"
    classifier_config_path = output_root / "classifier/runtime_config.json"
    segmentation_config_path = output_root / "segmentation/runtime_config.json"
    thresholds_path = output_root / "segmentation/thresholds.json"
    manifest_path = output_root / "manifest.json"

    export_linear_classifier_onnx(
        classifier_model,
        model=model,
        clip_frames=clip_frames,
        feature_dim=feature_dim,
    )
    export_deterministic_segmenter_onnx(
        segmentation_model,
        window_size=window_size,
        feature_dim=feature_dim,
    )
    labels_path.parent.mkdir(parents=True, exist_ok=True)
    labels_path.write_text("\n".join(model.labels) + "\n", encoding="utf-8")

    write_json(
        classifier_config_path,
        {
            "generated_by": "scripts/train_demo_gestures_classifier.py",
            "artifact_kind": "runtime_classifier",
            "dataset_kind": "slovo_demo_gestures_v1",
            "trained": True,
            "source_pipeline": "pose_words",
            "labels_total": len(model.labels),
            "clip_frames": clip_frames,
            "input_dim": feature_dim,
            "model": {
                "type": "standardized_linear_ridge_classifier",
                "feature_projection": model.feature_projection,
                "model_input_dim": int(model.mean.shape[0]),
                "labels_total": len(model.labels),
                "clip_frames": clip_frames,
                "input_dim": feature_dim,
                "ridge_alpha": float(config["training"]["ridge_alpha"]),
                "logit_scale": float(model.logit_scale),
            },
            "input": {
                "name": "features",
                "shape": [1, clip_frames, feature_dim],
                "dtype": "float32",
            },
            "output": {
                "name": "logits",
                "shape": [1, len(model.labels)],
                "dtype": "float32",
            },
            "norm_flags": {
                "use_shoulder_norm": bool(feature_cfg["apply_shoulder_norm"]),
                "use_hands_3d_norm": bool(feature_cfg["canonical_hands_3d"]),
            },
            "training_report": repo_display(training_report_path),
        },
    )
    write_json(
        segmentation_config_path,
        {
            "generated_by": "scripts/train_demo_gestures_classifier.py",
            "artifact_kind": "runtime_segmentation",
            "dataset_kind": "deterministic_isolated_gesture_window",
            "trained": False,
            "source_pipeline": "pose_words",
            "input_dim": feature_dim,
            "window_size": window_size,
            "step": int(segmentation_cfg["step"]),
            "min_segment_len": int(segmentation_cfg["min_segment_len"]),
            "bio_mapping": {"B": 0, "I": 1, "O": 2},
            "norm_flags": {
                "use_shoulder_norm": bool(feature_cfg["apply_shoulder_norm"]),
                "use_hands_3d_norm": bool(feature_cfg["canonical_hands_3d"]),
            },
            "notes": [
                "Deterministic isolated-gesture segmenter used to emit a completed segment for one-gesture smoke clips.",
                "Classifier quality is measured separately on real Slovo validation clips.",
            ],
        },
    )
    write_json(
        thresholds_path,
        {
            "generated_by": "scripts/train_demo_gestures_classifier.py",
            "artifact_kind": "runtime_thresholds",
            "dataset_kind": "deterministic_isolated_gesture_window",
            "trained": False,
            "source_pipeline": "pose_words",
            "bio_mapping": {"B": 0, "I": 1, "O": 2},
            **dict(segmentation_cfg["thresholds"]),
        },
    )

    descriptors = {
        "classifier_model": {
            "relative_path": "classifier/model.onnx",
            "component": "pose_words_classifier",
            "artifact_kind": "model",
            "required": True,
            "trained": True,
            "size_bytes": classifier_model.stat().st_size,
            "sha256": sha256_file(classifier_model),
        },
        "classifier_labels": {
            "relative_path": "classifier/labels.txt",
            "component": "pose_words_classifier",
            "artifact_kind": "labels",
            "required": True,
            "trained": True,
            "size_bytes": labels_path.stat().st_size,
            "sha256": sha256_file(labels_path),
        },
        "classifier_config": {
            "relative_path": "classifier/runtime_config.json",
            "component": "pose_words_classifier",
            "artifact_kind": "runtime_config",
            "required": False,
            "trained": True,
            "size_bytes": classifier_config_path.stat().st_size,
            "sha256": sha256_file(classifier_config_path),
        },
        "segmentation_model": {
            "relative_path": "segmentation/model.onnx",
            "component": "bio_segmentation",
            "artifact_kind": "model",
            "required": True,
            "trained": False,
            "size_bytes": segmentation_model.stat().st_size,
            "sha256": sha256_file(segmentation_model),
        },
        "segmentation_thresholds": {
            "relative_path": "segmentation/thresholds.json",
            "component": "bio_segmentation",
            "artifact_kind": "thresholds",
            "required": True,
            "trained": False,
            "size_bytes": thresholds_path.stat().st_size,
            "sha256": sha256_file(thresholds_path),
        },
        "segmentation_config": {
            "relative_path": "segmentation/runtime_config.json",
            "component": "bio_segmentation",
            "artifact_kind": "runtime_config",
            "required": False,
            "trained": False,
            "size_bytes": segmentation_config_path.stat().st_size,
            "sha256": sha256_file(segmentation_config_path),
        },
    }
    manifest = {
        "schema_version": 1,
        "contour": "pose_words",
        "profile_id": "runtime_active",
        "profile_role": "active",
        "profile_origin": "runtime",
        "readiness_class": "live_candidate",
        "source_pipeline": "pose_words",
        "generated_by": "scripts/train_demo_gestures_classifier.py",
        "dataset_kind": "slovo_demo_gestures_v1",
        "trained": True,
        "labels": list(model.labels),
        "task_codes": ["MODEL-01", "PW-07"],
        "training_config": repo_display(repo_path(DEFAULT_CONFIG)),
        "training_report": repo_display(training_report_path),
        "notes": [
            "Active classifier labels cover 10 demo gestures plus _no_event.",
            "Classifier was trained on materialized Slovo train split and validated on held-out materialized validation split.",
            "Segmentation artifact is a deterministic isolated-gesture segmenter for the current one-gesture live smoke clips.",
        ],
        "files": descriptors,
    }
    write_json(manifest_path, manifest)
    return manifest


def split_counts(samples: Sequence[DemoSample], labels: Sequence[str]) -> dict[str, dict[str, int]]:
    output: dict[str, dict[str, int]] = {
        label: {"train": 0, "validation": 0, "total": 0}
        for label in labels
    }
    for sample in samples:
        output[sample.label][sample.split] += 1
        output[sample.label]["total"] += 1
    return output


def feature_summary(records: Sequence[FeatureRecord], labels: Sequence[str]) -> dict[str, Any]:
    by_label: dict[str, list[FeatureRecord]] = {label: [] for label in labels}
    for record in records:
        by_label.setdefault(record.sample.label, []).append(record)
    rows: dict[str, Any] = {}
    for label, items in by_label.items():
        if not items:
            rows[label] = {"samples": 0, "min_feature_frames": 0, "avg_feature_frames": 0.0}
            continue
        feature_counts = [item.feature_frames for item in items]
        rows[label] = {
            "samples": len(items),
            "min_feature_frames": int(min(feature_counts)),
            "avg_feature_frames": round(float(sum(feature_counts) / len(feature_counts)), 3),
            "cache_hits": sum(1 for item in items if item.cache_hit),
        }
    return rows


def main() -> int:
    args = build_parser().parse_args()
    started = time.perf_counter()
    config_path = repo_path(args.config)
    config = read_json(config_path)
    labels = expected_labels(config)
    manifest_path = repo_path(config["materialized_manifest"])
    output_root = repo_path(args.output_root or config["active_output_root"])
    report_json = repo_path(args.report_json or config["report_json"])
    cache_dir = repo_path(args.feature_cache)
    archive_path = resolve_slovo_archive(args.slovo_root, config)

    samples, materialized_manifest = load_materialized_samples(
        manifest_path,
        labels=labels,
    )
    source_check = (
        {"skipped": True}
        if args.no_verify_source
        else verify_sources(samples, archive_path)
    )
    records, feature_failures = extract_features(
        samples,
        archive_path=archive_path,
        config=config,
        cache_dir=cache_dir,
        refresh_cache=args.refresh_cache,
    )
    clips, rejected = prepare_clips(records, config=config)
    model = train_linear_classifier(clips, labels=labels, config=config)
    train_metrics = classification_metrics(
        [clip for clip in clips if clip.split == "train"],
        labels=labels,
        model=model,
    )
    validation_metrics = classification_metrics(
        [clip for clip in clips if clip.split == "validation"],
        labels=labels,
        model=model,
    )

    duration = time.perf_counter() - started
    report = {
        "schema_version": 1,
        "report_id": "MODEL-01-PW-07-demo-gestures-classifier-results-v1",
        "generated_at_unix": time.time(),
        "duration_seconds": round(duration, 3),
        "training_command": " ".join(
            shlex.quote(part) for part in ["python3", *sys.argv]
        ),
        "config_path": repo_display(config_path),
        "materialized_manifest": repo_display(manifest_path),
        "source_manifest": str(materialized_manifest.get("source_manifest")),
        "source_archive": str(archive_path),
        "label_set": labels,
        "canonical_label_handling": {
            "aliases": materialized_manifest.get("label_canonicalization", {}).get("aliases", {}),
            "source_labels_preserved": True,
        },
        "class_counts": split_counts(samples, labels),
        "source_check": source_check,
        "feature_extraction": {
            "config": config["feature_extraction"],
            "summary": feature_summary(records, labels),
            "failures": feature_failures,
            "rejected_samples": rejected,
        },
        "model": {
            "type": "standardized_linear_ridge_classifier",
            "feature_projection": str(config["training"].get("feature_projection", "flatten")),
            "ridge_alpha": float(config["training"]["ridge_alpha"]),
            "logit_scale": float(model.logit_scale),
            "clip_frames": int(config["feature_extraction"]["clip_frames"]),
            "feature_dim": int(config["feature_extraction"]["feature_dim"]),
            "model_input_dim": int(model.mean.shape[0]),
        },
        "train_metrics": train_metrics,
        "validation_metrics": validation_metrics,
        "dataset_shortages": materialized_manifest.get("shortages", []),
        "class_status": materialized_manifest.get("class_status", {}),
        "live_smoke_excluded_sample_ids": sorted(LIVE_SMOKE_SAMPLE_IDS),
        "limitations": [
            "Small per-class Slovo subset; most gesture classes have 19 records after live smoke exclusions.",
            "Classifier uses MediaPipe pose features and a lightweight ridge-linear ONNX model.",
            "Segmentation artifact is deterministic for isolated one-gesture clips and is not a production sign boundary model.",
        ],
    }
    write_json(report_json, report)
    manifest = write_active_pack(
        output_root,
        config=config,
        model=model,
        training_report_path=report_json,
    )
    report["artifact"] = {
        "manifest_path": repo_display(output_root / "manifest.json"),
        "classifier_model": manifest["files"]["classifier_model"],
        "classifier_labels": manifest["files"]["classifier_labels"],
        "segmentation_model": manifest["files"]["segmentation_model"],
    }
    write_json(report_json, report)

    print(f"[train] labels={len(labels)} train_accuracy={train_metrics['accuracy']} validation_accuracy={validation_metrics['accuracy']}")
    print(f"[train] active manifest: {repo_display(output_root / 'manifest.json')}")
    print(f"[train] report: {repo_display(report_json)}")
    if feature_failures or rejected or validation_metrics["failed_cases"]:
        print("[train] completed with recorded weak/failure cases; see report JSON", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
