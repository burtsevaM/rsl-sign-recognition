from __future__ import annotations

import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = REPO_ROOT / "data/demo_gestures/manifest.json"
MATERIALIZED_MANIFEST_PATH = REPO_ROOT / "data/demo_gestures/materialized_manifest.json"

EXPECTED_GESTURES = [
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

EXPECTED_LIVE_SMOKE_SAMPLE_IDS = {
    "slovo_privet_f17a6060",
    "slovo_poka_8ba230dc",
    "slovo_da_2b1b2857",
    "slovo_horosho_43791c91",
    "slovo_ploho_27560a7e",
    "slovo_utro_c1766b2e",
    "slovo_ulica_908f133b",
    "slovo_dom_524d6b8f",
    "slovo_voda_90db4617",
    "slovo_rabotat_ffce2323",
}


def load_manifest() -> dict[str, object]:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def load_materialized_manifest() -> dict[str, object]:
    return json.loads(MATERIALIZED_MANIFEST_PATH.read_text(encoding="utf-8"))


def test_demo_gestures_manifest_is_external_source_contract() -> None:
    manifest = load_manifest()

    assert manifest["schema_version"] == 1
    assert manifest["dataset_id"] == "DATA-03-PW-08-demo-gestures-train-val-subset-v1"
    assert manifest["target_pipeline"] == "pose_words"
    assert manifest["self_contained"] is False
    assert manifest["storage_mode"] == "external_source_manifest"
    assert manifest["materialization_status"] == "materialized_with_shortages"
    assert manifest["materialized_manifest"] == "data/demo_gestures/materialized_manifest.json"


def test_final_demo_dictionary_and_counts_are_complete() -> None:
    manifest = load_manifest()
    counts = manifest["target_class_counts"]

    assert manifest["final_demo_dictionary"] == EXPECTED_GESTURES
    assert isinstance(counts, dict)
    for gesture in EXPECTED_GESTURES:
        class_count = counts[gesture]
        assert class_count == {
            "train": 15,
            "validation": 5,
            "total": 20,
        }


def test_each_gesture_has_train_validation_and_metadata() -> None:
    manifest = load_manifest()
    classes = manifest["classes"]
    assert isinstance(classes, list)
    gesture_classes = {
        item["label"]: item
        for item in classes
        if isinstance(item, dict) and item.get("role") == "gesture"
    }

    assert list(gesture_classes) == EXPECTED_GESTURES
    for gesture, item in gesture_classes.items():
        for split_name, expected_count in (("train", 15), ("validation", 5)):
            split = item[split_name]
            assert split["count"] == expected_count
            assert split["source_group_id"]
            assert "selection_rule" in split
        for field in (
            "license",
            "license_url",
            "attribution",
            "modified",
            "modification_notes",
            "upstream_label",
        ):
            assert field in item, gesture
        assert item["license"] == "CC BY-SA 4.0"
        assert item["license_url"] == "https://creativecommons.org/licenses/by-sa/4.0/"
        assert item["attribution"] == "Slovo Russian Sign Language Dataset and Models, hukenovs/slovo"
        assert item["modified"] is False


def test_no_event_class_is_declared_with_limitations() -> None:
    manifest = load_manifest()
    counts = manifest["target_class_counts"]
    classes = manifest["classes"]
    no_event = next(
        item
        for item in classes
        if isinstance(item, dict) and item.get("label") == "_no_event"
    )

    assert counts["_no_event"] == {
        "train": 10,
        "validation": 4,
        "total": 14,
    }
    assert no_event["role"] == "background"
    assert no_event["required_by_runtime"] is True
    assert no_event["modified"] is False
    assert no_event["upstream_label"] == "no_event"
    assert "No dummy" in no_event["modification_notes"]


def test_live_smoke_samples_are_explicitly_excluded_from_train_val() -> None:
    manifest = load_manifest()
    live_smoke_relation = manifest["live_smoke_relation"]

    assert live_smoke_relation["pr_number"] == 77
    assert set(live_smoke_relation["excluded_sample_ids"]) == EXPECTED_LIVE_SMOKE_SAMPLE_IDS
    assert "excluded" in live_smoke_relation["relationship"]

    for item in manifest["classes"]:
        if not isinstance(item, dict):
            continue
        for split_name in ("train", "validation"):
            split = item[split_name]
            assert "exclude" in split["selection_rule"].lower()


def test_source_and_expected_local_paths_are_recorded() -> None:
    manifest = load_manifest()
    source = manifest["source"]
    expected_sources = {
        item["source_id"]: item
        for item in manifest["expected_local_sources"]
        if isinstance(item, dict)
    }

    assert source["origin"] == "hukenovs/slovo"
    assert source["upstream_repository"] == "https://github.com/hukenovs/slovo"
    assert source["license"] == "CC BY-SA 4.0"
    assert source["modified"] is False

    assert set(expected_sources) == {"slovo_trimmed_archive"}
    assert expected_sources["slovo_trimmed_archive"]["expected_env_var"] == "SLOVO_TRIMMED_ARCHIVE"
    assert "mvp1/SuperLuchito--SimpleGesture2Letter-Model-Version-2" in expected_sources["slovo_trimmed_archive"]["default_local_path"]


def test_materialized_counts_are_not_confused_with_targets() -> None:
    manifest = load_manifest()
    counts = manifest["materialized_class_counts"]

    assert counts["привет"] == {
        "train": 14,
        "validation": 5,
        "total": 19,
    }
    assert counts["пока"] == {
        "train": 14,
        "validation": 5,
        "total": 19,
    }
    assert counts["утро"] == {
        "train": 15,
        "validation": 4,
        "total": 19,
    }
    assert counts["_no_event"] == {
        "train": 10,
        "validation": 4,
        "total": 14,
    }


def test_materialized_manifest_has_all_final_classes_with_non_zero_splits() -> None:
    source_manifest = load_manifest()
    materialized = load_materialized_manifest()
    counts = materialized["materialized_counts"]
    statuses = materialized["class_status"]

    assert materialized["target_gestures"] == EXPECTED_GESTURES
    assert "_no_event" in counts
    for label in [*EXPECTED_GESTURES, "_no_event"]:
        assert label in counts
        assert label in statuses
        assert counts[label]["train"] > 0, label
        assert counts[label]["validation"] > 0, label
        assert statuses[label]["status"] in {"ok", "shortage"}
        assert statuses[label]["materialized_train"] == counts[label]["train"]
        assert statuses[label]["materialized_validation"] == counts[label]["validation"]
    assert materialized["issue_closure_ready"] is True
    assert source_manifest["materialization_status"] == "materialized_with_shortages"


def test_materialized_sample_records_are_traceable_and_exclude_live_smoke() -> None:
    materialized = load_materialized_manifest()
    samples = materialized["samples"]
    sample_ids = {
        sample["sample_id"]
        for sample in samples
    }

    assert EXPECTED_LIVE_SMOKE_SAMPLE_IDS.isdisjoint(sample_ids)
    for sample in samples:
        for field in (
            "sample_id",
            "sha256",
            "byte_size",
            "split",
            "label",
            "source",
            "source_label",
            "source_path",
        ):
            assert field in sample, sample
        assert sample["split"] in {"train", "validation"}
        assert isinstance(sample["byte_size"], int)
        assert sample["byte_size"] > 0
        assert isinstance(sample["sha256"], str)
        assert len(sample["sha256"]) == 64
        assert sample["source"] == "slovo"


def test_materialized_manifest_records_explicit_aliases_without_silent_remap() -> None:
    materialized = load_materialized_manifest()
    aliases = materialized["label_canonicalization"]["aliases"]
    samples = materialized["samples"]

    assert aliases == {
        "привет!": "привет",
        "no_event": "_no_event",
    }
    assert any(
        sample["label"] == "привет" and sample["source_label"] == "Привет!"
        for sample in samples
    )
    assert any(
        sample["label"] == "_no_event" and sample["source_label"] == "no_event"
        for sample in samples
    )
    assert all(
        not (sample["label"] == "работать" and sample["source_label"].lower() == "работа")
        for sample in samples
    )
