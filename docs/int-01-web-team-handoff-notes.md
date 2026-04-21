# INT-01 - Handoff Notes для web team

## 1. Назначение документа

Этот документ закрывает docs/integration handoff-часть issue `#25 INT-01`.

Он нужен как **минимальный и честный handoff package** для web team вокруг clean runtime surface, который уже описан в clean repo.

Документ покрывает:

- на какие уже зафиксированные документы и semantics web team может опираться;
- где проходит граница между `mock path` и ожиданиями от будущего `live runtime path`;
- как трактовать `/health`, `/ready` и `WS /ws/stream` на текущем этапе;
- какие ограничения у handoff-контура остаются до первого working runtime increment.

Документ **не** покрывает:

- реализацию runtime;
- реальный совместный integration run;
- production-ready handoff;
- изменение `contract v1`;
- claims о полном working runtime surface в clean repo.

## 2. Текущее состояние integration-ready контура

На текущем этапе clean repo фиксирует **docs-first integration surface**, а не рабочий production-like runtime.

Уже зафиксировано и доступно как source context для web team:

- [docs/contracts/websocket-contract-v1.md](contracts/websocket-contract-v1.md) - канонический `WebSocket contract v1`;
- [docs/contracts/mock-protocol-mode.md](contracts/mock-protocol-mode.md) - отдельный `mock protocol mode` поверх того же контракта;
- [docs/runtime-skeleton.md](runtime-skeleton.md) - semantics `/health` и `/ready` для будущего runtime shell;
- [docs/artifact-policy.md](artifact-policy.md) - readiness expectations для active artifacts;
- [docs/qa-01-smoke-test-strategy.md](qa-01-smoke-test-strategy.md) - минимальные smoke/manual expectations.

На это web team уже может опираться:

- stable JSON envelope и stable поля `contract v1`;
- documented mock path для UI/integration parsing без live runtime;
- честное разделение liveness и readiness;
- минимальные expectations для future smoke и manual integration checks.

Пока **нельзя** считать готовым:

- рабочий live runtime в clean repo;
- production-grade readiness contour;
- доказанную доступность `WS /ws/stream` как live transport surface;
- наличие active artifacts и working runtime shell;
- end-to-end handoff beyond documented surface.

## 3. Contract Version

Актуальная зафиксированная версия контракта: **`1.0`**.

Source of truth для `contract v1`:

- основной документ: [docs/contracts/websocket-contract-v1.md](contracts/websocket-contract-v1.md);
- для `mock path`: [docs/contracts/mock-protocol-mode.md](contracts/mock-protocol-mode.md);
- для mock fixtures: `docs/contracts/fixtures/*.json`.

Для web team это означает:

- ориентироваться нужно на `contract_version` в рамках документированной линии `v1` (`1.x`);
- stable minimum surface определяется именно документом `websocket-contract-v1.md`, а не draft runtime payload;
- `mock mode` не создает отдельный контракт и не меняет смысл `v1`, а использует его поверх внешней integration boundary.

## 4. Граница между mock и live

### Что можно использовать через mock mode уже сейчас

Через `mock path` web team может:

- разбирать тот же JSON envelope `type`, `contract_version`, `payload`;
- использовать stable поля `recognition.result`, `control.ack` и `error`;
- проверять `HOLD` и `COMMIT` сценарии через fixtures;
- прогонять UI/integration parsing и controlled error handling без live runtime.

### Что относится к live runtime expectations

К `live runtime path` относятся только ожидания, завязанные на:

- реальный runtime shell;
- active artifacts;
- transport surface `WS /ws/stream` как live endpoint;
- readiness gates `runtime_shell`, `active_artifacts`, `transport_surface`.

### Где проходит граница

Граница проходит на **внешнем integration/config choice**:

- `mock` выбирается до начала session как controlled integration path;
- `live` предполагает реальный runtime path, а не fixture playback;
- payload не должен содержать `mock: true` или другие mock-only protocol markers;
- успешный `mock` run не доказывает `live readiness`.

### Какие ожидания допустимы сейчас

Допустимо ожидать сейчас:

- совместимость mock fixtures со stable surface `contract v1`;
- documented parsing rules для `v1` и совместимых `1.x`-расширений;
- documented semantics для `/health` и `/ready`.

Преждевременно ожидать сейчас:

- что `mock` и `live` уже взаимозаменяемы;
- что `WS /ws/stream` реально поднят и обслуживает live traffic;
- что clean repo уже дает полный working backend contour;
- что successful mock checks подтверждают production readiness.

## 5. Readiness Semantics

### `/health`

`/health` трактуется только как **liveness probe**.

Он подтверждает:

- процесс жив;
- runtime shell отвечает как HTTP-сервис;
- какой `runtime_mode` сейчас выбран.

Он **не** подтверждает:

- что live runtime готов принимать session;
- что active artifacts доступны;
- что `WS /ws/stream` готов к live traffic;
- что сервис production-ready.

### `/ready`

`/ready` трактуется только как **readiness probe для `live_runtime_path`**.

Он подтверждает только то, что для live path закрыты gates:

- `runtime_shell`;
- `active_artifacts`;
- `transport_surface`.

Он **не** подтверждает:

- production-hardening;
- model quality;
- полноту runtime surface beyond documented increment;
- readiness для `mock path`.

Ключевая граница: readiness integration surface не равна production readiness. Даже документированные `/health` и `/ready` остаются semantics для будущего runtime shell, пока implementation-layer еще не перенесен.

## 6. Точки соприкосновения с web team

### `/health`

Назначение:

- дать web/integration layer минимальный liveness signal и текущий `runtime_mode`.

Что должна ожидать web team:

- `HTTP 200` для живого процесса;
- минимальный response shape со `status = "ok"`, `probe = "liveness"`, `runtime_mode`.

Что уже стабилизировано:

- смысл probe как liveness-only surface;
- отсутствие claims о readiness через `/health`.

Что пока ограничено:

- endpoint описан на уровне semantics, а не как уже реализованная live surface;
- `/health` не говорит ничего о готовности artifacts или WebSocket transport.

### `/ready`

Назначение:

- показать, готов ли сервис именно к `live_runtime_path`.

Что должна ожидать web team:

- `HTTP 200` только при закрытых gates `runtime_shell`, `active_artifacts`, `transport_surface`;
- `HTTP 503`, если любой из этих gates не закрыт;
- response shape с `probe = "readiness"`, `runtime_mode`, `ready_for = "live_runtime_path"`, `gates`.

Что уже стабилизировано:

- distinction между liveness и readiness;
- правило, что `mock` availability не делает live path ready;
- правило, что missing active artifacts валят `/ready`, но не обязаны валить `/health`.

Что пока ограничено или зависит от следующих increment'ов:

- реальная materialization active artifacts;
- рабочий readiness assembly в коде;
- подтверждение gate-ов на живом runtime shell.

### `WS /ws/stream`

Назначение:

- быть runtime-facing transport surface для `contract v1`.

Что должна ожидать web team:

- WebSocket endpoint по пути `WS /ws/stream`;
- binary JPEG frames как канонический input path;
- JSON messages `recognition.result`, `control.ack`, `error`;
- `control.clear_text` как допустимое JSON control message.

Что уже стабилизировано:

- версия контракта `1.0`;
- stable envelope и minimum stable payload surface;
- правило, что partial/final semantics идут через `payload.text_state.committed`, а не через отдельные message types.

Что пока ограничено или зависит от следующих increment'ов:

- реальная live-доступность endpoint;
- runtime behavior поверх active artifacts;
- transport smoke against actual backend;
- любые claims о latency, stability или strict frame-to-result correlation.

## 7. Известные ограничения

Текущий handoff намеренно ограничен:

- это минимальный docs-first package, а не working runtime handoff;
- clean repo не делает claims о production-grade runtime;
- mock checks и fixtures не заменяют live runtime path;
- smoke/manual expectations пока описаны как strategy, а не как полностью реализованный test contour;
- readiness semantics документированы честно, но не подтверждены working implementation layer в clean repo;
- нельзя делать вывод о полноте runtime surface сверх того, что прямо описано в `contract v1`, `RT-02`, `ART-01` и `QA-01`;
- handoff не должен трактоваться как сигнал, что web team уже может полагаться на full live backend parity.

## 8. Проверка и ожидания для integration increment

Сейчас можно ссылаться на следующие checks и проверки:

- doc-level сверка `contract v1`, `mock protocol mode`, `RT-02`, `ART-01` и `QA-01`;
- mock-compatible parsing checks на fixtures из `docs/contracts/fixtures/`;
- manual/doc expectations для `/health`, `/ready` и `WS /ws/stream`, описанные в `QA-01`.

Что web team уже может проверить сейчас:

- корректный разбор `recognition.result`, `control.ack`, `error` по stable surface;
- работу UI/integration logic с `HOLD`, `COMMIT`, `clear_text` и `runtime_unavailable` через mock fixtures;
- tolerant behavior к отсутствию optional debug/runtime blocks и к additive полям в совместимой линии `v1` (`1.x`).

Что пока остается предметом следующего working increment:

- реальная live-проверка `/health`, `/ready` и `WS /ws/stream` на поднятом runtime shell;
- проверка readiness gates против active artifacts;
- backend smoke на actual transport surface, а не на fixture playback;
- manual confirmation, что live path не использует hidden fallback или mock substitute.

## 9. Основа для следующего шага

В follow-up issue на первый working handoff increment стоит включить:

- реализацию minimal runtime-facing surface для `/health`, `/ready` и `WS /ws/stream` в clean repo;
- minimal backend smoke against real live path;
- manual integration checklist с web team для отличения `mock-ready` от `live-ready`;
- явную проверку active artifact gate без скрытого fallback в validation/bootstrap profiles.

Это именно база для следующей задачи. Данный документ не реализует этот increment и не должен читаться как подтверждение, что такой runtime surface уже появился.
