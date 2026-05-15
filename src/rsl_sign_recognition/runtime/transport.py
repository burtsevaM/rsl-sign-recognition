"""Transport readiness boundary for the clean runtime shell."""

from __future__ import annotations

from dataclasses import dataclass

from rsl_sign_recognition.runtime.pose_words import LivePoseWordsRuntimeService
from rsl_sign_recognition.runtime.readiness import GateStatus


@dataclass(frozen=True)
class LiveTransportSurface:
    """Readiness boundary for the WebSocket surface linked to live runtime."""

    ws_stream_path: str = "/ws/stream"
    bound_pose_words_runtime: LivePoseWordsRuntimeService | None = None

    def evaluate(
        self,
        *,
        expected_pose_words_runtime: LivePoseWordsRuntimeService,
    ) -> GateStatus:
        if self.bound_pose_words_runtime is not expected_pose_words_runtime:
            return GateStatus(
                passed=False,
                reason_codes=(
                    "transport_surface_not_linked_to_live_runtime_pipeline",
                ),
            )
        return GateStatus(passed=True)
