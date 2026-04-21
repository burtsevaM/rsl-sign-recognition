"""FastAPI dependencies for the runtime shell."""

from __future__ import annotations

from fastapi import Request

from rsl_sign_recognition.runtime.shell import RuntimeShell


def get_runtime_shell(request: Request) -> RuntimeShell:
    return request.app.state.runtime_shell
