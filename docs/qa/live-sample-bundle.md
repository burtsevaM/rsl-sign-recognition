# DATA-02 - Live sample bundle для QA-04

## 1. Назначение

Этот документ фиксирует переносимый bundle реального live input для `QA-04` / issue `#76`.

Bundle нужен не для offline evaluation и не для доказательства качества модели. Его задача практичнее: дать live e2e smoke небольшой demo dictionary, который можно прогнать через настоящий runtime path:

`backend -> /ready=200 -> WS /ws/stream -> binary JPEG frames -> recognition.result -> expected label`

`DATA-02` не обучает новую модель. Он расширяет bundle и честно показывает, какие gestures текущий active runtime/model setup уже распознает, а какие пока остаются live smoke gap.

## 2. Финальный набор gestures

Текущий tracked bundle содержит `10` legal/portable real-video samples:

| sample_id | expected_label | source | frames / duration / fps | local path |
| --- | --- | --- | --- | --- |
| `slovo_privet_f17a6060` | `привет` | public example video | `112 / 3.733333 s / 30 fps` | `data/live_samples/videos/slovo-privet-f17a6060.mp4` |
| `slovo_poka_8ba230dc` | `пока` | trimmed dataset archive | `48 / 1.600000 s / 30 fps` | `data/live_samples/videos/slovo-poka-8ba230dc.mp4` |
| `slovo_da_2b1b2857` | `да` | trimmed dataset archive | `30 / 1.000000 s / 30 fps` | `data/live_samples/videos/slovo-da-2b1b2857.mp4` |
| `slovo_horosho_43791c91` | `хорошо` | trimmed dataset archive | `34 / 1.133333 s / 30 fps` | `data/live_samples/videos/slovo-horosho-43791c91.mp4` |
| `slovo_ploho_27560a7e` | `плохо` | trimmed dataset archive | `42 / 1.400000 s / 30 fps` | `data/live_samples/videos/slovo-ploho-27560a7e.mp4` |
| `slovo_utro_c1766b2e` | `утро` | trimmed dataset archive | `27 / 0.900000 s / 30 fps` | `data/live_samples/videos/slovo-utro-c1766b2e.mp4` |
| `slovo_ulica_908f133b` | `улица` | trimmed dataset archive | `37 / 1.233333 s / 30 fps` | `data/live_samples/videos/slovo-ulica-908f133b.mp4` |
| `slovo_dom_524d6b8f` | `дом` | trimmed dataset archive | `45 / 1.500000 s / 30 fps` | `data/live_samples/videos/slovo-dom-524d6b8f.mp4` |
| `slovo_voda_90db4617` | `вода` | trimmed dataset archive | `44 / 1.466667 s / 30 fps` | `data/live_samples/videos/slovo-voda-90db4617.mp4` |
| `slovo_rabotat_ffce2323` | `работать` | trimmed dataset archive | `46 / 1.533333 s / 30 fps` | `data/live_samples/videos/slovo-rabotat-ffce2323.mp4` |

Machine-readable metadata хранится в [data/live_samples/manifest.json](../../data/live_samples/manifest.json).

## 3. Что вошло и что пришлось заменить

Из базового списка issue удалось подтвердить:

- `привет`
- `пока`
- `да`
- `хорошо`
- `плохо`

Для `спасибо`, `пожалуйста`, `нет`, `можно`, `помощь` в выбранном legal source не нашлись те же labels. Вместо них использованы разрешенные запасные слова:

- `утро`
- `улица`
- `дом`
- `вода`

Из следующей группы запасных вариантов `мама` и `папа` в source также не подтвердились как те же labels, а вместо планового `работа` в Slovo есть отдельный реальный upstream label `работать`. Он добавлен как десятый sample без ручной нормализации в `работа`, чтобы bundle оставался честным к source metadata.

## 4. Источник данных и metadata

Все samples происходят из публичного проекта `Slovo: Russian Sign Language Dataset and Models`:

- upstream repository: `https://github.com/hukenovs/slovo`;
- license: `CC BY-SA 4.0`;
- license URL: `https://creativecommons.org/licenses/by-sa/4.0/`;
- attribution: `Slovo Russian Sign Language Dataset and Models, hukenovs/slovo`.

`привет` сохранен из public example video, добавленного в `DATA-01`. Остальные девять clips извлечены без изменения content bytes из trimmed dataset archive `slovo.zip`; у них изменено только repository-local имя файла. Для `Пока` и `Плохо` source metadata отдельно хранит оригинальное upstream spelling, а `expected_label` использует normalized lowercase форму, согласованную с runtime-facing labels. Для десятого sample source label `работать` сохранен буквально и не подменен плановым словом `работа`.

Каждая запись manifest фиксирует:

- `sample_id`;
- `expected_label`;
- repo-relative `local_path`;
- `upstream_repository` / `upstream_path`;
- `license` / `license_url`;
- `attribution`;
- `modified` / `modification_notes`;
- `frame_count`;
- `duration_seconds`;
- `fps`;
- `sha256`;
- `byte_size`.

## 5. Размещение bundle-а

Перед запуском smoke bundle должен лежать в checkout-е по относительным путям:

```text
data/live_samples/
  README.md
  manifest.json
  videos/
    slovo-privet-f17a6060.mp4
    slovo-poka-8ba230dc.mp4
    slovo-da-2b1b2857.mp4
    slovo-horosho-43791c91.mp4
    slovo-ploho-27560a7e.mp4
    slovo-utro-c1766b2e.mp4
    slovo-ulica-908f133b.mp4
    slovo-dom-524d6b8f.mp4
    slovo-voda-90db4617.mp4
    slovo-rabotat-ffce2323.mp4
```

Быстрая проверка manifest:

```bash
python3 -m json.tool data/live_samples/manifest.json
```

## 6. Как запускать live smoke

На всем bundle-е:

```bash
python3 scripts/run_live_e2e_smoke.py --base-url http://127.0.0.1:8000 --sample-manifest data/live_samples/manifest.json --max-samples 10 --min-passed 8 --http-timeout-seconds 60
```

На одном sample:

```bash
python3 scripts/run_live_e2e_smoke.py \
  --base-url http://127.0.0.1:8000 \
  --sample-id slovo_privet_f17a6060
```

Runner по умолчанию прогоняет весь bundle, печатает `sample_id`, expected label, actual label, `PASS` / `FAIL`, confidence, `committed` и итоговую статистику. `--max-samples` остается ручным диагностическим ограничителем; `0` означает полный набор.

## 7. Что ожидать от результата

Текущий active MODEL-01 classifier pack содержит `_no_event` и все `10` runtime labels из bundle. Поэтому bundle теперь проверяет не только наличие labels в classifier-е, но и фактическое live e2e поведение на real-video samples:

- passed samples подтверждают strict condition `committed=true` и `actual_label == expected_label`;
- failed samples остаются в summary и показывают текущие live confusions.

Если часть samples не распознается:

1. не скрывать failed rows;
2. сохранять фактический `K/N passed`;
3. не трактовать smoke как обучение модели;
4. открывать отдельные data/model follow-up tasks, если нужен рост покрытия словаря.

Минимальный merge-oriented threshold для `#76` - `8/10 passed`. Если итог ниже `8/10`, результат следует оформлять как data investigation, а не как доказательство готового расширенного распознавания.

### Фактический smoke result на 2026-05-19

Команда:

```bash
./.venv/bin/python scripts/run_live_e2e_smoke.py --base-url http://127.0.0.1:8000 --sample-manifest data/live_samples/manifest.json --max-samples 10 --min-passed 8 --http-timeout-seconds 60
```

| sample_id | expected | actual | result | confidence | committed |
| --- | --- | --- | --- | --- | --- |
| `slovo_privet_f17a6060` | `привет` | `привет` | `PASS` | `0.938670` | `true` |
| `slovo_poka_8ba230dc` | `пока` | `пока` | `PASS` | `0.467108` | `true` |
| `slovo_da_2b1b2857` | `да` | `да` | `PASS` | `0.941735` | `true` |
| `slovo_horosho_43791c91` | `хорошо` | `хорошо` | `PASS` | `0.978893` | `true` |
| `slovo_ploho_27560a7e` | `плохо` | `плохо` | `PASS` | `0.991616` | `true` |
| `slovo_utro_c1766b2e` | `утро` | `дом` | `FAIL` | `0.799179` | `true` |
| `slovo_ulica_908f133b` | `улица` | `улица` | `PASS` | `0.875830` | `true` |
| `slovo_dom_524d6b8f` | `дом` | `дом` | `PASS` | `0.295213` | `true` |
| `slovo_voda_90db4617` | `вода` | `вода` | `PASS` | `0.999952` | `true` |
| `slovo_rabotat_ffce2323` | `работать` | `работать` | `PASS` | `0.991799` | `true` |

Итог: `9/10 passed`.

Отдельный single-sample прогон:

```bash
./.venv/bin/python scripts/run_live_e2e_smoke.py \
  --base-url http://127.0.0.1:8000 \
  --sample-manifest data/live_samples/manifest.json \
  --sample-id slovo_privet_f17a6060
```

Итог single-sample run: `1/1 passed`.

Фактический результат превысил merge-oriented ориентир `8/10`, поэтому DATA-02 / QA-04 может закрывать `#76`. Ограничения остаются честно зафиксированы: `утро` проходит через committed event, но распознается как `дом`, поэтому этот smoke не является production-quality benchmark-ом или доказательством полного качества модели.

## 8. Что не считается валидной заменой

Для `QA-04` и будущих расширений bundle-а **не считаются** валидной заменой:

- synthetic clips;
- pre-segmented feature clips;
- mock responses;
- machine-local absolute paths;
- placeholder videos;
- metadata без понятного source/license/attribution.

## 9. Ограничения

- Bundle содержит `10` legal samples, но десятый жест использует подтвержденный upstream label `работать`, потому что плановый label `работа` в выбранном source отсутствует.
- Текущий active model setup является lightweight MODEL-01 classifier pack для demo dictionary, а не production-quality моделью.
- Один live smoke не является benchmark-ом и не заменяет dataset-level evaluation.
- Расширение набора данных и подключение active classifier pack теперь разделены честно: bundle сделан здесь, MODEL-01 pack подключен через отдельную model issue `#78`.
