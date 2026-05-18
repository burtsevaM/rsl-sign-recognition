from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys

import pytest


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts/run_live_e2e_smoke.py"
SPEC = importlib.util.spec_from_file_location("run_live_e2e_smoke", SCRIPT_PATH)
assert SPEC is not None
assert SPEC.loader is not None
RUNNER = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = RUNNER
SPEC.loader.exec_module(RUNNER)


def sample_entry(sample_path: Path, *, sample_id: str = "sample_01") -> dict[str, object]:
    return {
        "sample_id": sample_id,
        "expected_label": "привет",
        "local_path": str(sample_path),
        "duration_seconds": 1.0,
        "fps": 30.0,
        "source": {
            "upstream_repository": "https://example.test/source",
            "license": "CC BY-SA 4.0",
            "license_url": "https://example.test/license",
            "attribution": "Example dataset",
            "modified": False,
            "modification_notes": "content bytes unchanged",
        },
    }


def write_manifest(tmp_path: Path, *, sample_count: int = 1) -> Path:
    samples: list[dict[str, object]] = []
    for index in range(sample_count):
        sample_path = tmp_path / f"sample-{index}.mp4"
        sample_path.write_bytes(b"video")
        samples.append(sample_entry(sample_path, sample_id=f"sample_{index + 1:02d}"))
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "samples": samples
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return manifest_path


def test_load_samples_selects_requested_sample(tmp_path: Path) -> None:
    samples = RUNNER.load_samples(
        write_manifest(tmp_path),
        sample_ids=["sample_01"],
        max_samples=0,
    )

    assert len(samples) == 1
    assert samples[0].sample_id == "sample_01"
    assert samples[0].expected_label == "привет"
    assert samples[0].local_path == (tmp_path / "sample-0.mp4").resolve()


def test_load_samples_reports_unknown_sample_id(tmp_path: Path) -> None:
    with pytest.raises(RUNNER.SmokeError, match="sample ids were not found"):
        RUNNER.load_samples(
            write_manifest(tmp_path),
            sample_ids=["missing"],
            max_samples=0,
        )


def test_load_samples_runs_full_bundle_when_max_samples_is_zero(tmp_path: Path) -> None:
    samples = RUNNER.load_samples(
        write_manifest(tmp_path, sample_count=3),
        sample_ids=None,
        max_samples=0,
    )

    assert [sample.sample_id for sample in samples] == [
        "sample_01",
        "sample_02",
        "sample_03",
    ]


def test_load_samples_rejects_missing_source_metadata(tmp_path: Path) -> None:
    sample_path = tmp_path / "sample.mp4"
    sample_path.write_bytes(b"video")
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "samples": [
                    {
                        "sample_id": "sample_01",
                        "expected_label": "привет",
                        "local_path": str(sample_path),
                        "duration_seconds": 1.0,
                        "fps": 30.0,
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    with pytest.raises(RUNNER.SmokeError, match="source metadata is required"):
        RUNNER.load_samples(
            manifest_path,
            sample_ids=None,
            max_samples=0,
        )


def test_validate_recognition_result_requires_stable_contract_surface() -> None:
    payload = RUNNER.validate_recognition_result(
        {
            "type": "recognition.result",
            "contract_version": "1.0",
            "payload": {
                "status": "COMMIT",
                "word": "привет",
                "confidence": 0.9,
                "hand_present": True,
                "hold": {},
                "text_state": {"value": "привет", "committed": True},
                "timestamp_ms": 1,
            },
        }
    )

    assert payload["text_state"]["committed"] is True


def test_validate_recognition_result_rejects_missing_committed_flag() -> None:
    with pytest.raises(RUNNER.SmokeError, match="text_state.committed"):
        RUNNER.validate_recognition_result(
            {
                "type": "recognition.result",
                "contract_version": "1.0",
                "payload": {
                    "status": "NONE",
                    "word": "NONE",
                    "confidence": 0.0,
                    "hand_present": False,
                    "hold": {},
                    "text_state": {"value": ""},
                    "timestamp_ms": 1,
                },
            }
        )


def test_build_parser_exposes_sample_selection_and_timeout_flags() -> None:
    parser = RUNNER.build_parser()
    help_text = parser.format_help()

    assert "--sample-id" in help_text
    assert "--max-samples" in help_text
    assert "--http-timeout-seconds" in help_text


def test_sample_passed_requires_committed_result() -> None:
    assert (
        RUNNER.sample_passed(
            expected_label="привет",
            actual_label="привет",
            committed=False,
        )
        is False
    )


def test_sample_passed_rejects_wrong_label() -> None:
    assert (
        RUNNER.sample_passed(
            expected_label="привет",
            actual_label="пока",
            committed=True,
        )
        is False
    )
