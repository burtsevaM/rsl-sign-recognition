# QA-01 - Smoke Test Strategy для clean runtime repo

## 1. Назначение документа

Этот документ закрывает docs/policy часть issue `#24 QA-01`.

Его задача:

- честно зафиксировать **минимальную smoke test strategy** для clean repo `rsl-sign-recognition`;
- заранее разделить **automated contract checks**, **automated mock-based checks**, **minimal backend smoke** и **manual checks**;
- согласовать минимальный smoke contour с уже зафиксированными `CTR-01`, `CTR-02`, `RT-02` и `ART-01`;
- не создавать ложного впечатления, что clean repo уже содержит production-grade test contour или migrated runtime implementation.

Важно:

- это **strategy document**, а не реализация тестов;
- документ **не** добавляет runtime code, test files, CI automation, mock server или artifact loader;
- документ описывает, **что именно должно проверяться**, когда в clean repo появится соответствующая runtime surface;
- до runtime-level migration и появления active artifacts часть этой стратегии остается только policy-границей и manual expectation.

## 2. Scope и честная граница стратегии

В scope QA-01 входят только минимальные правила для smoke-контура:

- какие contract-level проверки считаются обязательными для `WebSocket contract v1`;
- какие сценарии могут и должны проверяться через `mock path`;
- какой минимальный backend smoke нужен для `/health`, `/ready` и `WS /ws/stream`;
- какие проверки пока нельзя честно объявлять fully automated;
- как smoke strategy соотносится с active artifact policy и readiness semantics.

В QA-01 **не входят**:

- реализация test suite;
- перенос runtime implementation;
- полная CI automation;
- hardening runtime behavior;
- baseline comparison для `words`;
- изменение `contract v1`, mock protocol mode, readiness semantics или artifact policy.

## 3. Что считается automated уже на уровне стратегии

QA-01 фиксирует не готовый набор test jobs, а **минимальный целевой automated contour**, который должен появляться поэтапно и только там, где у clean repo действительно есть соответствующая surface.

Это означает:

- `automated contract checks` могут опираться на документированный contract и fixtures без live runtime;
- `automated mock-based checks` могут работать без active artifacts и без live backend;
- `minimal backend smoke` можно честно автоматизировать только после появления runtime shell, probe endpoints и transport surface;
- успешный `mock` run **не** считается доказательством live readiness;
- отсутствие live runtime implementation и active artifacts сейчас **не является багом стратегии**, а является частью честного состояния clean repo.

## 4. Automated contract checks

`Automated contract checks` должны покрывать **только stable contract surface v1**, не притворяясь runtime-hardening suite.

### 4.1. Envelope и versioning

Обязательные automated checks:

- каждый JSON message использует versioned envelope с обязательными полями `type`, `contract_version`, `payload`;
- `payload` не равен `null`;
- `contract_version` обязателен для всех JSON-сообщений `client -> server` и `server -> client`;
- binary JPEG input не использует JSON envelope и не обязан содержать `contract_version`;
- при совместимом `major = 1` клиентская сторона должна использовать known required fields и игнорировать unknown optional fields;
- `1.x` трактуется как совместимая minor-линейка без breaking semantics;
- несовместимый `major` должен приводить к controlled incompatibility path, а не к "best effort" парсингу;
- неизвестные envelope/payload fields в рамках совместимого `major` не должны ломать consumer logic.

### 4.2. Message types и обязательные semantics

Обязательные automated checks:

- в v1 допустимы только `control.clear_text` для `client -> server` и `recognition.result`, `control.ack`, `error` для `server -> client`;
- `control.clear_text` использует `payload = {}` и не переносит business-data;
- unsupported control action под тем же envelope должен приводить к `error`, а не к silent ignore;
- успешная обработка `control.clear_text` должна подтверждаться `control.ack`;
- `control.ack` должен содержать `payload.action = "clear_text"` и `payload.accepted = true`;
- `recognition.result` должен оставаться единым output stream без искусственного разделения на `partial.result` / `final.result`;
- committed/final update должен определяться через `payload.text_state.committed`, а не через отдельный message type;
- `error` должен использовать обязательные поля `code`, `message`, `recoverable`, а `details` должен оставаться optional.

### 4.3. Stable payload surface и optional blocks

Обязательные automated checks:

- `recognition.result` проверяется по required stable fields: `status`, `word`, `confidence`, `hand_present`, `hold`, `text_state`, `timestamp_ms`;
- `hold` должен содержать `elapsed_ms`, `remaining_ms`, `target_ms`, `progress`, `unit`;
- `text_state` должен содержать `value` и `committed`;
- UI- и integration-layer не должны зависеть от `topk`, `skeleton`, `segments`, `perf`, `bio`, `debug`, `segment_event`, `state_detail`, `vlm`, `top1`, `mode`, `letter`, `score`, `bbox_norm`;
- отсутствие optional debug/runtime blocks не считается contract failure;
- появление unknown optional fields в `1.x` не считается contract failure;
- `payload.error` внутри `recognition.result` допустим только как recoverable frame-local notice и не заменяет session-level `error`.

### 4.4. Error semantics

Минимальный automated contract contour должен явно проверять:

- `unsupported_contract_version` для incompatible major version;
- `invalid_json` для некорректного JSON control packet;
- `unsupported_message_type` для неизвестного JSON `type`;
- `unsupported_control_action` для неподдержанного control action;
- `frame_decode_failed` для transport-level проблем с текущим binary JPEG frame;
- `runtime_unavailable` как session-level non-recoverable error внутри live path;
- `internal_error` как non-recoverable server-side failure.

### 4.5. Transport-level input

Хотя binary JPEG input относится к transport-level surface, минимальная contract strategy должна фиксировать и проверять следующее:

- единственный обязательный input path v1 для frame stream - WebSocket binary JPEG frame;
- JSON wrapper для frame input не является частью v1;
- contract-level checks не должны вводить fake base64 fallback или новый JSON handshake;
- live transport smoke позже должен подтвердить, что `WS /ws/stream` принимает именно binary JPEG input как канонический путь.

## 5. Automated mock-based checks

`Automated mock-based checks` нужны для тех сценариев, которые можно проверить без live runtime, active artifacts и live readiness.

### 5.1. Что разрешено проверять через mock mode

Через `mock path` можно и нужно проверять:

- разбор versioned envelope `contract v1`;
- required stable fields в `recognition.result`;
- различение `HOLD` и `COMMIT` через `payload.status` и `payload.text_state.committed`;
- control path для `control.clear_text` / `control.ack`;
- session-level `error` path на fixture `runtime_unavailable`;
- отсутствие зависимости UI от optional debug/runtime blocks;
- tolerance к unknown optional fields при совместимом `major`.

### 5.2. Канонический mock boundary

Для QA-01 фиксируется та же граница, что и в `CTR-02`:

- `mock path` включается только на внешней integration/config boundary;
- `mock path` не добавляет поля вроде `mock: true`, `session_id`, `request_id`, `trace_id` в payload;
- `mock path` не подменяет live runtime behavior;
- `mock path` и `live path` не должны смешиваться в одной и той же readiness semantics;
- успешный mock-based smoke не должен переводить `/ready` для `live_runtime_path` в true.

### 5.3. Минимальные mock-compatible scenarios

Минимальный набор automated mock-based checks должен опираться на уже зафиксированные fixtures:

- `docs/contracts/fixtures/mock-recognition-result-hold.json` - проверка partial/live state без commit;
- `docs/contracts/fixtures/mock-recognition-result-commit.json` - проверка committed update через `text_state.committed = true`;
- `docs/contracts/fixtures/mock-control-ack-clear-text.json` - проверка `control.ack` после `clear_text`;
- `docs/contracts/fixtures/mock-session-error-runtime-unavailable.json` - проверка session-level non-recoverable `error`.

Сценарии, которые остаются валидными без live runtime:

- contract parsing и field-level validation;
- UI/integration parsing по stable surface;
- control-flow на уровне documented messages;
- controlled error handling;
- smoke-checks, которым не нужны live artifacts и real runtime shell.

Сценарии, которые mock path **не** закрывает:

- live readiness;
- наличие active artifacts;
- реальную доступность `WS /ws/stream` как live transport endpoint;
- session behavior поверх реально поднятого runtime shell;
- доказательство, что service действительно готов обслуживать live traffic.

## 6. Minimal backend smoke

`Minimal backend smoke` начинается только там, где у clean repo действительно есть backend surface. До появления runtime shell этот раздел остается целевым обязательным contour, а не описанием уже существующих тестов.

### 6.1. `/health` как liveness smoke

Минимальный smoke для `/health` должен проверять:

- endpoint отвечает как service-level liveness probe;
- успешный ответ имеет `HTTP 200`;
- response shape содержит минимум `status = "ok"`, `probe = "liveness"`, `runtime_mode`;
- `/health` отражает факт, что процесс жив и отвечает как runtime shell service;
- `/health` не объявляет runtime ready только потому, что процесс поднят;
- missing active manifest или missing required files не должны автоматически валить `/health`, если процесс жив.

### 6.2. `/ready` как readiness smoke

Минимальный smoke для `/ready` должен проверять:

- `/ready` не равен `/health` по смыслу;
- readiness трактуется только как readiness для `live_runtime_path`;
- при закрытых `runtime_shell`, `active_artifacts`, `transport_surface` probe возвращает `HTTP 200`;
- при незакрытом хотя бы одном gate probe возвращает `HTTP 503`;
- response shape содержит `probe = "readiness"`, `runtime_mode`, `ready_for = "live_runtime_path"`, `gates`;
- в `mock` mode `/ready` не должен притворяться live-ready только потому, что доступны mock fixtures;
- отсутствие active manifest или required active files должно валить `/ready`;
- наличие только `validation` или `bootstrap` profile не должно переводить `/ready` в ready.

### 6.3. `WS /ws/stream` как minimal transport surface smoke

Минимальный smoke для `WS /ws/stream` должен подтверждать только transport-level доступность live surface, а не качество распознавания.

Обязательный минимальный smoke contour:

- documentированный endpoint `WS /ws/stream` поднят как runtime-facing transport surface;
- live path принимает binary JPEG frame как канонический transport-level input;
- control message `control.clear_text` можно отправить как JSON envelope по тому же контракту;
- transport surface возвращает только contract-shaped server messages или contract-shaped errors;
- smoke различает `mock path` и `live path`: mock fixtures не считаются доказательством доступности live WebSocket surface;
- проверка не обещает strict frame-to-result correlation, model quality, latency hardening или production stability.

### 6.4. Что именно должен различать backend smoke

Backend smoke обязан явно разводить:

- `process alive` и `runtime ready`;
- `mock available` и `live runtime ready`;
- `transport surface exists` и `runtime behavior hardened`;
- `session-level runtime_unavailable` и `pre-session readiness failure`.

Без этого smoke contour будет вводить новый смысл readiness и противоречить `RT-02`.

## 7. Manual checks

Даже после появления минимальной automation часть smoke strategy должна оставаться manual, пока clean repo не получит реальный runtime shell, active artifacts и runtime-level implementation.

### 7.1. Manual checks, связанные с artifact policy

Явно manual остаются проверки, завязанные на фактическую availability artifacts:

- отсутствие `artifacts/runtime/active/pose_words/manifest.json`;
- наличие manifest без одного или нескольких `required: true` files;
- частично собранный active set, где classifier files есть, а segmentation files нет;
- наличие только `validation` profile;
- наличие только `bootstrap` profile;
- ситуация, когда non-active profile физически полон, но по policy не должен закрывать live readiness;
- отсутствие optional `required: false` companion metadata, которое не должно ломать readiness само по себе.

Эти проверки можно формализовать в future test plan, но до появления реального artifact reader и materialized artifact set они остаются manual/policy validation, а не честно закрытой automation.

### 7.2. Manual checks на readiness boundary

Явно manual остаются:

- подтверждение, что `/ready = 503` действительно вызван отсутствием active manifest, а не случайной mock/live wiring ошибкой;
- подтверждение, что `/health = 200` сохраняется при not-ready live runtime, если процесс жив;
- подтверждение, что bootstrap/validation profiles не подменяют active profile;
- подтверждение, что `runtime_unavailable` не подменяет `/ready`, если проблема известна заранее на уровне сервиса;
- проверка, что live session после успешного readiness использует именно active runtime path, а не hidden fallback.

### 7.3. Manual checks на текущем minimal-runtime этапе

Даже после появления минимального FastAPI runtime shell честно manual остаются:

- end-to-end подтверждение live path поверх реальных active artifacts;
- проверка, что `WS /ws/stream` реально обслуживает live traffic, а не только mock/integration harness;
- проверка service behavior при runtime-level startup failures;
- проверка реального `frame_decode_failed` и `runtime_unavailable` на живом backend;
- все сценарии, где без runtime code и artifact availability нельзя отличить policy agreement от фактического behavior.

## 8. Связь с active artifact policy и readiness semantics

QA-01 **не вводит новый смысл** readiness. Стратегия обязана интерпретироваться только так, как уже зафиксировано в `RT-02` и `ART-01`.

Это означает:

- `bootstrap` и `validation` profiles не подменяют `active` profile;
- отсутствие active manifest валит `active_artifacts` gate и `/ready`;
- отсутствие required active files валит `/ready`, даже если процесс жив;
- `/health` может оставаться `HTTP 200`, если процесс жив, даже когда live runtime not ready;
- `mock mode` не считается заменой live readiness;
- `WS /ws/stream` как minimal backend smoke относится к live transport surface, а не к fixture playback;
- strategy не должна переопределять `runtime_shell`, `active_artifacts` или `transport_surface`;
- strategy не должна обещать, что readiness можно полностью доказать документационной automation без runtime migration.

## 9. Non-goals и ограничения

Эта стратегия намеренно **не** обещает:

- что checks уже реализованы в репозитории;
- что Foundation CI уже запускает contract, mock или backend smoke;
- что clean repo уже содержит working backend runtime;
- что mock contour покрывает live runtime behavior;
- что readiness можно считать закрытой без active artifacts;
- что `words` baseline входит в scope QA-01;
- что issue #24 закрывает `INT-01`, runtime migration или production hardening.

Итоговая честная граница такая:

- automated contract checks и automated mock-based checks могут появляться раньше live runtime;
- minimal backend smoke зависит от реального runtime shell и transport surface;
- manual checks остаются обязательной частью контура, пока readiness и artifact availability не подтверждаются реальным implementation layer.
