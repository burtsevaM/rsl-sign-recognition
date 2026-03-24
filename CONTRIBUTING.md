# CONTRIBUTING

## Назначение

Этот документ фиксирует правила совместной разработки для `rsl-sign-recognition` как clean ML runtime repository.

Репозиторий развивается через milestones, epics, issues и pull requests. Это не research sandbox: даже на раннем этапе здесь действуют явные правила по scope, миграции и обновлению документации.

## Основные принципы

- не пушить напрямую в `main`;
- каждая заметная правка должна быть привязана к issue из backlog или созданной на его основе задаче;
- один PR должен закрывать одну понятную цель;
- управление задачами строится по модели `milestone -> epic issue -> sub-issues`;
- `sub-issues` используются для иерархии внутри epic, а GitHub Relationships (`blocked by` / `blocking`) — только для реального строгого порядка выполнения;
- документация, контракт и код обновляются синхронно;
- перенос из `gesture-recognition-draft` разрешен только через отдельные migration tasks;
- clean repo не должен получать массово скопированные директории, артефакты или transitional code.

## Стратегия веток

Используем короткоживущие ветки под одну задачу.

Формат имен:

- `feat/<id>-slug`
- `fix/<id>-slug`
- `docs/<id>-slug`
- `chore/<id>-slug`

Примеры:

- `feat/CTR-01-ws-contract-v1`
- `fix/RT-02-readiness-handler`
- `docs/INF-01-foundation-docs`
- `chore/INF-02-ci-skeleton`

## Коммиты

Используем `Conventional Commits`.

Рекомендуемый формат:

```text
type(scope): краткое описание
```

Примеры:

- `docs(repo): bootstrap clean ML repository foundation`
- `feat(contract): add websocket contract v1 draft`
- `chore(ci): add runtime quality skeleton`
- `fix(runtime): correct readiness status mapping`

Допустимые типы:

- `feat`
- `fix`
- `docs`
- `refactor`
- `test`
- `chore`
- `ci`

## Workflow по задачам

1. Выбрать issue из `docs/backlog.md` или создать issue на его основе.
2. Определить milestone и parent epic, если задача входит в epic-level контур.
3. Зафиксировать native GitHub relationships: sub-issue для иерархии и `blocked by` / `blocking` только для зависимостей со строгим порядком выполнения.
4. Согласовать acceptance criteria и создать отдельную ветку по конвенции выше.
5. Выполнить изменение в рамках согласованного scope.
6. Приложить результаты проверки и открыть PR по шаблону.

## Правило миграции из draft repo

`gesture-recognition-draft` используется как источник архитектурной правды, смыслов и исходных формулировок, но не как место для правок в рамках clean repo workflow.

Обязательные правила:

- не переносить код, артефакты, конфиги и scripts без отдельной задачи;
- не копировать черновой репозиторий целиком или крупными блоками;
- в migration issue явно указывать source context, target scope и non-goals;
- переносить только то, что нужно для product-oriented и reproducible runtime;
- если изменение опирается на draft-only bootstrap/fallback path, это должно быть явно описано и изолировано.

## Когда обязательно обновлять документацию

Документация должна обновляться в том же PR, если меняется хотя бы один из пунктов:

- архитектурные границы clean repo;
- integration contract или структура payload;
- runtime behavior, readiness или health semantics;
- artifact policy, manifest или load path;
- roadmap, backlog или migration priorities;
- правила процесса разработки.

Минимум нужно проверить `README.md`, `docs/architecture.md`, `docs/roadmap.md`, `docs/backlog.md` и связанные шаблоны, если они затронуты.

## Краткий PR checklist

Перед открытием PR проверь:

- есть ссылка на issue;
- scope PR не выходит за рамки одной задачи;
- описано, что именно изменилось;
- описано, как изменение проверялось;
- обновлены docs, если менялись архитектура, контракт или процесс;
- в diff нет случайно перенесенных артефактов, runtime-конфигов или product code из draft repo.

## Definition of Done

Задача считается завершенной, если:

- выполнены acceptance criteria issue;
- diff обозримый и соответствует scope задачи;
- документация и контракт обновлены, если это требовалось;
- результаты проверки приложены в PR или явно объяснено, почему проверка пока неприменима;
- изменение не создает ложного впечатления, что clean repo уже содержит полный рабочий ML runtime.
