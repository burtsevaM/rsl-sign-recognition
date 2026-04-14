# Mock protocol mode для contract v1

## 1. Назначение

Этот документ фиксирует `mock protocol mode` как **отдельный документированный integration path** поверх `WebSocket contract v1`.

`mock mode` нужен для двух практических сценариев:

- web team может собирать и проверять клиентскую интеграцию до появления live runtime surface в clean repo;
- smoke-checks могут воспроизводимо прогонять минимальные contract-level сценарии без зависимости от живого backend runtime.

Важно:

- `mock mode` не является live runtime behavior;
- `mock mode` не меняет смысл `contract v1`;
- `mock mode` не добавляет новые protocol-level поля в live messages;
- clean repo по-прежнему не объявляет live runtime реализованным.

## 2. Связь с CTR-01

`CTR-02` опирается на `CTR-01`, а не существует параллельно ему.

Это означает:

- `mock mode` использует тот же JSON envelope: `type`, `contract_version`, `payload`;
- `mock mode` повторяет те же stable поля, что и `contract v1`;
- `mock mode` по умолчанию не требует optional debug/runtime blocks;
- fixtures для `mock mode` должны оставаться совместимыми с правилами `docs/contracts/websocket-contract-v1.md`.

Для `CTR-02` зафиксирована та же версия контракта: `contract_version = "1.0"`.

## 3. Scope

В scope этого документа входят:

- описание цели `mock mode` и его границ;
- канонический способ активации `mock mode` через integration/config boundary;
- минимальный набор mock fixtures для web integration и smoke-checks;
- правила, какие поля web team может использовать в `mock` так же, как в `live`;
- явное разведение `mock path` и `real runtime path`.

## 4. Non-goals

В scope этой задачи не входят:

- реализация live runtime;
- backend migration;
- полный integration handoff;
- реализация mock server или mock adapter в коде clean repo;
- новые обязательные поля live-контракта;
- новые protocol-level markers вроде `mock`, `session_id`, `request_id`, `trace_id`;
- `session.start` / `session.stop`;
- фиксация `/health`, `/ready`, artifact readiness или runtime activation logic.

## 5. Канонический activation path

### 5.1. Что считается каноническим

Канонический способ включения `mock mode` для clean repo — **внешний integration/config selection на границе интеграции**, сделанный **до** начала конкретной session.

Практически это означает:

- web client, smoke runner или отдельный integration harness выбирает источник сообщений заранее;
- при выборе `mock` источником становятся подготовленные fixtures или их управляемое воспроизведение;
- при выборе `live` источником остается реальный runtime path через `WS /ws/stream`.

### 5.2. Что не считается допустимым activation path

Для `CTR-02` недопустимо:

- добавлять поле вроде `mock: true` в `recognition.result`, `control.ack` или `error`;
- вводить новый обязательный handshake внутри live-протокола;
- смешивать включение `mock` с live payload semantics;
- использовать presence/absence optional debug blocks как переключатель между `mock` и `live`.

## 6. Соотношение mock path и live path

| Аспект | Mock path | Live path |
| --- | --- | --- |
| Источник сообщений | Fixtures или их контролируемое воспроизведение | Реальный runtime |
| Точка активации | Внешний integration/config boundary | Реальный transport/runtime boundary |
| Envelope | Такой же, как в `contract v1` | Такой же, как в `contract v1` |
| Stable поля | Те же, что в `contract v1` | Те же, что в `contract v1` |
| Optional debug/runtime blocks | По умолчанию не требуются | Могут присутствовать, но не обязательны |
| Назначение | Web integration и smoke-checks без live runtime | Реальная runtime-интеграция |

Ключевое правило:

`mock path` должен быть виден как **controlled integration path**, а не как разновидность live runtime behavior.

## 7. Stable surface, которую можно использовать и в mock, и в live

### 7.1. Для `recognition.result`

Web team и smoke-checks могут одинаково опираться на:

- `type`
- `contract_version`
- `payload.status`
- `payload.word`
- `payload.confidence`
- `payload.hand_present`
- `payload.hold`
- `payload.text_state.value`
- `payload.text_state.committed`
- `payload.timestamp_ms`

### 7.2. Для `control.ack`

Можно одинаково опираться на:

- `type`
- `contract_version`
- `payload.action`
- `payload.accepted`

### 7.3. Для `error`

Можно одинаково опираться на:

- `type`
- `contract_version`
- `payload.code`
- `payload.message`
- `payload.recoverable`

`payload.details` допустим, но не является обязательной частью mock surface.

## 8. Какие поля нельзя считать обязательными

Для `mock mode` и `live path` одинаково нельзя считать обязательными:

- `topk`
- `skeleton`
- `segments`
- `perf`
- `bio`
- `debug`
- `segment_event`
- `state_detail`
- `vlm`
- `top1`
- `mode`
- `letter`
- `score`
- `bbox_norm`
- `payload.details` внутри `error`

Отсутствие этих полей не является нарушением контракта для `CTR-02`.

## 9. Минимально обязательные fixtures

В рамках `CTR-02` минимальный набор fixtures зафиксирован таким:

| Файл | Сценарий | Назначение |
| --- | --- | --- |
| `docs/contracts/fixtures/mock-recognition-result-hold.json` | `recognition.result` со статусом `HOLD` | Проверка partial/live state без commit |
| `docs/contracts/fixtures/mock-recognition-result-commit.json` | `recognition.result` со статусом `COMMIT` | Проверка committed update через `text_state.committed = true` |
| `docs/contracts/fixtures/mock-control-ack-clear-text.json` | `control.ack` для `clear_text` | Проверка control path без live runtime |
| `docs/contracts/fixtures/mock-session-error-runtime-unavailable.json` | session-level `error` | Проверка non-recoverable error path |

Этот набор намеренно минимален:

- он покрывает стабильные contract-level сценарии;
- он не делает вид, что mock mode уже описывает полный runtime lifecycle;
- он не раздувает scope optional debug/runtime payload blocks.

## 10. Как использовать fixtures

Рекомендуемый способ использования:

1. integration layer заранее выбирает `mock path`;
2. после этого клиент или smoke harness читает fixture payload как готовое JSON-сообщение `contract v1`;
3. разбор сообщения и UI-логика используют те же stable поля, что и для live path;
4. различение `mock` и `live` происходит на integration boundary, а не внутри payload.

Для `recognition.result` это особенно важно:

- `HOLD` fixture проверяет partial/live state;
- `COMMIT` fixture проверяет committed update;
- ни один из fixtures не вводит новые поля ради mock-only семантики.

## 11. Что эта задача осознанно не решает

`CTR-02` не решает следующие вопросы:

- какой именно mock adapter или mock server будет использован в следующем integration increment;
- как именно воспроизводить последовательность из нескольких fixtures на уровне конкретного test harness;
- как будут устроены `health` / `ready` и artifact gates;
- как live runtime позже будет подключаться к web team поверх реального backend;
- как выглядит полный handoff package для `INT-01`.

Это осознанные ограничения задачи. Они не должны маскироваться под уже существующую реализацию.
