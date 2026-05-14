"""Offline quality validation for the active pose_words artifact pack."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

import numpy as np

from rsl_sign_recognition.inference.pose_words import (
    PoseWordOnnxModel,
    find_no_event_index,
)
from rsl_sign_recognition.pipelines.pose_words.clip import resample_to_fixed_T
from rsl_sign_recognition.runtime.artifacts import (
    ActiveArtifactLoader,
    ResolvedActiveArtifacts,
)
from rsl_sign_recognition.segmentation.decoder import decode_segments
from rsl_sign_recognition.segmentation.model_onnx import (
    BioSegmenterOnnxModel,
    load_bio_thresholds,
)


VALIDATION_ID = "PW-06-offline-pose-words-validation"
DEFAULT_MANIFEST = Path("artifacts/runtime/active/pose_words/manifest.json")
SUPPORTED_SYNTHETIC_LABELS = frozenset({"_no_event", "привет", "пока"})


@dataclass(frozen=True, slots=True)
class OfflineValidationSample:
    sample_id: str
    source: str
    expected_label: str
    features: np.ndarray
    notes: str


def repo_relative_path(repo_root: Path, value: str | Path) -> Path:
    raw_path = Path(value)
    if raw_path.is_absolute():
        raise ValueError(f"path must be repo-relative: {raw_path}")
    if any(part == ".." for part in raw_path.parts):
        raise ValueError(f"path must not contain '..': {raw_path}")

    resolved_root = repo_root.resolve()
    resolved_path = (resolved_root / raw_path).resolve()
    try:
        resolved_path.relative_to(resolved_root)
    except ValueError as exc:
        raise ValueError(f"path escapes repository root: {raw_path}") from exc
    return resolved_path


def read_labels(labels_path: Path) -> list[str]:
    labels = [
        line.strip()
        for line in labels_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if not labels:
        raise ValueError(f"pose_words labels file is empty: {labels_path}")
    return labels


def select_target_labels(labels: Sequence[str], *, max_targets: int = 5) -> list[str]:
    no_event_idx = find_no_event_index(labels)
    targets: list[str] = []
    for idx, label in enumerate(labels):
        if no_event_idx is not None and idx == no_event_idx:
            continue
        if label not in SUPPORTED_SYNTHETIC_LABELS:
            continue
        targets.append(str(label))
        if len(targets) >= max(1, int(max_targets)):
            break
    if not targets:
        raise ValueError(
            "no supported pose_words labels found for synthetic offline validation; "
            f"available labels: {list(labels)}"
        )
    return targets


def build_synthetic_clip(
    label: str,
    *,
    sample_index: int,
    feature_dim: int,
    length: int,
) -> np.ndarray:
    if label not in SUPPORTED_SYNTHETIC_LABELS:
        raise ValueError(f"unsupported synthetic label: {label}")

    t = np.linspace(0.0, 1.0, num=int(length), dtype=np.float32)
    features = np.zeros((int(length), int(feature_dim)), dtype=np.float32)
    phase = float(sample_index + 1)
    seed_offset = 0 if label == "_no_event" else 100 if label == "привет" else 200
    rng = np.random.default_rng(1000 + int(sample_index) + seed_offset)

    if label == "_no_event":
        wave = np.sin((2.0 * np.pi * t * (1.0 + 0.1 * phase)))[:, None]
        features += 0.015 * wave
        features[:, 120:] += 0.01
    elif label == "привет":
        features[:, :40] = (
            0.90 + 0.08 * np.sin((2.0 * np.pi * t) + phase / 10.0)[:, None]
        )
        features[:, 40:80] = (
            0.35 + 0.05 * np.cos((3.0 * np.pi * t) + phase / 8.0)[:, None]
        )
        features[:, 120:140] = t[:, None]
        features[:, 140:] = 0.2
    elif label == "пока":
        features[:, 80:120] = (
            -0.85 + 0.10 * np.cos((3.5 * np.pi * t) + phase / 7.0)[:, None]
        )
        features[:, 20:40] = (
            0.28 + 0.02 * np.sin((2.5 * np.pi * t) + phase / 5.0)[:, None]
        )
        features[:, 140:] = (1.0 - t)[:, None]
        features[:, :10] = -0.15

    noise = rng.normal(loc=0.0, scale=0.008, size=features.shape).astype(np.float32)
    return np.ascontiguousarray(features + noise, dtype=np.float32)


def build_validation_samples(
    labels: Sequence[str],
    *,
    target_labels: Sequence[str],
    feature_dim: int,
    samples_per_label: int = 3,
    include_no_event: bool = True,
) -> list[OfflineValidationSample]:
    samples: list[OfflineValidationSample] = []
    labels_to_generate: list[str] = []
    no_event_idx = find_no_event_index(labels)
    if include_no_event and no_event_idx is not None:
        no_event_label = labels[no_event_idx]
        if no_event_label in SUPPORTED_SYNTHETIC_LABELS:
            labels_to_generate.append(no_event_label)
    labels_to_generate.extend(str(label) for label in target_labels)

    for label_position, label in enumerate(labels_to_generate):
        for local_idx in range(max(1, int(samples_per_label))):
            sample_index = label_position * 10 + 100 + local_idx
            length = 24 + ((local_idx + label_position) % 6)
            features = build_synthetic_clip(
                label,
                sample_index=sample_index,
                feature_dim=feature_dim,
                length=length,
            )
            samples.append(
                OfflineValidationSample(
                    sample_id=f"{label}_synthetic_{local_idx:02d}",
                    source="synthetic_fixture_from_draft_validation_context",
                    expected_label=label,
                    features=features,
                    notes=(
                        "pre-segmented synthetic pose_words feature clip; "
                        "not camera/video input"
                    ),
                )
            )
    return samples


def summarize_results(samples: Sequence[dict[str, Any]]) -> dict[str, Any]:
    sample_count = len(samples)
    correct_count = sum(1 for sample in samples if bool(sample["top1_correct"]))
    confidences = [float(sample["confidence"]) for sample in samples]
    by_label: dict[str, list[dict[str, Any]]] = {}
    for sample in samples:
        by_label.setdefault(str(sample["expected_label"]), []).append(sample)

    class_rows: list[dict[str, Any]] = []
    for label in sorted(by_label):
        rows = by_label[label]
        support = len(rows)
        correct = sum(1 for row in rows if bool(row["top1_correct"]))
        avg_conf = (
            float(sum(float(row["confidence"]) for row in rows) / support)
            if support
            else 0.0
        )
        confusions = sorted(
            {
                str(row["predicted_label"])
                for row in rows
                if str(row["predicted_label"]) != label
            }
        )
        class_rows.append(
            {
                "label": label,
                "support": int(support),
                "correct": int(correct),
                "top1_accuracy": _round(correct / support if support else 0.0),
                "avg_confidence": _round(avg_conf),
                "main_confusion": ", ".join(confusions) if confusions else "",
            }
        )

    return {
        "sample_count": int(sample_count),
        "correct": int(correct_count),
        "top1_accuracy": _round(correct_count / sample_count if sample_count else 0.0),
        "avg_confidence": _round(
            sum(confidences) / len(confidences) if confidences else 0.0
        ),
        "confusion_cases": [
            sample
            for sample in samples
            if not bool(sample.get("top1_correct", False))
        ],
        "classes": class_rows,
    }


def confidence_threshold_summary(
    samples: Sequence[dict[str, Any]],
    *,
    target_labels: Sequence[str],
) -> dict[str, Any]:
    target_set = {str(label) for label in target_labels}
    target_rows = [
        sample
        for sample in samples
        if str(sample["expected_label"]) in target_set
    ]
    correct_confidences = [
        float(sample["confidence"])
        for sample in target_rows
        if bool(sample["top1_correct"])
    ]
    if not target_rows or len(correct_confidences) != len(target_rows):
        return {
            "candidate_threshold": None,
            "production_threshold_ready": False,
            "reason": (
                "threshold не выбран: есть ошибки top-1 или нет target samples"
            ),
        }

    min_correct = min(correct_confidences)
    candidate = math.floor((min_correct - 0.001) * 100.0) / 100.0
    candidate = max(0.0, min(1.0, candidate))
    return {
        "candidate_threshold": _round(candidate),
        "min_correct_target_confidence": _round(min_correct),
        "production_threshold_ready": False,
        "reason": (
            "candidate threshold рассчитан только для synthetic technical set; "
            "для production/live threshold нужны реальные negatives и hard cases"
        ),
    }


def run_offline_validation(
    *,
    manifest_path: Path,
    samples_per_label: int = 3,
    max_target_labels: int = 5,
) -> dict[str, Any]:
    artifacts = ActiveArtifactLoader(manifest_path).load()
    labels = read_labels(artifacts.classifier_labels_path)
    target_labels = select_target_labels(labels, max_targets=max_target_labels)

    classifier = PoseWordOnnxModel(
        model_path=artifacts.classifier_model_path,
        labels_path=artifacts.classifier_labels_path,
        config_path=artifacts.classifier_config_path,
        ort_num_threads=1,
    )
    feature_dim = int(classifier.input_feature_dim or classifier.config_feature_dim or 159)
    clip_frames = int(classifier.input_clip_frames or classifier.config_clip_frames or 32)

    segmentation_notes = _segmentation_status_by_label(
        artifacts=artifacts,
        labels=labels,
        target_labels=target_labels,
        feature_dim=feature_dim,
    )

    samples = build_validation_samples(
        labels,
        target_labels=target_labels,
        feature_dim=feature_dim,
        samples_per_label=samples_per_label,
    )

    result_rows: list[dict[str, Any]] = []
    for sample in samples:
        clip = resample_to_fixed_T(sample.features, T=clip_frames, method="linear")
        prediction = classifier.predict(clip)
        top1_correct = prediction.label == sample.expected_label
        label_note = segmentation_notes.get(sample.expected_label, "")
        notes = sample.notes
        if label_note:
            notes = f"{notes}; {label_note}"
        result_rows.append(
            {
                "sample_id": sample.sample_id,
                "source": sample.source,
                "expected_label": sample.expected_label,
                "predicted_label": prediction.label,
                "top1_correct": bool(top1_correct),
                "confidence": _round(prediction.probability),
                "notes": notes,
            }
        )

    summary = summarize_results(result_rows)
    target_summary = summarize_results(
        [
            sample
            for sample in result_rows
            if str(sample["expected_label"]) in set(target_labels)
        ]
    )

    return {
        "schema_version": 1,
        "validation_id": VALIDATION_ID,
        "validation_kind": "synthetic_technical_offline_validation",
        "artifact_pack": artifact_pack_summary(artifacts),
        "labels": labels,
        "target_labels": list(target_labels),
        "checked_gestures": list(target_labels),
        "samples": result_rows,
        "summary": summary,
        "target_summary": target_summary,
        "confidence_threshold": confidence_threshold_summary(
            result_rows,
            target_labels=target_labels,
        ),
        "limitations": [
            "Validation uses deterministic synthetic feature clips, not real camera/video samples.",
            "Classifier is tested offline on pre-segmented pose_words feature clips.",
            "Segmentation artifact is loaded and checked on synthetic clips, but live stream orchestration is not connected.",
            "This run does not evaluate WebSocket integration, frontend integration, training, export, or words baseline decisions.",
        ],
    }


def artifact_pack_summary(artifacts: ResolvedActiveArtifacts) -> dict[str, Any]:
    manifest = artifacts.manifest
    dataset_kind = manifest.metadata.get("dataset_kind", "")
    return {
        "manifest_path": _display_path(artifacts.manifest_path),
        "profile_id": manifest.profile_id,
        "profile_role": manifest.profile_role,
        "readiness_class": manifest.readiness_class,
        "source_pipeline": manifest.source_pipeline,
        "dataset_kind": dataset_kind,
        "classifier_model_sha256": _sha256(artifacts.classifier_model_path),
        "segmentation_model_sha256": _sha256(artifacts.segmentation_model_path),
        "classifier_config_path": (
            _display_path(artifacts.classifier_config_path)
            if artifacts.classifier_config_path is not None
            else None
        ),
        "segmentation_thresholds_path": _display_path(
            artifacts.segmentation_thresholds_path
        ),
    }


def write_json_report(report: dict[str, Any], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _segmentation_status_by_label(
    *,
    artifacts: ResolvedActiveArtifacts,
    labels: Sequence[str],
    target_labels: Sequence[str],
    feature_dim: int,
) -> dict[str, str]:
    segmenter = BioSegmenterOnnxModel(
        model_path=artifacts.segmentation_model_path,
        config_path=artifacts.segmentation_config_path,
        ort_num_threads=1,
    )
    thresholds = load_bio_thresholds(artifacts.segmentation_thresholds_path)
    no_event_idx = find_no_event_index(labels)
    checked_labels: list[str] = []
    if no_event_idx is not None:
        checked_labels.append(str(labels[no_event_idx]))
    checked_labels.extend(str(label) for label in target_labels)

    output: dict[str, str] = {}
    for idx, label in enumerate(checked_labels):
        features = build_synthetic_clip(
            label,
            sample_index=200 + idx,
            feature_dim=feature_dim,
            length=32,
        )
        sign_probs, phrase_probs, _latency_ms = segmenter.infer(features)
        sign_segments = decode_segments(
            sign_probs,
            th_B=thresholds.sign_th_b,
            th_O=thresholds.sign_th_o,
        )
        phrase_segments = decode_segments(
            phrase_probs,
            th_B=thresholds.phrase_th_b,
            th_O=thresholds.phrase_th_o,
        )
        output[label] = (
            f"segmentation sign_segments={len(sign_segments)}, "
            f"phrase_segments={len(phrase_segments)}"
        )
    return output


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _display_path(path: Path | None) -> str | None:
    if path is None:
        return None
    text = str(path)
    marker = "artifacts/runtime/active/pose_words/"
    if marker in text:
        return marker + text.split(marker, 1)[1]
    return path.name


def _round(value: float) -> float:
    return float(round(float(value), 6))


__all__ = [
    "DEFAULT_MANIFEST",
    "VALIDATION_ID",
    "OfflineValidationSample",
    "build_synthetic_clip",
    "build_validation_samples",
    "confidence_threshold_summary",
    "read_labels",
    "repo_relative_path",
    "run_offline_validation",
    "select_target_labels",
    "summarize_results",
    "write_json_report",
]
