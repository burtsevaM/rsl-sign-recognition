from __future__ import annotations

from dataclasses import replace
from io import BytesIO
import json
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from rsl_sign_recognition.api.factory import create_app
from rsl_sign_recognition.pipelines.pose_words.runtime import (
    build_pose_words_runtime_pipeline,
)
from rsl_sign_recognition.runtime.config import RuntimeMode, RuntimeShellSettings
from rsl_sign_recognition.runtime.pose_words import LivePoseWordsRuntimeService
from rsl_sign_recognition.runtime.services import RuntimeServiceRegistry


def build_client(tmp_path: Path, *, pipeline_factory=None) -> TestClient:
    settings = RuntimeShellSettings(
        runtime_mode=RuntimeMode.LIVE,
        repo_root=tmp_path,
        active_manifest_path=tmp_path / "artifacts/runtime/active/pose_words/manifest.json",
    )
    if pipeline_factory is None:
        return TestClient(create_app(settings=settings))

    pose_words_runtime = LivePoseWordsRuntimeService.from_settings(
        settings,
        pipeline_factory=pipeline_factory,
    )
    services = RuntimeServiceRegistry.build(
        settings,
        pose_words_runtime=pose_words_runtime,
    )
    return TestClient(create_app(settings=settings, services=services))


class FakePoseFeatureService:
    def process_rgb_frame(self, rgb_frame: np.ndarray):
        assert rgb_frame.dtype == np.uint8
        assert rgb_frame.ndim == 3
        return FakePoseFeatureResult()


class FakePoseFeatureResult:
    feature_vector = np.ones(159, dtype=np.float32)
    hand_present = True
    aux: dict[str, object] = {}


class FakeExtractor:
    def process(self, rgb_frame: np.ndarray):
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
        self.labels = [
            line.strip()
            for line in Path(labels_path).read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        self.input_clip_frames = 32
        self.config_clip_frames = None
        self.input_feature_dim = 159
        self.config_feature_dim = None

    def infer_probs(self, features_tf: np.ndarray) -> tuple[np.ndarray, float]:
        return np.asarray([0.05, 0.9, 0.05], dtype=np.float32), 3.0

    def find_no_event_index(self, label_name: str = "no_event") -> int | None:
        return 0


class FakeCompletedSegmenterModel:
    input_feature_dim = 159
    config_feature_dim = None

    def __init__(
        self,
        *,
        model_path: str | Path,
        config_path: str | Path | None = None,
        ort_num_threads: int = 1,
    ) -> None:
        pass

    def infer(self, features_tf: np.ndarray) -> tuple[np.ndarray, np.ndarray, float]:
        length = int(features_tf.shape[0])
        sign = np.zeros((length, 3), dtype=np.float32)
        phrase = np.zeros((length, 3), dtype=np.float32)
        sign[:, 2] = 1.0
        phrase[:, 2] = 1.0
        sign[0, :] = np.asarray([1.0, 0.0, 0.0], dtype=np.float32)
        return sign, phrase, 1.0


def fake_live_ws_pipeline_factory(artifacts):
    pipeline = build_pose_words_runtime_pipeline(
        artifacts,
        extractor_factory=FakeExtractor,
        classifier_factory=FakeClassifier,
        segmenter_model_factory=FakeCompletedSegmenterModel,
    )
    return replace(pipeline, pose_features=FakePoseFeatureService())


def write_active_pack(tmp_path: Path) -> None:
    manifest_path = tmp_path / "artifacts/runtime/active/pose_words/manifest.json"
    root = manifest_path.parent
    files = {
        "classifier_model": "classifier/model.onnx",
        "classifier_labels": "classifier/labels.txt",
        "segmentation_model": "segmentation/model.onnx",
        "segmentation_thresholds": "segmentation/thresholds.json",
        "segmentation_config": "segmentation/runtime_config.json",
    }
    for name, relative_path in files.items():
        artifact_path = root / relative_path
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        if name == "classifier_labels":
            artifact_path.write_text("_no_event\nпривет\nпока\n", encoding="utf-8")
        elif name == "segmentation_thresholds":
            artifact_path.write_text(
                '{"sign": {"th_b": 0.5, "th_o": 0.5}, '
                '"phrase": {"th_b": 0.5, "th_o": 0.5}}',
                encoding="utf-8",
            )
        elif name == "segmentation_config":
            artifact_path.write_text(
                '{"window_size": 2, "step": 1, "min_segment_len": 1}',
                encoding="utf-8",
            )
        else:
            artifact_path.write_bytes(name.encode("utf-8"))

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
                "files": {
                    name: {
                        "relative_path": relative_path,
                        "required": name != "segmentation_config",
                    }
                    for name, relative_path in files.items()
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def valid_jpeg_bytes() -> bytes:
    image = Image.fromarray(np.full((2, 2, 3), 127, dtype=np.uint8))
    buffer = BytesIO()
    image.save(buffer, format="JPEG")
    return buffer.getvalue()


def error_payload(
    code: str,
    *,
    recoverable: bool,
    details: dict[str, object] | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "code": code,
        "message": _error_message(code),
        "recoverable": recoverable,
    }
    if details is not None:
        payload["details"] = details

    return {
        "type": "error",
        "contract_version": "1.0",
        "payload": payload,
    }


def _error_message(code: str) -> str:
    return {
        "invalid_json": "Invalid JSON control message.",
        "unsupported_message_type": "Unsupported message type.",
        "unsupported_control_action": "Unsupported control action.",
        "unsupported_contract_version": "Unsupported contract version.",
        "frame_decode_failed": "Binary frame is not a valid JPEG packet.",
        "runtime_unavailable": "Runtime is unavailable for the current session.",
    }[code]


def test_ws_stream_accepts_connection(tmp_path: Path) -> None:
    with build_client(tmp_path) as client:
        with client.websocket_connect("/ws/stream"):
            pass


def test_control_clear_text_returns_ack(tmp_path: Path) -> None:
    with build_client(tmp_path) as client:
        with client.websocket_connect("/ws/stream") as websocket:
            websocket.send_json(
                {
                    "type": "control.clear_text",
                    "contract_version": "1.0",
                    "payload": {},
                }
            )

            assert websocket.receive_json() == {
                "type": "control.ack",
                "contract_version": "1.0",
                "payload": {
                    "action": "clear_text",
                    "accepted": True,
                },
            }


@pytest.mark.parametrize(
    "payload",
    [
        {"action": "clear_text"},
        {"unexpected": True},
    ],
)
def test_control_clear_text_rejects_non_empty_payload(
    tmp_path: Path,
    payload: dict[str, object],
) -> None:
    with build_client(tmp_path) as client:
        with client.websocket_connect("/ws/stream") as websocket:
            websocket.send_json(
                {
                    "type": "control.clear_text",
                    "contract_version": "1.0",
                    "payload": payload,
                }
            )

            response = websocket.receive_json()

    assert response != {
        "type": "control.ack",
        "contract_version": "1.0",
        "payload": {
            "action": "clear_text",
            "accepted": True,
        },
    }
    assert response == error_payload(
        "unsupported_control_action",
        recoverable=True,
    )


@pytest.mark.parametrize(
    "message",
    [
        {
            "type": "control.clear_text",
            "contract_version": "1.0",
        },
        {
            "type": "control.clear_text",
            "contract_version": "1.0",
            "payload": None,
        },
    ],
)
def test_control_clear_text_rejects_missing_or_non_object_payload(
    tmp_path: Path,
    message: dict[str, object],
) -> None:
    with build_client(tmp_path) as client:
        with client.websocket_connect("/ws/stream") as websocket:
            websocket.send_json(message)

            assert websocket.receive_json() == error_payload(
                "unsupported_control_action",
                recoverable=True,
            )


def test_invalid_json_returns_recoverable_error(tmp_path: Path) -> None:
    with build_client(tmp_path) as client:
        with client.websocket_connect("/ws/stream") as websocket:
            websocket.send_text("{")

            assert websocket.receive_json() == error_payload(
                "invalid_json",
                recoverable=True,
            )


def test_unknown_message_type_returns_recoverable_error(tmp_path: Path) -> None:
    with build_client(tmp_path) as client:
        with client.websocket_connect("/ws/stream") as websocket:
            websocket.send_json(
                {
                    "type": "session.start",
                    "contract_version": "1.0",
                    "payload": {},
                }
            )

            assert websocket.receive_json() == error_payload(
                "unsupported_message_type",
                recoverable=True,
            )


def test_unsupported_control_action_returns_recoverable_error(tmp_path: Path) -> None:
    with build_client(tmp_path) as client:
        with client.websocket_connect("/ws/stream") as websocket:
            websocket.send_json(
                {
                    "type": "control.reset_session",
                    "contract_version": "1.0",
                    "payload": {},
                }
            )

            assert websocket.receive_json() == error_payload(
                "unsupported_control_action",
                recoverable=True,
            )


def test_clear_text_requires_empty_payload(tmp_path: Path) -> None:
    with build_client(tmp_path) as client:
        with client.websocket_connect("/ws/stream") as websocket:
            websocket.send_json(
                {
                    "type": "control.clear_text",
                    "contract_version": "1.0",
                    "payload": {"unexpected": True},
                }
            )

            assert websocket.receive_json() == error_payload(
                "unsupported_control_action",
                recoverable=True,
            )


def test_missing_contract_version_returns_nonrecoverable_error(tmp_path: Path) -> None:
    with build_client(tmp_path) as client:
        with client.websocket_connect("/ws/stream") as websocket:
            websocket.send_json(
                {
                    "type": "control.clear_text",
                    "payload": {},
                }
            )

            assert websocket.receive_json() == error_payload(
                "unsupported_contract_version",
                recoverable=False,
            )


def test_incompatible_contract_major_returns_nonrecoverable_error(tmp_path: Path) -> None:
    with build_client(tmp_path) as client:
        with client.websocket_connect("/ws/stream") as websocket:
            websocket.send_json(
                {
                    "type": "control.clear_text",
                    "contract_version": "2.0",
                    "payload": {},
                }
            )

            assert websocket.receive_json() == error_payload(
                "unsupported_contract_version",
                recoverable=False,
            )


def test_binary_frame_returns_runtime_unavailable_without_fake_result(
    tmp_path: Path,
) -> None:
    with build_client(tmp_path) as client:
        with client.websocket_connect("/ws/stream") as websocket:
            websocket.send_bytes(valid_jpeg_bytes())

            assert websocket.receive_json() == error_payload(
                "runtime_unavailable",
                recoverable=False,
                details={"reason": "live_inference_pipeline_unavailable"},
            )


def test_invalid_binary_frame_returns_recoverable_decode_error(
    tmp_path: Path,
) -> None:
    with build_client(tmp_path) as client:
        with client.websocket_connect("/ws/stream") as websocket:
            websocket.send_bytes(b"not-a-jpeg")

            assert websocket.receive_json() == error_payload(
                "frame_decode_failed",
                recoverable=True,
            )


def test_binary_frame_with_jpeg_markers_but_invalid_body_returns_decode_error(
    tmp_path: Path,
) -> None:
    with build_client(tmp_path) as client:
        with client.websocket_connect("/ws/stream") as websocket:
            websocket.send_bytes(b"\xff\xd8\xff\xd9")

            assert websocket.receive_json() == error_payload(
                "frame_decode_failed",
                recoverable=True,
            )


def test_binary_jpeg_frame_returns_recognition_result_when_live_runtime_is_ready(
    tmp_path: Path,
) -> None:
    write_active_pack(tmp_path)

    with build_client(
        tmp_path,
        pipeline_factory=fake_live_ws_pipeline_factory,
    ) as client:
        with client.websocket_connect("/ws/stream") as websocket:
            websocket.send_bytes(valid_jpeg_bytes())
            first_response = websocket.receive_json()
            websocket.send_bytes(valid_jpeg_bytes())
            second_response = websocket.receive_json()

    assert first_response["type"] == "recognition.result"
    assert first_response["payload"]["status"] == "NONE"
    assert second_response == {
        "type": "recognition.result",
        "contract_version": "1.0",
        "payload": {
            "status": "COMMIT",
            "word": "привет",
            "confidence": pytest.approx(0.9),
            "hand_present": True,
            "hold": {
                "elapsed_ms": 1,
                "remaining_ms": 0,
                "target_ms": 1,
                "progress": 1.0,
                "unit": "segments",
            },
            "text_state": {
                "value": "привет",
                "committed": True,
            },
            "timestamp_ms": second_response["payload"]["timestamp_ms"],
        },
    }
    assert isinstance(second_response["payload"]["timestamp_ms"], int)
    assert "session_id" not in second_response
    assert "session_id" not in second_response["payload"]


def test_clear_text_resets_live_runtime_session_and_transcript(tmp_path: Path) -> None:
    write_active_pack(tmp_path)

    with build_client(
        tmp_path,
        pipeline_factory=fake_live_ws_pipeline_factory,
    ) as client:
        with client.websocket_connect("/ws/stream") as websocket:
            websocket.send_bytes(valid_jpeg_bytes())
            assert websocket.receive_json()["payload"]["status"] == "NONE"
            websocket.send_json(
                {
                    "type": "control.clear_text",
                    "contract_version": "1.0",
                    "payload": {},
                }
            )
            assert websocket.receive_json() == {
                "type": "control.ack",
                "contract_version": "1.0",
                "payload": {
                    "action": "clear_text",
                    "accepted": True,
                },
            }
            websocket.send_bytes(valid_jpeg_bytes())

            response = websocket.receive_json()

    assert response["type"] == "recognition.result"
    assert response["payload"]["status"] == "NONE"
    assert response["payload"]["text_state"] == {
        "value": "",
        "committed": False,
    }
