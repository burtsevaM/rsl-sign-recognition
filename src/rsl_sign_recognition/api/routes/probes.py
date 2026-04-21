"""Liveness and readiness probes for the clean runtime shell."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from rsl_sign_recognition.api.dependencies import get_runtime_shell
from rsl_sign_recognition.runtime.shell import RuntimeShell

router = APIRouter()


@router.get("/health")
def health(runtime_shell: RuntimeShell = Depends(get_runtime_shell)) -> dict[str, str]:
    return runtime_shell.health_payload()


@router.get("/ready")
def ready(runtime_shell: RuntimeShell = Depends(get_runtime_shell)) -> JSONResponse:
    snapshot = runtime_shell.readiness_snapshot()
    return JSONResponse(
        status_code=snapshot.http_status_code,
        content=snapshot.as_payload(),
    )
