#!/usr/bin/env python3
"""Run the QA-03 live end-to-end recognition smoke through the backend."""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass
from io import BytesIO
import importlib
import json
import sys
import time
from pathlib import Path
from typing import Any
from urllib import error as urllib_error
from urllib import request as urllib_request
from urllib.parse import urlparse, urlunparse

from PIL import Image


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SAMPLE_MANIFEST = Path("data/live_samples/manifest.json")
REQUIRED_RESULT_FIELDS = (
    "status",
    "word",
    "confidence",
    "hand_present",
    "hold",
    "text_state",
    "timestamp_ms",
)


class SmokeError(RuntimeError):
    """Controlled runner failure shown to the operator without a traceback."""


@dataclass(frozen=True, slots=True)
class SmokeSample:
    sample_id: str
    expected_label: str
    local_path: Path
    fps: float | None


@dataclass(frozen=True, slots=True)
class SampleResult:
    sample_id: str
    expected_label: str
    actual_label: str | None
    confidence: float | None
    committed: bool
    passed: bool
    frames_sent: int
    committed_labels: tuple[str, ...]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run a live QA-03 smoke through /health, /ready and WS /ws/stream "
            "using repository live sample videos."
        )
    )
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:8000",
        help="Backend HTTP base URL.",
    )
    parser.add_argument(
        "--ws-url",
        default=None,
        help="Optional explicit WebSocket URL. Defaults to <base-url>/ws/stream.",
    )
    parser.add_argument(
        "--sample-manifest",
        default=str(DEFAULT_SAMPLE_MANIFEST),
        help="Repo-relative path to the live sample manifest.",
    )
    parser.add_argument(
        "--sample-id",
        action="append",
        dest="sample_ids",
        help="Limit the run to one or more sample ids from the manifest.",
    )
    parser.add_argument(
        "--max-samples",
        type=int,
        default=5,
        help="Maximum number of manifest samples to run when --sample-id is absent.",
    )
    parser.add_argument(
        "--max-frames",
        type=int,
        default=0,
        help="Optional frame cap per sample; 0 sends the whole clip.",
    )
    parser.add_argument(
        "--frame-stride",
        type=int,
        default=1,
        help="Send every Nth decoded frame.",
    )
    parser.add_argument(
        "--jpeg-quality",
        type=int,
        default=90,
        help="JPEG quality for binary packets sent to the backend.",
    )
    parser.add_argument(
        "--http-timeout-seconds",
        type=float,
        default=30.0,
        help="Timeout for /health and /ready requests.",
    )
    parser.add_argument(
        "--realtime",
        action="store_true",
        help="Sleep between frames using sample FPS to mimic real-time cadence.",
    )
    return parser


def repo_relative_path(path_text: str) -> Path:
    path = Path(path_text)
    resolved = path if path.is_absolute() else (REPO_ROOT / path)
    return resolved.resolve()


def load_samples(
    manifest_path: Path,
    *,
    sample_ids: list[str] | None,
    max_samples: int,
) -> list[SmokeSample]:
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SmokeError(f"sample manifest not found: {manifest_path}") from exc
    except json.JSONDecodeError as exc:
        raise SmokeError(f"sample manifest is not valid JSON: {manifest_path}") from exc

    raw_samples = manifest.get("samples")
    if not isinstance(raw_samples, list) or not raw_samples:
        raise SmokeError("sample manifest does not contain any samples")

    selected_ids = set(sample_ids or ())
    samples: list[SmokeSample] = []
    for raw_sample in raw_samples:
        if not isinstance(raw_sample, dict):
            continue
        sample_id = raw_sample.get("sample_id")
        expected_label = raw_sample.get("expected_label")
        local_path = raw_sample.get("local_path")
        if not all(isinstance(value, str) and value for value in (sample_id, expected_label, local_path)):
            continue
        if selected_ids and sample_id not in selected_ids:
            continue
        sample_path = repo_relative_path(local_path)
        if not sample_path.is_file():
            try:
                display_path = sample_path.relative_to(REPO_ROOT)
            except ValueError:
                display_path = sample_path
            raise SmokeError(
                f"sample file is missing for {sample_id}: "
                f"{display_path}"
            )
        fps_value = raw_sample.get("fps")
        fps = float(fps_value) if isinstance(fps_value, (int, float)) else None
        samples.append(
            SmokeSample(
                sample_id=sample_id,
                expected_label=expected_label,
                local_path=sample_path,
                fps=fps if fps and fps > 0 else None,
            )
        )

    if selected_ids:
        found_ids = {sample.sample_id for sample in samples}
        missing_ids = sorted(selected_ids - found_ids)
        if missing_ids:
            raise SmokeError(
                "sample ids were not found in the manifest: " + ", ".join(missing_ids)
            )

    if max_samples < 1:
        raise SmokeError("--max-samples must be a positive integer")
    if not samples:
        raise SmokeError("no usable samples selected from the manifest")
    return samples[:max_samples]


def require_dependency(module_name: str, install_hint: str) -> Any:
    try:
        return importlib.import_module(module_name)
    except ImportError as exc:
        raise SmokeError(
            f"{module_name} is required for the live smoke. Install it with: "
            f"{install_hint}"
        ) from exc


def fetch_json(url: str, *, timeout_seconds: float) -> tuple[int, dict[str, object]]:
    if timeout_seconds <= 0:
        raise SmokeError("--http-timeout-seconds must be positive")
    try:
        with urllib_request.urlopen(url, timeout=timeout_seconds) as response:
            status = int(response.status)
            body = response.read().decode("utf-8")
    except urllib_error.HTTPError as exc:
        status = int(exc.code)
        body = exc.read().decode("utf-8")
    except urllib_error.URLError as exc:
        raise SmokeError(f"backend is unreachable at {url}: {exc.reason}") from exc
    except TimeoutError as exc:
        raise SmokeError(
            f"backend timed out at {url} after {timeout_seconds:.1f}s"
        ) from exc

    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        raise SmokeError(
            f"backend returned non-JSON from {url}: status={status}"
        ) from exc
    if not isinstance(payload, dict):
        raise SmokeError(f"backend returned non-object JSON from {url}")
    return status, payload


def verify_health(base_url: str, *, timeout_seconds: float) -> None:
    status, payload = fetch_json(
        f"{base_url.rstrip('/')}/health",
        timeout_seconds=timeout_seconds,
    )
    if status != 200 or payload.get("probe") != "liveness":
        raise SmokeError(f"/health check failed: status={status}, payload={payload}")


def verify_ready(base_url: str, *, timeout_seconds: float) -> None:
    status, payload = fetch_json(
        f"{base_url.rstrip('/')}/ready",
        timeout_seconds=timeout_seconds,
    )
    if status != 200:
        reason_codes = payload.get("reason_codes", [])
        raise SmokeError(
            "/ready is not live-ready: "
            f"status={status}, gates={payload.get('gates')}, "
            f"reason_codes={reason_codes}"
        )
    if payload.get("probe") != "readiness" or payload.get("ready_for") != "live_runtime_path":
        raise SmokeError(f"/ready payload is not a live readiness response: {payload}")


def ws_url_for(base_url: str) -> str:
    parsed = urlparse(base_url)
    if parsed.scheme not in {"http", "https"}:
        raise SmokeError("--base-url must use http or https")
    ws_scheme = "wss" if parsed.scheme == "https" else "ws"
    return urlunparse((ws_scheme, parsed.netloc, "/ws/stream", "", "", ""))


def iter_jpeg_frames(
    sample: SmokeSample,
    *,
    max_frames: int,
    frame_stride: int,
    jpeg_quality: int,
):
    if frame_stride < 1:
        raise SmokeError("--frame-stride must be a positive integer")
    if not 1 <= jpeg_quality <= 100:
        raise SmokeError("--jpeg-quality must be in range 1..100")

    imageio_v3 = require_dependency(
        "imageio.v3",
        "python3 -m pip install '.[e2e-smoke]'",
    )

    frames_sent = 0
    for index, frame in enumerate(imageio_v3.imiter(sample.local_path)):
        if index % frame_stride != 0:
            continue
        image = Image.fromarray(frame)
        if image.mode != "RGB":
            image = image.convert("RGB")
        buffer = BytesIO()
        image.save(buffer, format="JPEG", quality=jpeg_quality)
        yield buffer.getvalue()
        frames_sent += 1
        if max_frames > 0 and frames_sent >= max_frames:
            break


def validate_recognition_result(message: dict[str, object]) -> dict[str, object]:
    if message.get("type") != "recognition.result":
        raise SmokeError(f"expected recognition.result, got: {message}")

    contract_version = message.get("contract_version")
    if not isinstance(contract_version, str) or contract_version.split(".", 1)[0] != "1":
        raise SmokeError(f"unsupported recognition.result contract version: {message}")

    payload = message.get("payload")
    if not isinstance(payload, dict):
        raise SmokeError(f"recognition.result payload is missing: {message}")

    missing = [field for field in REQUIRED_RESULT_FIELDS if field not in payload]
    if missing:
        raise SmokeError(
            "recognition.result is missing stable fields: " + ", ".join(missing)
        )

    text_state = payload.get("text_state")
    if not isinstance(text_state, dict) or "committed" not in text_state:
        raise SmokeError("recognition.result.text_state.committed is required")
    return payload


def sample_passed(
    *,
    expected_label: str,
    actual_label: str | None,
    committed: bool,
) -> bool:
    return committed and actual_label == expected_label


async def run_sample(
    sample: SmokeSample,
    *,
    ws_url: str,
    max_frames: int,
    frame_stride: int,
    jpeg_quality: int,
    realtime: bool,
) -> SampleResult:
    websockets = require_dependency(
        "websockets",
        "python3 -m pip install '.[e2e-smoke]'",
    )

    committed_labels: list[str] = []
    actual_label: str | None = None
    confidence: float | None = None
    committed = False
    frames_sent = 0
    frame_delay = (1.0 / sample.fps) if realtime and sample.fps else 0.0

    async with websockets.connect(ws_url, max_size=8 * 1024 * 1024) as websocket:
        for frame_bytes in iter_jpeg_frames(
            sample,
            max_frames=max_frames,
            frame_stride=frame_stride,
            jpeg_quality=jpeg_quality,
        ):
            await websocket.send(frame_bytes)
            frames_sent += 1
            raw_message = await websocket.recv()
            if not isinstance(raw_message, str):
                raise SmokeError("backend returned a non-text WebSocket response")
            try:
                message = json.loads(raw_message)
            except json.JSONDecodeError as exc:
                raise SmokeError("backend returned invalid JSON over WebSocket") from exc
            if not isinstance(message, dict):
                raise SmokeError("backend returned non-object JSON over WebSocket")
            if message.get("type") == "error":
                raise SmokeError(f"backend returned error for {sample.sample_id}: {message}")

            payload = validate_recognition_result(message)
            text_state = payload["text_state"]
            is_committed = bool(text_state.get("committed"))
            if is_committed:
                committed = True
                actual_label = str(payload["word"])
                confidence = float(payload["confidence"])
                committed_labels.append(actual_label)
            if frame_delay > 0:
                await asyncio.sleep(frame_delay)

    passed = sample_passed(
        expected_label=sample.expected_label,
        actual_label=actual_label,
        committed=committed,
    )
    return SampleResult(
        sample_id=sample.sample_id,
        expected_label=sample.expected_label,
        actual_label=actual_label,
        confidence=confidence,
        committed=committed,
        passed=passed,
        frames_sent=frames_sent,
        committed_labels=tuple(committed_labels),
    )


async def run_smoke(args: argparse.Namespace) -> list[SampleResult]:
    base_url = args.base_url.rstrip("/")
    verify_health(base_url, timeout_seconds=args.http_timeout_seconds)
    verify_ready(base_url, timeout_seconds=args.http_timeout_seconds)
    manifest_path = repo_relative_path(args.sample_manifest)
    samples = load_samples(
        manifest_path,
        sample_ids=args.sample_ids,
        max_samples=args.max_samples,
    )
    ws_url = args.ws_url or ws_url_for(base_url)
    results: list[SampleResult] = []
    for sample in samples:
        results.append(
            await run_sample(
                sample,
                ws_url=ws_url,
                max_frames=args.max_frames,
                frame_stride=args.frame_stride,
                jpeg_quality=args.jpeg_quality,
                realtime=args.realtime,
            )
        )
    return results


def print_summary(results: list[SampleResult]) -> None:
    print("sample_id | expected | actual | pass | confidence | committed | frames")
    print("--- | --- | --- | --- | --- | --- | ---")
    for result in results:
        actual = result.actual_label or "-"
        confidence = "-" if result.confidence is None else f"{result.confidence:.6f}"
        print(
            f"{result.sample_id} | {result.expected_label} | {actual} | "
            f"{'PASS' if result.passed else 'FAIL'} | {confidence} | "
            f"{str(result.committed).lower()} | {result.frames_sent}"
        )
        if result.committed_labels:
            labels = ", ".join(result.committed_labels)
            print(f"  committed_labels: {labels}")


def main() -> int:
    args = build_parser().parse_args()
    started_at = time.monotonic()
    try:
        results = asyncio.run(run_smoke(args))
    except SmokeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("ERROR: interrupted", file=sys.stderr)
        return 130

    print_summary(results)
    passed = all(result.passed for result in results)
    print(
        "summary: "
        f"{sum(result.passed for result in results)}/{len(results)} passed "
        f"in {time.monotonic() - started_at:.2f}s"
    )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
