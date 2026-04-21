"""Transport readiness boundary for the clean runtime shell."""

from __future__ import annotations

from dataclasses import dataclass

from rsl_sign_recognition.runtime.readiness import GateStatus


@dataclass(frozen=True)
class LiveTransportSurface:
    """Future boundary for the live WebSocket transport surface."""

    ws_stream_path: str = "/ws/stream"

    def evaluate(self) -> GateStatus:
        return GateStatus(
            passed=False,
            reason_codes=("live_ws_stream_not_implemented",),
        )
