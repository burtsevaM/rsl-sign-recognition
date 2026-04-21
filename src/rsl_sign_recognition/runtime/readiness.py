"""Shared readiness primitives for the clean runtime shell."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class GateStatus:
    passed: bool
    reason_codes: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ReadinessSnapshot:
    runtime_mode: str
    gates: dict[str, bool]
    reason_codes: tuple[str, ...] = field(default_factory=tuple)
    ready_for: str = "live_runtime_path"

    @property
    def is_ready(self) -> bool:
        return all(self.gates.values())

    @property
    def http_status_code(self) -> int:
        return 200 if self.is_ready else 503

    def as_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "status": "ready" if self.is_ready else "not_ready",
            "probe": "readiness",
            "runtime_mode": self.runtime_mode,
            "ready_for": self.ready_for,
            "gates": self.gates,
        }
        if self.reason_codes:
            payload["reason_codes"] = list(self.reason_codes)
        return payload
