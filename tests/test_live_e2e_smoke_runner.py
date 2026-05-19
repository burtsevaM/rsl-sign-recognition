from __future__ import annotations

import asyncio
import hashlib
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

EXPECTED_TRACKED_BUNDLE = {
    "slovo_privet_f17a6060": "привет",
    "slovo_poka_8ba230dc": "пока",
    "slovo_da_2b1b2857": "да",
    "slovo_horosho_43791c91": "хорошо",
    "slovo_ploho_27560a7e": "плохо",
    "slovo_utro_c1766b2e": "утро",
    "slovo_ulica_908f133b": "улица",
    "slovo_dom_524d6b8f": "дом",
    "slovo_voda_90db4617": "вода",
    "slovo_rabotat_ffce2323": "работать",
}


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


def test_tracked_live_sample_bundle_matches_manifest_metadata() -> None:
    manifest_path = RUNNER.REPO_ROOT / "data/live_samples/manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    samples = manifest["samples"]

    assert manifest["bundle_id"] == "DATA-02-live-sample-bundle-v3"
    assert len(samples) == 10
    actual_labels_by_sample_id = {
        sample["sample_id"]: sample["expected_label"]
        for sample in samples
    }
    assert actual_labels_by_sample_id == EXPECTED_TRACKED_BUNDLE

    for sample in samples:
        local_path = Path(sample["local_path"])
        assert not local_path.is_absolute()
        sample_path = RUNNER.REPO_ROOT / local_path
        assert sample_path.is_file()
        assert sample["live_input"] is True
        assert sample["byte_size"] == sample_path.stat().st_size
        assert hashlib.sha256(sample_path.read_bytes()).hexdigest() == sample["sha256"]

        source = sample["source"]
        for field in (
            "name",
            "origin",
            "upstream_repository",
            "upstream_path",
            "license",
            "license_url",
            "attribution",
            "modified",
            "modification_notes",
        ):
            assert field in source
        assert source["modified"] is False
        assert source["upstream_repository"] == "https://github.com/hukenovs/slovo"
        assert source["license"] == "CC BY-SA 4.0"


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
