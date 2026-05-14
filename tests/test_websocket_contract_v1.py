from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from rsl_sign_recognition.contracts.websocket_v1 import (
    control_ack,
    frame_decode_failed_error,
    recognition_result,
    response_for_client_text,
    runtime_unavailable_error,
)


FIXTURES_ROOT = (
    Path(__file__).resolve().parents[1] / "docs/contracts/fixtures"
)
SERVER_MESSAGE_TYPES = {"recognition.result", "control.ack", "error"}
FORBIDDEN_PROTOCOL_TYPES = {
    "partial.result",
    "final.result",
    "session.start",
    "session.stop",
    "frame.jpeg",
}
FORBIDDEN_PROTOCOL_FIELDS = {"mock", "session_id", "request_id", "trace_id"}


def load_fixture(name: str) -> dict[str, Any]:
    with (FIXTURES_ROOT / name).open(encoding="utf-8") as handle:
        payload = json.load(handle)
    assert isinstance(payload, dict)
    return payload


def assert_contract_envelope(message: dict[str, Any]) -> None:
    assert set(message) == {"type", "contract_version", "payload"}
    assert message["type"] in SERVER_MESSAGE_TYPES
    assert message["contract_version"] == "1.0"
    assert isinstance(message["payload"], dict)
    assert message["payload"] is not None
    assert FORBIDDEN_PROTOCOL_FIELDS.isdisjoint(message)
    assert FORBIDDEN_PROTOCOL_FIELDS.isdisjoint(message["payload"])


def assert_error_message(
    message: dict[str, Any],
    *,
    code: str,
    recoverable: bool,
) -> None:
    assert_contract_envelope(message)
    assert message["type"] == "error"
    payload = message["payload"]
    assert payload["code"] == code
    assert isinstance(payload["message"], str)
    assert payload["message"]
    assert payload["recoverable"] is recoverable
    if "details" in payload:
        assert isinstance(payload["details"], dict)


def assert_recognition_result(
    message: dict[str, Any],
    *,
    status: str,
    committed: bool,
) -> None:
    assert_contract_envelope(message)
    assert message["type"] == "recognition.result"

    payload = message["payload"]
    assert payload["status"] == status
    assert isinstance(payload["word"], str)
    assert isinstance(payload["confidence"], int | float)
    assert 0 <= payload["confidence"] <= 1
    assert isinstance(payload["hand_present"], bool)
    assert isinstance(payload["timestamp_ms"], int)

    hold = payload["hold"]
    assert isinstance(hold, dict)
    assert set(hold) == {
        "elapsed_ms",
        "remaining_ms",
        "target_ms",
        "progress",
        "unit",
    }
    assert isinstance(hold["elapsed_ms"], int)
    assert isinstance(hold["remaining_ms"], int)
    assert isinstance(hold["target_ms"], int)
    assert isinstance(hold["progress"], int | float)
    assert 0 <= hold["progress"] <= 1
    assert hold["unit"] in {"ms", "frames", "segments"}

    text_state = payload["text_state"]
    assert isinstance(text_state, dict)
    assert set(text_state) == {"value", "committed"}
    assert isinstance(text_state["value"], str)
    assert text_state["committed"] is committed


@pytest.mark.parametrize(
    ("fixture_name", "status", "committed"),
    [
        ("mock-recognition-result-hold.json", "HOLD", False),
        ("mock-recognition-result-commit.json", "COMMIT", True),
    ],
)
def test_recognition_result_fixtures_follow_contract_v1_stable_surface(
    fixture_name: str,
    status: str,
    committed: bool,
) -> None:
    message = load_fixture(fixture_name)

    assert_recognition_result(message, status=status, committed=committed)


def test_control_ack_fixture_follows_contract_v1() -> None:
    message = load_fixture("mock-control-ack-clear-text.json")

    assert_contract_envelope(message)
    assert message == {
        "type": "control.ack",
        "contract_version": "1.0",
        "payload": {
            "action": "clear_text",
            "accepted": True,
        },
    }


def test_runtime_unavailable_fixture_is_contract_error_not_live_result() -> None:
    message = load_fixture("mock-session-error-runtime-unavailable.json")

    assert_error_message(message, code="runtime_unavailable", recoverable=False)
    assert message["type"] != "recognition.result"


def test_server_helpers_emit_documented_contract_v1_messages_only() -> None:
    messages = [
        control_ack("clear_text"),
        frame_decode_failed_error(),
        recognition_result(load_fixture("mock-recognition-result-hold.json")["payload"]),
        runtime_unavailable_error(),
    ]

    for message in messages:
        assert_contract_envelope(message)
        assert message["type"] not in FORBIDDEN_PROTOCOL_TYPES


def test_runtime_unavailable_helper_preserves_mock_live_boundary() -> None:
    message = runtime_unavailable_error()

    assert_error_message(message, code="runtime_unavailable", recoverable=False)
    assert message["payload"]["details"] == {
        "reason": "live_inference_pipeline_unavailable",
    }
    assert "mock" not in message["payload"]


def test_frame_decode_failed_helper_is_recoverable_contract_error() -> None:
    message = frame_decode_failed_error()

    assert_error_message(message, code="frame_decode_failed", recoverable=True)


@pytest.mark.parametrize(
    ("raw_message", "code", "recoverable"),
    [
        ("{", "invalid_json", True),
        (
            json.dumps(
                {
                    "type": "control.clear_text",
                    "contract_version": "2.0",
                    "payload": {},
                }
            ),
            "unsupported_contract_version",
            False,
        ),
        (
            json.dumps(
                {
                    "type": "control.reset_session",
                    "contract_version": "1.0",
                    "payload": {},
                }
            ),
            "unsupported_control_action",
            True,
        ),
    ],
)
def test_client_json_path_returns_documented_negative_contract_errors(
    raw_message: str,
    code: str,
    recoverable: bool,
) -> None:
    response = response_for_client_text(raw_message)

    assert_error_message(response, code=code, recoverable=recoverable)


@pytest.mark.parametrize(
    "message_type",
    sorted(FORBIDDEN_PROTOCOL_TYPES),
)
def test_client_json_path_rejects_undocumented_protocol_message_types(
    message_type: str,
) -> None:
    response = response_for_client_text(
        json.dumps(
            {
                "type": message_type,
                "contract_version": "1.0",
                "payload": {},
            }
        )
    )

    assert_error_message(response, code="unsupported_message_type", recoverable=True)
