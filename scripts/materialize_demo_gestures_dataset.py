#!/usr/bin/env python3
"""Materialize the DATA-03 / PW-08 demo gesture train/validation manifest."""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
import hashlib
from io import StringIO
import json
import os
from pathlib import Path
import sys
from typing import Iterable
import zipfile


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SLOVO_ROOT = Path(
    "/Users/mariaburtseva/Documents/проект грант/mvp1/"
    "SuperLuchito--SimpleGesture2Letter-Model-Version-2/backend/data/slovo"
)
DEFAULT_SOURCE_MANIFEST = REPO_ROOT / "data/demo_gestures/manifest.json"
DEFAULT_OUTPUT_MANIFEST = REPO_ROOT / "data/demo_gestures/materialized_manifest.json"
DEFAULT_LIVE_MANIFEST = REPO_ROOT / "data/live_samples/manifest.json"
SOURCE_DATASET = "Slovo Russian Sign Language Dataset"
LICENSE = "CC BY-SA 4.0"
LICENSE_URL = "https://creativecommons.org/licenses/by-sa/4.0/"
ATTRIBUTION = "Slovo Russian Sign Language Dataset and Models, hukenovs/slovo"
TARGET_GESTURES = [
    "привет",
    "пока",
    "да",
    "хорошо",
    "плохо",
    "утро",
    "улица",
    "дом",
    "вода",
    "работать",
]
TARGET_COUNTS = {
    "train": 15,
    "validation": 5,
}
NO_EVENT_LABEL = "_no_event"
NO_EVENT_TARGET_COUNTS = {
    "train": 10,
    "validation": 4,
}
SLOVO_SLUGS = {
    "привет": "privet",
    "пока": "poka",
    "да": "da",
    "хорошо": "horosho",
    "плохо": "ploho",
    "утро": "utro",
    "улица": "ulica",
    "дом": "dom",
    "вода": "voda",
    "работать": "rabotat",
    NO_EVENT_LABEL: "no_event",
}
SLOVO_LABEL_ALIASES = {
    "привет!": "привет",
    "no_event": NO_EVENT_LABEL,
}


@dataclass(frozen=True, slots=True)
class SlovoSource:
    root: Path
    annotations_path: str
    archive_path: Path | None
    video_paths: frozenset[str]


@dataclass(frozen=True, slots=True)
class SlovoRow:
    attachment_id: str
    label: str
    source_label: str
    split: str
    video_path: str


@dataclass(frozen=True, slots=True)
class SampleRecord:
    sample_id: str
    label: str
    source_label: str
    split: str
    source: str
    source_dataset: str
    source_path: str
    byte_size: int
    sha256: str
    license: str
    license_url: str
    attribution: str
    modified: bool
    modification_notes: str
    excluded_from_live_smoke: bool

    def as_dict(self) -> dict[str, object]:
        return {
            "sample_id": self.sample_id,
            "label": self.label,
            "source_label": self.source_label,
            "split": self.split,
            "source": self.source,
            "source_dataset": self.source_dataset,
            "source_path": self.source_path,
            "byte_size": self.byte_size,
            "sha256": self.sha256,
            "license": self.license,
            "license_url": self.license_url,
            "attribution": self.attribution,
            "modified": self.modified,
            "modification_notes": self.modification_notes,
            "excluded_from_live_smoke": self.excluded_from_live_smoke,
        }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build DATA-03 / PW-08 train/validation manifest from local Slovo data."
    )
    parser.add_argument(
        "--slovo-root",
        default=None,
        help=(
            "Path to local Slovo root, unpacked directory, or slovo.zip. "
            "Defaults to SLOVO_DATA_ROOT or the known mvp1 local path."
        ),
    )
    parser.add_argument(
        "--source-manifest",
        default=str(DEFAULT_SOURCE_MANIFEST),
        help="Path to data/demo_gestures/manifest.json.",
    )
    parser.add_argument(
        "--live-manifest",
        default=str(DEFAULT_LIVE_MANIFEST),
        help="Path to data/live_samples/manifest.json.",
    )
    parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT_MANIFEST),
        help="Where to write the materialized manifest JSON.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Return a non-zero exit code when target counts are not fully materialized.",
    )
    return parser


def resolve_slovo_root(path_text: str | None) -> Path:
    if path_text:
        return Path(path_text).expanduser().resolve()
    env_path = os.environ.get("SLOVO_DATA_ROOT")
    if env_path:
        return Path(env_path).expanduser().resolve()
    return DEFAULT_SLOVO_ROOT


def discover_slovo_source(slovo_root: Path) -> SlovoSource:
    if slovo_root.is_file() and slovo_root.suffix == ".zip":
        return discover_zip_source(slovo_root, slovo_root.parent)

    archive = slovo_root / "slovo.zip"
    if archive.is_file():
        return discover_zip_source(archive, slovo_root)

    annotations = next(slovo_root.rglob("annotations.csv"), None)
    if annotations is None:
        raise FileNotFoundError(f"annotations.csv was not found under {slovo_root}")

    video_paths = {
        path.relative_to(slovo_root).as_posix()
        for path in slovo_root.rglob("*.mp4")
    }
    if not video_paths:
        raise FileNotFoundError(f"no .mp4 files were found under {slovo_root}")
    return SlovoSource(
        root=slovo_root,
        annotations_path=annotations.relative_to(slovo_root).as_posix(),
        archive_path=None,
        video_paths=frozenset(video_paths),
    )


def discover_zip_source(archive_path: Path, root: Path) -> SlovoSource:
    with zipfile.ZipFile(archive_path) as archive:
        names = archive.namelist()
    annotations = [name for name in names if name.endswith("annotations.csv")]
    if not annotations:
        raise FileNotFoundError(f"annotations.csv was not found in {archive_path}")
    video_paths = frozenset(name for name in names if name.endswith(".mp4"))
    if not video_paths:
        raise FileNotFoundError(f"no .mp4 files were found in {archive_path}")
    return SlovoSource(
        root=root,
        annotations_path=annotations[0],
        archive_path=archive_path,
        video_paths=video_paths,
    )


def read_annotations(source: SlovoSource) -> list[SlovoRow]:
    if source.archive_path is not None:
        with zipfile.ZipFile(source.archive_path) as archive:
            text = archive.read(source.annotations_path).decode("utf-8-sig")
    else:
        text = (source.root / source.annotations_path).read_text(encoding="utf-8-sig")

    reader = csv.DictReader(StringIO(text), delimiter="\t")
    required_fields = {"attachment_id", "text", "train"}
    if not reader.fieldnames or not required_fields.issubset(set(reader.fieldnames)):
        raise ValueError(
            "annotations.csv must contain tab-separated attachment_id, text and train fields"
        )

    rows: list[SlovoRow] = []
    for raw in reader:
        attachment_id = str(raw.get("attachment_id", "")).strip()
        source_label = str(raw.get("text", "")).strip()
        label = canonical_label(source_label)
        if not attachment_id or not label:
            continue
        split = "train" if is_train_value(raw.get("train")) else "validation"
        video_path = f"{'train' if split == 'train' else 'test'}/{attachment_id}.mp4"
        rows.append(
            SlovoRow(
                attachment_id=attachment_id,
                label=label,
                source_label=source_label,
                split=split,
                video_path=video_path,
            )
        )
    return rows


def is_train_value(value: object) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes"}


def normalize_label(value: str) -> str:
    return value.strip().lower()


def canonical_label(value: str) -> str:
    normalized = normalize_label(value)
    return SLOVO_LABEL_ALIASES.get(normalized, normalized)


def sample_id_for(label: str, attachment_id: str) -> str:
    return f"slovo_{SLOVO_SLUGS[label]}_{attachment_id[:8]}"


def load_live_smoke_exclusions(
    source_manifest_path: Path,
    live_manifest_path: Path,
) -> set[str]:
    excluded: set[str] = set()
    for manifest_path in (source_manifest_path, live_manifest_path):
        if not manifest_path.is_file():
            continue
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            continue
        relation = payload.get("live_smoke_relation")
        if isinstance(relation, dict):
            excluded.update(
                item
                for item in relation.get("excluded_sample_ids", [])
                if isinstance(item, str)
            )
        for sample in payload.get("samples", []):
            if not isinstance(sample, dict):
                continue
            sample_id = sample.get("sample_id")
            if isinstance(sample_id, str):
                excluded.add(sample_id)
    return excluded


def is_excluded_live_smoke(row: SlovoRow, label: str, excluded_ids: set[str]) -> bool:
    sample_id = sample_id_for(label, row.attachment_id)
    short_id = row.attachment_id[:8]
    return sample_id in excluded_ids or any(item.endswith(short_id) for item in excluded_ids)


def build_materialized_manifest(
    *,
    source: SlovoSource,
    rows: Iterable[SlovoRow],
    source_manifest_path: Path,
    live_manifest_path: Path,
    target_gestures: list[str] | None = None,
    target_counts: dict[str, int] | None = None,
) -> dict[str, object]:
    target_gestures = target_gestures or TARGET_GESTURES
    target_counts = target_counts or TARGET_COUNTS
    class_targets = {
        label: dict(target_counts)
        for label in target_gestures
    }
    class_targets[NO_EVENT_LABEL] = dict(NO_EVENT_TARGET_COUNTS)
    target_labels = set(class_targets)
    excluded_ids = load_live_smoke_exclusions(source_manifest_path, live_manifest_path)
    rows_by_label_split: dict[tuple[str, str], list[SlovoRow]] = {}
    missing_video_rows: list[dict[str, str]] = []
    excluded_rows: list[dict[str, str]] = []

    for row in rows:
        if row.label not in target_labels:
            continue
        if row.video_path not in source.video_paths:
            missing_video_rows.append(
                {
                    "label": row.label,
                    "split": row.split,
                    "attachment_id": row.attachment_id,
                    "expected_video_path": row.video_path,
                }
            )
            continue
        if is_excluded_live_smoke(row, row.label, excluded_ids):
            excluded_rows.append(
                {
                    "sample_id": sample_id_for(row.label, row.attachment_id),
                    "label": row.label,
                    "split": row.split,
                    "source_path": source_path_for(source, row.video_path),
                }
            )
            continue
        rows_by_label_split.setdefault((row.label, row.split), []).append(row)

    samples: list[SampleRecord] = []
    class_counts: dict[str, dict[str, int]] = {}
    class_status: dict[str, dict[str, object]] = {}
    shortages: list[dict[str, object]] = []
    for label in list(target_gestures) + [NO_EVENT_LABEL]:
        class_counts[label] = {}
        targets = class_targets[label]
        for split, target_count in targets.items():
            candidates = sorted(
                rows_by_label_split.get((label, split), []),
                key=lambda row: row.attachment_id,
            )
            selected = candidates[:target_count]
            class_counts[label][split] = len(selected)
            if len(selected) < target_count:
                shortages.append(
                    {
                        "label": label,
                        "split": split,
                        "target": target_count,
                        "materialized": len(selected),
                        "missing": target_count - len(selected),
                    }
                )
            for row in selected:
                samples.append(sample_record_for(source, row, label))
        class_counts[label]["total"] = (
            class_counts[label].get("train", 0)
            + class_counts[label].get("validation", 0)
        )
        class_status[label] = status_for_class(
            label=label,
            targets=targets,
            counts=class_counts[label],
        )

    return {
        "schema_version": 1,
        "dataset_id": "DATA-03-PW-08-demo-gestures-materialized-v1",
        "source_manifest": repo_relative(source_manifest_path),
        "source_dataset": SOURCE_DATASET,
        "source_root": str(source.root),
        "source_archive": str(source.archive_path) if source.archive_path else None,
        "annotations_path": source.annotations_path,
        "video_files_found": len(source.video_paths),
        "target_gestures": target_gestures,
        "target_counts": {
            "gestures": target_counts,
            NO_EVENT_LABEL: NO_EVENT_TARGET_COUNTS,
        },
        "materialized_counts": class_counts,
        "class_status": class_status,
        "issue_closure_ready": all(
            item["status"] in {"ok", "shortage"}
            and int(item["materialized_train"]) > 0
            and int(item["materialized_validation"]) > 0
            for item in class_status.values()
        ),
        "samples": [sample.as_dict() for sample in samples],
        "live_smoke_exclusions": {
            "source": [
                repo_relative(source_manifest_path),
                repo_relative(live_manifest_path),
            ],
            "excluded_sample_ids": sorted(excluded_ids),
            "excluded_rows": excluded_rows,
        },
        "shortages": shortages,
        "missing_video_rows": missing_video_rows,
        "source_license": {
            "license": LICENSE,
            "license_url": LICENSE_URL,
            "attribution": ATTRIBUTION,
        },
        "label_canonicalization": {
            "policy": "Only explicit orthographic/runtime aliases are canonicalized; semantic synonyms are not remapped silently.",
            "aliases": SLOVO_LABEL_ALIASES,
            "non_goal_examples": {
                "здравствуйте": "candidate synonym only; not remapped to привет",
                "работа": "different word; not remapped to работать",
            },
        },
        "source_search_report": {
            "привет": "Found as source label Привет! in local Slovo annotations.csv: 15 train / 5 validation before live smoke exclusion.",
            NO_EVENT_LABEL: "Found as source label no_event in local Slovo annotations.csv: 300 train / 100 validation before target selection.",
        },
        "known_limitations": [
            "Heavy Slovo videos are not copied or committed to this repository.",
            "Slovo source label Привет! is canonicalized to runtime/demo label привет; the live smoke example remains excluded from training.",
            "Slovo source label no_event is canonicalized to runtime background label _no_event; fake background clips are not created.",
            "After excluding PR #77 live smoke clips, most gesture classes remain below the 15/5 target and are marked as shortage.",
        ],
    }


def status_for_class(
    *,
    label: str,
    targets: dict[str, int],
    counts: dict[str, int],
) -> dict[str, object]:
    target_train = int(targets["train"])
    target_validation = int(targets["validation"])
    materialized_train = int(counts.get("train", 0))
    materialized_validation = int(counts.get("validation", 0))
    shortage_train = max(0, target_train - materialized_train)
    shortage_validation = max(0, target_validation - materialized_validation)
    if materialized_train == 0 or materialized_validation == 0:
        status = "missing"
        notes = "No usable train or validation records were materialized from legal local sources."
    elif shortage_train or shortage_validation:
        status = "shortage"
        notes = "Usable train and validation records exist, but materialized counts are below target after exclusions."
    else:
        status = "ok"
        notes = "Target train and validation counts were materialized from legal local sources."
    if label == NO_EVENT_LABEL and status == "ok":
        notes = "Runtime background class was materialized from explicit Slovo no_event rows."
    return {
        "target_train": target_train,
        "target_validation": target_validation,
        "materialized_train": materialized_train,
        "materialized_validation": materialized_validation,
        "status": status,
        "shortage_train": shortage_train,
        "shortage_validation": shortage_validation,
        "notes": notes,
    }


def sample_record_for(source: SlovoSource, row: SlovoRow, label: str) -> SampleRecord:
    byte_size, digest = file_stats(source, row.video_path)
    return SampleRecord(
        sample_id=sample_id_for(label, row.attachment_id),
        label=label,
        source_label=row.source_label,
        split=row.split,
        source="slovo",
        source_dataset=SOURCE_DATASET,
        source_path=source_path_for(source, row.video_path),
        byte_size=byte_size,
        sha256=digest,
        license=LICENSE,
        license_url=LICENSE_URL,
        attribution=ATTRIBUTION,
        modified=False,
        modification_notes="Content bytes are referenced from local Slovo source; no video is copied or modified by this script.",
        excluded_from_live_smoke=False,
    )


def file_stats(source: SlovoSource, video_path: str) -> tuple[int, str]:
    digest = hashlib.sha256()
    if source.archive_path is not None:
        with zipfile.ZipFile(source.archive_path) as archive:
            info = archive.getinfo(video_path)
            with archive.open(info) as file_obj:
                for chunk in iter(lambda: file_obj.read(1024 * 1024), b""):
                    digest.update(chunk)
            return int(info.file_size), digest.hexdigest()

    path = source.root / video_path
    with path.open("rb") as file_obj:
        for chunk in iter(lambda: file_obj.read(1024 * 1024), b""):
            digest.update(chunk)
    return path.stat().st_size, digest.hexdigest()


def source_path_for(source: SlovoSource, video_path: str) -> str:
    if source.archive_path is not None:
        return f"{source.archive_path}::{video_path}"
    return str((source.root / video_path).resolve())


def repo_relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return str(path)


def write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    args = build_parser().parse_args()
    slovo_root = resolve_slovo_root(args.slovo_root)
    source_manifest_path = Path(args.source_manifest).resolve()
    live_manifest_path = Path(args.live_manifest).resolve()
    output_path = Path(args.output).resolve()

    try:
        source = discover_slovo_source(slovo_root)
        rows = read_annotations(source)
        manifest = build_materialized_manifest(
            source=source,
            rows=rows,
            source_manifest_path=source_manifest_path,
            live_manifest_path=live_manifest_path,
        )
        write_json(output_path, manifest)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    counts = manifest["materialized_counts"]
    print(f"Slovo root: {source.root}")
    print(f"annotations.csv: {source.annotations_path}")
    print(f"video files found: {manifest['video_files_found']}")
    print(f"materialized manifest: {output_path}")
    for label in TARGET_GESTURES:
        item = counts[label]
        status = manifest["class_status"][label]["status"]
        print(
            f"{label}: train={item['train']}/{TARGET_COUNTS['train']} "
            f"validation={item['validation']}/{TARGET_COUNTS['validation']} "
            f"status={status}"
        )
    no_event = counts[NO_EVENT_LABEL]
    no_event_status = manifest["class_status"][NO_EVENT_LABEL]["status"]
    print(
        f"{NO_EVENT_LABEL}: train={no_event['train']}/{NO_EVENT_TARGET_COUNTS['train']} "
        f"validation={no_event['validation']}/{NO_EVENT_TARGET_COUNTS['validation']} "
        f"status={no_event_status}"
    )
    shortages = manifest["shortages"]
    if shortages:
        print(f"shortages: {len(shortages)}", file=sys.stderr)
        for shortage in shortages:
            print(
                "WARNING: "
                f"{shortage['label']} {shortage['split']} "
                f"materialized={shortage['materialized']} "
                f"target={shortage['target']}",
                file=sys.stderr,
            )
        return 1 if args.strict else 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
