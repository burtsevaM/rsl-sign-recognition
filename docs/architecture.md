# Архитектура clean ML repository

## 1. Назначение clean repo

`rsl-sign-recognition` создается как clean repository для воспроизводимого product-oriented ML runtime распознавания РЖЯ в сценарии sign-to-text.

На foundation-этапе этот репозиторий намеренно содержит только:

- process documentation;
- архитектурные договоренности;
- roadmap и backlog;
- GitHub templates для issue-based разработки.

Это не описание уже перенесенного runtime. Это описание целевого clean contour и правил его поэтапной сборки.

## 2. Роль clean repo в общей системе

Clean repo должен стать местом, где живут:

- стабильные границы будущего runtime;
- минимально необходимый integration contract;
- сервисная логика, нужная для поддержки runtime;
- reproducible migration path из draft-контура в поддерживаемый продуктовый репозиторий.

В общей системе проект делится на два уровня ответственности:

- `rsl-sign-recognition` — clean repo для runtime, контрактов, readiness и reproducible support contour;
- `gesture-recognition-draft` — рабочий sandbox для experiments, validation, bootstrap/fallback, research и transitional logic.

## 3. Что входит в clean repo

После поэтапной миграции сюда должны входить только product-facing и reproducible части:

- versioned WebSocket contract и integration docs;
- runtime skeleton и orchestration для основного pipeline;
- `pose_words` inference path, segmentation runtime и связанная readiness-логика;
- artifact manifest/load policy для active runtime artifacts;
- smoke, contract и integration checks;
- handoff-документация для web/integration команды.

На текущем этапе фактически присутствуют только foundation docs и process assets.

## 4. Что сюда не входит

На уровне clean architecture сюда не должны входить:

- training/export scripts;
- dataset preparation и research utilities;
- validation outputs и technical validation reports как рабочий runtime-контур;
- dummy/bootstrap artifacts как основной product path;
- runtime logs и machine-local recovery files;
- `config.yaml` и другие draft runtime-конфиги без отдельной migration задачи;
- frontend demo, experimental browser inference и другие exploratory контуры;
- `letters` как равноправный word-oriented runtime mode;
- `words` как равноправный долгосрочный product path.

Такие элементы остаются в draft repo, пока не появится отдельное решение об их ограниченном переносе.

## 5. Основной pipeline: `pose_words`

Целевым основным pipeline для word recognition зафиксирован `pose_words`.

Это решение взято из архитектурных материалов draft repo и основано на том, что `pose_words`:

- ближе к долгосрочной pose-first архитектуре;
- лучше согласуется с segmentation layer;
- архитектурно подходит для будущего развития sign pipeline;
- уже был предметом отдельного technical validation path в draft-контуре.

Это решение не означает:

- что `pose_words` уже перенесен в clean repo;
- что он уже доказан как production-ready replacement;
- что baseline сравнение с `words` больше не нужно.

## 6. Статус `words`: baseline/reference

`words` сохраняется как baseline/reference pipeline до выполнения validation и integration условий.

Практический смысл этого статуса:

- `words` не должен развиваться как равноправный основной product path в clean architecture;
- `words` может использоваться как reference для сравнения качества, latency и handoff-рисков;
- окончательное снятие роли `words` нельзя объявлять только по факту архитектурного решения в пользу `pose_words`.

До закрытия соответствующих gates `words` остается частью draft/research contour, а не основой clean repo.

`letters` при этом может сохраняться в draft repo как отдельный baseline или архивный контур, но не должен автоматически мигрировать в clean word-oriented runtime repository как третий равноправный режим.

## 7. Границы между draft repo и clean repo

Границы должны быть явными.

| Clean repo | Draft repo |
| --- | --- |
| reproducible product-oriented runtime | experiments и research |
| integration contract и mock fixtures | validation workflows |
| health/readiness semantics | bootstrap/fallback paths |
| active artifact policy | dummy artifacts и validation outputs |
| smoke/integration checks | training/export и dataset tooling |
| handoff docs для интеграции | transitional logic и исторический технический задел |

Ключевое правило миграции:

- clean repo получает только issue-scoped перенос;
- draft repo остается источником правды по текущему состоянию и validation context;
- массовое копирование директорий, runtime-кода и артефактов запрещено.

## 8. Предлагаемая структура будущего репозитория

Ниже описана целевая структура, а не текущие файлы foundation-этапа.

```text
docs/
.github/
configs/
src/
  api/
  contracts/
  runtime/
  pipelines/
    pose_words/
    words_baseline/   # только если baseline нужен осознанно
  features/
    pose/
  segmentation/
  inference/
  decoding/
tests/
tools/
artifacts/
```

Принципы этой структуры:

- transport/API слой должен быть тонким;
- contract layer должен быть versioned и явным;
- runtime orchestration не должен жить вперемешку с train/export кодом;
- artifacts должны быть отделены от validation outputs и bootstrap fallback;
- baseline-модули допускаются только как явно ограниченные и вторичные.

## 9. Приоритеты migration

Рекомендуемый порядок переноса:

1. Зафиксировать integration contract, mock mode и runtime boundaries.
2. Собрать runtime skeleton с `/health` и `/ready`.
3. Подготовить перенос `pose_words` wrappers и segmentation runtime.
4. Выделить active artifact manifest/load path без переноса лишних validation/bootstrap outputs.
5. Добавить smoke, contract и integration checks.
6. Подготовить handoff notes и минимально необходимую docs migration.

Что не переносится на раннем этапе:

- training/export scripts;
- dataset и synthetic builders;
- bootstrap/dummy artifacts как рабочий путь;
- validation reports и manual experiment outputs;
- mixed frontend/backend demo contour из draft repo.

Эти шаги уже разложены по backlog-задачам и должны мигрировать именно так:

- `MIG-01` — перенос только product-runtime-oriented docs и архитектурных договоренностей;
- `CTR-01` и `CTR-02` — integration contract и mock protocol mode;
- `RT-01` и `RT-02` — runtime skeleton и health/readiness semantics;
- `PW-01` и `PW-02` — перенос `pose_words` runtime surface и segmentation layer;
- `ART-01` — active artifact manifest/load path;
- `QA-01` и `INT-01` — smoke/integration checks и handoff docs.

## 10. Интеграционный слой

### WebSocket contract

Clean repo должен содержать versioned WebSocket contract для sign-to-text runtime:

- с явной `contract_version`;
- с зафиксированными обязательными и optional полями;
- с отдельным описанием control messages, payload и ошибок;
- с документированной совместимостью для web team.

Текущая зафиксированная версия контракта описана в [docs/contracts/websocket-contract-v1.md](contracts/websocket-contract-v1.md).

### Mock mode

До полной готовности runtime нужен mock protocol mode:

- для параллельной работы web team;
- для контрактных и smoke-проверок;
- для воспроизводимых integration fixtures без зависимости от живого runtime.

### Feature flags

Нужны feature flags или эквивалентный конфигурационный слой для:

- переключения `mock` / `live` режимов;
- включения optional debug payload;
- управляемого включения нестабильных integration частей без ломающего поведения.

### Health/readiness

Clean runtime должен иметь как минимум:

- `/health` для базового статуса сервиса;
- `/ready` для readiness и проверки критических runtime dependencies;
- явную индикацию missing artifacts и активного artifact profile;
- недвусмысленную семантику для integration и smoke automation.

### Smoke/integration checks

Минимальный набор проверок для clean repo:

- contract checks на payload и versioning;
- mock-based integration checks;
- backend smoke на startup/readiness/runtime surface;
- integration smoke для handoff с web team;
- manual checks там, где без них нельзя подтвердить стабильность.

Все эти элементы описывают target clean architecture. Их наличие должно появляться поэтапно через отдельные milestones и issues, а не объявляться реализованным заранее.

Draft-only operational details из validation/bootstrap контура сюда не переносятся как уже существующее поведение clean repo. Это относится к локальным install/promote workflow, validation outputs, конкретным активным профилям артефактов и recovery path: на этапе `M0` в clean repo фиксируется только архитектурный принцип, что active runtime artifacts, readiness gates и smoke semantics должны быть отделены от bootstrap и validation context и вводиться через отдельные задачи.
