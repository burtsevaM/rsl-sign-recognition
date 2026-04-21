"""Transport readiness boundary for the clean runtime shell."""

from __future__ import annotations

from dataclasses import dataclass

from rsl_sign_recognition.runtime.readiness import GateStatus


@dataclass(frozen=True)
class LiveTransportSurface:
    """Future boundary for the live WebSocket transport surface."""

    ws_stream_path: str = "/ws/stream"
    live_transport_enabled: bool = False

    def evaluate(self) -> GateStatus:
        if self.live_transport_enabled:
            return GateStatus(passed=True)

        return GateStatus(
            passed=False,
            reason_codes=("ws_stream_route_missing",),
        )
