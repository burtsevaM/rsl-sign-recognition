# ROADMAP

## Планирование и допущения

- дата foundation-планирования: **19 марта 2026 года**;
- на старте `rsl-sign-recognition` не содержит перенесенного продуктового runtime-кода;
- migration идет по задачам, а не массовым переносом файлов из draft repo;
- `gesture-recognition-draft` остается основным источником архитектурной правды, validation context и переходных решений;
- критическая внешняя зависимость: readiness интеграции с web team и доступность активного runtime contour для handoff.

## Канонические milestones

### M0 — Foundation & Process

Срок: **до 29 марта 2026 года**

Цель:
- создать clean foundation для дальнейшей issue-based миграции.

Что должно быть готово:
- root docs (`README`, `CONTRIBUTING`, `architecture`, `roadmap`, `backlog`);
- PR template и issue templates;
- канонические milestones, epics, labels и task-коды;
- базовый CI skeleton для foundation-level checks;
- явные границы между clean repo и draft repo;
- зафиксированное правило, что runtime-код еще не перенесен.

Зависимости:
- доступ к архитектурным материалам и README из `gesture-recognition-draft`;
- процессовый референс из `grant-project`;
- согласование канонической системы обозначений.

Критерии завершения:
- документация не противоречит сама себе;
- clean repo не содержит случайно перенесенного продуктового кода, артефактов и runtime-конфигов;
- foundation-структура готова для следующего этапа постановки реальных issues.

### M1 — Contract & Runtime Skeleton

Срок: **до 12 апреля 2026 года**

Цель:
- зафиксировать интеграционный контракт и подготовить минимальный runtime skeleton без притворства, что весь ML runtime уже перенесен.

Что должно быть готово:
- WebSocket contract v1;
- mock protocol mode и набор mock fixtures;
- базовый runtime skeleton с явными модульными границами;
- описание `/health` и `/ready`;
- расширение foundation CI под contract/runtime surface.

Зависимости:
- завершение `M0`;
- доступ к draft runtime context и текущему WebSocket payload;
- участие web team в обсуждении contract semantics.

Критерии завершения:
- contract versioning зафиксирован и документирован;
- web team может работать против mock или зафиксированного контракта;
- runtime skeleton не смешивает product scope с training/export и draft-only bootstrap logic.

### M2 — Integration-ready sign-to-text MVP

Срок: **до 31 мая 2026 года**

Цель:
- подготовить clean repo к интеграционно-готовому sign-to-text MVP вокруг `pose_words`.

Что должно быть готово:
- миграционный перенос runtime-core частей для `pose_words`;
- segmentation runtime и inference wrappers в clean boundaries;
- active artifact manifest/load path;
- smoke и integration checks;
- handoff notes для web team.

Зависимости:
- завершение `M1`;
- доступность активных runtime artifacts и согласованный artifact policy;
- совместная проверка с web team;
- ручная проверка ключевых integration сценариев.

Критерии завершения:
- clean repo содержит integration-ready runtime surface для sign-to-text MVP;
- `pose_words` представлен как основной pipeline, а `words` остается baseline/reference;
- есть честные smoke и handoff-материалы без заявлений о production-ready зрелости.

### M3 — Hardening & August Alignment

Срок: **до 31 августа 2026 года**

Цель:
- усилить стабильность, поддержку и интеграционную готовность clean runtime к августовскому этапу проекта.

Что должно быть готово:
- hardening runtime behavior и readiness semantics;
- усиленные smoke/contract/manual checks;
- уточненный artifact lifecycle;
- обновленные handoff/runbook документы;
- согласованный статус baseline/reference для `words` на основе validation и integration данных.

Зависимости:
- завершение `M2`;
- baseline comparison и manual stability validation;
- согласование августовских ожиданий с web team и общим проектным планом.

Критерии завершения:
- clean repo поддерживаем и понятен как основной runtime-oriented contour;
- известные ограничения и ручные проверки явно документированы;
- архитектурные материалы готовы к августовскому handoff без смешения clean и draft обязанностей.

## Критический путь

1. Закрыть foundation и каноническую систему обозначений в `M0`.
2. Зафиксировать contract v1 и mock mode в `M1`.
3. Поднять runtime skeleton и readiness semantics в `M1`.
4. Перенести минимально необходимый `pose_words` runtime surface в `M2`.
5. Закрыть artifact policy, smoke checks и handoff notes к `M2`.
6. Провести hardening и августовское выравнивание в `M3`.

## Управленческий принцип

Каждый milestone должен оставлять после себя честное состояние репозитория:

- не объявлять перенесенным то, что еще живет только в draft repo;
- не смешивать foundation/process с фактической runtime-ready зрелостью;
- не подменять integration readiness наличием чернового validation path.
