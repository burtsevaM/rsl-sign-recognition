"""Runtime service composition for the clean runtime shell."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, Sequence

from rsl_sign_recognition.runtime.artifacts import ActiveArtifactGate
from rsl_sign_recognition.runtime.config import RuntimeMode, RuntimeShellSettings
from rsl_sign_recognition.runtime.readiness import GateStatus, ReadinessSnapshot
from rsl_sign_recognition.runtime.transport import LiveTransportSurface


class RuntimeReadinessHook(Protocol):
    """Future runtime-level hook for startup and service readiness checks."""

    def evaluate(self) -> GateStatus:
        ...


@dataclass(frozen=True)
class RuntimeServiceRegistry:
    settings: RuntimeShellSettings
    artifact_gate: ActiveArtifactGate
    transport_surface: LiveTransportSurface
    runtime_hooks: Sequence[RuntimeReadinessHook] = field(default_factory=tuple)

    @classmethod
    def build(
        cls,
        settings: RuntimeShellSettings,
        *,
        artifact_gate: ActiveArtifactGate | None = None,
        transport_surface: LiveTransportSurface | None = None,
        runtime_hooks: Sequence[RuntimeReadinessHook] | None = None,
    ) -> "RuntimeServiceRegistry":
        return cls(
            settings=settings,
            artifact_gate=artifact_gate or ActiveArtifactGate(settings.active_manifest_path),
            transport_surface=transport_surface
            or LiveTransportSurface(ws_stream_path=settings.ws_stream_path),
            runtime_hooks=tuple(runtime_hooks or ()),
        )

    def evaluate_runtime_shell(self) -> GateStatus:
        if self.settings.runtime_mode is not RuntimeMode.LIVE:
            return GateStatus(
                passed=False,
                reason_codes=("runtime_mode_not_live",),
            )

        reason_codes: list[str] = []
        for hook in self.runtime_hooks:
            status = hook.evaluate()
            if status.passed:
                continue
            reason_codes.extend(status.reason_codes)

        if reason_codes:
            return GateStatus(
                passed=False,
                reason_codes=tuple(dict.fromkeys(reason_codes)),
            )

        return GateStatus(passed=True)

    def evaluate_readiness(self) -> ReadinessSnapshot:
        runtime_shell = self.evaluate_runtime_shell()
        active_artifacts = self.artifact_gate.evaluate()
        transport_surface = self.transport_surface.evaluate()

        reason_codes = tuple(
            dict.fromkeys(
                [
                    *runtime_shell.reason_codes,
                    *active_artifacts.reason_codes,
                    *transport_surface.reason_codes,
                ]
            )
        )

        return ReadinessSnapshot(
            runtime_mode=self.settings.runtime_mode.value,
            gates={
                "runtime_shell": runtime_shell.passed,
                "active_artifacts": active_artifacts.passed,
                "transport_surface": transport_surface.passed,
            },
            reason_codes=reason_codes,
        )
