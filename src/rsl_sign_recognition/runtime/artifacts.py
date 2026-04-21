"""Artifact readiness boundary for the clean runtime shell."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from rsl_sign_recognition.runtime.readiness import GateStatus


@dataclass(frozen=True)
class ActiveArtifactGate:
    """Minimal active-artifact gate based on the clean manifest policy."""

    manifest_path: Path

    def evaluate(self) -> GateStatus:
        if not self.manifest_path.is_file():
            return GateStatus(passed=False, reason_codes=("active_manifest_missing",))

        try:
            manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return GateStatus(
                passed=False,
                reason_codes=("active_manifest_invalid_json",),
            )

        if manifest.get("profile_role") != "active":
            return GateStatus(
                passed=False,
                reason_codes=("active_profile_role_invalid",),
            )

        if manifest.get("readiness_class") != "live_candidate":
            return GateStatus(
                passed=False,
                reason_codes=("active_profile_not_live_candidate",),
            )

        files = manifest.get("files")
        if not isinstance(files, dict) or not files:
            return GateStatus(
                passed=False,
                reason_codes=("active_manifest_files_missing",),
            )

        missing_required: list[str] = []
        for descriptor in files.values():
            if not isinstance(descriptor, dict):
                return GateStatus(
                    passed=False,
                    reason_codes=("active_manifest_descriptor_invalid",),
                )

            if not descriptor.get("required", False):
                continue

            relative_path = descriptor.get("relative_path")
            if not isinstance(relative_path, str) or not relative_path:
                return GateStatus(
                    passed=False,
                    reason_codes=("active_manifest_relative_path_invalid",),
                )

            artifact_path = self.manifest_path.parent / relative_path
            if not artifact_path.is_file():
                missing_required.append(relative_path)

        if missing_required:
            return GateStatus(
                passed=False,
                reason_codes=("active_required_artifacts_missing",),
            )

        return GateStatus(passed=True)
