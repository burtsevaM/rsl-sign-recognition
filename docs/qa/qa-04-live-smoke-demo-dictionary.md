# QA-04 - Live smoke demo dictionary

## Цель

`QA-04` расширяет live e2e smoke после минимального `QA-03` с одного sample `привет` до небольшого проверяемого demo dictionary.

Эта задача не обучает новую модель. Она отвечает на другой вопрос: какие gestures можно честно положить в переносимый live bundle уже сейчас и что текущий active runtime/model setup реально делает с этим набором.

## Финальный bundle

| sample_id | expected_label | source | modified |
| --- | --- | --- | --- |
| `slovo_privet_f17a6060` | `привет` | public example video | `false` |
| `slovo_poka_8ba230dc` | `пока` | trimmed dataset archive | `false` |
| `slovo_da_2b1b2857` | `да` | trimmed dataset archive | `false` |
| `slovo_horosho_43791c91` | `хорошо` | trimmed dataset archive | `false` |
| `slovo_ploho_27560a7e` | `плохо` | trimmed dataset archive | `false` |
| `slovo_utro_c1766b2e` | `утро` | trimmed dataset archive | `false` |
| `slovo_ulica_908f133b` | `улица` | trimmed dataset archive | `false` |
| `slovo_dom_524d6b8f` | `дом` | trimmed dataset archive | `false` |
| `slovo_voda_90db4617` | `вода` | trimmed dataset archive | `false` |
| `slovo_rabotat_ffce2323` | `работать` | trimmed dataset archive | `false` |

Финальный список зафиксирован также в [data/live_samples/manifest.json](../../data/live_samples/manifest.json) и [docs/qa/live-sample-bundle.md](live-sample-bundle.md).

## Замены относительно исходного плана

В bundle удалось подтвердить базовые gestures `привет`, `пока`, `да`, `хорошо`, `плохо`.

Слова `спасибо`, `пожалуйста`, `нет`, `можно`, `помощь` в выбранном legal source не нашлись как те же labels, поэтому использованы запасные `утро`, `улица`, `дом`, `вода`.

Из следующей группы запасных вариантов `мама` и `папа` в source также не подтвердились как те же labels. Для планового слова `работа` в Slovo нашелся только отдельный upstream label `работать`; он добавлен как десятый sample без ручной подмены label.

## Команды

Полный прогон:

```bash
python3 scripts/run_live_e2e_smoke.py --base-url http://127.0.0.1:8000
```

Один sample:

```bash
python3 scripts/run_live_e2e_smoke.py \
  --base-url http://127.0.0.1:8000 \
  --sample-id slovo_privet_f17a6060
```

Runner должен явно печатать:

- `sample_id`;
- expected label;
- actual label;
- `PASS` / `FAIL`;
- confidence;
- `committed`;
- итоговый summary вида `K/N passed`.

## Интерпретация результата

Текущий active classifier pack содержит только `_no_event`, `привет`, `пока`. Поэтому ожидаемо, что расширенный bundle может показать data/model gap на gestures вне текущего label set.

Если итог ниже `8/10`, это не нужно маскировать. Такой PR описывается как data investigation: bundle, manifest, runner и документация расширены, но сам active model setup еще не подтверждает достаточное покрытие demo dictionary. Для полноценного закрытия `#76` нужен совместимый active classifier pack из model issue `#78`.

## Фактический live smoke result

Дата прогона: `2026-05-19`.

| sample_id | expected | actual | result | confidence | committed |
| --- | --- | --- | --- | --- | --- |
| `slovo_privet_f17a6060` | `привет` | `привет` | `PASS` | `0.717108` | `true` |
| `slovo_poka_8ba230dc` | `пока` | `-` | `FAIL` | `-` | `false` |
| `slovo_da_2b1b2857` | `да` | `-` | `FAIL` | `-` | `false` |
| `slovo_horosho_43791c91` | `хорошо` | `-` | `FAIL` | `-` | `false` |
| `slovo_ploho_27560a7e` | `плохо` | `-` | `FAIL` | `-` | `false` |
| `slovo_utro_c1766b2e` | `утро` | `-` | `FAIL` | `-` | `false` |
| `slovo_ulica_908f133b` | `улица` | `-` | `FAIL` | `-` | `false` |
| `slovo_dom_524d6b8f` | `дом` | `-` | `FAIL` | `-` | `false` |
| `slovo_voda_90db4617` | `вода` | `-` | `FAIL` | `-` | `false` |
| `slovo_rabotat_ffce2323` | `работать` | `-` | `FAIL` | `-` | `false` |

Summary полного runner-а: `1/10 passed`.

Проверенный single-sample run:

```bash
python3.11 scripts/run_live_e2e_smoke.py \
  --base-url http://127.0.0.1:8000 \
  --sample-id slovo_privet_f17a6060
```

Результат single-sample run: `1/1 passed`.

## Что делать при failed samples

1. Сохранить фактический smoke result в PR description.
2. Не удалять failed samples из bundle только ради красивого summary.
3. Не заменять реальные clips synthetic/placeholder input-ом.
4. До появления active pack из `#78` не считать `#76` закрытой через `Closes`.
