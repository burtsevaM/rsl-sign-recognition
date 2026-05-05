from __future__ import annotations

from types import SimpleNamespace
from typing import Any
import importlib

import numpy as np
import pytest

from rsl_sign_recognition.pipelines.pose_words.features import DEFAULT_FEATURE_DIM
from rsl_sign_recognition.pipelines.pose_words.pose_extraction import (
    PoseExtractor,
    PoseExtractorConfig,
    validate_rgb_frame,
)
from rsl_sign_recognition.pipelines.pose_words.pose_types import (
    BODY_LANDMARK_COUNT,
    FACE_LANDMARK_COUNT,
    HAND_LANDMARK_COUNT,
    PoseFrame,
    PoseLandmarksGroup,
)
from rsl_sign_recognition.pipelines.pose_words.service import PoseFeatureService


def test_pose_extractor_config_does_not_import_mediapipe() -> None:
    config = PoseExtractorConfig(include_face=True)

    assert config.include_face is True


@pytest.mark.parametrize(
    "frame",
    [
        "not-array",
        np.zeros((8, 8, 3), dtype=np.float32),
        np.zeros((8, 8), dtype=np.uint8),
        np.zeros((0, 8, 3), dtype=np.uint8),
        np.zeros((8, 0, 3), dtype=np.uint8),
        np.zeros((8, 8, 4), dtype=np.uint8),
    ],
)
def test_validate_rgb_frame_rejects_invalid_input(frame: Any) -> None:
    with pytest.raises(ValueError):
        validate_rgb_frame(frame)


def test_validate_rgb_frame_accepts_decoded_rgb_uint8() -> None:
    frame = np.zeros((8, 9, 3), dtype=np.uint8)

    validated = validate_rgb_frame(frame)

    assert validated.dtype == np.uint8
    assert validated.shape == (8, 9, 3)
    assert validated.flags.c_contiguous


def test_pose_extractor_reports_clear_error_when_mediapipe_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_import_module(name: str) -> Any:
        if name == "mediapipe":
            raise ModuleNotFoundError("No module named 'mediapipe'", name="mediapipe")
        return importlib.import_module(name)

    monkeypatch.setattr(
        "rsl_sign_recognition.pipelines.pose_words.pose_extraction.importlib.import_module",
        fake_import_module,
    )

    with pytest.raises(ImportError, match="mediapipe is required for PoseExtractor"):
        PoseExtractor()


class _FakeLandmark:
    def __init__(self, x: float, y: float, z: float, visibility: float | None = None):
        self.x = x
        self.y = y
        self.z = z
        if visibility is not None:
            self.visibility = visibility


class _FakeLandmarks:
    def __init__(self, count: int, *, with_visibility: bool = False) -> None:
        self.landmark = [
            _FakeLandmark(
                x=float(idx) * 0.01,
                y=float(idx) * 0.02,
                z=float(idx) * 0.03,
                visibility=1.0 if with_visibility else None,
            )
            for idx in range(count)
        ]


class _FakeHolistic:
    instances: list["_FakeHolistic"] = []

    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs
        self.closed = False
        _FakeHolistic.instances.append(self)

    def process(self, frame: np.ndarray) -> Any:
        self.last_frame = frame
        return SimpleNamespace(
            pose_landmarks=_FakeLandmarks(
                BODY_LANDMARK_COUNT,
                with_visibility=True,
            ),
            left_hand_landmarks=_FakeLandmarks(HAND_LANDMARK_COUNT),
            right_hand_landmarks=_FakeLandmarks(HAND_LANDMARK_COUNT),
            face_landmarks=_FakeLandmarks(FACE_LANDMARK_COUNT),
        )

    def close(self) -> None:
        self.closed = True


def test_pose_extractor_processes_rgb_frame_with_fake_mediapipe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_mp = SimpleNamespace(
        solutions=SimpleNamespace(
            holistic=SimpleNamespace(Holistic=_FakeHolistic),
        ),
    )
    monkeypatch.setattr(
        "rsl_sign_recognition.pipelines.pose_words.pose_extraction.importlib.import_module",
        lambda name: fake_mp if name == "mediapipe" else importlib.import_module(name),
    )

    extractor = PoseExtractor(include_face=False, min_detection_confidence=0.75)
    pose_frame = extractor.process(
        np.zeros((4, 5, 3), dtype=np.uint8),
        timestamp=123.0,
    )
    extractor.close()

    assert pose_frame is not None
    assert pose_frame.timestamp == 123.0
    assert pose_frame.body is not None
    assert pose_frame.body.points.shape == (BODY_LANDMARK_COUNT, 3)
    assert pose_frame.body.confidence is not None
    assert pose_frame.left_hand is not None
    assert pose_frame.left_hand.points.shape == (HAND_LANDMARK_COUNT, 3)
    assert pose_frame.face is None
    assert pose_frame.meta["image_size"] == [4, 5]
    assert _FakeHolistic.instances[-1].kwargs["min_detection_confidence"] == 0.75
    assert _FakeHolistic.instances[-1].closed is True


class _FakeExtractor:
    def __init__(self, pose_frame: PoseFrame | None) -> None:
        self.pose_frame = pose_frame
        self.seen_frame: np.ndarray | None = None

    def process(self, rgb_frame: np.ndarray) -> PoseFrame | None:
        self.seen_frame = rgb_frame
        return self.pose_frame


def _pose_frame() -> PoseFrame:
    body = np.zeros((BODY_LANDMARK_COUNT, 3), dtype=np.float32)
    body[11] = [-0.3, 0.0, 0.0]
    body[12] = [0.3, 0.0, 0.0]
    hand = np.zeros((HAND_LANDMARK_COUNT, 3), dtype=np.float32)
    hand[5] = [0.2, 0.1, 0.0]
    hand[9] = [0.0, 0.4, 0.0]
    hand[17] = [-0.2, 0.1, 0.0]
    return PoseFrame(
        timestamp=1.0,
        body=PoseLandmarksGroup(points=body),
        left_hand=PoseLandmarksGroup(points=hand),
    )


def test_pose_feature_service_uses_fake_extractor_without_mediapipe() -> None:
    extractor = _FakeExtractor(_pose_frame())
    service = PoseFeatureService(extractor=extractor)
    rgb_frame = np.zeros((8, 8, 3), dtype=np.uint8)

    result = service.process_rgb_frame(rgb_frame)

    assert extractor.seen_frame is not None
    assert result.pose_frame is not None
    assert result.feature_vector is not None
    assert result.feature_vector.shape == (DEFAULT_FEATURE_DIM,)
    assert result.feature_vector.dtype == np.float32
    assert result.hand_present is True


def test_pose_feature_service_handles_no_pose() -> None:
    service = PoseFeatureService(extractor=_FakeExtractor(None))

    result = service.process_rgb_frame(np.zeros((8, 8, 3), dtype=np.uint8))

    assert result.pose_frame is None
    assert result.feature_vector is None
    assert result.hand_present is False
    assert result.aux == {"reason": "pose_not_detected"}
