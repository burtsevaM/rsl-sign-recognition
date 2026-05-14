# PW-06 - Offline quality validation для `pose_words`

## Scope

Этот документ фиксирует результат PW-06: offline validation текущего active artifact pack для `pose_words` без WebSocket, frontend, live runtime orchestration, training/export и изменения baseline `words`.

Проверялся active pack из `artifacts/runtime/active/pose_words/`:

- manifest: `artifacts/runtime/active/pose_words/manifest.json`;
- classifier: `classifier/model.onnx`;
- labels: `classifier/labels.txt`;
- segmentation artifact: `segmentation/model.onnx`;
- thresholds: `segmentation/thresholds.json`.

ART-03 уже добавил этот pack как `runtime_active`, `readiness_class=live_candidate`, `dataset_kind=synthetic_fixture`. Поэтому PW-06 проверяет именно текущий active pack, но не заявляет production quality.

## Validation data

В clean repo не было готового малого validation set с реальными pose clips для этих labels. Поэтому использован маленький deterministic synthetic/technical validation set, подготовленный runner-ом `scripts/run_pose_words_offline_validation.py` по draft validation context `gesture-recognition-draft/backend/scripts/run_pose_words_validation.py`.

Проверка не использует реальные camera/video samples. Входом classifier являются pre-segmented `pose_words` feature clips `[T, F]`, ресемплированные до `[32, 159]`.

Фактические labels прочитаны из active `labels.txt`:

| class_id | label |
| --- | --- |
| 0 | `_no_event` |
| 1 | `привет` |
| 2 | `пока` |

Минимальный target set жестов/слов:

- `привет`;
- `пока`.

`_no_event` проверен как technical background class, но не считается demo gesture.

## Results

Machine-readable output последнего прогона сохранен в `docs/validation/pose_words-offline-quality-results.json`.

| sample_id | source | expected_label | predicted_label | top1_correct | confidence | notes |
| --- | --- | --- | --- | --- | --- | --- |
| `_no_event_synthetic_00` | `synthetic_fixture_from_draft_validation_context` | `_no_event` | `_no_event` | true | 0.624067 | pre-segmented synthetic clip; segmentation sign=0, phrase=0 |
| `_no_event_synthetic_01` | `synthetic_fixture_from_draft_validation_context` | `_no_event` | `_no_event` | true | 0.623721 | pre-segmented synthetic clip; segmentation sign=0, phrase=0 |
| `_no_event_synthetic_02` | `synthetic_fixture_from_draft_validation_context` | `_no_event` | `_no_event` | true | 0.624421 | pre-segmented synthetic clip; segmentation sign=0, phrase=0 |
| `привет_synthetic_00` | `synthetic_fixture_from_draft_validation_context` | `привет` | `привет` | true | 0.843885 | pre-segmented synthetic clip; segmentation sign=3, phrase=4 |
| `привет_synthetic_01` | `synthetic_fixture_from_draft_validation_context` | `привет` | `привет` | true | 0.843952 | pre-segmented synthetic clip; segmentation sign=3, phrase=4 |
| `привет_synthetic_02` | `synthetic_fixture_from_draft_validation_context` | `привет` | `привет` | true | 0.844213 | pre-segmented synthetic clip; segmentation sign=3, phrase=4 |
| `пока_synthetic_00` | `synthetic_fixture_from_draft_validation_context` | `пока` | `пока` | true | 0.750875 | pre-segmented synthetic clip; segmentation sign=5, phrase=2 |
| `пока_synthetic_01` | `synthetic_fixture_from_draft_validation_context` | `пока` | `пока` | true | 0.750046 | pre-segmented synthetic clip; segmentation sign=5, phrase=2 |
| `пока_synthetic_02` | `synthetic_fixture_from_draft_validation_context` | `пока` | `пока` | true | 0.749247 | pre-segmented synthetic clip; segmentation sign=5, phrase=2 |

Summary по всем checked classes:

| label | support | correct | top-1 accuracy | avg confidence | main confusion / weak cases |
| --- | ---: | ---: | ---: | ---: | --- |
| `_no_event` | 3 | 3 | 1.0 | 0.624070 | no confusion; lower confidence background class |
| `привет` | 3 | 3 | 1.0 | 0.844017 | no confusion on synthetic clips |
| `пока` | 3 | 3 | 1.0 | 0.750056 | no confusion on synthetic clips; weaker than `привет` by confidence |

Target words summary:

| metric | value |
| --- | ---: |
| checked words | 2 |
| samples | 6 |
| correct | 6 |
| top-1 accuracy | 1.0 |
| avg confidence | 0.797036 |
| confusion cases | 0 |

## Demo readiness

На synthetic technical set можно считать подтвержденными для минимального offline demo:

| word | confidence range | status |
| --- | --- | --- |
| `привет` | 0.843885-0.844213 | demo-ready only for synthetic/pre-segmented offline clips |
| `пока` | 0.749247-0.750875 | demo-ready only for synthetic/pre-segmented offline clips |

Слабые места:

- `_no_event` корректен, но confidence около 0.624 и не должен использоваться как доказательство качества gesture recognition.
- `пока` корректен, но заметно слабее `привет` по confidence.
- BIO segmentation на synthetic word clips возвращает несколько sign/phrase segments для `привет` и `пока`, поэтому segmentation остается weak case для будущего live orchestration.

## Confidence threshold

Для synthetic target words runner вычислил candidate threshold `0.74`, потому что минимальная confidence среди корректных target predictions равна `0.749247`.

Этот threshold нельзя считать production/live threshold:

- validation set synthetic и маленький;
- нет реальных negative samples и hard confusions;
- нет camera/video end-to-end прогона;
- segmentation пока показывает пере-сегментацию на synthetic sign clips.

Практический вывод: для offline synthetic demo можно использовать `0.74` как technical candidate, но live threshold должен выбираться отдельной задачей на реальных validation examples.

## How to repeat

Установить optional ONNX dependencies, если `onnxruntime` отсутствует:

```bash
python3 -m pip install '.[pose-words-inference,segmentation]'
```

Запустить validation:

```bash
python3 scripts/run_pose_words_offline_validation.py
```

Ожидаемый результат:

- обновляется `docs/validation/pose_words-offline-quality-results.json`;
- overall `top1_accuracy=1.0`;
- target words `top1_accuracy=1.0`.

## Limitations

- Это synthetic/technical validation, не реальный proof качества на целевом датасете.
- Проверка не подключает `WS /ws/stream`, frontend или live runtime orchestration.
- Runner не делает training/export и не меняет active artifacts.
- Проверка не решает baseline decision по `words`.
- Full `/ready` по-прежнему не становится green только из-за этих результатов: live transport/runtime pipeline остается отдельным незакрытым increment.
