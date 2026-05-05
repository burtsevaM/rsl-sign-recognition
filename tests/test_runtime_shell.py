from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from rsl_sign_recognition.api.factory import create_app
from rsl_sign_recognition.runtime.config import RuntimeMode, RuntimeShellSettings
from rsl_sign_recognition.runtime.services import RuntimeServiceRegistry
from rsl_sign_recognition.runtime.transport import LiveTransportSurface


def build_settings(tmp_path: Path, *, runtime_mode: RuntimeMode = RuntimeMode.LIVE) -> RuntimeShellSettings:
    return RuntimeShellSettings(
        runtime_mode=runtime_mode,
        repo_root=tmp_path,
        active_manifest_path=tmp_path / "artifacts/runtime/active/pose_words/manifest.json",
    )


def build_client(
    tmp_path: Path,
    *,
    runtime_mode: RuntimeMode = RuntimeMode.LIVE,
    transport_surface: LiveTransportSurface | None = None,
) -> TestClient:
    settings = build_settings(tmp_path, runtime_mode=runtime_mode)
    services = RuntimeServiceRegistry.build(
        settings,
        transport_surface=transport_surface
        or LiveTransportSurface(ws_stream_path=settings.ws_stream_path),
    )
    app = create_app(settings=settings, services=services)
    return TestClient(app)


def write_active_manifest(tmp_path: Path) -> None:
    manifest_path = tmp_path / "artifacts/runtime/active/pose_words/manifest.json"
    classifier_model = manifest_path.parent / "classifier/model.onnx"
    classifier_labels = manifest_path.parent / "classifier/labels.txt"
    segmentation_model = manifest_path.parent / "segmentation/model.onnx"
    segmentation_thresholds = manifest_path.parent / "segmentation/thresholds.json"

    classifier_model.parent.mkdir(parents=True, exist_ok=True)
    segmentation_model.parent.mkdir(parents=True, exist_ok=True)
    classifier_model.write_bytes(b"classifier")
    classifier_labels.write_text("hello\n", encoding="utf-8")
    segmentation_model.write_bytes(b"segmentation")
    segmentation_thresholds.write_text("{}", encoding="utf-8")

    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "contour": "pose_words",
                "profile_id": "runtime_active",
                "profile_role": "active",
                "profile_origin": "runtime",
                "readiness_class": "live_candidate",
                "source_pipeline": "pose_words",
                "files": {
                    "classifier_model": {
                        "relative_path": "classifier/model.onnx",
                        "required": True,
                    },
                    "classifier_labels": {
                        "relative_path": "classifier/labels.txt",
                        "required": True,
                    },
                    "segmentation_model": {
                        "relative_path": "segmentation/model.onnx",
                        "required": True,
                    },
                    "segmentation_thresholds": {
                        "relative_path": "segmentation/thresholds.json",
                        "required": True,
                    },
                },
            }
        ),
        encoding="utf-8",
    )


def test_health_reports_liveness_and_runtime_mode(tmp_path: Path) -> None:
    with build_client(tmp_path) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "probe": "liveness",
        "runtime_mode": "live",
    }


def test_ready_is_not_ready_without_manifest_and_live_ws(tmp_path: Path) -> None:
    with build_client(tmp_path) as client:
        response = client.get("/ready")

    assert response.status_code == 503
    assert response.json() == {
        "status": "not_ready",
        "probe": "readiness",
        "runtime_mode": "live",
        "ready_for": "live_runtime_path",
        "gates": {
            "runtime_shell": True,
            "active_artifacts": False,
            "transport_surface": False,
        },
        "reason_codes": [
            "active_manifest_missing",
            "live_runtime_pipeline_unavailable",
        ],
    }


def test_ready_stays_not_ready_when_manifest_exists_but_live_transport_is_missing(
    tmp_path: Path,
) -> None:
    write_active_manifest(tmp_path)

    with build_client(tmp_path) as client:
        response = client.get("/ready")

    assert response.status_code == 503
    assert response.json() == {
        "status": "not_ready",
        "probe": "readiness",
        "runtime_mode": "live",
        "ready_for": "live_runtime_path",
        "gates": {
            "runtime_shell": True,
            "active_artifacts": True,
            "transport_surface": False,
        },
        "reason_codes": ["live_runtime_pipeline_unavailable"],
    }


def test_ready_stays_not_ready_in_mock_mode(tmp_path: Path) -> None:
    write_active_manifest(tmp_path)

    with build_client(tmp_path, runtime_mode=RuntimeMode.MOCK) as client:
        response = client.get("/ready")

    assert response.status_code == 503
    assert response.json()["gates"] == {
        "runtime_shell": False,
        "active_artifacts": True,
        "transport_surface": False,
    }
    assert response.json()["reason_codes"] == [
        "runtime_mode_not_live",
        "live_runtime_pipeline_unavailable",
    ]


def test_transport_surface_cannot_become_ready_from_test_side_only() -> None:
    transport_surface = LiveTransportSurface(ws_stream_path="/ws/stream")

    assert transport_surface.evaluate().passed is False
    assert transport_surface.evaluate().reason_codes == (
        "live_runtime_pipeline_unavailable",
    )


def test_asgi_entrypoint_exposes_fastapi_app() -> None:
    from rsl_sign_recognition.asgi import app

    assert isinstance(app, FastAPI)
