# INT-02 - Integration handoff для web team по runtime surface

## 1. Назначение

Этот документ фиксирует первый integration increment для web team вокруг уже существующей runtime surface clean repo:

- `GET /health`;
- `GET /ready`;
- `WS /ws/stream`;
- `WebSocket contract v1`;
- readiness gates;
- mock/live boundary;
- `runtime_unavailable` behavior.

Цель increment - дать web team честную integration-ready поверхность для подключения UI, contract parsing, liveness/readiness handling и controlled error states. Этот handoff не объявляет clean repo production-ready runtime и не доказывает live распознавание жестов.

В scope INT-02 входит документация текущих ожиданий и проверок. В scope INT-02 не входят production rollout, новый protocol surface, full e2e recognition, реальные ONNX artifacts, live `pose_words` inference wiring или замена отсутствующего live pipeline mock-only успехом.

Source of truth:

- [WebSocket contract v1](../contracts/websocket-contract-v1.md);
- [runtime skeleton и probe semantics](../runtime-skeleton.md);
- [artifact policy и active artifact readiness](../artifact-policy.md);
- [QA-01/QA-02 smoke test strategy](../qa-01-smoke-test-strategy.md);
- [INT-01 handoff notes](../int-01-web-team-handoff-notes.md).

Документ `docs/validation-gates.md` в текущей базе отсутствует; readiness gate semantics сейчас зафиксированы в `docs/runtime-skeleton.md`, `docs/artifact-policy.md`, runtime-коде и QA-02 tests.

## 2. Что web team может интегрировать сейчас

Сейчас можно интегрировать:

- liveness check через `GET /health`;
- readiness check через `GET /ready`;
- WebSocket подключение к `WS /ws/stream`;
- JSON envelope `contract v1` с `type`, `contract_version`, `payload`;
- server messages `control.ack` и `error`;
- contract-level обработку `recognition.result` по fixtures и documented stable surface;
- UI-состояния для `not_ready`, recoverable errors и non-recoverable `runtime_unavailable`.

Сейчас нельзя считать готовым:

- live распознавание жестов;
- full `frame -> pose extraction -> segmentation -> classifier -> recognition.result` path;
- наличие реальных active ONNX artifacts;
- production readiness или latency/stability guarantees;
- обязательный `HTTP 200` на `/ready`;
- наличие live `recognition.result` после отправки JPEG frame.

Текущий `WS /ws/stream` является working transport surface: `control.clear_text` возвращает `control.ack`, invalid JSON/control/frame cases возвращают documented `error`, а валидный JPEG frame без подключенного live pipeline возвращает `runtime_unavailable`.

## 3. `/health`: liveness expectations

`GET /health` - это liveness endpoint. Он отвечает на вопрос: жив ли backend process и отвечает ли minimal runtime shell как HTTP service.

Успешный `/health` означает только:

- backend process поднят;
- FastAPI runtime shell отвечает;
- можно прочитать текущий `runtime_mode`.

Успешный `/health` не доказывает:

- наличие active artifacts;
- готовность `/ready`;
- доступность live inference;
- что `WS /ws/stream` вернет `recognition.result`;
- production readiness.

Минимальный успешный shape:

```json
{
  "status": "ok",
  "probe": "liveness",
  "runtime_mode": "live"
}
```

Минимальный manual check для web team:

```bash
curl -i http://localhost:8000/health
```

Ожидание: `HTTP 200` и `probe = "liveness"`. Если `/health = 200`, frontend может считать backend process живым, но обязан отдельно проверять `/ready` и WebSocket error states.

## 4. `/ready`: readiness expectations

`GET /ready` - это readiness endpoint для `live_runtime_path`. Он отвечает на вопрос: готов ли текущий runtime shell обслуживать live path в рамках clean repo boundaries.

Текущие readiness gates:

| Gate | Что означает | Текущее важное ограничение |
| --- | --- | --- |
| `runtime_shell` | Сервис запущен в live mode и runtime shell не находится в заведомо unavailable state. | В `mock` mode gate должен быть `false` для live readiness. |
| `active_artifacts` | Active manifest и required files для `pose_words` live path доступны по clean policy. | Валидный manifest закрывает только этот gate и не запускает ONNX sessions. |
| `transport_surface` | `WS /ws/stream` связан с live runtime pipeline, а не только с transport/error boundary. | Сейчас gate честно остается `false`: `live_runtime_pipeline_unavailable`. |

Возможные HTTP статусы сейчас:

- `HTTP 200` с `status = "ready"` возможен только если все gates `true`;
- `HTTP 503` с `status = "not_ready"` является ожидаемым честным состоянием, если хотя бы один gate не закрыт.

Минимальный not-ready shape:

```json
{
  "status": "not_ready",
  "probe": "readiness",
  "runtime_mode": "live",
  "ready_for": "live_runtime_path",
  "gates": {
    "runtime_shell": true,
    "active_artifacts": false,
    "transport_surface": false
  },
  "reason_codes": [
    "active_manifest_missing",
    "live_runtime_pipeline_unavailable"
  ]
}
```

Какие поля должна читать web team:

- `status` - `ready` или `not_ready`;
- `ready_for` - сейчас ожидается `live_runtime_path`;
- `runtime_mode` - `live` или `mock`;
- `gates.runtime_shell`;
- `gates.active_artifacts`;
- `gates.transport_surface`;
- `reason_codes`, если поле присутствует.

Как frontend должен показывать not-ready:

- не падать и не считать это ошибкой интеграции web team;
- показывать controlled state: backend online, live recognition not ready;
- не запускать сценарий, который требует production live recognition;
- позволять retry/reconnect только как пользовательское действие, а не бесконечный скрытый loop;
- логировать `reason_codes` для диагностики.

Важно: искусственно делать `/ready = 200` нельзя. Отсутствие live pipeline или active artifacts должно оставаться видимым через `HTTP 503`, gates и reason codes.

Для будущей RT-07 интеграции `/ready` должен оставаться pre-session truth. Если active manifest отсутствует, manifest невалиден, required artifact file отсутствует, runtime config невалиден, model loading падает или inference backend недоступен, web team должна видеть controlled `not_ready` / reason codes, а не successful live recognition. `contract v1` для WebSocket от этого не меняется.

## 5. `WS /ws/stream`: contract v1 expectations

Web team открывает WebSocket session по пути:

```text
WS /ws/stream
```

При локальном запуске это обычно:

```text
ws://localhost:8000/ws/stream
```

Для `contract v1` само подключение к documented endpoint означает работу по линии `1.x`. JSON messages всегда используют envelope:

```json
{
  "type": "control.clear_text",
  "contract_version": "1.0",
  "payload": {}
}
```

Client messages в v1:

- binary JPEG frame packet без JSON envelope;
- JSON `control.clear_text` с `contract_version = "1.0"` и `payload = {}`.

Server messages в v1:

- `recognition.result`;
- `control.ack`;
- `error`.

Текущая backend surface гарантирует contract-shaped responses для control/error paths. Она не гарантирует live `recognition.result` на JPEG frame, потому что live pipeline пока не подключен.

### `recognition.result`

`recognition.result` - stable contract message для sign-to-text stream. В текущем increment web team должна поддержать его parsing по contract/fixtures, но не ожидать, что live backend уже начнет присылать такие сообщения после кадров.

Stable поля:

- `payload.status`;
- `payload.word`;
- `payload.confidence`;
- `payload.hand_present`;
- `payload.hold`;
- `payload.text_state.value`;
- `payload.text_state.committed`;
- `payload.timestamp_ms`.

Partial/final semantics:

- `payload.text_state.committed = false` - live/partial state;
- `payload.text_state.committed = true` - committed token update.

Не нужно добавлять или ожидать `partial.result`, `final.result`, `session.start`, `session.stop` или JSON-wrapper для frame input. Эти message types не входят в `contract v1` и покрыты negative checks как unsupported.

### `control.ack`

После `control.clear_text` backend возвращает:

```json
{
  "type": "control.ack",
  "contract_version": "1.0",
  "payload": {
    "action": "clear_text",
    "accepted": true
  }
}
```

Frontend может использовать это как подтверждение, что сброс transcript/state принят для текущей session. Это не означает, что live inference готов.

### `error`

`error` содержит:

- `payload.code`;
- `payload.message`;
- `payload.recoverable`;
- optional `payload.details`.

Frontend должен корректно обрабатывать:

| Code | Recoverable | Что делать в UI |
| --- | --- | --- |
| `invalid_json` | `true` | Показать мягкую ошибку, исправить payload/client action, session можно продолжать. |
| `unsupported_message_type` | `true` | Не отправлять undocumented message type, session можно продолжать. |
| `unsupported_control_action` | `true` | Использовать только `control.clear_text`, session можно продолжать. |
| `frame_decode_failed` | `true` | Проверить JPEG encoding/current frame, session можно продолжать. |
| `unsupported_contract_version` | `false` | Остановить parsing как incompatible contract, предложить обновление/переподключение после исправления клиента. |
| `runtime_unavailable` | `false` | Показать controlled unavailable state, не считать это ошибкой web team, не ожидать live recognition в этой session. |
| `internal_error` | `false` | Показать controlled failure state и предложить retry later. |

### `runtime_unavailable`

Текущий валидный JPEG frame на `WS /ws/stream` без live pipeline возвращает:

```json
{
  "type": "error",
  "contract_version": "1.0",
  "payload": {
    "code": "runtime_unavailable",
    "message": "Runtime is unavailable for the current session.",
    "recoverable": false,
    "details": {
      "reason": "live_inference_pipeline_unavailable"
    }
  }
}
```

Это честная граница отсутствующего live runtime pipeline. Это не failure web-интеграции и не сигнал, что нужно изобретать mock-only success в live path.

Web team должна трактовать `runtime_unavailable` как controlled unavailable state:

- не показывать его как распознанное слово;
- не считать его `recognition.result`;
- не подставлять mock result вместо live result;
- не считать `empty_buffer` / `insufficient_buffer` тем же состоянием, если будущий live transport сможет вернуть controlled no-result до накопления достаточного input.

## 6. Mock/live boundary

### Mock / current limited behavior

Сейчас mock/current limited contour подходит для:

- automated smoke checks;
- contract-level checks;
- проверки message shape;
- проверки `recognition.result` по documented fixtures;
- проверки `control.clear_text` / `control.ack`;
- negative checks для `invalid_json`, `unsupported_contract_version`, `unsupported_control_action`, `frame_decode_failed`;
- проверки readiness semantics;
- проверки `runtime_unavailable` как честной границы отсутствующего live pipeline.

Mock/current limited behavior не закрывает:

- model quality;
- live pose extraction;
- segmentation correctness;
- classifier inference;
- frame-to-result correlation;
- production readiness.

Successful mock smoke доказывает только parsing, UI state handling и совместимость с documented fixtures. Он не доказывает, что active artifacts, runtime config, model loading, inference backend или live recognition доступны.

### Live behavior

Будущий live behavior потребует отдельных runtime/artifact задач:

- реальных active artifacts в `artifacts/runtime/active/pose_words/`;
- live `pose_words` path;
- обработки `frame -> pose extraction -> segmentation -> classifier -> recognition.result`;
- связки `PW-05`, `PW-04`, `PW-03` и `ART-02` через runtime orchestration;
- полноценной проверки live recognition с web team.

Когда live path появится, `/ready` должен стать `HTTP 200` только при закрытых gates, а `WS /ws/stream` сможет возвращать live `recognition.result`. До этого безопасное UI-ожидание такое: backend может быть online, но live recognition unavailable/not ready.

## 7. Verification checklist

### Backend team: automated smoke

- [ ] Запустить QA-02 focused checks:

```bash
pytest -q tests/test_websocket_contract_v1.py tests/test_runtime_smoke_checks.py
```

- [ ] Запустить общий test suite:

```bash
pytest -q
```

- [ ] Проверить `/health` как liveness: `HTTP 200`, `status = "ok"`, `probe = "liveness"`, `runtime_mode`.
- [ ] Проверить `/ready` как readiness: `HTTP 503` допустим и ожидаем при незакрытых gates.
- [ ] Проверить minimal `WS /ws/stream` session: `control.clear_text` возвращает `control.ack`.
- [ ] Проверить error path: valid JPEG без live pipeline возвращает `runtime_unavailable`.
- [ ] Проверить negative paths: `invalid_json`, `unsupported_contract_version`, `unsupported_control_action`, `frame_decode_failed`.
- [ ] Убедиться, что tests не вводят `partial.result`, `final.result`, `session.start`, `session.stop` или JSON frame wrapper.

### Web team: manual checks

- [ ] Поднять backend локально:

```bash
python3 -m uvicorn rsl_sign_recognition.asgi:app --app-dir src
```

- [ ] Открыть `GET /health` и убедиться, что process liveness отображается как backend online.
- [ ] Открыть `GET /ready` и убедиться, что `not_ready` / `HTTP 503` отображается как controlled live-readiness state, а не как crash UI.
- [ ] Подключиться к `WS /ws/stream`.
- [ ] Отправить `control.clear_text` по `contract v1` и обработать `control.ack`.
- [ ] Отправить минимальный JPEG binary frame и обработать `runtime_unavailable` как non-recoverable session-level state.
- [ ] Проверить, что frontend корректно показывает not-ready/runtime-unavailable state.
- [ ] Проверить, что frontend не ожидает production live recognition на этом этапе.
- [ ] Проверить, что frontend не зависит от optional debug/runtime blocks и игнорирует неизвестные optional поля в совместимой линии `1.x`.

## 8. Ограничения и риски

Ограничения, которые намеренно сохраняются после INT-02:

- clean repo не содержит full live recognition pipeline;
- `pose_words` inference wrapper, segmentation layer, pose feature layer и active artifact loader существуют как изолированные boundaries, но не связаны в live `WS /ws/stream`;
- реальные active ONNX artifacts не добавляются;
- `/ready = 503` может оставаться нормальным состоянием текущей базы;
- `runtime_unavailable` остается ожидаемым signal отсутствующего live pipeline;
- contract-level `recognition.result` поддерживается как documented surface, но live backend сейчас может не отправлять его;
- production rollout, hardening и full e2e validation остаются future scope.

Главное правило для web team: уже можно подключать UI к liveness/readiness/WS boundary и error handling, но нельзя считать это готовым распознаванием жестов.
