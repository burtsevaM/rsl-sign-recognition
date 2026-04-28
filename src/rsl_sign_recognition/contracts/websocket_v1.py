"""Helpers for the WebSocket contract v1 wire envelopes."""

from __future__ import annotations

import json
from typing import Any

CONTRACT_VERSION = "1.0"
EXPECTED_MAJOR_VERSION = "1"


def control_ack(action: str) -> dict[str, object]:
    return envelope(
        "control.ack",
        {
            "action": action,
            "accepted": True,
        },
    )


def error_envelope(
    code: str,
    *,
    message: str,
    recoverable: bool,
    details: dict[str, object] | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "code": code,
        "message": message,
        "recoverable": recoverable,
    }
    if details is not None:
        payload["details"] = details

    return envelope(
        "error",
        payload,
    )


def envelope(message_type: str, payload: dict[str, object]) -> dict[str, object]:
    return {
        "type": message_type,
        "contract_version": CONTRACT_VERSION,
        "payload": payload,
    }


def response_for_client_text(raw_message: str) -> dict[str, object]:
    try:
        message = json.loads(raw_message)
    except json.JSONDecodeError:
        return invalid_json_error()

    if not isinstance(message, dict):
        return invalid_json_error()

    if not is_compatible_contract_version(message.get("contract_version")):
        return unsupported_contract_version_error()

    message_type = message.get("type")
    payload = message.get("payload")

    if message_type == "control.clear_text":
        if payload != {}:
            return unsupported_control_action_error()
        return control_ack("clear_text")

    if isinstance(message_type, str) and message_type.startswith("control."):
        return unsupported_control_action_error()

    return unsupported_message_type_error()


def invalid_json_error() -> dict[str, object]:
    return error_envelope(
        "invalid_json",
        message="Invalid JSON control message.",
        recoverable=True,
    )


def unsupported_message_type_error() -> dict[str, object]:
    return error_envelope(
        "unsupported_message_type",
        message="Unsupported message type.",
        recoverable=True,
    )


def unsupported_control_action_error() -> dict[str, object]:
    return error_envelope(
        "unsupported_control_action",
        message="Unsupported control action.",
        recoverable=True,
    )


def unsupported_contract_version_error() -> dict[str, object]:
    return error_envelope(
        "unsupported_contract_version",
        message="Unsupported contract version.",
        recoverable=False,
    )


def runtime_unavailable_error() -> dict[str, object]:
    return error_envelope(
        "runtime_unavailable",
        message="Runtime is unavailable for the current session.",
        recoverable=False,
        details={"reason": "live_inference_pipeline_unavailable"},
    )


def frame_decode_failed_error() -> dict[str, object]:
    return error_envelope(
        "frame_decode_failed",
        message="Binary frame is not a valid JPEG packet.",
        recoverable=True,
    )


def is_compatible_contract_version(value: Any) -> bool:
    if not isinstance(value, str):
        return False

    major, _, _minor = value.partition(".")
    return major == EXPECTED_MAJOR_VERSION


def is_jpeg_packet(value: bytes) -> bool:
    return value.startswith(b"\xff\xd8") and value.endswith(b"\xff\xd9")
