# WebSocket contract v1 для sign-to-text runtime

## 1. Назначение документа

Этот документ фиксирует **versioned WebSocket contract v1** для sign-to-text runtime в clean-репозитории `rsl-sign-recognition`.

Это именно **целевой stable contract v1** для clean repo.

Важно:

- contract v1 не обязан один в один совпадать с текущим wire format из `gesture-recognition-draft`;
- при этом он опирается на подтвержденный draft runtime context там, где это помогает избежать выдуманной интеграционной семантики;
- для прямой интеграции со старым draft runtime может потребоваться adapter или migration layer.

Документ нужен для того, чтобы:

- убрать неоднозначность integration surface до активной runtime migration;
- дать web team минимальный и стабильный контракт для интеграции;
- зафиксировать честный contract-level contour без заявлений, что clean repo уже содержит полный runtime.

### Scope v1

В scope этой версии входят:

- transport-level правила для `WS /ws/stream`;
- формат client -> server сообщений;
- формат server -> client сообщений;
- правила передачи `contract_version`;
- отделение stable integration surface от optional debug/runtime blocks;
- handoff-правила для web team.

### Что не входит в scope v1

В scope этой задачи **не входят**:

- runtime implementation;
- mock mode implementation;
- `/health` и `/ready`;
- artifact readiness и runtime artifact policy;
- перенос inference logic, segmentation logic и product code;
- training/export code, configs, scripts и validation outputs.

## 2. Контекст

`rsl-sign-recognition` пока остается clean docs-first repository и еще не содержит перенесенный product runtime.

Контракт v1 фиксируется **раньше**, чем активная runtime migration, чтобы web team могла опираться на согласованный интерфейс, а не на случайные поля из draft runtime.

При подготовке v1 использовались два источника контекста:

- фактическое поведение в `gesture-recognition-draft`: `WS /ws/stream`, binary JPEG frames, JSON control packet `clear_text`, общий inference payload и optional `skeleton` / `segments` / `perf` / `bio`;
- integration-ожидания из `grant-project`: web team нужен стабильный WebSocket handoff, predictable partial/final semantics и явная обработка ошибок.

### Нормализация по сравнению с draft repo

v1 намеренно **сужает и формализует** текущий draft-контур:

- не добавляет неподтвержденный `session.start` / `session.stop`;
- не делает `mock` частью live-контракта;
- сохраняет binary JPEG stream как основной вход;
- вводит versioned JSON envelope для всех JSON-сообщений;
- оставляет runtime/debug payload строго optional.

## 3. Версионирование контракта

### Текущая версия

Текущая зафиксированная версия контракта: **`1.0`**.

### Где передается `contract_version`

- Во всех **JSON** сообщениях `client -> server` поле `contract_version` обязательно.
- Во всех **JSON** сообщениях `server -> client` поле `contract_version` обязательно.
- Binary frame packets `client -> server` поле `contract_version` **не содержат** и наследуют версию открытого `WS /ws/stream` соединения.
- Для v1 само подключение к документированному endpoint `WS /ws/stream` уже означает работу по контракту `1.x`.

### Что можно менять без breaking change

Без breaking change допустимо:

- добавлять новые optional поля;
- добавлять новые optional debug/runtime blocks;
- расширять `details` внутри error payload;
- уточнять документацию без изменения семантики.

### Что считается breaking change

Breaking change для v1:

- удаление обязательного поля;
- переименование обязательного поля;
- изменение типа обязательного поля;
- изменение смысла существующего обязательного поля;
- замена binary JPEG input на другой обязательный transport format;
- введение новых обязательных client messages до отправки кадров;
- изменение того, как определяется committed/final состояние.

### Когда повышать minor и major version

- `1.0` -> `1.1`, `1.2` и т.д.: для additive non-breaking изменений.
- `1.x` -> `2.0`: для любого breaking change.

### Как web team должна реагировать на несовместимую версию

- Если `major` отличается от ожидаемого, web team должна считать контракт несовместимым, прекратить парсинг payload и показать controlled integration error.
- Если `major` совпадает, а `minor` выше ожидаемого, web team должна продолжать работу по известным required полям и игнорировать неизвестные optional поля.

## 4. Транспортные допущения

### Transport

- Transport: `WebSocket`
- Endpoint v1: `WS /ws/stream`

### High-level lifecycle

1. Клиент открывает `WS /ws/stream`.
2. Успешное открытие сокета считается стартом runtime session.
3. Клиент отправляет binary JPEG frames.
4. Сервер возвращает stream JSON-сообщений `recognition.result`.
5. При необходимости клиент отправляет `control.clear_text`.
6. Сервер отвечает `control.ack`.
7. Закрытие WebSocket считается завершением session.

### Что ожидается от клиента

- отправлять binary packets только как JPEG-encoded frame bytes;
- использовать JSON только для control messages;
- не рассчитывать на строгую связь `1 frame -> 1 result`;
- игнорировать неизвестные optional поля при совместимом `major`.

### Что ожидается от сервера

- принимать binary JPEG stream без дополнительного JSON wrapper;
- возвращать versioned JSON messages;
- не требовать mock-specific behavior в live-контракте v1;
- не считать отсутствие optional debug blocks ошибкой.

### Что считается transport-level, а что payload-level

- **Transport-level**: открытие/закрытие WebSocket, binary JPEG packet как frame input.
- **Payload-level**: JSON envelope, `type`, `contract_version`, `payload`, result/error semantics.

### Что v1 намеренно не фиксирует

CTR-01 **не фиксирует** как часть контракта:

- hard limits по `fps`, resolution и `jpeg_quality`;
- keepalive/ping protocol;
- explicit `request_id`, `trace_id`, `session_id`;
- base64 JSON frame fallback.

Эти пункты требуют отдельного runtime/integration уточнения и не должны выдумываться в рамках v1.

## 5. Общая структура JSON-сообщения

Все JSON-сообщения в v1 используют единый envelope.

| Поле | Обязательность | Тип | Семантика |
| --- | --- | --- | --- |
| `type` | обязательно | `string` | Тип сообщения. |
| `contract_version` | обязательно | `string` | Версия контракта. Для v1: `1.0` или совместимая `1.x`. |
| `payload` | обязательно | `object` | Содержимое сообщения. |

### Правила envelope

- Клиент и сервер должны игнорировать неизвестные поля envelope, если `major` совместим.
- `payload` не должен быть `null`.
- Для binary frame packets envelope **не используется**.

### Типы сообщений в v1

| Направление | `type` | Назначение |
| --- | --- | --- |
| `client -> server` | `control.clear_text` | Сбросить накопленный transcript и текущее runtime state в рамках текущей session. |
| `server -> client` | `recognition.result` | Передать текущее sign-to-text состояние. |
| `server -> client` | `control.ack` | Подтвердить обработку control message. |
| `server -> client` | `error` | Сообщить о protocol/runtime problem. |

## 6. Входные сообщения (`client -> server`)

### 6.1. Binary frame packet

Это **не JSON message**, а transport-level binary packet.

#### Назначение

Передает следующий JPEG-кадр в текущую WebSocket session.

#### Формат

- WebSocket binary frame
- payload: полные JPEG bytes одного кадра

#### Обязательные требования

- packet должен быть JPEG-декодируемым;
- packet не содержит JSON envelope;
- packet интерпретируется как очередной frame текущей session.

#### Ограничения

- v1 не обещает strict `request/response` correlation на уровне кадра;
- сервер может пропускать или коалесцировать обработку части кадров под нагрузкой;
- клиент не должен ждать отдельный ack на каждый кадр.

#### Порядок использования

- Можно отправлять только после успешного WebSocket connect.
- Можно отправлять многократно до закрытия соединения.

### 6.2. `control.clear_text`

#### Назначение

Сбрасывает накопленный transcript и текущий decoder/session state без переоткрытия сокета.

#### JSON-структура

| Поле | Обязательность | Тип | Семантика |
| --- | --- | --- | --- |
| `type` | обязательно | `string` | Должно быть равно `control.clear_text`. |
| `contract_version` | обязательно | `string` | Версия контракта, например `1.0`. |
| `payload` | обязательно | `object` | Для v1 должен быть пустым объектом `{}`. |

#### Ограничения

- `payload` не используется для передачи business-data;
- unsupported action под тем же envelope должна приводить к `error`;
- команда влияет только на текущую открытую WebSocket session.

#### Порядок использования

- Может отправляться в любой момент после открытия сокета.
- После успешной обработки сервер должен прислать `control.ack`.

#### Пример JSON

```json
{
  "type": "control.clear_text",
  "contract_version": "1.0",
  "payload": {}
}
```

## 7. Выходные сообщения (`server -> client`)

### 7.1. `recognition.result`

Это основной message type для sign-to-text stream.

v1 **не разделяет** stream на отдельные `partial.result` и `final.result` message types. Вместо этого:

- текущее live-состояние приходит как `recognition.result`;
- committed/final состояние определяется через `payload.text_state.committed`.

Это решение принято осознанно, потому что фактический draft runtime уже работает как единый поток однотипных inference messages, а не как два разных output channel.

#### Обязательные stable поля `payload`

| Поле | Обязательность | Тип | Можно использовать в UI как stable surface | Семантика |
| --- | --- | --- | --- | --- |
| `status` | обязательно | `string` | да | Текущее runtime state. |
| `word` | обязательно | `string` | да | Текущий token-кандидат или только что committed token. Если token отсутствует, допускается `NONE`. |
| `confidence` | обязательно | `number` | да | Confidence текущего `word` в диапазоне `0..1`. |
| `hand_present` | обязательно | `boolean` | да | Есть ли сейчас достаточно данных во входе для sign detection. |
| `hold` | обязательно | `object` | да | Прогресс до commit threshold. |
| `text_state` | обязательно | `object` | да | Текущее накопленное текстовое состояние session. |
| `timestamp_ms` | обязательно | `integer` | да | Серверный monotonic timestamp для упорядочивания внутри session. Это не wall-clock UTC timestamp. |

#### Допустимые значения `status`

| Значение | Статус в v1 | Семантика |
| --- | --- | --- |
| `NONE` | stable | Нет подтвержденного token-кандидата. |
| `HOLD` | stable | Кандидат есть, но commit threshold еще не достигнут. |
| `UNKNOWN` | stable | Кандидат есть, но confidence/margin недостаточны для commit. |
| `COMMIT` | stable | Текущий `word` был committed в `text_state.value` в этом сообщении. |
| `COOLDOWN` | stable | Временный post-commit cooldown. |
| `POSE` | optional runtime-specific | Есть tracking/pose state без готового word result. UI не должна полагаться на это значение как на обязательное. |

#### Структура `hold`

| Поле | Обязательность | Тип | Семантика |
| --- | --- | --- | --- |
| `elapsed_ms` | обязательно | `integer` | Сколько единиц уже накоплено. |
| `remaining_ms` | обязательно | `integer` | Сколько единиц осталось до target. |
| `target_ms` | обязательно | `integer` | Целевое значение hold threshold. |
| `progress` | обязательно | `number` | Нормализованный прогресс `0..1`. |
| `unit` | обязательно | `string` | Единица измерения: `ms`, `frames` или `segments`. |

**Важно:**

поля `elapsed_ms` / `remaining_ms` / `target_ms` сохраняют исторические имена из draft payload, но их нужно интерпретировать **только вместе с** `hold.unit`.

#### Структура `text_state`

| Поле | Обязательность | Тип | Семантика |
| --- | --- | --- | --- |
| `value` | обязательно | `string` | Накопленный committed transcript текущей session. |
| `committed` | обязательно | `boolean` | `true`, если именно это сообщение добавило текущий `word` в `value`. |

#### Optional field `error` внутри `recognition.result`

`payload.error` допустим как **recoverable frame-local error block**, если runtime продолжает session.

Формат такой же, как у `error.payload`, но его нельзя использовать как замену общему session-level `error` message.

#### Пример minimal `recognition.result`

```json
{
  "type": "recognition.result",
  "contract_version": "1.0",
  "payload": {
    "status": "HOLD",
    "word": "ПРИВЕТ",
    "confidence": 0.91,
    "hand_present": true,
    "hold": {
      "elapsed_ms": 1,
      "remaining_ms": 1,
      "target_ms": 2,
      "progress": 0.5,
      "unit": "segments"
    },
    "text_state": {
      "value": "",
      "committed": false
    },
    "timestamp_ms": 12451893
  }
}
```

#### Пример committed `recognition.result`

```json
{
  "type": "recognition.result",
  "contract_version": "1.0",
  "payload": {
    "status": "COMMIT",
    "word": "ПРИВЕТ",
    "confidence": 0.96,
    "hand_present": true,
    "hold": {
      "elapsed_ms": 2,
      "remaining_ms": 0,
      "target_ms": 2,
      "progress": 1.0,
      "unit": "segments"
    },
    "text_state": {
      "value": "ПРИВЕТ",
      "committed": true
    },
    "timestamp_ms": 12451961
  }
}
```

### 7.2. `control.ack`

#### Когда отправляется

После успешной обработки `control.clear_text`.

#### Структура `payload`

| Поле | Обязательность | Тип | Семантика |
| --- | --- | --- | --- |
| `action` | обязательно | `string` | Подтвержденное действие. Для v1: `clear_text`. |
| `accepted` | обязательно | `boolean` | Для v1 при успехе всегда `true`. |

#### Пример JSON

```json
{
  "type": "control.ack",
  "contract_version": "1.0",
  "payload": {
    "action": "clear_text",
    "accepted": true
  }
}
```

### 7.3. `error`

#### Когда отправляется

Для protocol-level или session-level ошибок, когда клиент должен скорректировать поведение или завершить текущую сессию.

#### Структура `payload`

| Поле | Обязательность | Тип | Семантика |
| --- | --- | --- | --- |
| `code` | обязательно | `string` | Machine-readable code. |
| `message` | обязательно | `string` | Human-readable message. Можно безопасно показывать пользователю в сокращенном виде. |
| `recoverable` | обязательно | `boolean` | Можно ли продолжать текущую session без переоткрытия сокета. |
| `details` | опционально | `object` | Диагностические детали для логов. Не обязательны и не должны использоваться как UI contract. |

#### Минимальный набор `code` для v1

| `code` | Recoverable | Когда использовать |
| --- | --- | --- |
| `unsupported_contract_version` | нет | Клиент запросил несовместимую major version. |
| `invalid_json` | да | Пришел некорректный JSON control packet. |
| `unsupported_message_type` | да | Пришел неизвестный JSON `type`. |
| `unsupported_control_action` | да | Пришел неподдержанный control action. |
| `frame_decode_failed` | да | Сервер не смог декодировать текущий binary frame. |
| `runtime_unavailable` | нет | Runtime не может продолжать работу для этой session. |
| `internal_error` | нет | Необработанная серверная ошибка. |

#### Пример JSON

```json
{
  "type": "error",
  "contract_version": "1.0",
  "payload": {
    "code": "runtime_unavailable",
    "message": "Runtime is unavailable for the current session.",
    "recoverable": false,
    "details": {
      "reason": "segmentation_runtime_unavailable"
    }
  }
}
```

## 8. Разделение stable contract и optional debug/runtime blocks

Это ключевая граница v1.

### 8.1. Stable integration surface

Web team может опираться только на следующие поля `recognition.result.payload`:

- `status`
- `word`
- `confidence`
- `hand_present`
- `hold`
- `text_state`
- `timestamp_ms`
- optional `error` только как recoverable notice

Отсутствие других полей **не должно** считаться нарушением контракта.

### 8.2. Что подтверждено текущим draft runtime

Ниже перечислено то, на что этот документ опирается как на **подтвержденный draft runtime context**, а не как на новую выдуманную семантику:

| Элемент | Статус источника | Как трактуется в clean contract v1 |
| --- | --- | --- |
| `WS /ws/stream` | подтверждено draft runtime | Используется как целевой transport endpoint v1. |
| Binary JPEG frames | подтверждено draft runtime | Остаются обязательным transport input path v1. |
| `control.clear_text` | подтверждено draft runtime | Сохраняется как supported control message v1. |
| Единый поток `recognition.result` | подтверждено draft runtime | Не вводятся искусственные `partial.result` / `final.result` в рамках CTR-01. |
| `payload.text_state.committed` как признак committed update | подтверждено draft-aligned semantics | Используется как stable способ различать live/committed состояние в v1. |
| Optional blocks `skeleton`, `segments`, `perf`, `bio` | подтверждено draft runtime | Считаются допустимыми optional blocks, но не частью minimum stable surface. |
| Исторические поля и aliases вроде `letter`, `score`, runtime-specific diagnostics | подтверждено draft/runtime context частично | Могут встречаться как legacy/runtime payload details, но не являются required contract surface. |

### 8.3. Что допускается или резервируется clean contract v1

Ниже перечислены поля и блоки, которые **допускаются в clean contract v1**, но их наличие или точная форма **не гарантируется текущей draft-реализацией** как обязательная часть интеграции.

Ниже перечислены поля, которые допускаются в v1, но **не являются обязательными** и не должны использоваться как единственный источник product-логики.

| Поле / блок | Статус в v1 | Для чего существует | Что должна делать web team |
| --- | --- | --- | --- |
| `mode` | optional runtime | Внутренний runtime mode (`words`, `pose_words`). | Не использовать для product decision-making. |
| `letter` | optional legacy | Исторический alias текущего token. | Предпочитать `word`. |
| `score` | optional runtime | Raw model score. | Предпочитать `confidence`. |
| `bbox_norm` | optional runtime | Внутренние координаты detection box. | Игнорировать, если UI не строит debug overlay. |
| `topk` | optional runtime | Список кандидатов и score. | Можно показывать только как debug. |
| `vlm` | optional legacy/runtime | Данные VLM decision path из draft repo. | Не считать обязательным для sign-to-text UI. |
| `debug` | optional runtime | Произвольные внутренние numeric diagnostics. | Не использовать как стабильный API. |
| `top1` | optional runtime | Детализация top1/no-event логики. | Игнорировать в основном UI. |
| `state_detail` | optional runtime | Внутренние счетчики hold/cooldown. | Не опираться на exact shape. |
| `skeleton` | optional debug | Raw/norm pose landmarks. | Использовать только для debug overlay. |
| `segments` | optional debug/runtime | Segmentation windows/sign/phrase segments. | Не считать обязательным для UX основного переводчика. |
| `perf` | optional debug/runtime | Latency/FPS/drop metrics. | Использовать только для diagnostics. |
| `bio` | optional debug/runtime | Snapshot segmentation configuration/state. | Не использовать как stable API. |
| `segment_event` | optional debug/runtime | Последний segment event. | Не считать reliable contract-level commit marker. |

Дополнительное правило интерпретации:

- перечисление блока в этой таблице означает, что clean contract v1 **разрешает** его появление;
- это **не означает**, что текущий draft runtime всегда присылает такой блок в стабильной форме;
- это также **не означает**, что web team должна строить обязательную логику вокруг этого блока.

### 8.4. Обязательное правило для optional blocks

- optional blocks могут отсутствовать полностью;
- optional blocks могут появляться частично;
- добавление новых optional blocks в рамках `1.x` не считается breaking change;
- product UI не должна ломаться при их отсутствии.

#### Пример `recognition.result` с optional debug/runtime blocks

```json
{
  "type": "recognition.result",
  "contract_version": "1.0",
  "payload": {
    "status": "HOLD",
    "word": "ПРИВЕТ",
    "confidence": 0.91,
    "hand_present": true,
    "hold": {
      "elapsed_ms": 1,
      "remaining_ms": 1,
      "target_ms": 2,
      "progress": 0.5,
      "unit": "segments"
    },
    "text_state": {
      "value": "",
      "committed": false
    },
    "timestamp_ms": 12451893,
    "topk": [
      { "letter": "ПРИВЕТ", "score": 0.91 },
      { "letter": "СПАСИБО", "score": 0.07 }
    ],
    "segments": {
      "sign": [
        { "start": 31, "end": 42, "score": 0.88 }
      ],
      "phrase": []
    },
    "perf": {
      "latency_ms": 48.3,
      "fps_in": 6.0,
      "fps_total": 5.7
    },
    "debug": {
      "margin": 0.22
    }
  }
}
```

## 9. Ошибки и служебные ответы

### Recoverable vs non-recoverable

**Recoverable**

- `invalid_json`
- `unsupported_message_type`
- `unsupported_control_action`
- `frame_decode_failed`
- `recognition.result.payload.error` при продолжении session

Ожидаемое поведение клиента:

- показать мягкое сообщение;
- продолжить session или повторить действие;
- записать `code` и `details` в логи, если это нужно.

**Non-recoverable**

- `unsupported_contract_version`
- `runtime_unavailable`
- `internal_error`

Ожидаемое поведение клиента:

- считать текущую session завершенной или непригодной;
- предложить reconnect / повтор позже;
- не продолжать парсинг как будто stream остается валидным.

### Что можно безопасно показывать пользователю

Можно показывать:

- короткое human-readable сообщение на основе `payload.message`;
- мягкое указание на повтор попытки, если `recoverable = true`;
- controlled failure state, если `recoverable = false`.

Не нужно показывать пользователю без фильтрации:

- `details`;
- raw debug blocks;
- внутренние runtime причины из optional payload fields.

## 10. Handoff для web team

### Minimum stable contract для интеграции

Для интеграции web team достаточно поддержать следующий минимум:

1. открыть `WS /ws/stream`;
2. отправлять binary JPEG frames;
3. опционально отправлять `control.clear_text`;
4. принимать JSON envelope с `type`, `contract_version`, `payload`;
5. из `recognition.result.payload` использовать только stable поля.

### На какие поля web team может опираться

- `payload.status`
- `payload.word`
- `payload.confidence`
- `payload.hand_present`
- `payload.hold`
- `payload.text_state.value`
- `payload.text_state.committed`
- `payload.timestamp_ms`

### Как трактовать partial/final without separate message types

- `payload.text_state.committed = false`: это live/partial state.
- `payload.text_state.committed = true`: это final/committed token update.

Таким образом web team получает expected partial/final semantics **без** выдумывания дополнительного message type, которого сейчас нет в фактическом draft runtime.

### Какие поля web team должна игнорировать, если их нет

Если отсутствуют, это **нормально**:

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

### Как безопасно обрабатывать ошибки

- Для `type = "error"` ориентироваться на `payload.code`, `payload.message`, `payload.recoverable`.
- Для recoverable случаев не ронять UI и позволять продолжить stream.
- Для non-recoverable случаев завершать текущую session и предлагать reconnect.
- `details` использовать только для логов/диагностики.

### Ожидания по backward compatibility

- В пределах `1.x` web team должна игнорировать неизвестные optional поля.
- В пределах `1.x` existing stable поля не должны менять тип и смысл.
- Несовместимая major version требует явного обновления клиента.

### Соотношение с CTR-02

CTR-02 (`mock protocol mode`) должен:

- использовать тот же envelope;
- повторять те же stable поля;
- иметь право не включать optional debug/runtime blocks по умолчанию.

CTR-01 фиксирует контракт так, чтобы CTR-02 мог строиться **поверх него**, а не параллельно ему.

### Что web team не должна ожидать от CTR-01

CTR-01 **не обещает**:

- `session.start` / `session.stop`;
- mock adapter;
- ready/health semantics;
- artifact readiness;
- жестко зафиксированный operational profile по `fps` и resolution;
- полную parity с draft debug UI.

## 11. Non-goals

Прямо вне scope этого документа:

- runtime implementation;
- mock mode implementation;
- readiness/health behavior;
- artifact readiness;
- перенос inference logic;
- перенос segmentation runtime;
- перенос runtime configs;
- перенос training/export code;
- перенос product/backend/frontend code из `gesture-recognition-draft`;
- массовое копирование директорий или fixtures из draft repo.

## 12. Open questions / assumptions

### Зафиксированные assumptions для v1

- Session lifecycle в v1 определяется через **WebSocket open/close**, потому что это подтверждено текущим draft runtime и не требует выдумывать неподтвержденный handshake.
- Binary JPEG frame stream остается единственным обязательным input path v1.
- `recognition.result` остается единым output stream; committed/final определяется через `text_state.committed`.

### Open questions, которые осознанно не решаются в CTR-01

- Нужно ли позже вводить явные `session.start` / `session.stop`.
- Нужен ли отдельный `warning` message type.
- Нужно ли фиксировать hard transport profile по `fps`, resolution и retry strategy.
- Нужно ли выносить `request_id` / `trace_id` / `session_id` в future contract version.
- Нужно ли полностью убирать статус `POSE` из future runtime-ready contract после завершения runtime migration.

Эти вопросы важны, но их решение относится к следующим integration/runtime задачам, а не к фиксации минимального contract v1.
