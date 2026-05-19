from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import numpy as np
import pytest


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts/train_demo_gestures_classifier.py"
SPEC = importlib.util.spec_from_file_location("train_demo_gestures_classifier", SCRIPT_PATH)
assert SPEC is not None
assert SPEC.loader is not None
TRAIN = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = TRAIN
SPEC.loader.exec_module(TRAIN)


def make_clip(sample_id: str, label: str, value: float) -> object:
    features = np.full((4, 3), value, dtype=np.float32)
    return TRAIN.PreparedClip(
        sample_id=sample_id,
        label=label,
        split="train",
        window_kind="middle",
        features=features,
        source_feature_frames=4,
    )


def test_expected_labels_requires_no_event_first() -> None:
    with pytest.raises(ValueError, match="_no_event"):
        TRAIN.expected_labels({"labels": ["привет", "_no_event"]})


def test_summarize_clip_features_uses_mean_std_and_delta() -> None:
    clip = np.asarray(
        [
            [1.0, 2.0],
            [3.0, 4.0],
            [5.0, 8.0],
        ],
        dtype=np.float32,
    )

    summary = TRAIN.summarize_clip_features(clip)

    np.testing.assert_allclose(summary[:2], [3.0, 14.0 / 3.0])
    np.testing.assert_allclose(summary[2:4], clip.std(axis=0))
    np.testing.assert_allclose(summary[4:], [4.0, 6.0])


def test_train_linear_classifier_keeps_label_mapping_and_predicts_training_clips() -> None:
    labels = ["_no_event", "привет", "пока"]
    clips = [
        make_clip("no_event", "_no_event", -1.0),
        make_clip("privet", "привет", 1.0),
        make_clip("poka", "пока", 3.0),
    ]
    config = {
        "training": {
            "feature_projection": "temporal_summary_mean_std_delta",
            "ridge_alpha": 0.01,
            "class_weight": "balanced",
            "logit_scale": 6.0,
        }
    }

    model = TRAIN.train_linear_classifier(clips, labels=labels, config=config)
    predictions = TRAIN.predict_logits(model, clips).argmax(axis=1)

    assert list(model.labels) == labels
    assert model.feature_projection == "temporal_summary_mean_std_delta"
    assert predictions.tolist() == [0, 1, 2]
