"""Runtime-shell facade exposed to the FastAPI transport layer."""

from __future__ import annotations

from dataclasses import dataclass

from rsl_sign_recognition.runtime.config import RuntimeShellSettings
from rsl_sign_recognition.runtime.readiness import ReadinessSnapshot
from rsl_sign_recognition.runtime.services import RuntimeServiceRegistry


@dataclass(frozen=True)
class RuntimeShell:
    settings: RuntimeShellSettings
    services: RuntimeServiceRegistry

    def health_payload(self) -> dict[str, str]:
        return {
            "status": "ok",
            "probe": "liveness",
            "runtime_mode": self.settings.runtime_mode.value,
        }

    def readiness_snapshot(self) -> ReadinessSnapshot:
        return self.services.evaluate_readiness()
