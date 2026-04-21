"""Configuration for the clean runtime shell."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
import os


class RuntimeMode(str, Enum):
    LIVE = "live"
    MOCK = "mock"


@dataclass(frozen=True)
class RuntimeShellSettings:
    runtime_mode: RuntimeMode
    repo_root: Path
    active_manifest_path: Path
    ws_stream_path: str = "/ws/stream"

    @classmethod
    def from_env(cls) -> "RuntimeShellSettings":
        repo_root = Path(
            os.getenv("RSL_REPO_ROOT", Path(__file__).resolve().parents[3])
        ).resolve()

        manifest_setting = Path(
            os.getenv(
                "RSL_ACTIVE_MANIFEST_PATH",
                "artifacts/runtime/active/pose_words/manifest.json",
            )
        )
        if not manifest_setting.is_absolute():
            manifest_setting = (repo_root / manifest_setting).resolve()

        runtime_mode = RuntimeMode(os.getenv("RSL_RUNTIME_MODE", RuntimeMode.LIVE.value))

        return cls(
            runtime_mode=runtime_mode,
            repo_root=repo_root,
            active_manifest_path=manifest_setting,
            ws_stream_path=os.getenv("RSL_WS_STREAM_PATH", "/ws/stream"),
        )
