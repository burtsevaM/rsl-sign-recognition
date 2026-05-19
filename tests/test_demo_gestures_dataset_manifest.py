from __future__ import annotations

import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = REPO_ROOT / "data/demo_gestures/manifest.json"

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
    assert no_event["modified"] is True
    assert "Background windows" in no_event["modification_notes"]


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

    assert set(expected_sources) == {
        "slovo_trimmed_archive",
        "slovo_original_or_360p_archive",
    }
    assert expected_sources["slovo_trimmed_archive"]["expected_env_var"] == "SLOVO_TRIMMED_ARCHIVE"
    assert expected_sources["slovo_original_or_360p_archive"]["expected_env_var"] == "SLOVO_ORIGINAL_OR_360P_ARCHIVE"
    assert "mvp1/SuperLuchito--SimpleGesture2Letter-Model-Version-2" in expected_sources["slovo_trimmed_archive"]["default_local_path"]


def test_materialized_counts_are_not_confused_with_targets() -> None:
    manifest = load_manifest()
    counts = manifest["materialized_class_counts"]

    assert counts["привет"] == {
        "train": 0,
        "validation": 0,
        "total": 0,
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
        "train": 0,
        "validation": 0,
        "total": 0,
    }
