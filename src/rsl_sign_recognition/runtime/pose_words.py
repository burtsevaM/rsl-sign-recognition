"""Service-level live pose_words runtime orchestration."""

from __future__ import annotations

from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any
from uuid import uuid4

import numpy as np

from rsl_sign_recognition.pipelines.pose_words.clip import resample_to_fixed_T
from rsl_sign_recognition.pipelines.pose_words.runtime import (
    PoseWordsRuntimePipeline,
    PoseWordsRuntimeAssemblyError,
    build_pose_words_runtime_pipeline,
)
from rsl_sign_recognition.runtime.artifacts import (
    ActiveArtifactLoadError,
    ActiveArtifactLoader,
    ResolvedActiveArtifacts,
)
from rsl_sign_recognition.runtime.config import RuntimeMode, RuntimeShellSettings
from rsl_sign_recognition.runtime.readiness import GateStatus


class LivePoseWordsRuntimeStatus(str, Enum):
    READY = "ready"
    UNAVAILABLE = "unavailable"
    INVALID = "invalid"


class PoseWordsSessionStatus(str, Enum):
    INITIALIZED = "initialized"
    ACTIVE = "active"
    CLOSED = "closed"


class PoseWordsRuntimeEventStatus(str, Enum):
    RESULT = "result"
    NO_RESULT = "no_result"
    ERROR = "error"


PipelineFactory = Callable[[ResolvedActiveArtifacts], PoseWordsRuntimePipeline]


@dataclass(frozen=True, slots=True)
class PoseWordsFeatureEntry:
    index: int
    feature_vector: np.ndarray


@dataclass(frozen=True, slots=True)
class PoseWordsBufferSnapshot:
    length: int
    max_size: int
    next_index: int
    start_index: int | None = None
    end_index: int | None = None

    @property
    def empty(self) -> bool:
        return self.length == 0

    def as_payload(self) -> dict[str, object]:
        return {
            "length": int(self.length),
            "max_size": int(self.max_size),
            "next_index": int(self.next_index),
            "start_index": self.start_index,
            "end_index": self.end_index,
            "empty": self.empty,
        }


class PoseWordsFeatureBuffer:
    """Bounded runtime-facing feature buffer for one live session."""

    def __init__(self, *, feature_dim: int, max_size: int) -> None:
        parsed_feature_dim = int(feature_dim)
        parsed_max_size = int(max_size)
        if parsed_feature_dim < 1:
            raise ValueError("feature_dim must be a positive integer")
        if parsed_max_size < 1:
            raise ValueError("max_size must be a positive integer")
        self.feature_dim = parsed_feature_dim
        self.max_size = parsed_max_size
        self._entries: deque[PoseWordsFeatureEntry] = deque(maxlen=parsed_max_size)
        self._next_index = 0

    def push(self, feature_vector: np.ndarray) -> PoseWordsFeatureEntry:
        feature = self._coerce_feature(feature_vector)
        entry = PoseWordsFeatureEntry(
            index=int(self._next_index),
            feature_vector=feature,
        )
        self._next_index += 1
        self._entries.append(entry)
        return entry

    def clear(self) -> None:
        self._entries.clear()
        self._next_index = 0

    def snapshot(self) -> PoseWordsBufferSnapshot:
        if not self._entries:
            return PoseWordsBufferSnapshot(
                length=0,
                max_size=self.max_size,
                next_index=self._next_index,
            )
        return PoseWordsBufferSnapshot(
            length=len(self._entries),
            max_size=self.max_size,
            next_index=self._next_index,
            start_index=int(self._entries[0].index),
            end_index=int(self._entries[-1].index),
        )

    def _coerce_feature(self, feature_vector: np.ndarray) -> np.ndarray:
        arr = np.asarray(feature_vector, dtype=np.float32)
        if arr.size == 0:
            raise ValueError("feature vector must contain at least one value")
        feature = arr.reshape(-1).astype(np.float32, copy=False)
        if int(feature.shape[0]) != self.feature_dim:
            raise ValueError(
                f"feature vector dim mismatch: expected {self.feature_dim}, "
                f"got {feature.shape[0]}"
            )
        if not np.all(np.isfinite(feature)):
            raise ValueError("feature vector must contain only finite values")
        return np.ascontiguousarray(feature, dtype=np.float32)


@dataclass(frozen=True, slots=True)
class PoseWordsRecognition:
    label: str
    confidence: float
    class_index: int
    segment_start: int
    segment_end: int
    segment_score: float
    classifier_latency_ms: float

    def as_payload(self) -> dict[str, object]:
        return {
            "label": self.label,
            "confidence": float(self.confidence),
            "class_index": int(self.class_index),
            "segment": {
                "start": int(self.segment_start),
                "end": int(self.segment_end),
                "score": float(self.segment_score),
            },
            "classifier_latency_ms": float(self.classifier_latency_ms),
        }


@dataclass(frozen=True, slots=True)
class PoseWordsRuntimeEvent:
    status: PoseWordsRuntimeEventStatus
    session_id: str
    session_status: PoseWordsSessionStatus
    reason_code: str | None
    buffer: PoseWordsBufferSnapshot
    feature_index: int | None = None
    hand_present: bool | None = None
    recognition: PoseWordsRecognition | None = None
    details: dict[str, object] = field(default_factory=dict)

    @property
    def has_result(self) -> bool:
        return self.status is PoseWordsRuntimeEventStatus.RESULT

    def as_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "status": self.status.value,
            "session_id": self.session_id,
            "session_status": self.session_status.value,
            "has_result": self.has_result,
            "buffer": self.buffer.as_payload(),
        }
        if self.reason_code is not None:
            payload["reason_code"] = self.reason_code
        if self.feature_index is not None:
            payload["feature_index"] = int(self.feature_index)
        if self.hand_present is not None:
            payload["hand_present"] = bool(self.hand_present)
        if self.recognition is not None:
            payload["recognition"] = self.recognition.as_payload()
        if self.details:
            payload["details"] = dict(self.details)
        return payload


@dataclass(frozen=True, slots=True)
class PoseWordsSessionSnapshot:
    session_id: str
    status: PoseWordsSessionStatus
    buffer: PoseWordsBufferSnapshot

    def as_payload(self) -> dict[str, object]:
        return {
            "session_id": self.session_id,
            "status": self.status.value,
            "buffer": self.buffer.as_payload(),
        }


@dataclass(frozen=True, slots=True)
class PoseWordsSessionCreateResult:
    status: LivePoseWordsRuntimeStatus
    reason_codes: tuple[str, ...] = field(default_factory=tuple)
    session: "PoseWordsLiveSession | None" = None
    runtime_state: "LivePoseWordsRuntimeState | None" = None

    @property
    def created(self) -> bool:
        return self.session is not None

    def as_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "status": self.status.value,
            "created": self.created,
            "runtime_path": "pose_words",
        }
        if self.reason_codes:
            payload["reason_codes"] = list(self.reason_codes)
        if self.session is not None:
            payload["session"] = self.session.snapshot().as_payload()
        if self.runtime_state is not None:
            payload["runtime_state"] = self.runtime_state.as_payload()
        return payload


@dataclass(frozen=True, slots=True)
class LivePoseWordsRuntimeState:
    """Controlled service-level state for the live pose_words path."""

    status: LivePoseWordsRuntimeStatus
    reason_codes: tuple[str, ...] = field(default_factory=tuple)
    manifest_path: Path | None = None
    profile_id: str | None = None
    missing_artifacts: tuple[str, ...] = field(default_factory=tuple)
    components: tuple[str, ...] = field(default_factory=tuple)
    pipeline: PoseWordsRuntimePipeline | None = None
    artifacts: ResolvedActiveArtifacts | None = None

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
        if self.missing_artifacts:
            payload["missing_artifacts"] = list(self.missing_artifacts)
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
                missing_artifacts=exc.missing_artifacts,
            )

        try:
            pipeline = self.pipeline_factory(artifacts)
        except PoseWordsRuntimeAssemblyError as exc:
            return self._component_failure_state(
                artifacts,
                exc.reason_code,
                exc,
                status=_status_for_pipeline_failure(exc.reason_code),
            )
        except ImportError as exc:
            return self._component_failure_state(
                artifacts,
                "inference_backend_unavailable",
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
        except (OSError, RuntimeError) as exc:
            return self._component_failure_state(
                artifacts,
                "pose_words_model_loading_failed",
                exc,
                status=LivePoseWordsRuntimeStatus.INVALID,
            )
        except (ValueError, TypeError) as exc:
            return self._component_failure_state(
                artifacts,
                "pose_words_runtime_config_invalid",
                exc,
                status=LivePoseWordsRuntimeStatus.INVALID,
            )

        return self._ready_state(artifacts, pipeline)

    def evaluate_readiness(self) -> GateStatus:
        """Return the public readiness view of the live pose_words orchestrator."""

        state = self.initialize()
        if state.available:
            return GateStatus(passed=True)
        return GateStatus(
            passed=False,
            reason_codes=_readiness_reason_codes_for_state(state),
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
        if isinstance(exc, PoseWordsRuntimeAssemblyError):
            metadata["phase"] = exc.phase
            if exc.__cause__ is not None:
                metadata["cause_exception"] = type(exc.__cause__).__name__
        if str(exc):
            metadata["message"] = str(exc)
        reason_codes = (reason_code, *_metadata_reason_codes(metadata))
        return LivePoseWordsRuntimeState(
            status=status,
            reason_codes=reason_codes,
            manifest_path=artifacts.manifest_path,
            profile_id=artifacts.profile_id,
        )

    def _ready_state(
        self,
        artifacts: ResolvedActiveArtifacts,
        pipeline: PoseWordsRuntimePipeline,
    ) -> LivePoseWordsRuntimeState:
        return LivePoseWordsRuntimeState(
            status=LivePoseWordsRuntimeStatus.READY,
            manifest_path=artifacts.manifest_path,
            profile_id=artifacts.profile_id,
            components=(
                "active_artifact_loader",
                "pose_feature_service",
                "bio_segmentation",
                "pose_words_classifier",
                "pose_words_session_state",
            ),
            pipeline=pipeline,
            artifacts=artifacts,
        )

    def create_session(
        self,
        *,
        session_id: str | None = None,
        max_buffer: int | None = None,
    ) -> PoseWordsSessionCreateResult:
        if self.settings.runtime_mode is not RuntimeMode.LIVE:
            state = LivePoseWordsRuntimeState(
                status=LivePoseWordsRuntimeStatus.UNAVAILABLE,
                reason_codes=("runtime_mode_not_live",),
                manifest_path=self.settings.active_manifest_path,
            )
            return PoseWordsSessionCreateResult(
                status=state.status,
                reason_codes=state.reason_codes,
                runtime_state=state,
            )

        try:
            artifacts = self.artifact_loader.load()
        except ActiveArtifactLoadError as exc:
            state = LivePoseWordsRuntimeState(
                status=_status_for_artifact_error(exc),
                reason_codes=exc.reason_codes,
                manifest_path=self.settings.active_manifest_path,
                missing_artifacts=exc.missing_artifacts,
            )
            return PoseWordsSessionCreateResult(
                status=state.status,
                reason_codes=state.reason_codes,
                runtime_state=state,
            )

        try:
            pipeline = self.pipeline_factory(artifacts)
        except PoseWordsRuntimeAssemblyError as exc:
            failure = self._component_failure_state(
                artifacts,
                exc.reason_code,
                exc,
                status=_status_for_pipeline_failure(exc.reason_code),
            )
            return PoseWordsSessionCreateResult(
                status=failure.status,
                reason_codes=failure.reason_codes,
                runtime_state=failure,
            )
        except ImportError as exc:
            failure = self._component_failure_state(
                artifacts,
                "inference_backend_unavailable",
                exc,
                status=LivePoseWordsRuntimeStatus.UNAVAILABLE,
            )
            return PoseWordsSessionCreateResult(
                status=failure.status,
                reason_codes=failure.reason_codes,
                runtime_state=failure,
            )
        except FileNotFoundError as exc:
            failure = self._component_failure_state(
                artifacts,
                "pose_words_runtime_component_missing",
                exc,
                status=LivePoseWordsRuntimeStatus.UNAVAILABLE,
            )
            return PoseWordsSessionCreateResult(
                status=failure.status,
                reason_codes=failure.reason_codes,
                runtime_state=failure,
            )
        except (OSError, RuntimeError) as exc:
            failure = self._component_failure_state(
                artifacts,
                "pose_words_model_loading_failed",
                exc,
                status=LivePoseWordsRuntimeStatus.INVALID,
            )
            return PoseWordsSessionCreateResult(
                status=failure.status,
                reason_codes=failure.reason_codes,
                runtime_state=failure,
            )
        except (ValueError, TypeError) as exc:
            failure = self._component_failure_state(
                artifacts,
                "pose_words_runtime_config_invalid",
                exc,
                status=LivePoseWordsRuntimeStatus.INVALID,
            )
            return PoseWordsSessionCreateResult(
                status=failure.status,
                reason_codes=failure.reason_codes,
                runtime_state=failure,
            )

        state = self._ready_state(artifacts, pipeline)
        session = PoseWordsLiveSession(
            pipeline=pipeline,
            session_id=session_id,
            max_buffer=max_buffer,
        )
        return PoseWordsSessionCreateResult(
            status=LivePoseWordsRuntimeStatus.READY,
            session=session,
            runtime_state=state,
        )

    def close_session(self, session: "PoseWordsLiveSession") -> PoseWordsRuntimeEvent:
        return session.close()


class PoseWordsLiveSession:
    """Stateful runtime session for live pose_words decoding without transport."""

    def __init__(
        self,
        *,
        pipeline: PoseWordsRuntimePipeline,
        session_id: str | None = None,
        max_buffer: int | None = None,
    ) -> None:
        self.pipeline = pipeline
        self.session_id = session_id or str(uuid4())
        self.status = PoseWordsSessionStatus.INITIALIZED
        resolved_max_buffer = (
            int(max_buffer)
            if max_buffer is not None
            else int(getattr(pipeline.segmenter, "max_buffer", 0) or pipeline.clip_frames * 2)
        )
        self.buffer = PoseWordsFeatureBuffer(
            feature_dim=pipeline.feature_dim,
            max_size=max(1, resolved_max_buffer),
        )

    def snapshot(self) -> PoseWordsSessionSnapshot:
        return PoseWordsSessionSnapshot(
            session_id=self.session_id,
            status=self.status,
            buffer=self.buffer.snapshot(),
        )

    def reset(self) -> PoseWordsRuntimeEvent:
        if self.status is PoseWordsSessionStatus.CLOSED:
            return self._error("session_closed")
        self.buffer.clear()
        reset = getattr(self.pipeline.segmenter, "reset", None)
        if callable(reset):
            reset()
        self.status = PoseWordsSessionStatus.INITIALIZED
        return self._no_result("session_reset")

    def close(self) -> PoseWordsRuntimeEvent:
        self.buffer.clear()
        reset = getattr(self.pipeline.segmenter, "reset", None)
        if callable(reset):
            reset()
        self.status = PoseWordsSessionStatus.CLOSED
        return self._no_result("session_closed")

    def decode_next(self) -> PoseWordsRuntimeEvent:
        closed = self._closed_event()
        if closed is not None:
            return closed
        if self.buffer.snapshot().empty:
            return self._no_result("empty_buffer")
        if not self.pipeline.segmenter.has_enough_frames:
            return self._no_result("insufficient_buffer")
        return self._no_result("no_completed_segment")

    def push_frame(self, rgb_frame: np.ndarray) -> PoseWordsRuntimeEvent:
        closed = self._closed_event()
        if closed is not None:
            return closed

        try:
            pose_result = self.pipeline.pose_features.process_rgb_frame(rgb_frame)
        except (TypeError, ValueError) as exc:
            return self._error("invalid_rgb_frame", exception=exc)
        except (RuntimeError, OSError) as exc:
            return self._error("pose_feature_runtime_failed", exception=exc)

        if pose_result.feature_vector is None:
            reason = pose_result.aux.get("reason")
            flushed = self._flush_pending_segment(hand_present=False)
            if flushed is not None:
                return flushed
            return self._no_result(
                str(reason) if isinstance(reason, str) and reason else "pose_not_detected",
                hand_present=False,
            )
        if not pose_result.hand_present:
            flushed = self._flush_pending_segment(hand_present=False)
            if flushed is not None:
                return flushed
            return self._no_result("no_hand_detected", hand_present=False)
        return self.push_feature(pose_result.feature_vector, hand_present=True)

    def _flush_pending_segment(
        self,
        *,
        hand_present: bool | None,
    ) -> PoseWordsRuntimeEvent | None:
        flush = getattr(self.pipeline.segmenter, "flush_active_segments", None)
        if not callable(flush):
            return None
        try:
            segmentation = flush()
        except (ImportError, OSError, RuntimeError, TypeError, ValueError) as exc:
            return self._error(
                "decoder_runtime_failed",
                exception=exc,
                hand_present=hand_present,
            )
        if not bool(segmentation.ran_inference):
            return None
        if not (segmentation.sign_segments or segmentation.phrase_segments):
            return None
        return self._decode_segmentation_result(
            segmentation,
            feature_index=self.buffer.snapshot().end_index or 0,
            hand_present=hand_present,
        )

    def push_feature(
        self,
        feature_vector: np.ndarray,
        *,
        hand_present: bool | None = None,
    ) -> PoseWordsRuntimeEvent:
        closed = self._closed_event()
        if closed is not None:
            return closed

        try:
            entry = self.buffer.push(feature_vector)
        except ValueError as exc:
            reason = (
                "feature_dimension_mismatch"
                if "dim mismatch" in str(exc)
                else "invalid_feature_vector"
            )
            return self._error(reason, exception=exc, hand_present=hand_present)

        self.status = PoseWordsSessionStatus.ACTIVE
        try:
            segmentation = self.pipeline.segmenter.update(entry.feature_vector)
        except (ImportError, OSError, RuntimeError, TypeError, ValueError) as exc:
            return self._error(
                "decoder_runtime_failed",
                exception=exc,
                feature_index=entry.index,
                hand_present=hand_present,
            )

        return self._decode_segmentation_result(
            segmentation,
            feature_index=entry.index,
            hand_present=hand_present,
        )

    def _decode_segmentation_result(
        self,
        segmentation: Any,
        *,
        feature_index: int,
        hand_present: bool | None,
    ) -> PoseWordsRuntimeEvent:
        if not self.pipeline.segmenter.has_enough_frames:
            return self._no_result(
                "insufficient_buffer",
                feature_index=feature_index,
                hand_present=hand_present,
            )
        if not bool(segmentation.ran_inference):
            return self._no_result(
                "segmentation_pending",
                feature_index=feature_index,
                hand_present=hand_present,
            )

        segments = list(segmentation.sign_segments or segmentation.phrase_segments)
        if not segments:
            reason = (
                "no_completed_segment"
                if bool(segmentation.active_sign or segmentation.active_phrase)
                else "no_active_segment"
            )
            return self._no_result(
                reason,
                feature_index=feature_index,
                hand_present=hand_present,
            )

        segment = sorted(segments, key=lambda item: (item.end, item.start))[0]
        span = self.pipeline.segmenter.get_feature_span(segment.start, segment.end)
        if span is None:
            return self._no_result(
                "segment_feature_span_unavailable",
                feature_index=feature_index,
                hand_present=hand_present,
            )

        try:
            clip = resample_to_fixed_T(span, T=self.pipeline.clip_frames)
            probs, latency_ms = self.pipeline.classifier.infer_probs(clip)
            probabilities = np.asarray(probs, dtype=np.float32).reshape(-1)
            if probabilities.size == 0:
                raise ValueError("classifier returned empty probability vector")
            class_index = int(np.argmax(probabilities))
            labels = list(getattr(self.pipeline.classifier, "labels", ()))
            if class_index >= len(labels):
                raise ValueError(
                    "classifier probability vector is longer than labels list"
                )
        except (RuntimeError, TypeError, ValueError) as exc:
            return self._error(
                "classifier_runtime_failed",
                exception=exc,
                feature_index=feature_index,
                hand_present=hand_present,
            )

        label = str(labels[class_index])
        confidence = float(probabilities[class_index])
        if self.pipeline.no_event_index is not None and class_index == int(
            self.pipeline.no_event_index
        ):
            return self._no_result(
                "no_event",
                feature_index=feature_index,
                hand_present=hand_present,
                details={"label": label, "confidence": confidence},
            )

        recognition = PoseWordsRecognition(
            label=label,
            confidence=confidence,
            class_index=class_index,
            segment_start=int(segment.start),
            segment_end=int(segment.end),
            segment_score=float(segment.score),
            classifier_latency_ms=float(latency_ms),
        )
        return PoseWordsRuntimeEvent(
            status=PoseWordsRuntimeEventStatus.RESULT,
            session_id=self.session_id,
            session_status=self.status,
            reason_code=None,
            buffer=self.buffer.snapshot(),
            feature_index=feature_index,
            hand_present=hand_present,
            recognition=recognition,
        )

    def _closed_event(self) -> PoseWordsRuntimeEvent | None:
        if self.status is PoseWordsSessionStatus.CLOSED:
            return self._error("session_closed")
        return None

    def _no_result(
        self,
        reason_code: str,
        *,
        feature_index: int | None = None,
        hand_present: bool | None = None,
        details: dict[str, object] | None = None,
    ) -> PoseWordsRuntimeEvent:
        return PoseWordsRuntimeEvent(
            status=PoseWordsRuntimeEventStatus.NO_RESULT,
            session_id=self.session_id,
            session_status=self.status,
            reason_code=reason_code,
            buffer=self.buffer.snapshot(),
            feature_index=feature_index,
            hand_present=hand_present,
            details=details or {},
        )

    def _error(
        self,
        reason_code: str,
        *,
        exception: BaseException | None = None,
        feature_index: int | None = None,
        hand_present: bool | None = None,
    ) -> PoseWordsRuntimeEvent:
        details: dict[str, object] = {}
        if exception is not None:
            details["exception"] = type(exception).__name__
            if str(exception):
                details["message"] = str(exception)
        return PoseWordsRuntimeEvent(
            status=PoseWordsRuntimeEventStatus.ERROR,
            session_id=self.session_id,
            session_status=self.status,
            reason_code=reason_code,
            buffer=self.buffer.snapshot(),
            feature_index=feature_index,
            hand_present=hand_present,
            details=details,
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


def _status_for_pipeline_failure(reason_code: str) -> LivePoseWordsRuntimeStatus:
    unavailable = {
        "inference_backend_unavailable",
        "pose_extraction_backend_unavailable",
        "pose_words_runtime_component_missing",
    }
    if reason_code in unavailable:
        return LivePoseWordsRuntimeStatus.UNAVAILABLE
    return LivePoseWordsRuntimeStatus.INVALID


def _metadata_reason_codes(metadata: dict[str, Any]) -> tuple[str, ...]:
    reason_codes: list[str] = []
    exception_name = metadata.get("exception")
    if isinstance(exception_name, str) and exception_name:
        reason_codes.append(f"exception:{exception_name}")
    cause_exception = metadata.get("cause_exception")
    if isinstance(cause_exception, str) and cause_exception:
        reason_codes.append(f"cause:{cause_exception}")
    phase = metadata.get("phase")
    if isinstance(phase, str) and phase:
        reason_codes.append(f"phase:{phase}")
    return tuple(reason_codes)


def _readiness_reason_codes_for_state(
    state: LivePoseWordsRuntimeState,
) -> tuple[str, ...]:
    reason_codes = set(state.reason_codes)
    if "runtime_mode_not_live" in reason_codes:
        return ("runtime_mode_not_live",)

    mapped: list[str] = []
    if {
        "inference_backend_unavailable",
        "pose_extraction_backend_unavailable",
    } & reason_codes:
        mapped.append("pose_words_runtime_dependency_unavailable")
    if "pose_words_runtime_component_missing" in reason_codes:
        mapped.append("pose_words_runtime_component_missing")
    if {
        "pose_words_runtime_config_invalid",
        "pose_words_model_loading_failed",
    } & reason_codes:
        mapped.append("pose_words_runtime_misconfigured")

    if mapped:
        return tuple(dict.fromkeys(mapped))
    return ("live_runtime_pipeline_unavailable",)


__all__ = [
    "LivePoseWordsRuntimeService",
    "LivePoseWordsRuntimeState",
    "LivePoseWordsRuntimeStatus",
    "PipelineFactory",
    "PoseWordsBufferSnapshot",
    "PoseWordsFeatureBuffer",
    "PoseWordsLiveSession",
    "PoseWordsRecognition",
    "PoseWordsRuntimeEvent",
    "PoseWordsRuntimeEventStatus",
    "PoseWordsSessionCreateResult",
    "PoseWordsSessionSnapshot",
    "PoseWordsSessionStatus",
]
