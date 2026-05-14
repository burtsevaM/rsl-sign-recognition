"""Service-level live pose_words runtime orchestration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from rsl_sign_recognition.pipelines.pose_words.runtime import (
    PoseWordsRuntimePipeline,
    build_pose_words_runtime_pipeline,
)
from rsl_sign_recognition.runtime.artifacts import (
    ActiveArtifactLoadError,
    ActiveArtifactLoader,
    ResolvedActiveArtifacts,
)
from rsl_sign_recognition.runtime.config import RuntimeMode, RuntimeShellSettings


class LivePoseWordsRuntimeStatus(str, Enum):
    READY = "ready"
    UNAVAILABLE = "unavailable"
    INVALID = "invalid"


PipelineFactory = Callable[[ResolvedActiveArtifacts], PoseWordsRuntimePipeline]


@dataclass(frozen=True, slots=True)
class LivePoseWordsRuntimeState:
    """Controlled service-level state for the live pose_words path."""

    status: LivePoseWordsRuntimeStatus
    reason_codes: tuple[str, ...] = field(default_factory=tuple)
    manifest_path: Path | None = None
    profile_id: str | None = None
    components: tuple[str, ...] = field(default_factory=tuple)
    pipeline: PoseWordsRuntimePipeline | None = None

    @property
    def available(self) -> bool:
        return self.status is LivePoseWordsRuntimeStatus.READY

    def as_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "status": self.status.value,
            "runtime_path": "pose_words",
            "available": self.available,
            "components": list(self.components),
        }
        if self.reason_codes:
            payload["reason_codes"] = list(self.reason_codes)
        if self.manifest_path is not None:
            payload["manifest_path"] = str(self.manifest_path)
        if self.profile_id is not None:
            payload["profile_id"] = self.profile_id
        return payload


class LivePoseWordsRuntimeService:
    """Initialize the live pose_words path without WebSocket transport wiring."""

    def __init__(
        self,
        *,
        settings: RuntimeShellSettings,
        artifact_loader: ActiveArtifactLoader | None = None,
        pipeline_factory: PipelineFactory | None = None,
    ) -> None:
        self.settings = settings
        self.artifact_loader = artifact_loader or ActiveArtifactLoader(
            settings.active_manifest_path
        )
        self.pipeline_factory = pipeline_factory or build_pose_words_runtime_pipeline

    @classmethod
    def from_settings(
        cls,
        settings: RuntimeShellSettings,
        *,
        pipeline_factory: PipelineFactory | None = None,
    ) -> "LivePoseWordsRuntimeService":
        return cls(settings=settings, pipeline_factory=pipeline_factory)

    def initialize(self) -> LivePoseWordsRuntimeState:
        if self.settings.runtime_mode is not RuntimeMode.LIVE:
            return LivePoseWordsRuntimeState(
                status=LivePoseWordsRuntimeStatus.UNAVAILABLE,
                reason_codes=("runtime_mode_not_live",),
                manifest_path=self.settings.active_manifest_path,
            )

        try:
            artifacts = self.artifact_loader.load()
        except ActiveArtifactLoadError as exc:
            return LivePoseWordsRuntimeState(
                status=_status_for_artifact_error(exc),
                reason_codes=exc.reason_codes,
                manifest_path=self.settings.active_manifest_path,
            )

        try:
            pipeline = self.pipeline_factory(artifacts)
        except ImportError as exc:
            return self._component_failure_state(
                artifacts,
                "pose_words_runtime_dependency_unavailable",
                exc,
                status=LivePoseWordsRuntimeStatus.UNAVAILABLE,
            )
        except FileNotFoundError as exc:
            return self._component_failure_state(
                artifacts,
                "pose_words_runtime_component_missing",
                exc,
                status=LivePoseWordsRuntimeStatus.UNAVAILABLE,
            )
        except (OSError, ValueError, TypeError) as exc:
            return self._component_failure_state(
                artifacts,
                "pose_words_runtime_misconfigured",
                exc,
                status=LivePoseWordsRuntimeStatus.INVALID,
            )

        return LivePoseWordsRuntimeState(
            status=LivePoseWordsRuntimeStatus.READY,
            manifest_path=artifacts.manifest_path,
            profile_id=artifacts.profile_id,
            components=(
                "active_artifact_loader",
                "pose_feature_service",
                "bio_segmentation",
                "pose_words_classifier",
            ),
            pipeline=pipeline,
        )

    def _component_failure_state(
        self,
        artifacts: ResolvedActiveArtifacts,
        reason_code: str,
        exc: BaseException,
        *,
        status: LivePoseWordsRuntimeStatus,
    ) -> LivePoseWordsRuntimeState:
        metadata: dict[str, Any] = {"exception": type(exc).__name__}
        if str(exc):
            metadata["message"] = str(exc)
        reason_codes = (reason_code, *_metadata_reason_codes(metadata))
        return LivePoseWordsRuntimeState(
            status=status,
            reason_codes=reason_codes,
            manifest_path=artifacts.manifest_path,
            profile_id=artifacts.profile_id,
        )


def _status_for_artifact_error(
    exc: ActiveArtifactLoadError,
) -> LivePoseWordsRuntimeStatus:
    unavailable = {
        "active_manifest_missing",
        "active_required_artifacts_missing",
        "active_manifest_read_failed",
    }
    if exc.reason_code in unavailable:
        return LivePoseWordsRuntimeStatus.UNAVAILABLE
    return LivePoseWordsRuntimeStatus.INVALID


def _metadata_reason_codes(metadata: dict[str, Any]) -> tuple[str, ...]:
    exception_name = metadata.get("exception")
    if not isinstance(exception_name, str) or not exception_name:
        return ()
    return (f"exception:{exception_name}",)


__all__ = [
    "LivePoseWordsRuntimeService",
    "LivePoseWordsRuntimeState",
    "LivePoseWordsRuntimeStatus",
    "PipelineFactory",
]
