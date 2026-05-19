from __future__ import annotations

import asyncio
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts/run_live_e2e_smoke.py"
SPEC = importlib.util.spec_from_file_location("run_live_e2e_smoke", SCRIPT_PATH)
assert SPEC is not None
assert SPEC.loader is not None
RUNNER = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = RUNNER
SPEC.loader.exec_module(RUNNER)


def write_manifest(tmp_path: Path) -> Path:
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
                        "fps": 30.0,
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return manifest_path


def sample_result(
    sample_id: str,
    *,
    expected_label: str = "привет",
    actual_label: str | None = "привет",
    committed: bool = True,
    passed: bool = True,
) -> RUNNER.SampleResult:
    return RUNNER.SampleResult(
        sample_id=sample_id,
        expected_label=expected_label,
        actual_label=actual_label,
        confidence=0.9,
        committed=committed,
        passed=passed,
        frames_sent=12,
        committed_labels=(actual_label,) if committed and actual_label else (),
    )


def test_load_samples_selects_requested_sample(tmp_path: Path) -> None:
    samples = RUNNER.load_samples(
        write_manifest(tmp_path),
        sample_ids=["sample_01"],
        max_samples=5,
    )

    assert len(samples) == 1
    assert samples[0].sample_id == "sample_01"
    assert samples[0].expected_label == "привет"
    assert samples[0].local_path == (tmp_path / "sample.mp4").resolve()


def test_load_samples_reports_unknown_sample_id(tmp_path: Path) -> None:
    with pytest.raises(RUNNER.SmokeError, match="sample ids were not found"):
        RUNNER.load_samples(
            write_manifest(tmp_path),
            sample_ids=["missing"],
            max_samples=5,
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
    assert "--min-passed" in help_text
    assert "--http-timeout-seconds" in help_text
    assert "--flush-boundary-frames" in help_text


def test_default_exit_decision_requires_all_samples_to_pass() -> None:
    results = [
        sample_result("sample_01"),
        sample_result(
            "sample_02",
            expected_label="пока",
            actual_label="привет",
            passed=False,
        ),
    ]

    decision = RUNNER.exit_decision(results, min_passed=None)

    assert decision.threshold == 2
    assert decision.passed_count == 1
    assert decision.success is False


def test_min_passed_threshold_accepts_eight_of_ten() -> None:
    results = [
        sample_result(f"sample_{index:02d}", passed=index < 8)
        for index in range(10)
    ]

    decision = RUNNER.exit_decision(results, min_passed=8)

    assert decision.passed_count == 8
    assert decision.total_count == 10
    assert decision.threshold == 8
    assert decision.success is True


def test_min_passed_threshold_rejects_invalid_values() -> None:
    with pytest.raises(RUNNER.SmokeError, match="at least 1"):
        RUNNER.validate_min_passed(0, total_samples=10)

    with pytest.raises(RUNNER.SmokeError, match="cannot exceed"):
        RUNNER.validate_min_passed(11, total_samples=10)


def test_run_smoke_validates_threshold_before_backend(tmp_path: Path) -> None:
    args = SimpleNamespace(
        base_url="http://127.0.0.1:1",
        sample_manifest=str(write_manifest(tmp_path)),
        sample_ids=None,
        max_samples=1,
        min_passed=2,
        http_timeout_seconds=0.01,
        ws_url=None,
        max_frames=0,
        frame_stride=1,
        jpeg_quality=90,
        realtime=False,
        flush_boundary_frames=1,
    )

    with pytest.raises(RUNNER.SmokeError, match="cannot exceed"):
        asyncio.run(RUNNER.run_smoke(args))


def test_summary_keeps_failed_samples_visible(capsys: pytest.CaptureFixture[str]) -> None:
    results = [
        sample_result("slovo_privet_f17a6060"),
        sample_result(
            "slovo_poka_8ba230dc",
            expected_label="пока",
            actual_label="привет",
            passed=False,
        ),
    ]

    RUNNER.print_summary(results, min_passed=1, elapsed_seconds=1.25)

    output = capsys.readouterr().out
    assert "slovo_poka_8ba230dc | пока | привет | FAIL" in output
    assert "summary: 1/2 passed in 1.25s" in output
    assert "threshold: 1/2 passed required" in output
    assert "exit_decision: success" in output


def test_sample_passed_requires_committed_result() -> None:
    assert (
        RUNNER.sample_passed(
            expected_label="привет",
            actual_label="привет",
            committed=False,
        )
        is False
    )


def test_sample_passed_accepts_only_committed_exact_label() -> None:
    assert (
        RUNNER.sample_passed(
            expected_label="привет",
            actual_label="привет",
            committed=True,
        )
        is True
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
