from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from rsl_sign_recognition.api.factory import create_app
from rsl_sign_recognition.runtime.config import RuntimeMode, RuntimeShellSettings


def build_client(
    tmp_path: Path,
    *,
    runtime_mode: RuntimeMode = RuntimeMode.LIVE,
) -> TestClient:
    settings = RuntimeShellSettings(
        runtime_mode=runtime_mode,
        repo_root=tmp_path,
        active_manifest_path=tmp_path
        / "artifacts/runtime/active/pose_words/manifest.json",
    )
    return TestClient(create_app(settings=settings))


def write_active_artifact_manifest(tmp_path: Path) -> None:
    manifest_path = tmp_path / "artifacts/runtime/active/pose_words/manifest.json"
    root = manifest_path.parent
    required_files = {
        "classifier_model": "classifier/model.onnx",
        "classifier_labels": "classifier/labels.txt",
        "segmentation_model": "segmentation/model.onnx",
        "segmentation_thresholds": "segmentation/thresholds.json",
    }

    for name, relative_path in required_files.items():
        artifact_path = root / relative_path
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
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
                        "required": True,
                    }
                    for name, relative_path in required_files.items()
                },
            }
        ),
        encoding="utf-8",
    )


def error_message(code: str) -> str:
    return {
        "invalid_json": "Invalid JSON control message.",
        "unsupported_control_action": "Unsupported control action.",
        "unsupported_contract_version": "Unsupported contract version.",
        "frame_decode_failed": "Binary frame is not a valid JPEG packet.",
        "runtime_unavailable": "Runtime is unavailable for the current session.",
    }[code]


def error_response(
    code: str,
    *,
    recoverable: bool,
    details: dict[str, object] | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "code": code,
        "message": error_message(code),
        "recoverable": recoverable,
    }
    if details is not None:
        payload["details"] = details

    return {
        "type": "error",
        "contract_version": "1.0",
        "payload": payload,
    }


def test_health_liveness_smoke_stays_green_when_live_runtime_is_not_ready(
    tmp_path: Path,
) -> None:
    with build_client(tmp_path) as client:
        health = client.get("/health")
        ready = client.get("/ready")

    assert health.status_code == 200
    assert health.json() == {
        "status": "ok",
        "probe": "liveness",
        "runtime_mode": "live",
    }
    assert ready.status_code == 503
    assert ready.json()["status"] == "not_ready"
    assert ready.json()["ready_for"] == "live_runtime_path"
    assert ready.json()["gates"] == {
        "runtime_shell": True,
        "active_artifacts": False,
        "transport_surface": False,
    }
    assert ready.json()["reason_codes"] == [
        "active_manifest_missing",
        "live_runtime_pipeline_unavailable",
    ]


def test_ready_smoke_keeps_transport_not_ready_after_artifact_gate_passes(
    tmp_path: Path,
) -> None:
    write_active_artifact_manifest(tmp_path)

    with build_client(tmp_path) as client:
        response = client.get("/ready")

    assert response.status_code == 503
    assert response.json() == {
        "status": "not_ready",
        "probe": "readiness",
        "runtime_mode": "live",
        "ready_for": "live_runtime_path",
        "gates": {
            "runtime_shell": True,
            "active_artifacts": True,
            "transport_surface": False,
        },
        "reason_codes": ["live_runtime_pipeline_unavailable"],
    }


def test_minimal_ws_stream_smoke_covers_control_and_runtime_unavailable(
    tmp_path: Path,
) -> None:
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

            websocket.send_bytes(b"\xff\xd8\xff\xd9")
            assert websocket.receive_json() == error_response(
                "runtime_unavailable",
                recoverable=False,
                details={"reason": "live_inference_pipeline_unavailable"},
            )


def test_ws_stream_returns_invalid_json_for_malformed_control_message(
    tmp_path: Path,
) -> None:
    with build_client(tmp_path) as client:
        with client.websocket_connect("/ws/stream") as websocket:
            websocket.send_text("{")

            assert websocket.receive_json() == error_response(
                "invalid_json",
                recoverable=True,
            )


def test_ws_stream_rejects_unsupported_contract_major_version(
    tmp_path: Path,
) -> None:
    with build_client(tmp_path) as client:
        with client.websocket_connect("/ws/stream") as websocket:
            websocket.send_json(
                {
                    "type": "control.clear_text",
                    "contract_version": "2.0",
                    "payload": {},
                }
            )

            assert websocket.receive_json() == error_response(
                "unsupported_contract_version",
                recoverable=False,
            )


def test_ws_stream_rejects_unknown_control_action(tmp_path: Path) -> None:
    with build_client(tmp_path) as client:
        with client.websocket_connect("/ws/stream") as websocket:
            websocket.send_json(
                {
                    "type": "control.reset_session",
                    "contract_version": "1.0",
                    "payload": {},
                }
            )

            assert websocket.receive_json() == error_response(
                "unsupported_control_action",
                recoverable=True,
            )


def test_ws_stream_returns_frame_decode_failed_for_invalid_binary_frame(
    tmp_path: Path,
) -> None:
    with build_client(tmp_path) as client:
        with client.websocket_connect("/ws/stream") as websocket:
            websocket.send_bytes(b"not-a-jpeg")

            assert websocket.receive_json() == error_response(
                "frame_decode_failed",
                recoverable=True,
            )


def test_mock_mode_smoke_does_not_make_live_readiness_ready(
    tmp_path: Path,
) -> None:
    write_active_artifact_manifest(tmp_path)

    with build_client(tmp_path, runtime_mode=RuntimeMode.MOCK) as client:
        health = client.get("/health")
        ready = client.get("/ready")

    assert health.status_code == 200
    assert health.json()["runtime_mode"] == "mock"
    assert ready.status_code == 503
    assert ready.json()["runtime_mode"] == "mock"
    assert ready.json()["ready_for"] == "live_runtime_path"
    assert ready.json()["gates"] == {
        "runtime_shell": False,
        "active_artifacts": True,
        "transport_surface": False,
    }
    assert ready.json()["reason_codes"] == [
        "runtime_mode_not_live",
        "live_runtime_pipeline_unavailable",
    ]
