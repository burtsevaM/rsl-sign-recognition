from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from rsl_sign_recognition.validation.pose_words_offline import (
    build_synthetic_clip,
    build_validation_samples,
    confidence_threshold_summary,
    repo_relative_path,
    select_target_labels,
    summarize_results,
)


def test_repo_relative_path_rejects_absolute_path(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="repo-relative"):
        repo_relative_path(tmp_path, tmp_path / "out.json")


def test_repo_relative_path_rejects_parent_traversal(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match=r"\.\."):
        repo_relative_path(tmp_path, "../out.json")


def test_select_target_labels_skips_no_event_and_unknown_labels() -> None:
    labels = ["_no_event", "привет", "unknown", "пока"]

    assert select_target_labels(labels, max_targets=5) == ["привет", "пока"]
    assert select_target_labels(labels, max_targets=1) == ["привет"]


def test_build_validation_samples_uses_supported_active_labels() -> None:
    labels = ["_no_event", "привет", "пока"]
    samples = build_validation_samples(
        labels,
        target_labels=["привет", "пока"],
        feature_dim=159,
        samples_per_label=2,
    )

    assert [sample.expected_label for sample in samples] == [
        "_no_event",
        "_no_event",
        "привет",
        "привет",
        "пока",
        "пока",
    ]
    assert all(sample.features.shape[1] == 159 for sample in samples)
    assert all(sample.source == "synthetic_fixture_from_draft_validation_context" for sample in samples)


def test_build_synthetic_clip_is_deterministic() -> None:
    first = build_synthetic_clip("привет", sample_index=7, feature_dim=159, length=24)
    second = build_synthetic_clip("привет", sample_index=7, feature_dim=159, length=24)

    assert first.dtype == np.float32
    assert first.shape == (24, 159)
    assert np.allclose(first, second)


def test_summarize_results_counts_accuracy_and_confusions() -> None:
    summary = summarize_results(
        [
            {
                "expected_label": "привет",
                "predicted_label": "привет",
                "top1_correct": True,
                "confidence": 0.8,
            },
            {
                "expected_label": "привет",
                "predicted_label": "пока",
                "top1_correct": False,
                "confidence": 0.6,
            },
            {
                "expected_label": "пока",
                "predicted_label": "пока",
                "top1_correct": True,
                "confidence": 0.7,
            },
        ]
    )

    assert summary["sample_count"] == 3
    assert summary["correct"] == 2
    assert summary["top1_accuracy"] == pytest.approx(0.666667)
    assert len(summary["confusion_cases"]) == 1
    assert summary["classes"][0]["label"] == "пока"
    assert summary["classes"][1]["main_confusion"] == "пока"


def test_confidence_threshold_summary_marks_synthetic_threshold_not_production() -> None:
    summary = confidence_threshold_summary(
        [
            {
                "expected_label": "привет",
                "predicted_label": "привет",
                "top1_correct": True,
                "confidence": 0.8438,
            },
            {
                "expected_label": "пока",
                "predicted_label": "пока",
                "top1_correct": True,
                "confidence": 0.7501,
            },
        ],
        target_labels=["привет", "пока"],
    )

    assert summary["candidate_threshold"] == 0.74
    assert summary["production_threshold_ready"] is False
