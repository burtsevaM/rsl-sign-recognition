from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from rsl_sign_recognition.api.factory import create_app
from rsl_sign_recognition.runtime.config import RuntimeMode, RuntimeShellSettings


def build_client(tmp_path: Path) -> TestClient:
    settings = RuntimeShellSettings(
        runtime_mode=RuntimeMode.LIVE,
        repo_root=tmp_path,
        active_manifest_path=tmp_path / "artifacts/runtime/active/pose_words/manifest.json",
    )
    return TestClient(create_app(settings=settings))


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
                "unsupported_message_type",
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
            websocket.send_bytes(b"\xff\xd8\xff\xd9")

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
