# ART-03 - Active artifact pack для `pose_words`

Этот документ фиксирует минимальный active artifact pack, подготовленный для clean repo в рамках ART-03.

Pack предназначен для runtime-facing проверки `ActiveArtifactLoader` / `ActiveArtifactGate` и не доказывает production-quality распознавание. Он закрывает только наличие, структуру и manifest-compatible layout для classifier + BIO segmentation artifacts.

## Layout

```text
artifacts/
  runtime/
    active/
      pose_words/
        manifest.json
        classifier/
          model.onnx
          labels.txt
          runtime_config.json
        segmentation/
          model.onnx
          thresholds.json
          runtime_config.json
```

## Required и optional files

Required files:

- `classifier/model.onnx`
- `classifier/labels.txt`
- `segmentation/model.onnx`
- `segmentation/thresholds.json`

Optional companion files:

- `classifier/runtime_config.json`
- `segmentation/runtime_config.json`

В текущем ART-03 pack optional config-файлы добавлены в Git, но loader не требует их физического наличия для `active_artifacts` readiness gate.

## Source mapping из draft repo

Источник: `https://github.com/burtsevaM/gesture-recognition-draft`, ветка `burtseva_ma_mvp_words`, active profile `validation_active`.

| Draft path | Clean path |
| --- | --- |
| `backend/artifacts/runtime/active/pose_words/pose_word_model.onnx` | `artifacts/runtime/active/pose_words/classifier/model.onnx` |
| `backend/artifacts/runtime/active/pose_words/pose_word_labels.txt` | `artifacts/runtime/active/pose_words/classifier/labels.txt` |
| `backend/artifacts/runtime/active/pose_words/pose_word_config.json` | `artifacts/runtime/active/pose_words/classifier/runtime_config.json` |
| `backend/artifacts/runtime/active/pose_words/bio_segmenter.onnx` | `artifacts/runtime/active/pose_words/segmentation/model.onnx` |
| `backend/artifacts/runtime/active/pose_words/bio_thresholds.json` | `artifacts/runtime/active/pose_words/segmentation/thresholds.json` |
| `backend/artifacts/runtime/active/pose_words/bio_config.json` | `artifacts/runtime/active/pose_words/segmentation/runtime_config.json` |
| `backend/artifacts/runtime/active/pose_words/pose_words_active_manifest.json` | source context for `manifest.json`, not copied as runtime manifest |

Draft config files contained validation-local path fields. Clean `runtime_config.json` files intentionally keep only runtime-facing metadata and shape/model parameters, without draft load roots, absolute paths, `backend/config.yaml`, bootstrap fallback, validation output paths, or machine-local paths.

## Labels / class ids

Classifier labels are taken from the draft active labels file without inventing new classes:

| id | label |
| --- | --- |
| `0` | `_no_event` |
| `1` | `привет` |
| `2` | `пока` |

The exact runtime label order is stored in `artifacts/runtime/active/pose_words/classifier/labels.txt`.

## Manifest safety rules

`manifest.json` uses only paths relative to its own directory:

- `classifier/model.onnx`
- `classifier/labels.txt`
- `classifier/runtime_config.json`
- `segmentation/model.onnx`
- `segmentation/thresholds.json`
- `segmentation/runtime_config.json`

It does not contain absolute artifact paths, empty `relative_path` values, `..` traversal, machine-local paths, draft repo load roots, `backend/config.yaml`, validation fallback roots, or bootstrap fallback roots.

## Проверка readiness gate

Проверить JSON manifest:

```bash
python -m json.tool artifacts/runtime/active/pose_words/manifest.json
```

Проверить targeted artifact loader tests:

```bash
pytest tests/test_runtime_artifacts.py
```

Локально проверить, что `active_artifacts` gate закрывается:

```bash
python - <<'PY'
from pathlib import Path
from rsl_sign_recognition.runtime.artifacts import ActiveArtifactGate, ActiveArtifactLoader

manifest = Path("artifacts/runtime/active/pose_words/manifest.json")
resolved = ActiveArtifactLoader(manifest).load()
status = ActiveArtifactGate(manifest).evaluate()

print("profile_id=", resolved.profile_id)
print("active_artifacts=", status.passed)
print("reason_codes=", list(status.reason_codes))
PY
```

Ожидаемо:

- `profile_id= runtime_active`
- `active_artifacts= True`
- `reason_codes= []`

Важно: даже при `active_artifacts=true` общий `/ready` в clean repo может оставаться `HTTP 503`, пока `transport_surface=false` и live `WS /ws/stream` pipeline еще не собран.

## Ограничения

- Pack основан на `synthetic_fixture` technical validation artifacts.
- Это runtime/technical pack, а не production-quality proof.
- Pack не добавляет training/export scripts, dataset, validation outputs, backups, bootstrap workflow или draft-only operational logic.
- Pack не подключает live inference к frontend или WebSocket runtime.
- `words` baseline не удаляется и не деактивируется этой задачей.
