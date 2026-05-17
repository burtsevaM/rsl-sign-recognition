# QA-03 - E2E smoke минимального live recognition

## Цель проверки

`QA-03` проверяет именно live path:

`backend -> /health -> /ready -> WS /ws/stream -> binary JPEG frames -> recognition.result`

Smoke нужен, чтобы подтвердить минимальное end-to-end распознавание через настоящий backend/WebSocket path, а не через mock fixtures или pre-segmented feature clips.

## Prerequisites

- checkout репозитория с active pack в `artifacts/runtime/active/pose_words/`;
- tracked live sample bundle в `data/live_samples/`;
- Python extras для live runtime и smoke runner:

```bash
python3 -m pip install '.[pose-extraction,pose-words-inference,segmentation,e2e-smoke]'
```

- текущий live прогон подтвержден на Python `3.11` с совместимой `pose-extraction` dependency line;
- backend, поднятый из корня репозитория:

```bash
python3 -m uvicorn rsl_sign_recognition.asgi:app --app-dir src
```

## Выбранные gestures и expected labels

Текущий переносимый bundle содержит один честный live sample:

| sample_id | expected_label | input |
| --- | --- | --- |
| `slovo_privet_f17a6060` | `привет` | `data/live_samples/videos/slovo-privet-f17a6060.mp4` |

Expected labels берутся из `data/live_samples/manifest.json`, а sample path остается repo-relative.

## Как запускать smoke

```bash
python3 scripts/run_live_e2e_smoke.py --base-url http://127.0.0.1:8000
```

Полезные варианты:

```bash
python3 scripts/run_live_e2e_smoke.py --help
python3 scripts/run_live_e2e_smoke.py --sample-id slovo_privet_f17a6060
python3 scripts/run_live_e2e_smoke.py --realtime
```

Runner:

- проверяет `/health` как liveness;
- проверяет `/ready` как live readiness и завершает работу с понятной ошибкой, если backend не ready;
- открывает `WS /ws/stream`;
- декодирует MP4 sample в RGB frames;
- отправляет каждый кадр как binary JPEG packet;
- принимает `recognition.result`;
- проверяет stable contract fields `status`, `word`, `confidence`, `hand_present`, `hold`, `text_state`, `timestamp_ms`;
- определяет committed/final состояние только через `payload.text_state.committed`;
- печатает summary по каждому gesture и возвращает `0` только если все выбранные samples прошли.

Runner не вводит base64 fallback, новый handshake или отдельный final message type.

## Что считается pass/fail

`PASS`:

- `/health = 200`;
- `/ready = 200`;
- backend возвращает `recognition.result` с contract-compatible `1.x`;
- хотя бы один result для sample имеет `payload.text_state.committed = true`;
- committed `payload.word` равен `expected_label`.

`FAIL`:

- backend не поднят или `/ready != 200`;
- WebSocket вернул `error`;
- `recognition.result` нарушил stable contract surface;
- committed result отсутствует;
- committed `word` не совпал с expected label.

## Результаты текущего прогона

Дата прогона: `2026-05-18`.

Команда:

```bash
python3 scripts/run_live_e2e_smoke.py --base-url http://127.0.0.1:8000
```

| sample_id | expected | actual | result | confidence | committed |
| --- | --- | --- | --- | --- | --- |
| `slovo_privet_f17a6060` | `привет` | `привет` | `PASS` | `0.717108` | `true` |

Фактический summary runner-а:

```text
sample_id | expected | actual | pass | confidence | committed | frames
--- | --- | --- | --- | --- | --- | ---
slovo_privet_f17a6060 | привет | привет | PASS | 0.717108 | true | 112
  committed_labels: привет
summary: 1/1 passed
```

Что подтверждено этим прогоном:

- backend поднялся и отдал `/health = 200`;
- `/ready = 200` прошел как live readiness;
- `WS /ws/stream` принял binary JPEG frames из реального MP4 sample;
- backend возвращал contract-valid `recognition.result`;
- committed/final состояние корректно проверялось только через `payload.text_state.committed`.
- committed result для `привет` реально появился и совпал с `expected_label`.

Какие gestures прошли:

- `привет` - `PASS`, `confidence = 0.717108`, `committed = true`.

Какие gestures не прошли:

- failed samples в текущем bundle отсутствуют.

Текущий статус QA-03: `green for minimal live smoke: 1/1 passed`.

## Что было исправлено после первого partial прогона

- live runtime теперь строит `PoseFeatureService` по `norm_flags` active artifact pack-а, чтобы feature composition совпадала с тем, на чем обучены classifier и BIO layer;
- live session умеет завершать уже активный BIO segment на честной boundary-ситуации, когда рука исчезает из кадра, поэтому gesture не остается навсегда в `NONE` только из-за отсутствия trailing `O` frames в конце clip-а.

## Ограничения

- Сейчас bundle содержит только один реальный gesture sample, поэтому QA-03 проверяет минимум `1` gesture, а не полноценный набор из `5`.
- Active artifact pack остается technical/runtime pack на synthetic validation artifacts, а не production-quality model proof.
- Один smoke sample не является benchmark-ом, не измеряет качество на датасете и не заменяет production-grade evaluation.
- Offline результаты `PW-06` полезны как контекст, но не заменяют live e2e confirmation через WebSocket.
