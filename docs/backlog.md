# BACKLOG

Этот backlog фиксирует канонический foundation-level план для clean repo `rsl-sign-recognition`.

Он нужен как source of truth для milestones, epics, labels и task-кодов. Когда задачи уже заведены в GitHub, их текущий статус отслеживается через issues и PR, а backlog остается каноническим описанием scope и acceptance criteria.

## Канонические milestones

- `M0` — Foundation & Process
- `M1` — Contract & Runtime Skeleton
- `M2` — Integration-ready sign-to-text MVP
- `M3` — Hardening & August Alignment

## Канонические epics

- `Epic A — Repository foundation` → `epic:foundation`
- `Epic B — Integration contract` → `epic:contract`
- `Epic C — Runtime core` → `epic:runtime-core`
- `Epic D — pose_words inference` → `epic:pose-words`
- `Epic E — Runtime artifacts` → `epic:artifacts`
- `Epic F — Tests & quality` → `epic:qa`
- `Epic G — Handoff & migration` → `epic:migration`

## Коды задач

Используются следующие префиксы:

- `INF` — foundation / infra / repo setup
- `CTR` — contract
- `RT` — runtime core
- `PW` — pose_words
- `ART` — artifacts
- `QA` — tests / quality
- `MIG` — migration
- `INT` — integration / handoff

## Стартовый backlog

### M0 — Foundation & Process

#### Epic A — Repository foundation

##### [INF-01] Инициализировать clean repo и root process docs

- Summary: оформить foundation-структуру clean repo без переноса продуктового кода.
- Milestone: `M0 — Foundation & Process`
- Epic: `Epic A — Repository foundation`
- Recommended labels: `milestone:m0`, `epic:foundation`, `area:docs`, `type:task`, `priority:P0`, `size:M`
- Dependencies: нет.
- Acceptance criteria:
  - [ ] В репозитории есть `README.md`, `CONTRIBUTING.md`, `docs/architecture.md`, `docs/roadmap.md`, `docs/backlog.md`.
  - [ ] Во всех root docs одинаково описаны границы clean repo и draft repo.
  - [ ] Явно зафиксировано, что продуктовый runtime-код еще не перенесен.

##### [INF-02] Настроить базовый CI skeleton

- Summary: подготовить минимальный CI contour для docs/contracts/runtime-surface checks без привязки к еще не перенесенному коду.
- Milestone: `M0 — Foundation & Process`
- Epic: `Epic A — Repository foundation`
- Recommended labels: `milestone:m0`, `epic:foundation`, `area:ci`, `type:task`, `priority:P0`, `size:S`
- Dependencies: `INF-01`.
- Acceptance criteria:
  - [ ] Есть описанный CI skeleton для `pull_request` и `push`.
  - [ ] CI не делает вид, что в clean repo уже существует рабочий backend runtime.
  - [ ] В pipeline предусмотрено место для будущих docs, contract и smoke checks.

#### Epic G — Handoff & migration

##### [MIG-01] Перенести только product runtime docs из draft

- Summary: выделить из draft repo только те документы, которые нужны clean runtime contour, без переноса runbook-шума и без копирования кода.
- Milestone: `M0 — Foundation & Process`
- Epic: `Epic G — Handoff & migration`
- Recommended labels: `milestone:m0`, `epic:migration`, `area:docs`, `type:task`, `priority:P1`, `size:M`
- Dependencies: `INF-01`.
- Follow-up task directions: `CTR-01`, `CTR-02`, `RT-01`, `RT-02`, `PW-01`, `PW-02`, `ART-01`, `QA-01`, `INT-01`.
- Acceptance criteria:
  - [ ] Перенесены только clean-runtime-oriented формулировки и архитектурные договоренности.
  - [ ] Validation, bootstrap и draft-only operational details не представлены как часть clean runtime.
  - [ ] В документации есть явные ссылки на будущие migration issues, а не на массовый перенос файлов.

### M1 — Contract & Runtime Skeleton

#### Epic B — Integration contract

##### [CTR-01] Зафиксировать WebSocket contract v1

- Summary: выделить и задокументировать первую версию WebSocket контракта для sign-to-text runtime.
- Milestone: `M1 — Contract & Runtime Skeleton`
- Epic: `Epic B — Integration contract`
- Recommended labels: `milestone:m1`, `epic:contract`, `area:contracts`, `type:task`, `priority:P0`, `size:M`, `needs-web-team`
- Dependencies: `INF-01`.
- Acceptance criteria:
  - [ ] Описаны входные сообщения, выходные payload и версии контракта.
  - [ ] Отделены обязательные поля от optional debug/runtime blocks.
  - [ ] Зафиксированы условия изменения контракта и handoff для web team.

##### [CTR-02] Описать mock protocol mode

- Summary: определить mock mode, который позволяет web team и smoke checks работать без живого runtime.
- Milestone: `M1 — Contract & Runtime Skeleton`
- Epic: `Epic B — Integration contract`
- Recommended labels: `milestone:m1`, `epic:contract`, `area:integration`, `type:feature`, `priority:P0`, `size:S`, `needs-web-team`
- Dependencies: `CTR-01`.
- Acceptance criteria:
  - [ ] Описан режим `mock` и правила его включения.
  - [ ] Подготовлен минимальный набор mock payload fixtures.
  - [ ] Поведение mock mode не смешивается с реальным runtime path.

#### Epic C — Runtime core

##### [RT-01] Собрать runtime skeleton

- Summary: подготовить структуру clean runtime repo для API, contracts, runtime orchestration и pipeline boundaries.
- Milestone: `M1 — Contract & Runtime Skeleton`
- Epic: `Epic C — Runtime core`
- Recommended labels: `milestone:m1`, `epic:runtime-core`, `area:runtime`, `type:feature`, `priority:P0`, `size:M`
- Dependencies: `INF-01`, `CTR-01`.
- Acceptance criteria:
  - [ ] Есть целевая структура модулей для `api`, `contracts`, `runtime`, `pipelines`, `segmentation`, `inference`.
  - [ ] Границы runtime skeleton описаны без переноса training/export кода.
  - [ ] Архитектурные решения согласованы с `docs/architecture.md`.

##### [RT-02] Описать `/health` и `/ready`

- Summary: формализовать health/readiness semantics для clean runtime.
- Milestone: `M1 — Contract & Runtime Skeleton`
- Epic: `Epic C — Runtime core`
- Recommended labels: `milestone:m1`, `epic:runtime-core`, `area:api`, `type:task`, `priority:P0`, `size:S`
- Dependencies: `RT-01`.
- Acceptance criteria:
  - [ ] Описано, что возвращает `/health`.
  - [ ] Описано, что проверяет `/ready`.
  - [ ] Есть правила для missing artifacts, readiness gates и integration smoke.

### M2 — Integration-ready sign-to-text MVP

#### Epic D — pose_words inference

##### [PW-01] Подготовить перенос `pose_words` inference wrapper

- Summary: выделить границы и требования для переноса основного `pose_words` inference wrapper в clean repo.
- Milestone: `M2 — Integration-ready sign-to-text MVP`
- Epic: `Epic D — pose_words inference`
- Recommended labels: `milestone:m2`, `epic:pose-words`, `area:inference`, `type:task`, `priority:P0`, `size:M`, `needs-manual-check`
- Dependencies: `RT-01`, `CTR-01`.
- Acceptance criteria:
  - [ ] Определен source scope в draft repo и target scope в clean repo.
  - [ ] Явно отделены runtime-required части от training/export и validation utilities.
  - [ ] Зафиксированы ограничения и ручные проверки для первого migration increment.

##### [PW-02] Подготовить перенос segmentation runtime

- Summary: выделить streaming segmentation как отдельный runtime слой для clean repo.
- Milestone: `M2 — Integration-ready sign-to-text MVP`
- Epic: `Epic D — pose_words inference`
- Recommended labels: `milestone:m2`, `epic:pose-words`, `area:segmentation`, `type:task`, `priority:P0`, `size:M`, `needs-manual-check`
- Dependencies: `RT-01`, `PW-01`.
- Scope doc: [docs/pw-02-segmentation-runtime-scope.md](pw-02-segmentation-runtime-scope.md)
- Acceptance criteria:
  - [ ] Зафиксированы границы segmentation layer и его зависимости.
  - [ ] Определено, какие части segmentation относятся к runtime, а какие остаются в draft validation/research contour.
  - [ ] Согласованы требования к smoke и manual validation для segmentation path.

#### Epic E — Runtime artifacts

##### [ART-01] Подготовить active artifact manifest/load path

- Summary: формализовать хранение и загрузку active runtime artifacts без переноса validation outputs и bootstrap fallback как основного пути.
- Milestone: `M2 — Integration-ready sign-to-text MVP`
- Epic: `Epic E — Runtime artifacts`
- Recommended labels: `milestone:m2`, `epic:artifacts`, `area:runtime`, `type:task`, `priority:P0`, `size:M`, `needs-dataset`, `needs-manual-check`
- Dependencies: `RT-02`, `PW-01`, `PW-02`.
- Acceptance criteria:
  - [ ] Описан manifest и expected active runtime layout.
  - [ ] Разделены active, validation и bootstrap artifacts.
  - [ ] Нет зависимости на `config.yaml` и другие draft-only runtime paths без отдельной задачи.

#### Epic F — Tests & quality

##### [QA-01] Добавить smoke test strategy

- Summary: описать минимальную стратегию smoke/contract/integration проверок для clean runtime repo.
- Milestone: `M2 — Integration-ready sign-to-text MVP`
- Epic: `Epic F — Tests & quality`
- Recommended labels: `milestone:m2`, `epic:qa`, `area:ci`, `type:task`, `priority:P1`, `size:S`, `needs-manual-check`
- Dependencies: `CTR-01`, `CTR-02`, `RT-02`, `ART-01`.
- Acceptance criteria:
  - [ ] Зафиксированы contract checks, mock-based checks и backend smoke.
  - [ ] Ручные проверки явно перечислены и не маскируются под полную автоматизацию.
  - [ ] Стратегия согласована с readiness и artifact policy.

#### Epic G — Handoff & migration

##### [MIG-02] Зафиксировать controlled migration governance для runtime-required модулей

- Summary: зафиксировать source-to-target mapping, exclusions, guardrails и manual checks для будущих runtime migration issues без переноса runtime-кода.
- Milestone: `M2 — Integration-ready sign-to-text MVP`
- Epic: `Epic G — Handoff & migration`
- Recommended labels: `milestone:m2`, `epic:migration`, `area:integration`, `type:task`, `priority:P0`, `size:M`, `needs-manual-check`
- Dependencies: `PW-01`, `PW-02`, `ART-01`, `RT-04`.
- Scope doc: [docs/mig-02-runtime-required-migration-governance.md](mig-02-runtime-required-migration-governance.md)
- Follow-up task directions: `PW-05`, `PW-03`, `PW-04`, `ART-02`.
- Acceptance criteria:
  - [ ] Есть source-to-target mapping для `PW-05`, `PW-03`, `PW-04` и `ART-02`.
  - [ ] Явно перечислены excluded draft areas: `words`, `letters`, training/export, validation runners, dataset prep, synthetic dataset logic, frontend/offline helpers, bootstrap-only paths, operational scripts, metrics-only helpers и unrelated draft glue.
  - [ ] Описаны guardrails против массового копирования `backend/app`, `main.py`, `pose/`, `segmentation/`, `pose_words/`, draft `config.yaml` и validation/bootstrap artifacts.
  - [ ] Описаны manual migration checks и hidden dependency rule для future implementation PR.

##### [INT-01] Подготовить handoff notes для web team

- Summary: оформить минимальный handoff package для интеграции clean runtime с веб-командой.
- Milestone: `M2 — Integration-ready sign-to-text MVP`
- Epic: `Epic G — Handoff & migration`
- Recommended labels: `milestone:m2`, `epic:migration`, `area:integration`, `type:task`, `priority:P1`, `size:S`, `needs-web-team`
- Dependencies: `CTR-01`, `CTR-02`, `RT-02`, `QA-01`.
- Acceptance criteria:
  - [ ] Есть краткое описание contract version, mock/live режимов и readiness semantics.
  - [ ] Зафиксированы точки соприкосновения с web team и известные ограничения.
  - [ ] Handoff notes не делают вид, что clean repo уже закрывает весь runtime surface production-уровня.

## Recommended GitHub labels

### Milestones

- `milestone:m0`
- `milestone:m1`
- `milestone:m2`
- `milestone:m3`

### Epics

- `epic:foundation`
- `epic:contract`
- `epic:runtime-core`
- `epic:pose-words`
- `epic:artifacts`
- `epic:qa`
- `epic:migration`

### Areas

- `area:docs`
- `area:api`
- `area:runtime`
- `area:segmentation`
- `area:inference`
- `area:contracts`
- `area:integration`
- `area:ci`

### Types

- `type:task`
- `type:feature`
- `type:bug`
- `type:chore`
- `type:research`

### Priority

- `priority:P0`
- `priority:P1`
- `priority:P2`

### Size

- `size:S`
- `size:M`
- `size:L`

### Cross-cutting

- `needs-web-team`
- `needs-dataset`
- `needs-manual-check`
