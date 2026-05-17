# DATA-01 - Live sample bundle для будущего QA-03

## 1. Назначение

Этот документ фиксирует минимальный переносимый bundle реального live input для последующего честного закрытия `QA-03` / issue `#58`.

Bundle нужен не для offline evaluation и не для демонстрации качества модели. Его задача проще и практичнее: дать будущему e2e smoke воспроизводимый источник кадров, который можно декодировать в JPEG и отправить в настоящий runtime path:

`backend -> /ready=200 -> WS /ws/stream -> binary JPEG frames -> recognition.result -> expected label`

## 2. Связь с QA-03 / issue #58

`QA-03` требует проверить не только classifier на готовых признаках, а полный live path через backend и WebSocket transport. Текущая offline validation из [docs/validation/pose_words-offline-quality.md](../validation/pose_words-offline-quality.md) подтверждает labels только на synthetic/pre-segmented feature clips и поэтому не может заменить live e2e sample.

`DATA-01` закрывает именно этот пробел: после появления bundle-а у `QA-03` есть честный video source, на котором можно строить отдельный smoke script/report без mock-подмены live input.

## 3. Выбранные gestures / labels

Для первого минимального bundle выбран один gesture:

| label | Почему выбран |
| --- | --- |
| `привет` | Это active label текущего classifier pack, он уже входит в offline validation target set и показывает более высокий confidence, чем `пока`, на текущем synthetic technical set. Для него также есть небольшой публичный реальный MP4 sample, который можно хранить переносимо прямо в репозитории. |

`пока` остается допустимым следующим кандидатом для расширения bundle-а, потому что он тоже входит в active labels и текущую offline validation. В рамках `DATA-01` он сознательно не добавлен: в доступном контексте не найден сопоставимо маленький и явно верифицируемый переносимый real-video source, а подмена feature clip-ом противоречила бы цели задачи.

## 4. Samples

| sample id | label | expected label | source | format | frames / duration | local path | limitations |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `slovo_privet_f17a6060` | `привет` | `привет` | `Slovo Russian Sign Language Dataset`, public example video `f17a6060-6ced-4bd1-9886-8578cfbb864f.mp4` | `MP4` | `112 frames` | `data/live_samples/videos/slovo-privet-f17a6060.mp4` | Один sample не является benchmark-ом; качество live recognition нужно отдельно подтвердить в `QA-03`; sample хранится как real video input, а не как готовые features. |

Machine-readable metadata хранится в [data/live_samples/manifest.json](../../data/live_samples/manifest.json).

## 5. Источник данных

Sample взят из публичного примера проекта `Slovo: Russian Sign Language Dataset and Models`:

- upstream repository: `hukenovs/slovo`;
- upstream path: `examples/f17a6060-6ced-4bd1-9886-8578cfbb864f.mp4`;
- license: `Creative Commons Attribution-ShareAlike 4.0 International`;
- checksum локальной копии: `sha256=98da3c5da34c473e5c1909db66c1fc81ce694f9ff59db1d392920ecf7bcf17f4`.

Выбор sample-а связан с текущим runtime contour:

- active labels зафиксированы как `_no_event`, `привет`, `пока` в [docs/artifacts/pose_words-active-pack.md](../artifacts/pose_words-active-pack.md);
- current offline validation target set уже включает `привет` и `пока`;
- выбранный sample можно использовать как **live input**, потому что это обычный RGB video clip, из которого будущий smoke извлекает последовательность кадров и сам отправляет их как binary JPEG packets в `WS /ws/stream`.

## 6. Где должен лежать bundle перед запуском smoke

Для текущей tracked-in-repository версии не нужен внешний download step. Перед будущим запуском `QA-03` bundle должен лежать в checkout-е ровно по относительным путям:

```text
data/live_samples/
  README.md
  manifest.json
  videos/
    slovo-privet-f17a6060.mp4
```

Проверка размещения:

```bash
python -m json.tool data/live_samples/manifest.json
shasum -a 256 data/live_samples/videos/slovo-privet-f17a6060.mp4
```

Ожидаемый checksum должен совпадать со значением из `manifest.json`.

## 7. Как будущий QA-03 сможет использовать sample

Будущий `QA-03` smoke должен:

1. прочитать `data/live_samples/manifest.json`;
2. взять MP4 sample по `local_path`;
3. декодировать video в последовательность RGB/JPEG frames без перехода к feature clips;
4. поднять backend и убедиться, что `/ready` вернул `HTTP 200`;
5. открыть `WS /ws/stream`;
6. отправить кадры как binary JPEG packets в документированном live path;
7. дождаться `recognition.result`;
8. сравнить фактически полученный label с `expected_label = "привет"`;
9. явно записать результат проверки и любые несовпадения в будущем report для `QA-03`.

Этот flow использует sample именно как live input source: runtime сам декодирует JPEG, извлекает pose, строит features, сегментирует поток и формирует result. В bundle не хранится готовый tensor `[T, F]`, pre-segmented segment или mock payload.

## 8. Что не считается валидной заменой

Для `QA-03` и будущих расширений bundle-а **не считаются** валидной заменой:

- synthetic clips;
- pre-segmented feature clips;
- mock responses;
- machine-local absolute paths;
- скрытые файлы, доступные только на одном компьютере.

Они могут быть полезны для отдельных offline или contract-level проверок, но не закрывают live e2e acceptance criteria.

## 9. Ограничения и риски

- Bundle пока минимален: он содержит только один gesture sample.
- Один реальный sample не доказывает устойчивое качество модели и не заменяет benchmark.
- Текущий выбор опирается на более сильный offline signal для `привет`, но offline validation все еще synthetic и не гарантирует успешный live result.
- Перед закрытием `QA-03` нужен отдельный ручной или automated прогон через настоящий backend/WebSocket path.
- В этой задаче `QA-03` smoke script не реализуется, `/ready` и runtime logic не меняются.

## 10. Что DATA-01 открывает дальше

После появления этого bundle-а можно вернуться к `QA-03` / issue `#58` и реализовать настоящий e2e smoke без mock-подмены live input. Следующее расширение bundle-а должно происходить только после появления столь же переносимого и проверенного real-video source для второго label.
