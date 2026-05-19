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
python3 scripts/run_live_e2e_smoke.py --base-url http://127.0.0.1:8000 --sample-manifest data/live_samples/manifest.json --max-samples 10 --min-passed 8 --http-timeout-seconds 60
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

Текущий active MODEL-01 classifier pack содержит `_no_event` и все `10` runtime labels из bundle: `привет`, `пока`, `да`, `хорошо`, `плохо`, `утро`, `улица`, `дом`, `вода`, `работать`. Поэтому `QA-04` проверяет уже не наличие labels в pack-е, а фактическое live e2e поведение на переносимых real-video samples.

Минимальный acceptance threshold для merge по `#76` - `8/10 passed`. Даже при выполненном threshold failed samples нельзя скрывать: smoke должен показывать фактические rows, committed state и confusion для каждого gesture.

## Фактический live smoke result

Дата прогона: `2026-05-19`.

| sample_id | expected | actual | result | confidence | committed |
| --- | --- | --- | --- | --- | --- |
| `slovo_privet_f17a6060` | `привет` | `привет` | `PASS` | `0.963399` | `true` |
| `slovo_poka_8ba230dc` | `пока` | `привет` | `FAIL` | `0.551401` | `true` |
| `slovo_da_2b1b2857` | `да` | `да` | `PASS` | `0.988729` | `true` |
| `slovo_horosho_43791c91` | `хорошо` | `хорошо` | `PASS` | `0.978082` | `true` |
| `slovo_ploho_27560a7e` | `плохо` | `плохо` | `PASS` | `0.926392` | `true` |
| `slovo_utro_c1766b2e` | `утро` | `привет` | `FAIL` | `0.778988` | `true` |
| `slovo_ulica_908f133b` | `улица` | `улица` | `PASS` | `0.909317` | `true` |
| `slovo_dom_524d6b8f` | `дом` | `дом` | `PASS` | `0.351574` | `true` |
| `slovo_voda_90db4617` | `вода` | `вода` | `PASS` | `0.999998` | `true` |
| `slovo_rabotat_ffce2323` | `работать` | `работать` | `PASS` | `0.993223` | `true` |

Summary полного runner-а: `8/10 passed`.

Команда полного прогона:

```bash
./.venv/bin/python scripts/run_live_e2e_smoke.py --base-url http://127.0.0.1:8000 --sample-manifest data/live_samples/manifest.json --max-samples 10 --min-passed 8 --http-timeout-seconds 60
```

Проверенный single-sample run:

```bash
./.venv/bin/python scripts/run_live_e2e_smoke.py \
  --base-url http://127.0.0.1:8000 \
  --sample-manifest data/live_samples/manifest.json \
  --sample-id slovo_privet_f17a6060
```

Результат single-sample run: `1/1 passed`.

## Что делать при failed samples

1. Сохранить фактический smoke result в PR description.
2. Не удалять failed samples из bundle только ради красивого summary.
3. Не заменять реальные clips synthetic/placeholder input-ом.
4. Если результат остается не ниже `8/10`, `#76` можно закрывать через `Closes`, но слабые samples нужно оставить в документации и follow-up notes.
