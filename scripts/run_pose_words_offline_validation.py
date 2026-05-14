#!/usr/bin/env python3
"""Run PW-06 offline validation for the active pose_words artifact pack."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from rsl_sign_recognition.validation.pose_words_offline import (  # noqa: E402
    DEFAULT_MANIFEST,
    repo_relative_path,
    run_offline_validation,
    write_json_report,
)


DEFAULT_OUTPUT_JSON = Path(
    "docs/validation/pose_words-offline-quality-results.json"
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run offline pose_words quality validation without WebSocket."
    )
    parser.add_argument(
        "--manifest",
        default=str(DEFAULT_MANIFEST),
        help="Repo-relative active pose_words manifest path.",
    )
    parser.add_argument(
        "--output-json",
        default=str(DEFAULT_OUTPUT_JSON),
        help="Repo-relative JSON report path, or '-' for stdout only.",
    )
    parser.add_argument(
        "--samples-per-label",
        type=int,
        default=3,
        help="Synthetic samples per checked label.",
    )
    parser.add_argument(
        "--max-target-labels",
        type=int,
        default=5,
        help="Maximum non-_no_event target labels to validate.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        manifest_path = repo_relative_path(REPO_ROOT, args.manifest)
        report = run_offline_validation(
            manifest_path=manifest_path,
            samples_per_label=args.samples_per_label,
            max_target_labels=args.max_target_labels,
        )
        text = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
        if str(args.output_json).strip() == "-":
            sys.stdout.write(text)
        else:
            output_path = repo_relative_path(REPO_ROOT, args.output_json)
            write_json_report(report, output_path)
            print(f"[pose_words_offline_validation] wrote {output_path.relative_to(REPO_ROOT)}")
            print(
                "[pose_words_offline_validation] "
                f"top1_accuracy={report['summary']['top1_accuracy']} "
                f"target_top1_accuracy={report['target_summary']['top1_accuracy']}"
            )
    except ImportError as exc:
        print(
            "ERROR: onnxruntime is required for offline pose_words validation. "
            "Install the existing optional extras, for example: "
            "python3 -m pip install '.[pose-words-inference,segmentation]'",
            file=sys.stderr,
        )
        print(f"Details: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
