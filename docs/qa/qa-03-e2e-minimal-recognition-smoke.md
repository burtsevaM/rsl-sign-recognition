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
| `slovo_privet_f17a6060` | `привет` | `-` | `FAIL` | `-` | `false` |

Фактический summary runner-а:

```text
sample_id | expected | actual | pass | confidence | committed | frames
--- | --- | --- | --- | --- | --- | ---
slovo_privet_f17a6060 | привет | - | FAIL | - | false | 112
summary: 0/1 passed
```

Что подтверждено этим прогоном:

- backend поднялся и отдал `/health = 200`;
- `/ready = 200` прошел как live readiness;
- `WS /ws/stream` принял binary JPEG frames из реального MP4 sample;
- backend возвращал contract-valid `recognition.result`;
- committed/final состояние корректно проверялось только через `payload.text_state.committed`.

Что не подтвердилось:

- текущий active runtime не дал committed label для sample `привет`;
- ни один gesture пока не подтвержден как green live e2e smoke;
- полное acceptance condition `минимум 1-5 жестов дают корректный результат` на этом активном pack-е пока не выполнено.

Текущий статус QA-03: `partial / blocked by live recognition quality on the current active pack`.

## Ограничения

- Сейчас bundle содержит только один реальный gesture sample, поэтому QA-03 проверяет минимум `1` gesture, а не полноценный набор из `5`.
- Active artifact pack остается technical/runtime pack на synthetic validation artifacts, а не production-quality model proof.
- Текущий tracked sample `привет` не дал committed live result на active pack-е в прогоне от `2026-05-18`.
- Один smoke sample не является benchmark-ом, не измеряет качество на датасете и не заменяет production-grade evaluation.
- Offline результаты `PW-06` полезны как контекст, но не заменяют live e2e confirmation через WebSocket.
