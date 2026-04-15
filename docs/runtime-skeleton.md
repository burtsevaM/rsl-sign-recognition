# Runtime Skeleton для clean repo

## 1. Назначение документа

Этот документ фиксирует **runtime skeleton boundaries** для clean-репозитория `rsl-sign-recognition`.

Его задача:

- определить будущий runtime contour до переноса кода;
- зафиксировать **target module structure** для `api`, `contracts`, `runtime`, `pipelines`, `segmentation` и `inference`;
- отделить clean runtime surface от training/export, draft-only operational details и mixed runtime/research контуров из `gesture-recognition-draft`.

Важно:

- это **не** описание уже мигрированной реализации;
- этот документ **не** создает новые runtime-модули в файловой системе;
- он нужен, чтобы следующие migration tasks переносили код в заранее согласованные границы, а не копировали старую структуру как есть.

## 2. Scope

В scope RT-01 входят:

- целевая модульная структура runtime surface;
- границы ответственности между transport/API, contract layer, orchestration runtime и pipeline-related слоями;
- связь runtime skeleton с уже зафиксированным `WebSocket contract v1`;
- фиксация того, что основным word-oriented pipeline остается `pose_words`, `words` сохраняется только как baseline/reference, а `letters` не считается равноправным word runtime path для clean repo.

## 3. Non-goals

В scope RT-01 **не входят**:

- перенос runtime-кода из `gesture-recognition-draft`;
- создание `src/`, `backend/` или других product directories;
- реализация `/health`, `/ready` и readiness semantics;
- формализация artifact lifecycle, active manifest и load path;
- training/export migration;
- перенос датасетных утилит, bootstrap/fallback logic, validation reports, configs, scripts или артефактов.

## 4. Зачем clean repo фиксирует runtime skeleton заранее

В draft-репозитории transport, orchestration, segmentation, inference, training/export и operational детали смешаны в одном рабочем контуре. Для clean repo это неприемлемо по двум причинам:

- future migration должна переносить только product-runtime-oriented части, а не наследовать смешанную структуру;
- web/integration контур уже требует понятных границ между contract surface, transport handlers и внутренней runtime orchestration.

Поэтому RT-01 фиксирует не реализацию, а **архитектурный каркас**, внутри которого позже будут выполняться `RT-02`, `PW-*`, `ART-*` и `QA-*` задачи.

## 5. Target Layout

Ниже описана **целевая**, а не текущая структура runtime surface.

```text
docs/
src/
  api/
  contracts/
  runtime/
  pipelines/
    pose_words/
    words_baseline/   # только отдельной задачей и только как baseline/reference
  segmentation/
  inference/
tests/
```

Принципы этого layout:

- `api` остается тонким transport-слоем;
- `contracts` живут отдельно от handler-кода и orchestration;
- `runtime` отвечает за orchestration, а не за transport schema или model internals;
- `pipelines` описывают product/runtime assembly для конкретных recognition paths;
- `segmentation` и `inference` выделены как отдельные runtime capabilities, чтобы не смешивать их с pipeline routing;
- training/export concerns в этот layout не входят.

## 6. Где проходит граница между transport/API и orchestration

Граница фиксируется так:

- `api` принимает transport event: WebSocket connect, binary JPEG frame, JSON control message или future HTTP probe;
- `api` валидирует transport-level форму сообщения и сопоставляет ее с versioned contract;
- после этого `api` передает в `runtime` уже нормализованное runtime-facing действие;
- все, что связано с session state, orchestration pipeline steps, вызовом segmentation/inference и сборкой domain result, относится к `runtime`, а не к `api`.

Иначе говоря, transport заканчивается в момент, когда handler больше не занимается wire-format и начинает обращаться к orchestration surface.

## 7. Модули runtime skeleton

### 7.1. `api`

**Зачем нужен**

- дать clean repo тонкий transport surface для WebSocket и будущих runtime-facing HTTP endpoints;
- изолировать transport wiring от ML/runtime orchestration.

**Что входит**

- transport handlers и router layer;
- transport-level parsing и protocol error mapping;
- привязка к versioned contracts;
- handoff в `runtime`;
- handlers для `/health` и `/ready` с semantics, зафиксированной в разделе 13 этого документа.

**Что не входит**

- orchestration session logic;
- pipeline selection rules;
- segmentation state;
- inference wrappers;
- training/export, artifact install/promote workflow и machine-local recovery paths.

**С какими слоями граничит**

- сверху: WebSocket/HTTP transport;
- снизу: `contracts` и `runtime`.

### 7.2. `contracts`

**Зачем нужен**

- держать versioned integration surface отдельно от transport wiring и runtime internals;
- сделать payload semantics устойчивыми для web team и contract checks.

**Что входит**

- versioned schemas и envelope definitions;
- описание обязательных и optional полей;
- error semantics, совместимость версий и handoff rules;
- typed contract models, если они понадобятся для handler/tests/documentation consistency.

**Что не входит**

- FastAPI/WebSocket handlers;
- orchestration state;
- model execution;
- training/export contracts и internal research formats.

**С какими слоями граничит**

- `api` использует `contracts` для transport-level валидации и сериализации;
- `runtime` не должен подменять собой contract layer и не должен хранить wire-format как внутреннюю доменную модель.

### 7.3. `runtime`

**Зачем нужен**

- быть orchestration layer для clean runtime contour;
- отделить session lifecycle и dependency coordination от transport и от model-specific code.

**Что входит**

- session/runtime orchestration;
- coordination между pipeline assembly, segmentation и inference;
- runtime-level dependency wiring;
- future readiness dependency graph и runtime service composition.

**Что не входит**

- WebSocket/HTTP transport handlers;
- versioned contract definitions;
- training/export workflows;
- dataset tooling;
- low-level model wrappers, если они относятся к reusable inference layer.

**С какими слоями граничит**

- сверху: `api`;
- снизу: `pipelines`, `segmentation`, `inference`.

### 7.4. `pipelines`

**Зачем нужен**

- зафиксировать product/runtime paths как осознанные assembly units, а не как случайные ветки в монолитном runtime;
- дать clean repo место для `pose_words` как основного path и для `words_baseline` только как явно ограниченного reference path.

**Что входит**

- pipeline composition rules;
- runtime-facing сборка шагов для конкретного recognition path;
- pipeline-specific adapters между orchestration, segmentation и inference;
- документированное различие между primary path и baseline/reference path.

**Что не входит**

- transport handlers;
- versioned contract layer;
- общая orchestration session logic;
- training/export scripts;
- неограниченное количество исторических режимов.

**С какими слоями граничит**

- сверху: `runtime`;
- снизу: `segmentation` и `inference`.

**Зафиксированное архитектурное решение**

- `pose_words` — основной clean runtime pipeline для word recognition;
- `words` — только baseline/reference и не равноправный product path;
- `letters` не входит в target word-oriented runtime skeleton как равноправный путь.

### 7.5. `segmentation`

**Зачем нужен**

- вынести streaming segmentation в самостоятельный runtime layer;
- не смешивать границы сегментов с transport logic или full pipeline orchestration.

**Что входит**

- streaming segmentation state;
- boundary detection и decoder logic для segment-level решений;
- segmentation-specific thresholds и runtime-facing segment outputs;
- специализированные wrappers для segmentation model execution, если они относятся только к segmentation layer.

**Что не входит**

- WebSocket/HTTP handling;
- общий session orchestration;
- full classifier pipeline;
- training датасеты, synthetic dataset generation и export workflows.

**С какими слоями граничит**

- `runtime` и `pipelines` вызывают `segmentation` как выделенную capability;
- `segmentation` может использовать `inference` только если это будет осознанно выделено как shared model runtime, а не как скрытая смешанная зависимость.

### 7.6. `inference`

**Зачем нужен**

- хранить model runtime wrappers и postprocessing, которые относятся к выполнению inference, а не к transport или orchestration.

**Что входит**

- runtime wrappers для model execution;
- loader/runtime-facing adapters для inference artifacts, когда они будут отдельно формализованы;
- postprocessing, ближайший к model outputs;
- shared inference primitives, которые могут использоваться несколькими pipeline layers.

**Что не входит**

- transport/API;
- versioned contracts;
- session orchestration;
- segmentation policy как отдельный streaming layer;
- training/export code, экспериментальные notebook/scaffold path и validation-only scripts.

**С какими слоями граничит**

- вызывается из `pipelines` и при необходимости из `segmentation`;
- подчиняется orchestration через `runtime`, а не управляет session flow самостоятельно.

## 8. Как `contracts` соотносятся с `runtime`

Разделение фиксируется так:

- `contracts` описывают, **как** runtime surface выглядит для внешнего интегратора;
- `runtime` определяет, **как** сервис внутри себя координирует pipeline, segmentation и inference;
- contract changes versionируются и обсуждаются как integration surface;
- runtime refactoring не должен автоматически менять contract, если не меняется внешняя семантика.

Это особенно важно для `WebSocket contract v1`: contract уже зафиксирован отдельно, а RT-01 определяет, где в clean repo будет жить слой, который его обслуживает, не смешивая это с ML orchestration.

## 9. Как `pipelines` соотносятся с `segmentation` и `inference`

Разделение фиксируется так:

- `pipelines` отвечают за composition конкретного runtime path;
- `segmentation` отвечает за выделение и сопровождение segment boundaries;
- `inference` отвечает за model execution и model-near postprocessing;
- `runtime` координирует их взаимодействие;
- `api` только передает управление в этот контур и отдает наружу contract-shaped результат.

Иначе говоря:

- `pipelines` — это не синоним model wrappers;
- `segmentation` — это не просто detail внутри `pose_words`, а отдельный runtime layer;
- `inference` — это не orchestration и не transport.

## 10. Связь с `WebSocket contract v1`

Runtime skeleton должен быть совместим с уже зафиксированным [WebSocket contract v1](contracts/websocket-contract-v1.md):

- `contracts` хранят versioned envelope и payload semantics;
- `api` реализует transport surface `WS /ws/stream` поверх этого contract layer;
- `runtime` возвращает domain result, который затем сериализуется в `recognition.result`, `control.ack` или `error`;
- optional debug/runtime blocks из контракта не должны размывать границы между transport layer и core runtime modules.

RT-01 не меняет сам contract v1. Он фиксирует, где этот contract должен жить относительно будущего runtime layout.

## 11. Что остается в `gesture-recognition-draft`

В draft repo остаются:

- текущий смешанный FastAPI/WebSocket runtime;
- training/export scripts;
- dataset preparation и synthetic dataset builders;
- validation workflows и technical validation reports;
- bootstrap/fallback paths;
- operational runbooks и machine-local recovery flows;
- active artifact install/promote details до отдельной artifact task;
- `letters` runtime path и полный `words` runtime path, пока не будет отдельной migration задачи на их ограниченный перенос;
- experimental browser/client-side scaffolds и другие exploratory части.

RT-01 использует draft repo только как источник архитектурного контекста:

- transport/API слой уже существует как смешанный FastAPI/WebSocket контур;
- orchestration, segmentation и inference там пока не разведены достаточно чисто;
- `pose_words` подтвержден как основной будущий pipeline direction;
- `words` и `letters` не должны автоматически становиться равноправными clean runtime modules.

## 12. Что runtime skeleton не включает

Runtime skeleton **не включает**:

- training concerns;
- export concerns;
- dataset lifecycle;
- manual validation workflows;
- artifact manifests и artifact promotion;
- runtime logs;
- перенос product code в текущей задаче.

Это означает, что после RT-01 clean repo честно фиксирует будущее устройство runtime surface, но по-прежнему **не делает вид**, что migrated runtime implementation уже существует.

## 13. Semantics для `/health` и `/ready`

RT-02 расширяет RT-01 не новым runtime scope, а **документированной probes-semantics** для будущего runtime shell.

Важно:

- это still docs-first описание для следующего implementation-layer;
- раздел не объявляет, что clean repo уже содержит working runtime;
- раздел не меняет `WebSocket contract v1` и не делает `mock mode` частью live runtime behavior;
- конкретный `artifact manifest`, active profile markers и primary load path зафиксированы отдельно в [docs/artifact-policy.md](artifact-policy.md) как scope `ART-01`.

### 13.1. Разделение ролей

Роли probes фиксируются так:

- `/health` отвечает только за **liveness** процесса и базовую доступность runtime shell как HTTP-сервиса;
- `/ready` отвечает только за **readiness** live runtime path в пределах уже согласованных clean boundaries;
- положительный `/health` не означает, что live runtime готов, артефакты доступны или `WS /ws/stream` может честно обслуживать live session;
- mock availability, contract fixtures и integration harness не считаются заменой live readiness.

### 13.2. `/health`: минимальный liveness probe

`/health` нужен для ответа на один вопрос: **жив ли процесс и может ли он ответить как runtime shell service**.

Каноническая semantics:

- успешный ответ: `HTTP 200`;
- минимально обязательные поля ответа:
  - `status` — literal `ok`;
  - `probe` — literal `liveness`;
  - `runtime_mode` — текущий configured mode (`mock` или `live`);
- дополнительные поля допустимы только если они остаются liveness-level и не маскируют readiness semantics.

Минимальный shape:

```json
{
  "status": "ok",
  "probe": "liveness",
  "runtime_mode": "live"
}
```

`/health` показывает:

- процесс поднят и HTTP probe surface отвечает;
- runtime shell запущен как сервисный процесс;
- какой runtime mode сейчас выбран для этого экземпляра сервиса.

`/health` **не проверяет**:

- загружены ли active artifacts;
- доступен ли live runtime path для новой session;
- готов ли `WS /ws/stream` обслуживать live traffic;
- есть ли runtime-level dependency graph для `pose_words`;
- можно ли использовать mock path вместо live path.

Следствие:

- missing artifacts не должны переводить `/health` в failed state;
- отсутствие live runtime readiness не должно подменять собой liveness failure;
- `/health` не должен притворяться сокращённой версией `/ready`.

### 13.3. `/ready`: readiness probe для live runtime path

`/ready` отвечает на другой вопрос: **готов ли текущий runtime shell обслуживать live runtime path в рамках clean repo boundaries**.

Каноническая semantics:

- успешный ответ возможен только при `HTTP 200`;
- неуспешный ответ для любого незакрытого gate: `HTTP 503`;
- `/ready` всегда интерпретируется как readiness именно для `live_runtime_path`, а не для mock fixtures.

Минимальный shape:

```json
{
  "status": "ready",
  "probe": "readiness",
  "runtime_mode": "live",
  "ready_for": "live_runtime_path",
  "gates": {
    "runtime_shell": true,
    "active_artifacts": true,
    "transport_surface": true
  }
}
```

Если хотя бы один gate не закрыт, ответ остаётся тем же по shape, но:

- `status` становится `not_ready`;
- соответствующие значения в `gates` становятся `false`;
- реализация может добавить `reason_codes`, но они не должны подменять собой состояние gate-ов.

Обязательные readiness gates:

- `runtime_shell` — live runtime shell выбран, собран и не находится в заведомо unavailable startup-state;
- `active_artifacts` — для live path доступны все активные runtime artifacts, которые требуются выбранному pipeline;
- `transport_surface` — live transport surface поднят и связан с runtime shell так, чтобы `WS /ws/stream` обслуживал именно live path, а не mock substitute.

### 13.4. Правила для readiness gates

#### `runtime_shell`

Gate закрыт только если:

- сервис находится в `live` mode;
- runtime shell и его runtime-facing зависимости инициализированы до состояния, в котором можно принять новую live session;
- нет известной глобальной причины, из-за которой новая live session заранее обречена на `runtime_unavailable`.

Gate не закрыт, если:

- экземпляр запущен в `mock` mode;
- live runtime shell не собран или не активирован;
- есть startup/runtime-level failure, из-за которой сервис заранее знает, что live path недоступен.

#### `active_artifacts`

Gate закрыт только если обязательные для live path active artifacts:

- определены для текущего runtime increment;
- действительно доступны runtime shell;
- могут быть использованы без обращения к draft-only bootstrap/fallback path.

RT-02 не задает manifest schema сам по себе: shape manifest, profile markers и clean load path описаны в [docs/artifact-policy.md](artifact-policy.md) как отдельный artifact-policy layer.

Но RT-02 фиксирует rule:

- missing artifacts всегда означают `active_artifacts = false` и `HTTP 503` на `/ready`;
- missing artifacts не должны ломать `/health`.

#### `transport_surface`

Gate закрыт только если live runtime path выставляет документированную transport surface:

- HTTP probes доступны как service-level surface;
- `WS /ws/stream` поднят как live transport endpoint;
- integration boundary не подменяет live path mock fixtures.

Gate не закрыт, если:

- transport поднят только для mock/integration harness;
- live WebSocket surface не связан с runtime shell;
- сервис отвечает на `/health`, но не способен принять live runtime traffic.

### 13.5. Missing artifacts и `runtime_unavailable`

`missing artifacts` и `runtime_unavailable` фиксируются как разные, но связанные ситуации.

`missing artifacts`:

- это причина readiness failure;
- влияет на `/ready`, а не на `/health`;
- означает, что live runtime path нельзя считать готовым даже если процесс жив.

`runtime_unavailable`:

- в контексте `CTR-01` / `CTR-02` остаётся session-level error code `runtime_unavailable` внутри WebSocket contract;
- не заменяет `/ready` и не становится transport-level shortcut для probe semantics;
- должен интерпретироваться как error текущей session, если недоступность проявилась уже после того, как сервис был готов принимать session.

Если причина известна заранее и затрагивает сервис целиком, semantics такие:

- `/ready` уже должен возвращать `HTTP 503`;
- соответствующий gate должен быть `false`;
- реализация может использовать `runtime_unavailable` в `reason_codes`, но readiness failure должна быть видна именно через `/ready`.

Иначе говоря:

- `/ready` — pre-session truth про готовность live path;
- `runtime_unavailable` — session/runtime-level signal внутри уже выбранного live path;
- эти сигналы не должны подменять друг друга.

### 13.6. Mock/live boundary и integration smoke

Связь с `CTR-02` фиксируется так:

- `mock mode` остаётся внешним integration choice и не превращается в разновидность live readiness;
- `/health` обязан показывать текущий `runtime_mode`, чтобы integration layer видел, находится ли сервис в `mock` или `live`;
- `/ready` в `mock` mode не должен возвращать `ready = true` для `live_runtime_path`, даже если mock fixtures доступны и smoke-checks проходят;
- mock-based smoke используют `CTR-02` fixtures и contract checks, а не считают успешный mock run доказательством live readiness;
- live smoke могут трактовать связку `/health = 200` и `/ready = 200` как минимальную предпосылку для начала runtime-facing checks, но не как доказательство production-hardening.

Это и есть честная clean boundary:

- `mock` помогает web team и smoke automation до появления live runtime surface;
- `live readiness` начинается только там, где закрыты `runtime_shell`, `active_artifacts` и `transport_surface`;
- ни одна из этих формулировок не означает, что полный working runtime уже перенесён в clean repo.
