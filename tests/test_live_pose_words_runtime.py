from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from rsl_sign_recognition.pipelines.pose_words.runtime import (
    build_pose_words_runtime_pipeline,
)
from rsl_sign_recognition.runtime.config import RuntimeMode, RuntimeShellSettings
from rsl_sign_recognition.runtime.pose_words import (
    LivePoseWordsRuntimeService,
    LivePoseWordsRuntimeStatus,
)


class FakeExtractor:
    def process(self, rgb_frame: np.ndarray) -> None:
        return None


class FakeClassifier:
    def __init__(
        self,
        *,
        model_path: str | Path,
        labels_path: str | Path,
        config_path: str | Path | None = None,
        ort_num_threads: int = 1,
    ) -> None:
        self.model_path = Path(model_path)
        self.labels_path = Path(labels_path)
        self.config_path = Path(config_path) if config_path is not None else None
        self.ort_num_threads = int(ort_num_threads)
        self.labels = [
            line.strip()
            for line in self.labels_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        self.input_clip_frames = 32
        self.config_clip_frames = None
        self.input_feature_dim = 159
        self.config_feature_dim = None

    def infer_probs(self, features_tf: np.ndarray) -> tuple[np.ndarray, float]:
        return np.asarray([1.0, 0.0, 0.0], dtype=np.float32), 0.0

    def find_no_event_index(self, label_name: str = "no_event") -> int | None:
        return 0


class FakeBioSegmenterModel:
    def __init__(
        self,
        *,
        model_path: str | Path,
        config_path: str | Path | None = None,
        ort_num_threads: int = 1,
    ) -> None:
        self.model_path = Path(model_path)
        self.config_path = Path(config_path) if config_path is not None else None
        self.ort_num_threads = int(ort_num_threads)
        self.input_feature_dim = 159
        self.config_feature_dim = None

    def infer(self, features_tf: np.ndarray) -> tuple[np.ndarray, np.ndarray, float]:
        length = int(features_tf.shape[0])
        probs = np.zeros((length, 3), dtype=np.float32)
        probs[:, 2] = 1.0
        return probs, probs.copy(), 0.0


def build_settings(tmp_path: Path) -> RuntimeShellSettings:
    return RuntimeShellSettings(
        runtime_mode=RuntimeMode.LIVE,
        repo_root=tmp_path,
        active_manifest_path=active_manifest_path(tmp_path),
    )


def active_manifest_path(tmp_path: Path) -> Path:
    return tmp_path / "artifacts/runtime/active/pose_words/manifest.json"


def write_active_pack(
    tmp_path: Path,
    *,
    skip_required: str | None = None,
    files: dict[str, object] | None = None,
) -> Path:
    manifest_path = active_manifest_path(tmp_path)
    root = manifest_path.parent
    descriptors: dict[str, object] = files or {
        "classifier_model": {
            "relative_path": "classifier/model.onnx",
            "required": True,
        },
        "classifier_labels": {
            "relative_path": "classifier/labels.txt",
            "required": True,
        },
        "segmentation_model": {
            "relative_path": "segmentation/model.onnx",
            "required": True,
        },
        "segmentation_thresholds": {
            "relative_path": "segmentation/thresholds.json",
            "required": True,
        },
        "segmentation_config": {
            "relative_path": "segmentation/runtime_config.json",
            "required": False,
        },
    }
    required_files = {
        "classifier_model": "classifier/model.onnx",
        "classifier_labels": "classifier/labels.txt",
        "segmentation_model": "segmentation/model.onnx",
        "segmentation_thresholds": "segmentation/thresholds.json",
        "segmentation_config": "segmentation/runtime_config.json",
    }
    for name, relative_path in required_files.items():
        if name == skip_required:
            continue
        artifact_path = root / relative_path
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        if name == "classifier_labels":
            artifact_path.write_text("_no_event\nпривет\nпока\n", encoding="utf-8")
        elif name.endswith("config"):
            artifact_path.write_text('{"window_size": 64}', encoding="utf-8")
        elif name == "segmentation_thresholds":
            artifact_path.write_text(
                '{"sign": {"th_b": 0.5, "th_o": 0.5}, '
                '"phrase": {"th_b": 0.5, "th_o": 0.5}}',
                encoding="utf-8",
            )
        else:
            artifact_path.write_bytes(name.encode("utf-8"))

    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "contour": "pose_words",
                "profile_id": "runtime_active",
                "profile_role": "active",
                "profile_origin": "runtime",
                "readiness_class": "live_candidate",
                "source_pipeline": "pose_words",
                "files": descriptors,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return manifest_path


def fake_pipeline_factory(artifacts):
    return build_pose_words_runtime_pipeline(
        artifacts,
        extractor_factory=FakeExtractor,
        classifier_factory=FakeClassifier,
        segmenter_model_factory=FakeBioSegmenterModel,
    )


def test_live_pose_words_runtime_initializes_from_active_manifest(
    tmp_path: Path,
) -> None:
    write_active_pack(tmp_path)
    service = LivePoseWordsRuntimeService.from_settings(
        build_settings(tmp_path),
        pipeline_factory=fake_pipeline_factory,
    )

    state = service.initialize()

    assert state.status is LivePoseWordsRuntimeStatus.READY
    assert state.available is True
    assert state.reason_codes == ()
    assert state.profile_id == "runtime_active"
    assert state.pipeline is not None
    assert state.pipeline.classifier.model_path == (
        active_manifest_path(tmp_path).parent / "classifier/model.onnx"
    ).resolve()
    assert state.pipeline.segmentation_model.model_path == (
        active_manifest_path(tmp_path).parent / "segmentation/model.onnx"
    ).resolve()
    assert state.pipeline.clip_frames == 32
    assert state.pipeline.feature_dim == 159
    assert state.pipeline.no_event_index == 0
    assert state.pipeline.segmenter.window == 64


def test_live_pose_words_runtime_reports_unavailable_for_missing_manifest(
    tmp_path: Path,
) -> None:
    service = LivePoseWordsRuntimeService.from_settings(
        build_settings(tmp_path),
        pipeline_factory=fake_pipeline_factory,
    )

    state = service.initialize()

    assert state.status is LivePoseWordsRuntimeStatus.UNAVAILABLE
    assert state.available is False
    assert state.reason_codes == ("active_manifest_missing",)
    assert state.pipeline is None


def test_live_pose_words_runtime_reports_unavailable_for_missing_required_artifact(
    tmp_path: Path,
) -> None:
    write_active_pack(tmp_path, skip_required="segmentation_model")
    service = LivePoseWordsRuntimeService.from_settings(
        build_settings(tmp_path),
        pipeline_factory=fake_pipeline_factory,
    )

    state = service.initialize()

    assert state.status is LivePoseWordsRuntimeStatus.UNAVAILABLE
    assert state.reason_codes == ("active_required_artifacts_missing",)
    assert state.pipeline is None


def test_live_pose_words_runtime_reports_invalid_for_bad_manifest_path(
    tmp_path: Path,
) -> None:
    files = {
        "classifier_model": {
            "relative_path": "../classifier/model.onnx",
            "required": True,
        },
        "classifier_labels": {
            "relative_path": "classifier/labels.txt",
            "required": True,
        },
        "segmentation_model": {
            "relative_path": "segmentation/model.onnx",
            "required": True,
        },
        "segmentation_thresholds": {
            "relative_path": "segmentation/thresholds.json",
            "required": True,
        },
    }
    write_active_pack(tmp_path, files=files)
    service = LivePoseWordsRuntimeService.from_settings(
        build_settings(tmp_path),
        pipeline_factory=fake_pipeline_factory,
    )

    state = service.initialize()

    assert state.status is LivePoseWordsRuntimeStatus.INVALID
    assert state.reason_codes == ("active_manifest_path_traversal_rejected",)
    assert state.pipeline is None


def test_live_pose_words_runtime_does_not_fallback_to_validation_or_bootstrap(
    tmp_path: Path,
) -> None:
    validation_manifest = (
        tmp_path / "artifacts/validation/pose_words/runtime_active/manifest.json"
    )
    bootstrap_manifest = (
        tmp_path / "artifacts/bootstrap/pose_words/runtime_active/manifest.json"
    )
    validation_manifest.parent.mkdir(parents=True, exist_ok=True)
    bootstrap_manifest.parent.mkdir(parents=True, exist_ok=True)
    validation_manifest.write_text("{}", encoding="utf-8")
    bootstrap_manifest.write_text("{}", encoding="utf-8")

    def fail_if_called(_artifacts):
        raise AssertionError("pipeline factory must not run without active manifest")

    service = LivePoseWordsRuntimeService.from_settings(
        build_settings(tmp_path),
        pipeline_factory=fail_if_called,
    )

    state = service.initialize()

    assert state.status is LivePoseWordsRuntimeStatus.UNAVAILABLE
    assert state.reason_codes == ("active_manifest_missing",)
    assert state.manifest_path == active_manifest_path(tmp_path)
