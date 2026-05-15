from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from rsl_sign_recognition.api.factory import create_app
from rsl_sign_recognition.runtime.config import RuntimeMode, RuntimeShellSettings
from rsl_sign_recognition.runtime.readiness import GateStatus
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
    pose_words_runtime=None,
) -> TestClient:
    settings = build_settings(tmp_path, runtime_mode=runtime_mode)
    services = RuntimeServiceRegistry.build(
        settings,
        transport_surface=transport_surface,
        pose_words_runtime=pose_words_runtime,
    )
    app = create_app(settings=settings, services=services)
    return TestClient(app)


@dataclass(frozen=True)
class StubPoseWordsRuntime:
    status: GateStatus

    def evaluate_readiness(self) -> GateStatus:
        return self.status


def write_active_manifest(tmp_path: Path, *, skip_required: str | None = None) -> None:
    manifest_path = tmp_path / "artifacts/runtime/active/pose_words/manifest.json"
    classifier_model = manifest_path.parent / "classifier/model.onnx"
    classifier_labels = manifest_path.parent / "classifier/labels.txt"
    segmentation_model = manifest_path.parent / "segmentation/model.onnx"
    segmentation_thresholds = manifest_path.parent / "segmentation/thresholds.json"

    classifier_model.parent.mkdir(parents=True, exist_ok=True)
    segmentation_model.parent.mkdir(parents=True, exist_ok=True)
    required_files = {
        "classifier_model": classifier_model,
        "classifier_labels": classifier_labels,
        "segmentation_model": segmentation_model,
        "segmentation_thresholds": segmentation_thresholds,
    }
    for name, path in required_files.items():
        if name == skip_required:
            continue
        if name.endswith("_labels"):
            path.write_text("hello\n", encoding="utf-8")
        elif name.endswith("_thresholds"):
            path.write_text("{}", encoding="utf-8")
        else:
            path.write_bytes(name.encode("utf-8"))

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


def rewrite_manifest(tmp_path: Path, **updates: object) -> None:
    manifest_path = tmp_path / "artifacts/runtime/active/pose_words/manifest.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload.update(updates)
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")


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
            "runtime_orchestrator": False,
            "transport_surface": True,
        },
        "reason_codes": [
            "active_manifest_missing",
            "live_runtime_pipeline_unavailable",
        ],
    }


def test_ready_stays_not_ready_when_manifest_exists_but_runtime_orchestrator_is_unavailable(
    tmp_path: Path,
) -> None:
    write_active_manifest(tmp_path)
    pose_words_runtime = StubPoseWordsRuntime(
        GateStatus(
            passed=False,
            reason_codes=("live_runtime_pipeline_unavailable",),
        )
    )

    with build_client(tmp_path, pose_words_runtime=pose_words_runtime) as client:
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
            "runtime_orchestrator": False,
            "transport_surface": True,
        },
        "reason_codes": ["live_runtime_pipeline_unavailable"],
    }


def test_ready_stays_not_ready_when_required_active_artifact_is_missing(
    tmp_path: Path,
) -> None:
    write_active_manifest(tmp_path, skip_required="segmentation_model")

    with build_client(tmp_path) as client:
        response = client.get("/ready")

    assert response.status_code == 503
    assert response.json()["gates"] == {
        "runtime_shell": True,
        "active_artifacts": False,
        "runtime_orchestrator": False,
        "transport_surface": True,
    }
    assert response.json()["reason_codes"] == [
        "active_required_artifacts_missing",
        "live_runtime_pipeline_unavailable",
    ]


def test_ready_reports_invalid_active_profile_marker(tmp_path: Path) -> None:
    write_active_manifest(tmp_path)
    rewrite_manifest(tmp_path, readiness_class="validation_only")

    with build_client(tmp_path) as client:
        response = client.get("/ready")

    assert response.status_code == 503
    assert response.json()["gates"] == {
        "runtime_shell": True,
        "active_artifacts": False,
        "runtime_orchestrator": False,
        "transport_surface": True,
    }
    assert response.json()["reason_codes"] == [
        "active_profile_not_live_candidate",
        "live_runtime_pipeline_unavailable",
    ]


def test_ready_stays_not_ready_in_mock_mode(tmp_path: Path) -> None:
    write_active_manifest(tmp_path)

    with build_client(tmp_path, runtime_mode=RuntimeMode.MOCK) as client:
        response = client.get("/ready")

    assert response.status_code == 503
    assert response.json()["gates"] == {
        "runtime_shell": False,
        "active_artifacts": True,
        "runtime_orchestrator": False,
        "transport_surface": True,
    }
    assert response.json()["reason_codes"] == ["runtime_mode_not_live"]


def test_ready_reports_invalid_runtime_orchestrator_state(tmp_path: Path) -> None:
    write_active_manifest(tmp_path)
    pose_words_runtime = StubPoseWordsRuntime(
        GateStatus(
            passed=False,
            reason_codes=("pose_words_runtime_misconfigured",),
        )
    )

    with build_client(tmp_path, pose_words_runtime=pose_words_runtime) as client:
        response = client.get("/ready")

    assert response.status_code == 503
    assert response.json()["gates"] == {
        "runtime_shell": True,
        "active_artifacts": True,
        "runtime_orchestrator": False,
        "transport_surface": True,
    }
    assert response.json()["reason_codes"] == ["pose_words_runtime_misconfigured"]


def test_ready_stays_not_ready_when_transport_is_not_linked_to_live_runtime(
    tmp_path: Path,
) -> None:
    write_active_manifest(tmp_path)
    pose_words_runtime = StubPoseWordsRuntime(GateStatus(passed=True))
    transport_surface = LiveTransportSurface(ws_stream_path="/ws/stream")

    with build_client(
        tmp_path,
        transport_surface=transport_surface,
        pose_words_runtime=pose_words_runtime,
    ) as client:
        response = client.get("/ready")

    assert response.status_code == 503
    assert response.json()["gates"] == {
        "runtime_shell": True,
        "active_artifacts": True,
        "runtime_orchestrator": True,
        "transport_surface": False,
    }
    assert response.json()["reason_codes"] == [
        "transport_surface_not_linked_to_live_runtime_pipeline"
    ]


def test_ready_stays_not_ready_when_transport_is_bound_to_another_runtime(
    tmp_path: Path,
) -> None:
    write_active_manifest(tmp_path)
    readiness_runtime = StubPoseWordsRuntime(GateStatus(passed=True))
    transport_runtime = StubPoseWordsRuntime(GateStatus(passed=True))
    transport_surface = LiveTransportSurface(
        ws_stream_path="/ws/stream",
        bound_pose_words_runtime=transport_runtime,
    )

    with build_client(
        tmp_path,
        transport_surface=transport_surface,
        pose_words_runtime=readiness_runtime,
    ) as client:
        response = client.get("/ready")

    assert response.status_code == 503
    assert response.json()["gates"] == {
        "runtime_shell": True,
        "active_artifacts": True,
        "runtime_orchestrator": True,
        "transport_surface": False,
    }
    assert response.json()["reason_codes"] == [
        "transport_surface_not_linked_to_live_runtime_pipeline"
    ]


def test_ready_is_ready_only_when_all_live_gates_pass(tmp_path: Path) -> None:
    write_active_manifest(tmp_path)
    pose_words_runtime = StubPoseWordsRuntime(GateStatus(passed=True))

    with build_client(tmp_path, pose_words_runtime=pose_words_runtime) as client:
        response = client.get("/ready")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "probe": "readiness",
        "runtime_mode": "live",
        "ready_for": "live_runtime_path",
        "gates": {
            "runtime_shell": True,
            "active_artifacts": True,
            "runtime_orchestrator": True,
            "transport_surface": True,
        },
    }


def test_transport_surface_requires_explicit_live_runtime_binding() -> None:
    expected_runtime = StubPoseWordsRuntime(GateStatus(passed=True))
    transport_surface = LiveTransportSurface(ws_stream_path="/ws/stream")

    status = transport_surface.evaluate(
        expected_pose_words_runtime=expected_runtime,
    )

    assert status.passed is False
    assert status.reason_codes == (
        "transport_surface_not_linked_to_live_runtime_pipeline",
    )


def test_transport_surface_rejects_different_live_runtime_binding() -> None:
    expected_runtime = StubPoseWordsRuntime(GateStatus(passed=True))
    bound_runtime = StubPoseWordsRuntime(GateStatus(passed=True))
    transport_surface = LiveTransportSurface(
        ws_stream_path="/ws/stream",
        bound_pose_words_runtime=bound_runtime,
    )

    status = transport_surface.evaluate(
        expected_pose_words_runtime=expected_runtime,
    )

    assert status.passed is False
    assert status.reason_codes == (
        "transport_surface_not_linked_to_live_runtime_pipeline",
    )


def test_transport_surface_passes_for_same_live_runtime_binding() -> None:
    runtime = StubPoseWordsRuntime(GateStatus(passed=True))
    transport_surface = LiveTransportSurface(
        ws_stream_path="/ws/stream",
        bound_pose_words_runtime=runtime,
    )

    status = transport_surface.evaluate(expected_pose_words_runtime=runtime)

    assert status.passed is True
    assert status.reason_codes == ()


def test_asgi_entrypoint_exposes_fastapi_app() -> None:
    from rsl_sign_recognition.asgi import app

    assert isinstance(app, FastAPI)
