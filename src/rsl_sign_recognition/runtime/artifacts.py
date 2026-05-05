"""Active runtime artifact loading for the clean runtime shell."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from rsl_sign_recognition.runtime.readiness import GateStatus


ACTIVE_MANIFEST_SCHEMA_VERSION = 1
ACTIVE_CONTOUR = "pose_words"
ACTIVE_PROFILE_ROLE = "active"
ACTIVE_READINESS_CLASS = "live_candidate"
ACTIVE_SOURCE_PIPELINE = "pose_words"

REQUIRED_LIVE_ARTIFACTS: Mapping[str, str] = {
    "classifier_model": "classifier/model.onnx",
    "classifier_labels": "classifier/labels.txt",
    "segmentation_model": "segmentation/model.onnx",
    "segmentation_thresholds": "segmentation/thresholds.json",
}

OPTIONAL_COMPANION_ARTIFACTS: Mapping[str, str] = {
    "classifier_config": "classifier/runtime_config.json",
    "segmentation_config": "segmentation/runtime_config.json",
}


class ActiveArtifactLoadError(RuntimeError):
    """Runtime-friendly active artifact failure with a stable reason code."""

    def __init__(
        self,
        reason_code: str,
        message: str,
        *,
        missing_artifacts: tuple[str, ...] = (),
    ) -> None:
        super().__init__(message)
        self.reason_code = reason_code
        self.reason_codes = (reason_code,)
        self.missing_artifacts = missing_artifacts


@dataclass(frozen=True, slots=True)
class ArtifactFileDescriptor:
    """One file descriptor from an active artifact manifest."""

    name: str
    relative_path: str
    resolved_path: Path
    component: str = ""
    artifact_kind: str = ""
    required: bool = False
    trained: bool | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ActiveArtifactManifest:
    """Validated active artifact manifest metadata and file descriptors."""

    manifest_path: Path
    schema_version: int
    contour: str
    profile_id: str
    profile_role: str
    profile_origin: str
    readiness_class: str
    source_pipeline: str
    files: Mapping[str, ArtifactFileDescriptor]
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ResolvedActiveArtifacts:
    """Resolved active artifact paths for the live pose_words runtime set."""

    manifest: ActiveArtifactManifest

    @property
    def manifest_path(self) -> Path:
        return self.manifest.manifest_path

    @property
    def profile_id(self) -> str:
        return self.manifest.profile_id

    @property
    def readiness_class(self) -> str:
        return self.manifest.readiness_class

    @property
    def files(self) -> Mapping[str, ArtifactFileDescriptor]:
        return self.manifest.files

    @property
    def classifier_model_path(self) -> Path:
        return self.files["classifier_model"].resolved_path

    @property
    def classifier_labels_path(self) -> Path:
        return self.files["classifier_labels"].resolved_path

    @property
    def segmentation_model_path(self) -> Path:
        return self.files["segmentation_model"].resolved_path

    @property
    def segmentation_thresholds_path(self) -> Path:
        return self.files["segmentation_thresholds"].resolved_path

    @property
    def classifier_config_path(self) -> Path | None:
        return _existing_optional_path(self.files.get("classifier_config"))

    @property
    def segmentation_config_path(self) -> Path | None:
        return _existing_optional_path(self.files.get("segmentation_config"))


@dataclass(frozen=True, slots=True)
class ActiveArtifactLoader:
    """Read, validate and resolve the active pose_words artifact manifest."""

    manifest_path: Path

    def load(self) -> ResolvedActiveArtifacts:
        manifest_path = Path(self.manifest_path)
        if not manifest_path.is_file():
            raise ActiveArtifactLoadError(
                "active_manifest_missing",
                f"active artifact manifest is missing: {manifest_path}",
            )

        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ActiveArtifactLoadError(
                "active_manifest_invalid_json",
                f"active artifact manifest must be valid JSON: {manifest_path}",
            ) from exc
        except OSError as exc:
            raise ActiveArtifactLoadError(
                "active_manifest_read_failed",
                f"active artifact manifest could not be read: {manifest_path}",
            ) from exc

        if not isinstance(payload, dict):
            raise ActiveArtifactLoadError(
                "active_manifest_invalid_shape",
                f"active artifact manifest must be a JSON object: {manifest_path}",
            )

        schema_version = _require_int(payload, "schema_version")
        if schema_version != ACTIVE_MANIFEST_SCHEMA_VERSION:
            raise ActiveArtifactLoadError(
                "active_manifest_schema_version_unsupported",
                "active artifact manifest schema_version must be 1",
            )

        contour = _require_non_empty_str(payload, "contour")
        if contour != ACTIVE_CONTOUR:
            raise ActiveArtifactLoadError(
                "active_manifest_contour_invalid",
                "active artifact manifest contour must be pose_words",
            )

        profile_role = _require_non_empty_str(payload, "profile_role")
        if profile_role != ACTIVE_PROFILE_ROLE:
            raise ActiveArtifactLoadError(
                "active_profile_role_invalid",
                "active artifact manifest profile_role must be active",
            )

        readiness_class = _require_non_empty_str(payload, "readiness_class")
        if readiness_class != ACTIVE_READINESS_CLASS:
            raise ActiveArtifactLoadError(
                "active_profile_not_live_candidate",
                "active artifact manifest readiness_class must be live_candidate",
            )

        source_pipeline = _require_non_empty_str(payload, "source_pipeline")
        if source_pipeline != ACTIVE_SOURCE_PIPELINE:
            raise ActiveArtifactLoadError(
                "active_manifest_source_pipeline_invalid",
                "active artifact manifest source_pipeline must be pose_words",
            )

        profile_id = _require_non_empty_str(payload, "profile_id")
        profile_origin = _require_non_empty_str(payload, "profile_origin")

        files_payload = payload.get("files")
        if not isinstance(files_payload, dict) or not files_payload:
            raise ActiveArtifactLoadError(
                "active_manifest_files_missing",
                "active artifact manifest files must be a non-empty JSON object",
            )

        files = _parse_files(
            files_payload,
            manifest_dir=manifest_path.parent.resolve(strict=False),
        )

        missing_required = [
            name for name in REQUIRED_LIVE_ARTIFACTS if name not in files
        ]
        for name, descriptor in files.items():
            if not _is_effectively_required(name, descriptor):
                continue
            if not descriptor.resolved_path.is_file():
                missing_required.append(name)

        if missing_required:
            unique_missing = tuple(dict.fromkeys(missing_required))
            raise ActiveArtifactLoadError(
                "active_required_artifacts_missing",
                "required active pose_words artifacts are missing: "
                + ", ".join(unique_missing),
                missing_artifacts=unique_missing,
            )

        manifest = ActiveArtifactManifest(
            manifest_path=manifest_path,
            schema_version=schema_version,
            contour=contour,
            profile_id=profile_id,
            profile_role=profile_role,
            profile_origin=profile_origin,
            readiness_class=readiness_class,
            source_pipeline=source_pipeline,
            files=files,
            metadata={
                key: value
                for key, value in payload.items()
                if key
                not in {
                    "schema_version",
                    "contour",
                    "profile_id",
                    "profile_role",
                    "profile_origin",
                    "readiness_class",
                    "source_pipeline",
                    "files",
                }
            },
        )
        return ResolvedActiveArtifacts(manifest=manifest)


@dataclass(frozen=True, slots=True)
class ActiveArtifactGate:
    """Readiness gate backed by the active artifact manifest loader."""

    manifest_path: Path

    def evaluate(self) -> GateStatus:
        try:
            ActiveArtifactLoader(self.manifest_path).load()
        except ActiveArtifactLoadError as exc:
            return GateStatus(passed=False, reason_codes=exc.reason_codes)
        return GateStatus(passed=True)


def _existing_optional_path(descriptor: ArtifactFileDescriptor | None) -> Path | None:
    if descriptor is None:
        return None
    return descriptor.resolved_path if descriptor.resolved_path.is_file() else None


def _is_effectively_required(name: str, descriptor: ArtifactFileDescriptor) -> bool:
    return name in REQUIRED_LIVE_ARTIFACTS or descriptor.required


def _parse_files(
    files_payload: Mapping[str, object],
    *,
    manifest_dir: Path,
) -> dict[str, ArtifactFileDescriptor]:
    files: dict[str, ArtifactFileDescriptor] = {}
    for name, raw_descriptor in files_payload.items():
        if not isinstance(raw_descriptor, dict):
            raise ActiveArtifactLoadError(
                "active_manifest_descriptor_invalid",
                f"active artifact descriptor must be a JSON object: {name}",
            )

        relative_path = raw_descriptor.get("relative_path")
        if not isinstance(relative_path, str) or not relative_path.strip():
            raise ActiveArtifactLoadError(
                "active_manifest_relative_path_invalid",
                f"active artifact descriptor relative_path is invalid: {name}",
            )
        relative_path = relative_path.strip()
        resolved_path = _resolve_manifest_relative_path(
            manifest_dir,
            relative_path,
            descriptor_name=name,
        )

        required_raw = raw_descriptor.get("required", False)
        if not isinstance(required_raw, bool):
            raise ActiveArtifactLoadError(
                "active_manifest_descriptor_invalid",
                f"active artifact descriptor required must be boolean: {name}",
            )

        trained_raw = raw_descriptor.get("trained")
        trained = trained_raw if isinstance(trained_raw, bool) else None
        files[name] = ArtifactFileDescriptor(
            name=name,
            relative_path=relative_path,
            resolved_path=resolved_path,
            component=_optional_str(raw_descriptor.get("component")),
            artifact_kind=_optional_str(raw_descriptor.get("artifact_kind")),
            required=required_raw,
            trained=trained,
            metadata={
                key: value
                for key, value in raw_descriptor.items()
                if key
                not in {
                    "relative_path",
                    "component",
                    "artifact_kind",
                    "required",
                    "trained",
                }
            },
        )
    return files


def _resolve_manifest_relative_path(
    manifest_dir: Path,
    relative_path: str,
    *,
    descriptor_name: str,
) -> Path:
    candidate = Path(relative_path)
    if candidate.is_absolute():
        raise ActiveArtifactLoadError(
            "active_manifest_absolute_path_rejected",
            f"active artifact path must be relative: {descriptor_name}",
        )
    if any(part == ".." for part in candidate.parts):
        raise ActiveArtifactLoadError(
            "active_manifest_path_traversal_rejected",
            f"active artifact path must not contain '..': {descriptor_name}",
        )

    resolved = (manifest_dir / candidate).resolve(strict=False)
    if not resolved.is_relative_to(manifest_dir):
        raise ActiveArtifactLoadError(
            "active_manifest_path_traversal_rejected",
            f"active artifact path escapes manifest directory: {descriptor_name}",
        )
    return resolved


def _require_int(payload: Mapping[str, object], key: str) -> int:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ActiveArtifactLoadError(
            "active_manifest_metadata_invalid",
            f"active artifact manifest {key} must be an integer",
        )
    return value


def _require_non_empty_str(payload: Mapping[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ActiveArtifactLoadError(
            "active_manifest_metadata_invalid",
            f"active artifact manifest {key} must be a non-empty string",
        )
    return value.strip()


def _optional_str(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""
