from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import sys

import pytest


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts/materialize_demo_gestures_dataset.py"
SPEC = importlib.util.spec_from_file_location("materialize_demo_gestures_dataset", SCRIPT_PATH)
assert SPEC is not None
assert SPEC.loader is not None
MATERIALIZE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MATERIALIZE
SPEC.loader.exec_module(MATERIALIZE)


def write_fake_slovo(tmp_path: Path) -> Path:
    slovo_root = tmp_path / "slovo"
    (slovo_root / "train").mkdir(parents=True)
    (slovo_root / "test").mkdir(parents=True)
    rows = [
        ("f17a6060-0000-0000-0000-000000000000", "Привет!", "True"),
        ("aaaaaaa1-0000-0000-0000-000000000000", "Привет!", "True"),
        ("aaaaaaa2-0000-0000-0000-000000000000", "Привет!", "False"),
        ("bbbbbbb1-0000-0000-0000-000000000000", "Здравствуйте", "True"),
        ("8ba230dc-0000-0000-0000-000000000000", "Пока", "True"),
        ("11111111-0000-0000-0000-000000000000", "Пока", "True"),
        ("22222222-0000-0000-0000-000000000000", "Пока", "False"),
        ("33333333-0000-0000-0000-000000000000", "Работа", "True"),
        ("44444444-0000-0000-0000-000000000000", "работать", "True"),
        ("55555555-0000-0000-0000-000000000000", "работать", "False"),
        ("no111111-0000-0000-0000-000000000000", "no_event", "True"),
        ("no222222-0000-0000-0000-000000000000", "no_event", "False"),
    ]
    annotations = slovo_root / "annotations.csv"
    annotations.write_text(
        "attachment_id\ttext\tuser_id\theight\twidth\tlength\ttrain\n"
        + "\n".join(
            f"{attachment_id}\t{label}\tuser\t720\t1280\t30\t{train}"
            for attachment_id, label, train in rows
        )
        + "\n",
        encoding="utf-8",
    )
    for attachment_id, _label, train in rows:
        split = "train" if train == "True" else "test"
        (slovo_root / split / f"{attachment_id}.mp4").write_bytes(
            f"video:{attachment_id}".encode("utf-8")
        )
    return slovo_root


def write_manifest(path: Path, excluded_sample_ids: list[str]) -> None:
    path.write_text(
        json.dumps(
            {
                "live_smoke_relation": {
                    "excluded_sample_ids": excluded_sample_ids,
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def test_resolve_slovo_root_defaults_to_repo_local_path(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.delenv("SLOVO_DATA_ROOT", raising=False)
    monkeypatch.setattr(MATERIALIZE, "LEGACY_MVP1_SLOVO_ROOT", tmp_path / "missing_slovo")

    assert MATERIALIZE.resolve_slovo_root(None) == MATERIALIZE.DEFAULT_SLOVO_ROOT


def build_fake_manifest(tmp_path: Path, excluded_sample_ids: list[str] | None = None) -> dict[str, object]:
    slovo_root = write_fake_slovo(tmp_path)
    source_manifest = tmp_path / "source_manifest.json"
    live_manifest = tmp_path / "live_manifest.json"
    write_manifest(source_manifest, excluded_sample_ids or [])
    write_manifest(live_manifest, [])
    source = MATERIALIZE.discover_slovo_source(slovo_root)
    rows = MATERIALIZE.read_annotations(source)
    return MATERIALIZE.build_materialized_manifest(
        source=source,
        rows=rows,
        source_manifest_path=source_manifest,
        live_manifest_path=live_manifest,
        target_gestures=["пока", "работать"],
        target_counts={
            "train": 1,
            "validation": 1,
        },
    )


def test_materialize_selects_train_validation_and_hashes_files(tmp_path: Path) -> None:
    manifest = build_fake_manifest(tmp_path)
    samples = manifest["samples"]
    by_id = {sample["sample_id"]: sample for sample in samples}

    assert manifest["video_files_found"] == 12
    assert manifest["materialized_counts"]["пока"] == {
        "train": 1,
        "validation": 1,
        "total": 2,
    }
    assert manifest["materialized_counts"]["работать"] == {
        "train": 1,
        "validation": 1,
        "total": 2,
    }
    sample = by_id["slovo_poka_11111111"]
    payload = b"video:11111111-0000-0000-0000-000000000000"
    assert sample["byte_size"] == len(payload)
    assert sample["sha256"] == hashlib.sha256(payload).hexdigest()
    assert sample["source"] == "slovo"
    assert sample["source_label"] == "Пока"
    assert sample["license"] == "CC BY-SA 4.0"
    assert sample["excluded_from_live_smoke"] is False
    assert manifest["class_status"]["пока"]["status"] == "ok"
    assert manifest["class_status"]["работать"]["status"] == "ok"
    assert manifest["class_status"]["_no_event"]["status"] == "shortage"


def test_materialize_excludes_live_smoke_samples(tmp_path: Path) -> None:
    manifest = build_fake_manifest(
        tmp_path,
        excluded_sample_ids=["slovo_poka_8ba230dc"],
    )
    sample_ids = {
        sample["sample_id"]
        for sample in manifest["samples"]
    }

    assert "slovo_poka_8ba230dc" not in sample_ids
    assert "slovo_poka_11111111" in sample_ids
    assert manifest["live_smoke_exclusions"]["excluded_rows"] == [
        {
            "sample_id": "slovo_poka_8ba230dc",
            "label": "пока",
            "split": "train",
            "source_path": str(
                tmp_path
                / "slovo/train/8ba230dc-0000-0000-0000-000000000000.mp4"
            ),
        }
    ]


def test_materialize_reports_shortage_without_fake_samples(tmp_path: Path) -> None:
    manifest = build_fake_manifest(
        tmp_path,
        excluded_sample_ids=["slovo_poka_8ba230dc", "slovo_poka_11111111"],
    )

    assert manifest["materialized_counts"]["пока"] == {
        "train": 0,
        "validation": 1,
        "total": 1,
    }
    assert {
        "label": "пока",
        "split": "train",
        "target": 1,
        "materialized": 0,
        "missing": 1,
    } in manifest["shortages"]
    assert manifest["class_status"]["пока"]["status"] == "missing"


def test_materialize_does_not_remap_labels_manually(tmp_path: Path) -> None:
    manifest = build_fake_manifest(tmp_path)
    sample_ids = {
        sample["sample_id"]
        for sample in manifest["samples"]
    }

    assert "slovo_rabotat_33333333" not in sample_ids
    assert "slovo_rabotat_44444444" in sample_ids
    assert "slovo_privet_bbbbbbb1" not in sample_ids


def test_materialize_uses_explicit_label_aliases_without_silent_remap(tmp_path: Path) -> None:
    slovo_root = write_fake_slovo(tmp_path)
    source_manifest = tmp_path / "source_manifest.json"
    live_manifest = tmp_path / "live_manifest.json"
    write_manifest(source_manifest, ["slovo_privet_f17a6060"])
    write_manifest(live_manifest, [])
    source = MATERIALIZE.discover_slovo_source(slovo_root)
    rows = MATERIALIZE.read_annotations(source)

    manifest = MATERIALIZE.build_materialized_manifest(
        source=source,
        rows=rows,
        source_manifest_path=source_manifest,
        live_manifest_path=live_manifest,
        target_gestures=["привет"],
        target_counts={
            "train": 1,
            "validation": 1,
        },
    )
    samples = {
        sample["sample_id"]: sample
        for sample in manifest["samples"]
    }

    assert "slovo_privet_f17a6060" not in samples
    assert samples["slovo_privet_aaaaaaa1"]["label"] == "привет"
    assert samples["slovo_privet_aaaaaaa1"]["source_label"] == "Привет!"
    assert samples["slovo_no_event_no111111"]["label"] == "_no_event"
    assert samples["slovo_no_event_no111111"]["source_label"] == "no_event"
    assert manifest["label_canonicalization"]["aliases"] == {
        "привет!": "привет",
        "no_event": "_no_event",
    }


def test_strict_mode_returns_non_zero_on_shortage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    slovo_root = write_fake_slovo(tmp_path)
    source_manifest = tmp_path / "source_manifest.json"
    live_manifest = tmp_path / "live_manifest.json"
    output = tmp_path / "materialized.json"
    write_manifest(source_manifest, ["slovo_poka_8ba230dc", "slovo_poka_11111111"])
    write_manifest(live_manifest, [])
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "materialize_demo_gestures_dataset.py",
            "--slovo-root",
            str(slovo_root),
            "--source-manifest",
            str(source_manifest),
            "--live-manifest",
            str(live_manifest),
            "--output",
            str(output),
            "--strict",
        ],
    )

    assert MATERIALIZE.main() == 1
    assert output.is_file()
