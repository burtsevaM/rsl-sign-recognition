# rsl-sign-recognition

`rsl-sign-recognition` — clean repository для ML-модуля распознавания РЖЯ в сценарии sign-to-text. Его задача — стать местом для воспроизводимого runtime-контура, интеграционного контракта, runtime-facing документации и поэтапной миграции из draft-репозитория в более чистую долгоживущую структуру.

На foundation-этапе этот репозиторий намеренно содержит только документацию, process assets и GitHub templates. Продуктовый runtime-код, backend wiring, модели, артефакты, конфиги и operational scripts сюда еще не перенесены.

## Что это за репозиторий

Этот репозиторий нужен как clean home для воспроизводимого ML runtime, который позже будет использоваться для интеграции с веб-платформой и других product-oriented сценариев.

Сюда будет переноситься только то, что соответствует этим требованиям:

- относится к целевому runtime-контуру, а не к исследовательской среде;
- имеет понятные границы, контракт и назначение;
- может поддерживаться через issue-based процесс;
- не зависит от скрытой локальной магии, черновых bootstrap-путей и случайных артефактов.

## Scope clean repo

Целевой scope этого репозитория:

- versioned integration contract для sign-to-text runtime;
- skeleton и сервисные границы будущего runtime;
- `pose_words` как основной pipeline для word recognition;
- policy для active runtime artifacts, readiness и smoke/integration checks;
- handoff-документация и reproducible process для дальнейшей миграции.

На текущем foundation-этапе здесь уже есть:

- `README.md`;
- `CONTRIBUTING.md`;
- архитектурная, roadmap и backlog-документация;
- PR template и issue templates;
- каноническая система milestones, epics, labels и task-кодов.

## Что остаётся в draft repo

Репозиторий `gesture-recognition-draft` остаётся местом для:

- экспериментов и research-веток;
- validation path и technical validation;
- bootstrap/fallback сценариев;
- training/export scripts и датасетных утилит;
- transitional logic во время миграции;
- исторического и технического задела, который еще не выделен в clean runtime.

Именно там пока продолжают жить смешанные runtime/training/validation/experimental части. Clean repo не должен притворяться, что этот контур уже перенесен.

## Текущее архитектурное направление

Для словарного распознавания целевым основным pipeline зафиксирован `pose_words`.

Это означает:

- `pose_words` рассматривается как основной будущий product path для word recognition;
- `words` сохраняется как baseline/reference до закрытия validation и integration условий;
- `words` не считается равноправным долгосрочным product path в clean architecture;
- `letters` не является равноправным word-oriented runtime path для clean repo и может рассматриваться только отдельной продуктовой задачей.

Наличие этого решения не означает, что clean repo уже содержит рабочий runtime или production-ready реализацию. На текущем этапе зафиксированы только foundation-границы и migration path.

## Документация

- [docs/architecture.md](docs/architecture.md) — назначение clean repo, целевая архитектура и границы миграции
- [docs/roadmap.md](docs/roadmap.md) — milestones `M0`-`M3`, зависимости и критерии завершения
- [docs/backlog.md](docs/backlog.md) — epics, стартовые задачи, recommended labels и acceptance criteria
- [CONTRIBUTING.md](CONTRIBUTING.md) — правила работы через issues, branches и PR

## Процесс разработки и migration approach

- Перенос из draft repo идет не массовым копированием, а через milestones, epics и отдельные issues.
- Любой перенос кода, документации или контрактов из `gesture-recognition-draft` должен иметь явную задачу, scope и acceptance criteria.
- Изменения архитектуры, интеграционного контракта или artifact policy должны сопровождаться обновлением документации в том же PR.
- Пока не начаты отдельные migration tasks, этот репозиторий остается foundation-скелетом без продуктового runtime-кода.

Следующие шаги уже зафиксированы в backlog как issue-scoped migration path, а не как массовый перенос файлов:

- `CTR-01` и `CTR-02` — integration contract и mock protocol mode;
- `RT-01` и `RT-02` — runtime skeleton и health/readiness semantics;
- `PW-01` и `PW-02` — перенос `pose_words` runtime wrapper и segmentation runtime;
- `ART-01` — active artifact manifest/load path;
- `QA-01` и `INT-01` — smoke/integration strategy и handoff notes.

При этом текущий docs-only этап переносит только product-runtime-oriented формулировки и архитектурные договоренности. Validation workflows, bootstrap/fallback path, локальные active artifact profiles и machine-local operational runbooks остаются в `gesture-recognition-draft` до отдельных migration tasks.

Итоговая идея проста: `rsl-sign-recognition` — это clean repo для воспроизводимого product-oriented ML runtime, а `gesture-recognition-draft` остается исследовательским и переходным контуром до поэтапной миграции.
