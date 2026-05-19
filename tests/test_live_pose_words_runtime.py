from __future__ import annotations

import json
import inspect
from dataclasses import replace
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from rsl_sign_recognition.pipelines.pose_words.runtime import (
    build_pose_words_runtime_pipeline,
)
from rsl_sign_recognition.runtime.config import RuntimeMode, RuntimeShellSettings
from rsl_sign_recognition.runtime.pose_words import (
    LivePoseWordsRuntimeService,
    LivePoseWordsRuntimeStatus,
    PoseWordsRuntimeEventStatus,
    PoseWordsSessionStatus,
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


class FakeRecognizingClassifier(FakeClassifier):
    def infer_probs(self, features_tf: np.ndarray) -> tuple[np.ndarray, float]:
        return np.asarray([0.05, 0.9, 0.05], dtype=np.float32), 3.0


class FakeFailingPoseFeatureService:
    def __init__(self, exc: Exception) -> None:
        self.exc = exc

    def process_rgb_frame(self, rgb_frame: np.ndarray):
        raise self.exc


class FakeNoHandPoseFeatureResult:
    feature_vector = None
    hand_present = False
    aux = {"reason": "no_hand_detected"}


class FakeNoHandPoseFeatureService:
    def process_rgb_frame(self, rgb_frame: np.ndarray):
        return FakeNoHandPoseFeatureResult()


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


class FakeCompletedSegmenterModel(FakeBioSegmenterModel):
    def infer(self, features_tf: np.ndarray) -> tuple[np.ndarray, np.ndarray, float]:
        length = int(features_tf.shape[0])
        sign = np.zeros((length, 3), dtype=np.float32)
        phrase = np.zeros((length, 3), dtype=np.float32)
        sign[:, 2] = 1.0
        phrase[:, 2] = 1.0
        sign[0, :] = np.asarray([1.0, 0.0, 0.0], dtype=np.float32)
        return sign, phrase, 1.0


class FakeActiveSegmenterModel(FakeBioSegmenterModel):
    def infer(self, features_tf: np.ndarray) -> tuple[np.ndarray, np.ndarray, float]:
        length = int(features_tf.shape[0])
        sign = np.zeros((length, 3), dtype=np.float32)
        phrase = np.zeros((length, 3), dtype=np.float32)
        sign[:, 1] = 1.0
        sign[0, :] = np.asarray([1.0, 0.0, 0.0], dtype=np.float32)
        phrase[:, 2] = 1.0
        return sign, phrase, 1.0


def build_settings(tmp_path: Path) -> RuntimeShellSettings:
    return RuntimeShellSettings(
        runtime_mode=RuntimeMode.LIVE,
        repo_root=tmp_path,
        active_manifest_path=active_manifest_path(tmp_path),
    )


def active_manifest_path(tmp_path: Path) -> Path:
    return tmp_path / "artifacts/runtime/active/pose_words/manifest.json"


def build_mock_settings(tmp_path: Path) -> RuntimeShellSettings:
    return RuntimeShellSettings(
        runtime_mode=RuntimeMode.MOCK,
        repo_root=tmp_path,
        active_manifest_path=active_manifest_path(tmp_path),
    )


def write_active_pack(
    tmp_path: Path,
    *,
    skip_required: str | None = None,
    empty_labels: bool = False,
    files: dict[str, object] | None = None,
    classifier_runtime_config: str | None = None,
    segmentation_runtime_config: str = '{"window_size": 64}',
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
        "classifier_config": {
            "relative_path": "classifier/runtime_config.json",
            "required": False,
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
        "classifier_config": "classifier/runtime_config.json",
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
            labels = "" if empty_labels else "_no_event\nпривет\nпока\n"
            artifact_path.write_text(labels, encoding="utf-8")
        elif name == "classifier_config":
            artifact_path.write_text(
                classifier_runtime_config
                if classifier_runtime_config is not None
                else segmentation_runtime_config,
                encoding="utf-8",
            )
        elif name == "segmentation_config":
            artifact_path.write_text(segmentation_runtime_config, encoding="utf-8")
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


def fake_pipeline_factory_with_completed_segments(artifacts):
    return build_pose_words_runtime_pipeline(
        artifacts,
        extractor_factory=FakeExtractor,
        classifier_factory=FakeClassifier,
        segmenter_model_factory=FakeCompletedSegmenterModel,
    )


def fake_pipeline_factory_with_active_segment(artifacts):
    return build_pose_words_runtime_pipeline(
        artifacts,
        extractor_factory=FakeExtractor,
        classifier_factory=FakeClassifier,
        segmenter_model_factory=FakeActiveSegmenterModel,
    )


def fake_pipeline_factory_with_recognition(artifacts):
    return build_pose_words_runtime_pipeline(
        artifacts,
        extractor_factory=FakeExtractor,
        classifier_factory=FakeRecognizingClassifier,
        segmenter_model_factory=FakeCompletedSegmenterModel,
    )


def fake_pipeline_factory_with_active_recognition(artifacts):
    return build_pose_words_runtime_pipeline(
        artifacts,
        extractor_factory=FakeExtractor,
        classifier_factory=FakeRecognizingClassifier,
        segmenter_model_factory=FakeActiveSegmenterModel,
    )


def fake_pipeline_factory_with_pose_feature_error(exc: Exception):
    def factory(artifacts):
        pipeline = fake_pipeline_factory(artifacts)
        return replace(
            pipeline,
            pose_features=FakeFailingPoseFeatureService(exc),
        )

    return factory


def fake_pipeline_factory_with_no_hand_boundary(artifacts):
    pipeline = fake_pipeline_factory_with_active_recognition(artifacts)
    return replace(
        pipeline,
        pose_features=FakeNoHandPoseFeatureService(),
    )


def create_session(
    tmp_path: Path,
    *,
    pipeline_factory=fake_pipeline_factory,
    max_buffer: int = 4,
):
    write_active_pack(
        tmp_path,
        segmentation_runtime_config=(
            '{"window_size": 2, "step": 1, "min_segment_len": 1}'
        ),
    )
    service = LivePoseWordsRuntimeService.from_settings(
        build_settings(tmp_path),
        pipeline_factory=pipeline_factory,
    )
    result = service.create_session(max_buffer=max_buffer)
    assert result.created
    assert result.session is not None
    return result.session


# RT-08 validates service-level orchestration. The happy path uses fake model
# wrappers so this test does not become an ONNXRuntime/live inference proof.
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
    assert "pose_words_session_state" in state.components
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


def test_live_pose_words_runtime_uses_active_pack_norm_flags(
    tmp_path: Path,
) -> None:
    write_active_pack(
        tmp_path,
        segmentation_runtime_config=(
            '{"window_size": 64, "norm_flags": '
            '{"use_shoulder_norm": false, "use_hands_3d_norm": false}}'
        ),
    )
    service = LivePoseWordsRuntimeService.from_settings(
        build_settings(tmp_path),
        pipeline_factory=fake_pipeline_factory,
    )

    state = service.initialize()

    assert state.pipeline is not None
    assert state.pipeline.pose_features.config.apply_shoulder_norm is False
    assert state.pipeline.pose_features.config.canonical_hands_3d is False


def test_live_pose_words_runtime_defaults_missing_norm_flags_to_safe_true(
    tmp_path: Path,
) -> None:
    write_active_pack(
        tmp_path,
        classifier_runtime_config='{"clip_frames": 32}',
        segmentation_runtime_config='{"window_size": 64}',
    )
    service = LivePoseWordsRuntimeService.from_settings(
        build_settings(tmp_path),
        pipeline_factory=fake_pipeline_factory,
    )

    state = service.initialize()

    assert state.pipeline is not None
    assert state.pipeline.pose_features.config.apply_shoulder_norm is True
    assert state.pipeline.pose_features.config.canonical_hands_3d is True


def test_live_pose_words_runtime_rejects_conflicting_norm_flags(
    tmp_path: Path,
) -> None:
    write_active_pack(
        tmp_path,
        classifier_runtime_config=(
            '{"norm_flags": {"use_shoulder_norm": true, '
            '"use_hands_3d_norm": true}}'
        ),
        segmentation_runtime_config=(
            '{"window_size": 64, "norm_flags": '
            '{"use_shoulder_norm": false, "use_hands_3d_norm": true}}'
        ),
    )
    service = LivePoseWordsRuntimeService.from_settings(
        build_settings(tmp_path),
        pipeline_factory=fake_pipeline_factory,
    )

    state = service.initialize()

    assert state.status is LivePoseWordsRuntimeStatus.INVALID
    assert state.pipeline is None
    assert "pose_words_runtime_config_invalid" in state.reason_codes
    assert "exception:PoseWordsRuntimeAssemblyError" in state.reason_codes
    assert "cause:ValueError" in state.reason_codes
    assert "phase:runtime_config" in state.reason_codes


def test_rt05_service_level_runtime_path_is_orchestrated_without_transport(
    tmp_path: Path,
) -> None:
    write_active_pack(
        tmp_path,
        segmentation_runtime_config=(
            '{"window_size": 2, "step": 1, "min_segment_len": 1}'
        ),
    )
    service = LivePoseWordsRuntimeService.from_settings(
        build_settings(tmp_path),
        pipeline_factory=fake_pipeline_factory_with_recognition,
    )

    result = service.create_session(session_id="rt05-session", max_buffer=4)

    assert result.created is True
    assert result.status is LivePoseWordsRuntimeStatus.READY
    assert result.reason_codes == ()
    assert result.session is not None
    assert result.runtime_state is not None
    assert result.runtime_state.available is True
    assert result.runtime_state.components == (
        "active_artifact_loader",
        "pose_feature_service",
        "bio_segmentation",
        "pose_words_classifier",
        "pose_words_session_state",
    )
    assert result.runtime_state.artifacts is not None
    active_root = active_manifest_path(tmp_path).parent.resolve()
    assert result.runtime_state.artifacts.manifest_path == active_manifest_path(tmp_path)
    assert result.runtime_state.artifacts.classifier_model_path == (
        active_root / "classifier/model.onnx"
    )
    assert result.runtime_state.artifacts.segmentation_model_path == (
        active_root / "segmentation/model.onnx"
    )
    assert not {
        "validation",
        "bootstrap",
        "gesture-recognition-draft",
    }.intersection(result.runtime_state.artifacts.manifest_path.parts)

    first_event = result.session.push_feature(np.ones(159, dtype=np.float32))
    second_event = result.session.push_feature(np.ones(159, dtype=np.float32))

    assert first_event.status is PoseWordsRuntimeEventStatus.NO_RESULT
    assert first_event.reason_code == "insufficient_buffer"
    assert second_event.status is PoseWordsRuntimeEventStatus.RESULT
    assert second_event.reason_code is None
    assert second_event.recognition is not None
    assert second_event.recognition.label == "привет"
    assert second_event.recognition.confidence == pytest.approx(0.9)
    assert "contract_version" not in second_event.as_payload()


def test_live_pose_words_runtime_flushes_active_segment_on_no_hand_boundary(
    tmp_path: Path,
) -> None:
    session = create_session(
        tmp_path,
        pipeline_factory=fake_pipeline_factory_with_active_recognition,
    )
    first_event = session.push_feature(np.ones(159, dtype=np.float32))
    second_event = session.push_feature(np.ones(159, dtype=np.float32))
    assert first_event.status is PoseWordsRuntimeEventStatus.NO_RESULT
    assert second_event.status is PoseWordsRuntimeEventStatus.NO_RESULT
    assert second_event.reason_code == "no_completed_segment"

    session = create_session(
        tmp_path,
        pipeline_factory=fake_pipeline_factory_with_no_hand_boundary,
    )
    session.push_feature(np.ones(159, dtype=np.float32))
    session.push_feature(np.ones(159, dtype=np.float32))

    flushed = session.push_frame(np.zeros((2, 2, 3), dtype=np.uint8))

    assert flushed.status is PoseWordsRuntimeEventStatus.RESULT
    assert flushed.recognition is not None
    assert flushed.recognition.label == "привет"


def test_live_pose_words_runtime_classifies_short_flush_segment_before_full_window(
    tmp_path: Path,
) -> None:
    write_active_pack(
        tmp_path,
        segmentation_runtime_config=(
            '{"window_size": 20, "step": 1, "min_segment_len": 1}'
        ),
    )
    service = LivePoseWordsRuntimeService.from_settings(
        build_settings(tmp_path),
        pipeline_factory=fake_pipeline_factory_with_no_hand_boundary,
    )
    result = service.create_session(max_buffer=32)
    assert result.created
    assert result.session is not None
    session = result.session

    for _ in range(6):
        event = session.push_feature(np.ones(159, dtype=np.float32))
        assert event.status is PoseWordsRuntimeEventStatus.NO_RESULT

    flushed = session.push_frame(np.zeros((2, 2, 3), dtype=np.uint8))

    assert flushed.status is PoseWordsRuntimeEventStatus.RESULT
    assert flushed.recognition is not None
    assert flushed.recognition.label == "привет"
    assert flushed.buffer.length == 6


def test_live_pose_words_runtime_no_hand_boundary_without_active_segment_stays_no_result(
    tmp_path: Path,
) -> None:
    session = create_session(tmp_path, pipeline_factory=fake_pipeline_factory)

    no_hand = session.push_frame(np.zeros((2, 2, 3), dtype=np.uint8))

    assert no_hand.status is PoseWordsRuntimeEventStatus.NO_RESULT
    assert no_hand.reason_code == "pose_not_detected"
    assert no_hand.recognition is None


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
    assert state.missing_artifacts == ()
    assert state.pipeline is None


def test_live_pose_words_runtime_readiness_uses_public_pipeline_reason_for_missing_manifest(
    tmp_path: Path,
) -> None:
    service = LivePoseWordsRuntimeService.from_settings(
        build_settings(tmp_path),
        pipeline_factory=fake_pipeline_factory,
    )

    gate = service.evaluate_readiness()

    assert gate.passed is False
    assert gate.reason_codes == ("live_runtime_pipeline_unavailable",)


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
    assert state.missing_artifacts == ("segmentation_model",)
    assert state.as_payload()["missing_artifacts"] == ["segmentation_model"]
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
    assert state.missing_artifacts == ()
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


@pytest.mark.parametrize(
    ("factory_error", "expected_status", "expected_reason", "expected_exception"),
    [
        (
            ImportError("missing optional runtime dependency"),
            LivePoseWordsRuntimeStatus.UNAVAILABLE,
            "inference_backend_unavailable",
            "exception:ImportError",
        ),
        (
            FileNotFoundError("runtime component disappeared"),
            LivePoseWordsRuntimeStatus.UNAVAILABLE,
            "pose_words_runtime_component_missing",
            "exception:FileNotFoundError",
        ),
        (
            ValueError("invalid runtime component"),
            LivePoseWordsRuntimeStatus.INVALID,
            "pose_words_runtime_config_invalid",
            "exception:ValueError",
        ),
        (
            TypeError("invalid runtime factory wiring"),
            LivePoseWordsRuntimeStatus.INVALID,
            "pose_words_runtime_config_invalid",
            "exception:TypeError",
        ),
    ],
)
def test_live_pose_words_runtime_controls_pipeline_factory_failures(
    tmp_path: Path,
    factory_error: Exception,
    expected_status: LivePoseWordsRuntimeStatus,
    expected_reason: str,
    expected_exception: str,
) -> None:
    write_active_pack(tmp_path)

    def failing_pipeline_factory(_artifacts: Any):
        raise factory_error

    service = LivePoseWordsRuntimeService.from_settings(
        build_settings(tmp_path),
        pipeline_factory=failing_pipeline_factory,
    )

    state = service.initialize()

    assert state.status is expected_status
    assert state.available is False
    assert expected_reason in state.reason_codes
    assert expected_exception in state.reason_codes
    assert state.missing_artifacts == ()
    assert state.pipeline is None


@pytest.mark.parametrize(
    ("factory_error", "expected_reason"),
    [
        (
            ImportError("missing optional runtime dependency"),
            "pose_words_runtime_dependency_unavailable",
        ),
        (
            FileNotFoundError("runtime component disappeared"),
            "pose_words_runtime_component_missing",
        ),
        (
            ValueError("invalid runtime component"),
            "pose_words_runtime_misconfigured",
        ),
    ],
)
def test_live_pose_words_runtime_readiness_maps_controlled_states_for_web_team(
    tmp_path: Path,
    factory_error: Exception,
    expected_reason: str,
) -> None:
    write_active_pack(tmp_path)

    def failing_pipeline_factory(_artifacts: Any):
        raise factory_error

    service = LivePoseWordsRuntimeService.from_settings(
        build_settings(tmp_path),
        pipeline_factory=failing_pipeline_factory,
    )

    gate = service.evaluate_readiness()

    assert gate.passed is False
    assert gate.reason_codes == (expected_reason,)


def test_default_pose_words_pipeline_failure_is_controlled_without_onnxruntime(
    tmp_path: Path,
) -> None:
    write_active_pack(tmp_path, empty_labels=True)
    service = LivePoseWordsRuntimeService.from_settings(build_settings(tmp_path))

    state = service.initialize()

    assert state.status is LivePoseWordsRuntimeStatus.INVALID
    assert state.available is False
    assert "pose_words_runtime_config_invalid" in state.reason_codes
    assert "exception:PoseWordsRuntimeAssemblyError" in state.reason_codes
    assert "cause:ValueError" in state.reason_codes
    assert "phase:classifier_config" in state.reason_codes
    assert state.missing_artifacts == ()
    assert state.pipeline is None


def test_pose_words_runtime_invalid_segmentation_config_is_controlled(
    tmp_path: Path,
) -> None:
    write_active_pack(tmp_path, segmentation_runtime_config="{not-json")
    service = LivePoseWordsRuntimeService.from_settings(
        build_settings(tmp_path),
        pipeline_factory=fake_pipeline_factory,
    )

    state = service.initialize()

    assert state.status is LivePoseWordsRuntimeStatus.INVALID
    assert state.available is False
    assert "pose_words_runtime_config_invalid" in state.reason_codes
    assert "exception:PoseWordsRuntimeAssemblyError" in state.reason_codes
    assert "cause:JSONDecodeError" in state.reason_codes
    assert "phase:runtime_config" in state.reason_codes
    assert state.pipeline is None


def test_pose_words_runtime_unavailable_when_inference_backend_is_missing(
    tmp_path: Path,
) -> None:
    write_active_pack(tmp_path)

    def classifier_backend_missing(**_kwargs: object):
        raise ImportError("onnxruntime is not installed")

    def pipeline_factory(artifacts):
        return build_pose_words_runtime_pipeline(
            artifacts,
            extractor_factory=FakeExtractor,
            classifier_factory=classifier_backend_missing,
            segmenter_model_factory=FakeBioSegmenterModel,
        )

    service = LivePoseWordsRuntimeService.from_settings(
        build_settings(tmp_path),
        pipeline_factory=pipeline_factory,
    )

    state = service.initialize()

    assert state.status is LivePoseWordsRuntimeStatus.UNAVAILABLE
    assert state.available is False
    assert "inference_backend_unavailable" in state.reason_codes
    assert "cause:ImportError" in state.reason_codes
    assert "phase:classifier_backend" in state.reason_codes
    assert state.pipeline is None


def test_pose_words_runtime_model_loading_error_is_controlled(
    tmp_path: Path,
) -> None:
    write_active_pack(tmp_path)

    def classifier_model_load_failed(**_kwargs: object):
        raise RuntimeError("ONNX session could not load model")

    def pipeline_factory(artifacts):
        return build_pose_words_runtime_pipeline(
            artifacts,
            extractor_factory=FakeExtractor,
            classifier_factory=classifier_model_load_failed,
            segmenter_model_factory=FakeBioSegmenterModel,
        )

    service = LivePoseWordsRuntimeService.from_settings(
        build_settings(tmp_path),
        pipeline_factory=pipeline_factory,
    )

    state = service.initialize()

    assert state.status is LivePoseWordsRuntimeStatus.INVALID
    assert state.available is False
    assert "pose_words_model_loading_failed" in state.reason_codes
    assert "cause:RuntimeError" in state.reason_codes
    assert "phase:classifier_model" in state.reason_codes
    assert state.pipeline is None


def test_mock_runtime_mode_does_not_make_live_pose_words_runtime_available(
    tmp_path: Path,
) -> None:
    write_active_pack(tmp_path)

    def fail_if_called(_artifacts):
        raise AssertionError("mock mode must not assemble live runtime")

    service = LivePoseWordsRuntimeService.from_settings(
        build_mock_settings(tmp_path),
        pipeline_factory=fail_if_called,
    )

    state = service.initialize()
    result = service.create_session()

    assert state.status is LivePoseWordsRuntimeStatus.UNAVAILABLE
    assert state.reason_codes == ("runtime_mode_not_live",)
    assert state.pipeline is None
    assert state.available is False
    assert result.created is False
    assert result.status is LivePoseWordsRuntimeStatus.UNAVAILABLE
    assert result.session is None


def test_pose_words_session_starts_initialized_with_empty_buffer(
    tmp_path: Path,
) -> None:
    session = create_session(tmp_path)

    snapshot = session.snapshot()

    assert snapshot.status is PoseWordsSessionStatus.INITIALIZED
    assert snapshot.buffer.empty is True
    assert snapshot.buffer.length == 0
    assert snapshot.buffer.next_index == 0


def test_pose_words_session_empty_buffer_returns_controlled_no_result(
    tmp_path: Path,
) -> None:
    session = create_session(tmp_path)

    event = session.decode_next()

    assert event.status is PoseWordsRuntimeEventStatus.NO_RESULT
    assert event.reason_code == "empty_buffer"
    assert event.buffer.empty is True


def test_pose_words_session_insufficient_buffer_is_controlled(
    tmp_path: Path,
) -> None:
    session = create_session(tmp_path)

    event = session.push_feature(np.ones(159, dtype=np.float32))

    assert event.status is PoseWordsRuntimeEventStatus.NO_RESULT
    assert event.reason_code == "insufficient_buffer"
    assert event.feature_index == 0
    assert event.buffer.length == 1
    assert session.snapshot().status is PoseWordsSessionStatus.ACTIVE


def test_pose_words_session_feature_indices_and_bounded_buffer_are_predictable(
    tmp_path: Path,
) -> None:
    session = create_session(tmp_path, max_buffer=2)

    events = [
        session.push_feature(np.full(159, value, dtype=np.float32))
        for value in (1.0, 2.0, 3.0)
    ]

    assert [event.feature_index for event in events] == [0, 1, 2]
    snapshot = session.snapshot()
    assert snapshot.buffer.length == 2
    assert snapshot.buffer.max_size == 2
    assert snapshot.buffer.start_index == 1
    assert snapshot.buffer.end_index == 2
    assert snapshot.buffer.next_index == 3


def test_pose_words_sessions_do_not_share_buffer_or_state(tmp_path: Path) -> None:
    write_active_pack(
        tmp_path,
        segmentation_runtime_config=(
            '{"window_size": 2, "step": 1, "min_segment_len": 1}'
        ),
    )
    service = LivePoseWordsRuntimeService.from_settings(
        build_settings(tmp_path),
        pipeline_factory=fake_pipeline_factory,
    )
    first = service.create_session(max_buffer=4).session
    second = service.create_session(max_buffer=4).session
    assert first is not None
    assert second is not None

    event = first.push_feature(np.ones(159, dtype=np.float32))

    assert event.feature_index == 0
    assert first.snapshot().buffer.length == 1
    assert second.snapshot().buffer.length == 0
    assert first.session_id != second.session_id


def test_pose_words_session_reset_and_close_lifecycle(tmp_path: Path) -> None:
    session = create_session(tmp_path)
    session.push_feature(np.ones(159, dtype=np.float32))

    reset = session.reset()

    assert reset.reason_code == "session_reset"
    assert session.snapshot().status is PoseWordsSessionStatus.INITIALIZED
    assert session.snapshot().buffer.empty is True
    event_after_reset = session.push_feature(np.ones(159, dtype=np.float32))
    assert event_after_reset.feature_index == 0

    close = session.close()
    event_after_close = session.push_feature(np.ones(159, dtype=np.float32))

    assert close.reason_code == "session_closed"
    assert close.session_status is PoseWordsSessionStatus.CLOSED
    assert event_after_close.status is PoseWordsRuntimeEventStatus.ERROR
    assert event_after_close.reason_code == "session_closed"
    assert event_after_close.buffer.empty is True


def test_pose_words_session_controls_invalid_feature_dimensions(
    tmp_path: Path,
) -> None:
    session = create_session(tmp_path)

    event = session.push_feature(np.ones(10, dtype=np.float32))

    assert event.status is PoseWordsRuntimeEventStatus.ERROR
    assert event.reason_code == "feature_dimension_mismatch"
    assert event.buffer.empty is True


def test_pose_words_session_pose_not_detected_is_no_result(tmp_path: Path) -> None:
    session = create_session(tmp_path)
    rgb = np.zeros((8, 8, 3), dtype=np.uint8)

    event = session.push_frame(rgb)

    assert event.status is PoseWordsRuntimeEventStatus.NO_RESULT
    assert event.reason_code == "pose_not_detected"
    assert event.hand_present is False
    assert event.buffer.empty is True


@pytest.mark.parametrize(
    ("exc", "expected_exception"),
    [
        (RuntimeError("pose backend crashed"), "RuntimeError"),
        (OSError("pose backend unavailable"), "OSError"),
    ],
)
def test_pose_words_session_controls_pose_feature_runtime_failures(
    tmp_path: Path,
    exc: Exception,
    expected_exception: str,
) -> None:
    session = create_session(
        tmp_path,
        pipeline_factory=fake_pipeline_factory_with_pose_feature_error(exc),
    )
    rgb = np.zeros((8, 8, 3), dtype=np.uint8)

    event = session.push_frame(rgb)

    assert event.status is PoseWordsRuntimeEventStatus.ERROR
    assert event.reason_code == "pose_feature_runtime_failed"
    assert event.details["exception"] == expected_exception
    assert event.details["message"] == str(exc)
    assert event.buffer.empty is True


@pytest.mark.parametrize(
    "bad_value",
    [np.nan, np.inf, -np.inf],
)
def test_pose_words_session_rejects_non_finite_feature_values(
    tmp_path: Path,
    bad_value: float,
) -> None:
    session = create_session(tmp_path)
    feature = np.ones(159, dtype=np.float32)
    feature[3] = bad_value

    event = session.push_feature(feature)

    assert event.status is PoseWordsRuntimeEventStatus.ERROR
    assert event.reason_code == "invalid_feature_vector"
    assert event.details["exception"] == "ValueError"
    assert event.buffer.empty is True


def test_pose_words_session_no_active_segment_is_domain_no_result(
    tmp_path: Path,
) -> None:
    session = create_session(tmp_path)

    session.push_feature(np.ones(159, dtype=np.float32))
    event = session.push_feature(np.ones(159, dtype=np.float32))

    assert event.status is PoseWordsRuntimeEventStatus.NO_RESULT
    assert event.reason_code == "no_active_segment"
    assert event.buffer.length == 2


def test_pose_words_session_no_completed_segment_is_domain_no_result(
    tmp_path: Path,
) -> None:
    session = create_session(
        tmp_path,
        pipeline_factory=fake_pipeline_factory_with_active_segment,
    )

    session.push_feature(np.ones(159, dtype=np.float32))
    event = session.push_feature(np.ones(159, dtype=np.float32))

    assert event.status is PoseWordsRuntimeEventStatus.NO_RESULT
    assert event.reason_code == "no_completed_segment"
    assert event.buffer.length == 2


def test_pose_words_session_no_event_label_is_domain_no_result(
    tmp_path: Path,
) -> None:
    session = create_session(
        tmp_path,
        pipeline_factory=fake_pipeline_factory_with_completed_segments,
    )

    session.push_feature(np.ones(159, dtype=np.float32))
    event = session.push_feature(np.ones(159, dtype=np.float32))

    assert event.status is PoseWordsRuntimeEventStatus.NO_RESULT
    assert event.reason_code == "no_event"
    assert event.details["label"] == "_no_event"
    assert event.has_result is False


def test_pose_words_session_returns_recognition_result_without_transport(
    tmp_path: Path,
) -> None:
    session = create_session(
        tmp_path,
        pipeline_factory=fake_pipeline_factory_with_recognition,
    )

    session.push_feature(np.ones(159, dtype=np.float32))
    event = session.push_feature(np.ones(159, dtype=np.float32))

    assert event.status is PoseWordsRuntimeEventStatus.RESULT
    assert event.reason_code is None
    assert event.recognition is not None
    assert event.recognition.label == "привет"
    assert event.recognition.confidence == pytest.approx(0.9)


def test_pose_words_session_create_result_is_controlled_when_runtime_unavailable(
    tmp_path: Path,
) -> None:
    service = LivePoseWordsRuntimeService.from_settings(
        build_settings(tmp_path),
        pipeline_factory=fake_pipeline_factory,
    )

    result = service.create_session()

    assert result.created is False
    assert result.status is LivePoseWordsRuntimeStatus.UNAVAILABLE
    assert result.reason_codes == ("active_manifest_missing",)
    assert result.session is None


def test_pose_words_decoder_boundary_has_no_websocket_transport_import() -> None:
    import rsl_sign_recognition.runtime.pose_words as pose_words_runtime

    source = inspect.getsource(pose_words_runtime)

    assert "api.routes" not in source
    assert "ws_stream" not in source
