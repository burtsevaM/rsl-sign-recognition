from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from rsl_sign_recognition.runtime.artifacts import (
    ActiveArtifactGate,
    ActiveArtifactLoadError,
    ActiveArtifactLoader,
    REQUIRED_LIVE_ARTIFACTS,
)


def manifest_path(tmp_path: Path) -> Path:
    return tmp_path / "artifacts/runtime/active/pose_words/manifest.json"


def default_files() -> dict[str, dict[str, object]]:
    return {
        "classifier_model": {
            "relative_path": "classifier/model.onnx",
            "component": "pose_words_classifier",
            "artifact_kind": "model",
            "required": True,
            "trained": True,
        },
        "classifier_labels": {
            "relative_path": "classifier/labels.txt",
            "component": "pose_words_classifier",
            "artifact_kind": "labels",
            "required": True,
            "trained": True,
        },
        "classifier_config": {
            "relative_path": "classifier/runtime_config.json",
            "component": "pose_words_classifier",
            "artifact_kind": "runtime_config",
            "required": False,
        },
        "segmentation_model": {
            "relative_path": "segmentation/model.onnx",
            "component": "bio_segmentation",
            "artifact_kind": "model",
            "required": True,
            "trained": True,
        },
        "segmentation_thresholds": {
            "relative_path": "segmentation/thresholds.json",
            "component": "bio_segmentation",
            "artifact_kind": "thresholds",
            "required": True,
        },
        "segmentation_config": {
            "relative_path": "segmentation/runtime_config.json",
            "component": "bio_segmentation",
            "artifact_kind": "runtime_config",
            "required": False,
        },
    }


def default_manifest(
    *,
    files: dict[str, Any] | None = None,
    **overrides: object,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": 1,
        "contour": "pose_words",
        "profile_id": "runtime_active",
        "profile_role": "active",
        "profile_origin": "runtime",
        "readiness_class": "live_candidate",
        "source_pipeline": "pose_words",
        "files": default_files() if files is None else files,
    }
    payload.update(overrides)
    return payload


def write_manifest(tmp_path: Path, payload: dict[str, object]) -> Path:
    path = manifest_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def write_required_files(tmp_path: Path, *, skip: str | None = None) -> None:
    root = manifest_path(tmp_path).parent
    for name, relative_path in REQUIRED_LIVE_ARTIFACTS.items():
        if name == skip:
            continue
        artifact_path = root / relative_path
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_bytes(name.encode("utf-8"))


def expect_load_error(path: Path, reason_code: str) -> ActiveArtifactLoadError:
    with pytest.raises(ActiveArtifactLoadError) as exc_info:
        ActiveArtifactLoader(path).load()
    assert exc_info.value.reason_code == reason_code
    return exc_info.value


def test_missing_manifest_gives_active_manifest_missing(tmp_path: Path) -> None:
    path = manifest_path(tmp_path)

    error = expect_load_error(path, "active_manifest_missing")

    assert "manifest" in str(error)
    assert ActiveArtifactGate(path).evaluate().reason_codes == (
        "active_manifest_missing",
    )


def test_invalid_json_gives_active_manifest_invalid_json(tmp_path: Path) -> None:
    path = manifest_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{", encoding="utf-8")

    expect_load_error(path, "active_manifest_invalid_json")


def test_manifest_must_be_json_object(tmp_path: Path) -> None:
    path = manifest_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("[]", encoding="utf-8")

    expect_load_error(path, "active_manifest_invalid_shape")


def test_schema_version_unsupported_fails_clearly(tmp_path: Path) -> None:
    write_required_files(tmp_path)
    path = write_manifest(tmp_path, default_manifest(schema_version=2))

    expect_load_error(path, "active_manifest_schema_version_unsupported")


def test_contour_must_be_pose_words(tmp_path: Path) -> None:
    write_required_files(tmp_path)
    path = write_manifest(tmp_path, default_manifest(contour="words"))

    expect_load_error(path, "active_manifest_contour_invalid")


def test_profile_role_must_be_active(tmp_path: Path) -> None:
    write_required_files(tmp_path)
    path = write_manifest(tmp_path, default_manifest(profile_role="validation"))

    expect_load_error(path, "active_profile_role_invalid")


def test_readiness_class_must_be_live_candidate(tmp_path: Path) -> None:
    write_required_files(tmp_path)
    path = write_manifest(
        tmp_path,
        default_manifest(readiness_class="validation_only"),
    )

    expect_load_error(path, "active_profile_not_live_candidate")


@pytest.mark.parametrize("files_value", [None, {}])
def test_files_missing_or_empty_fails(tmp_path: Path, files_value: object) -> None:
    write_required_files(tmp_path)
    payload = default_manifest()
    if files_value is None:
        payload.pop("files")
    else:
        payload["files"] = files_value
    path = write_manifest(tmp_path, payload)

    expect_load_error(path, "active_manifest_files_missing")


def test_descriptor_must_be_json_object(tmp_path: Path) -> None:
    write_required_files(tmp_path)
    files = default_files()
    files["classifier_model"] = "classifier/model.onnx"
    path = write_manifest(tmp_path, default_manifest(files=files))

    expect_load_error(path, "active_manifest_descriptor_invalid")


@pytest.mark.parametrize("relative_path", [None, "", "   "])
def test_relative_path_missing_or_empty_fails(
    tmp_path: Path,
    relative_path: object,
) -> None:
    write_required_files(tmp_path)
    files = default_files()
    if relative_path is None:
        files["classifier_model"].pop("relative_path")
    else:
        files["classifier_model"]["relative_path"] = relative_path
    path = write_manifest(tmp_path, default_manifest(files=files))

    expect_load_error(path, "active_manifest_relative_path_invalid")


def test_absolute_relative_path_is_rejected(tmp_path: Path) -> None:
    write_required_files(tmp_path)
    files = default_files()
    files["classifier_model"]["relative_path"] = str(
        tmp_path / "classifier/model.onnx"
    )
    path = write_manifest(tmp_path, default_manifest(files=files))

    expect_load_error(path, "active_manifest_absolute_path_rejected")


def test_path_traversal_is_rejected(tmp_path: Path) -> None:
    write_required_files(tmp_path)
    files = default_files()
    files["classifier_model"]["relative_path"] = "../model.onnx"
    path = write_manifest(tmp_path, default_manifest(files=files))

    expect_load_error(path, "active_manifest_path_traversal_rejected")


@pytest.mark.parametrize(
    "missing_name",
    [
        "classifier_model",
        "classifier_labels",
        "segmentation_model",
        "segmentation_thresholds",
    ],
)
def test_missing_required_artifact_file_fails(
    tmp_path: Path,
    missing_name: str,
) -> None:
    write_required_files(tmp_path, skip=missing_name)
    path = write_manifest(tmp_path, default_manifest())

    error = expect_load_error(path, "active_required_artifacts_missing")

    assert error.missing_artifacts == (missing_name,)


def test_optional_classifier_config_missing_does_not_fail(tmp_path: Path) -> None:
    write_required_files(tmp_path)
    path = write_manifest(tmp_path, default_manifest())

    resolved = ActiveArtifactLoader(path).load()

    assert resolved.classifier_config_path is None


def test_optional_segmentation_config_missing_does_not_fail(tmp_path: Path) -> None:
    write_required_files(tmp_path)
    path = write_manifest(tmp_path, default_manifest())

    resolved = ActiveArtifactLoader(path).load()

    assert resolved.segmentation_config_path is None


def test_valid_manifest_returns_resolved_paths(tmp_path: Path) -> None:
    write_required_files(tmp_path)
    root = manifest_path(tmp_path).parent
    classifier_config = root / "classifier/runtime_config.json"
    segmentation_config = root / "segmentation/runtime_config.json"
    classifier_config.write_text("{}", encoding="utf-8")
    segmentation_config.write_text("{}", encoding="utf-8")
    path = write_manifest(tmp_path, default_manifest())

    resolved = ActiveArtifactLoader(path).load()

    assert resolved.manifest_path == path
    assert resolved.profile_id == "runtime_active"
    assert resolved.readiness_class == "live_candidate"
    assert resolved.classifier_model_path == (root / "classifier/model.onnx").resolve()
    assert resolved.classifier_labels_path == (root / "classifier/labels.txt").resolve()
    assert resolved.segmentation_model_path == (
        root / "segmentation/model.onnx"
    ).resolve()
    assert resolved.segmentation_thresholds_path == (
        root / "segmentation/thresholds.json"
    ).resolve()
    assert resolved.classifier_config_path == classifier_config.resolve()
    assert resolved.segmentation_config_path == segmentation_config.resolve()
    assert ActiveArtifactGate(path).evaluate().passed is True
