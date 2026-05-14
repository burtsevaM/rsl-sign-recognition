"""Transport adapter between WebSocket contract v1 and live pose_words runtime."""

from __future__ import annotations

from dataclasses import dataclass, field
import time

from rsl_sign_recognition.api.frame_decode import FrameDecodeError, decode_jpeg_rgb
from rsl_sign_recognition.contracts.websocket_v1 import (
    frame_decode_failed_error,
    recognition_result,
    response_for_client_text,
    runtime_unavailable_error,
)
from rsl_sign_recognition.runtime.pose_words import (
    PoseWordsLiveSession,
    PoseWordsRuntimeEvent,
    PoseWordsRuntimeEventStatus,
    PoseWordsSessionCreateResult,
)
from rsl_sign_recognition.runtime.shell import RuntimeShell


@dataclass
class WsStreamRuntimeSession:
    """Per-WebSocket bridge that keeps transport state outside the runtime service."""

    runtime_session: PoseWordsLiveSession | None
    create_result: PoseWordsSessionCreateResult
    transcript: list[str] = field(default_factory=list)

    @classmethod
    def create(cls, runtime_shell: RuntimeShell) -> "WsStreamRuntimeSession":
        create_result = runtime_shell.services.pose_words_runtime.create_session()
        return cls(
            runtime_session=create_result.session if create_result.created else None,
            create_result=create_result,
        )

    def handle_text(self, raw_message: str) -> dict[str, object]:
        response = response_for_client_text(raw_message)
        if response.get("type") == "control.ack":
            self.transcript.clear()
            if self.runtime_session is not None:
                self.runtime_session.reset()
        return response

    def handle_binary(self, frame_bytes: bytes) -> dict[str, object]:
        try:
            rgb_frame = decode_jpeg_rgb(frame_bytes)
        except FrameDecodeError:
            return frame_decode_failed_error()

        if self.runtime_session is None:
            return runtime_unavailable_error()

        try:
            event = self.runtime_session.push_frame(rgb_frame)
        except Exception:
            return runtime_unavailable_error()

        return self._response_for_runtime_event(event)

    def close(self) -> None:
        if self.runtime_session is not None:
            self.runtime_session.close()

    def _response_for_runtime_event(
        self,
        event: PoseWordsRuntimeEvent,
    ) -> dict[str, object]:
        if event.status is PoseWordsRuntimeEventStatus.ERROR:
            return runtime_unavailable_error()
        if event.status is PoseWordsRuntimeEventStatus.RESULT:
            return recognition_result(self._result_payload(event))
        return recognition_result(self._no_result_payload(event))

    def _result_payload(self, event: PoseWordsRuntimeEvent) -> dict[str, object]:
        if event.recognition is None:
            return self._no_result_payload(event)

        word = event.recognition.label
        if word:
            self.transcript.append(word)
        return {
            "status": "COMMIT",
            "word": word or "NONE",
            "confidence": _clamp_probability(event.recognition.confidence),
            "hand_present": bool(event.hand_present),
            "hold": {
                "elapsed_ms": 1,
                "remaining_ms": 0,
                "target_ms": 1,
                "progress": 1.0,
                "unit": "segments",
            },
            "text_state": {
                "value": " ".join(self.transcript),
                "committed": True,
            },
            "timestamp_ms": _timestamp_ms(),
        }

    def _no_result_payload(self, event: PoseWordsRuntimeEvent) -> dict[str, object]:
        return {
            "status": "NONE",
            "word": "NONE",
            "confidence": 0.0,
            "hand_present": bool(event.hand_present),
            "hold": {
                "elapsed_ms": 0,
                "remaining_ms": 1,
                "target_ms": 1,
                "progress": 0.0,
                "unit": "segments",
            },
            "text_state": {
                "value": " ".join(self.transcript),
                "committed": False,
            },
            "timestamp_ms": _timestamp_ms(),
        }


def _clamp_probability(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _timestamp_ms() -> int:
    return int(time.monotonic_ns() // 1_000_000)


__all__ = ["WsStreamRuntimeSession"]
