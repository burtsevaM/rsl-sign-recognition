# Active artifact pack для `pose_words`

Этот документ фиксирует runtime layout текущего active artifact pack для `pose_words`.

Исторически layout был добавлен как ART-03 technical pack. В рамках MODEL-01 / PW-07 pack заменен на lightweight demo classifier для 10 gestures из #78 плюс `_no_event`. Он доказывает runtime loading и минимальный live smoke для demo dictionary, но не является production-quality моделью.

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

## Source

Текущий pack генерируется локально из Slovo subset:

- config: `configs/demo_gestures_classifier.json`;
- source manifest: `data/demo_gestures/manifest.json`;
- materialized manifest: `data/demo_gestures/materialized_manifest.json`;
- training script: `scripts/train_demo_gestures_classifier.py`;
- report: `docs/model/model-01-demo-gestures-classifier.md`;
- machine-readable metrics: `docs/model/model-01-demo-gestures-classifier-results.json`.

The classifier model is a standardized linear ridge ONNX model over MediaPipe `pose_words` feature clips. The segmentation model is a deterministic isolated-gesture ONNX helper for the current one-gesture smoke clips.

## Labels / class ids

Classifier labels are the final #79 / PR #83 demo dictionary plus `_no_event`:

| id | label |
| --- | --- |
| `0` | `_no_event` |
| `1` | `привет` |
| `2` | `пока` |
| `3` | `да` |
| `4` | `хорошо` |
| `5` | `плохо` |
| `6` | `утро` |
| `7` | `улица` |
| `8` | `дом` |
| `9` | `вода` |
| `10` | `работать` |

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

Проверить training/export:

```bash
python3 scripts/train_demo_gestures_classifier.py --config configs/demo_gestures_classifier.json --slovo-root data/slovo
```

Проверить full live smoke для PR #77 bundle:

```bash
python3 scripts/run_live_e2e_smoke.py --base-url http://127.0.0.1:8010 --sample-manifest .cache/live_samples_pr77/manifest.json --max-samples 10 --min-passed 8 --http-timeout-seconds 60
```

Последний зафиксированный результат: `9/10 passed`, см. `docs/qa/model-01-live-smoke.md`.

## Ограничения

- Pack обучен на малом Slovo subset и не является production-quality proof.
- Validation accuracy остается слабой для части классов; `утро` не проходит текущий live smoke bundle.
- Follow-up на улучшение demo classifier до `10/10`: #85.
- Segmentation artifact рассчитан на isolated one-gesture smoke clips, а не на полноценное boundary detection в длинном live потоке.
- Pack не добавляет bootstrap workflow, backups или draft-only operational logic.
- `words` baseline не удаляется и не деактивируется этой задачей.
