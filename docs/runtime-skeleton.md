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
- future handlers для `/health` и `/ready`, когда это будет формализовано отдельной задачей.

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
