# DATA-03 / PW-08 - train/validation subset для demo gestures

## Назначение

Эта директория фиксирует воспроизводимый train/validation subset contract для 10 demo gestures. Он нужен, чтобы следующая задача `MODEL-02 / PW-09` обучала classifier не на одном live smoke sample на слово, а на отдельном наборе train/validation данных.

Эта задача не обучает модель, не экспортирует artifact, не меняет decoder thresholds и не закрывает `#76` напрямую.

## Содержимое

- `manifest.json` - machine-readable manifest dataset subset-а;
- этот `README.md` - report по источникам, splits, ограничениям и связи с downstream задачами.

Локальный `Slovo` найден в старом проекте `mvp1`:

```text
/Users/mariaburtseva/Documents/проект грант/mvp1/SuperLuchito--SimpleGesture2Letter-Model-Version-2/backend/data/slovo
```

Внутри найден `slovo.zip` с `annotations.csv`, `15300` train videos и `5100` test videos. Полный archive занимает около 15 GB и в Git не добавляется.

## Финальный demo dictionary

| gesture | target train | target validation | materialized train | materialized validation | notes |
| --- | ---: | ---: | ---: | ---: | --- |
| `привет` | 15 | 5 | 0 | 0 | label отсутствует в local `annotations.csv`; live smoke sample исключен |
| `пока` | 15 | 5 | 14 | 5 | upstream spelling `Пока`; один train sample исключен как live smoke |
| `да` | 15 | 5 | 14 | 5 | один train sample исключен как live smoke |
| `хорошо` | 15 | 5 | 14 | 5 | один train sample исключен как live smoke |
| `плохо` | 15 | 5 | 14 | 5 | upstream spelling `Плохо`; один train sample исключен как live smoke |
| `утро` | 15 | 5 | 15 | 4 | один validation sample исключен как live smoke |
| `улица` | 15 | 5 | 14 | 5 | один train sample исключен как live smoke |
| `дом` | 15 | 5 | 14 | 5 | один train sample исключен как live smoke |
| `вода` | 15 | 5 | 14 | 5 | один train sample исключен как live smoke |
| `работать` | 15 | 5 | 14 | 5 | upstream label `работать`; один train sample исключен как live smoke |

Дополнительно зафиксирован runtime-required background class:

| class | target train | target validation | materialized train | materialized validation | notes |
| --- | ---: | ---: | ---: | ---: | --- |
| `_no_event` | 10 | 4 | 0 | 0 | требуется current `pose_words` label set; нужны legal no-hand/pause windows, fake samples не создаются |

## Dataset split

Train split:

- для gesture classes используются строки `Slovo` annotations с `train=True`;
- target count: 15 samples на gesture;
- порядок отбора: stable sort by `attachment_id`;
- live smoke sample IDs из PR #77 исключаются, если встречаются в source rows.

Validation split:

- для gesture classes используются строки `Slovo` annotations с `train=False`;
- target count: 5 samples на gesture;
- порядок отбора: stable sort by `attachment_id`;
- live smoke sample IDs из PR #77 исключаются.

`_no_event`:

- нужен, потому что current active classifier labels содержат `_no_event`, а runtime переводит этот label в `no_result`;
- должен собираться из legal no-hand/pause windows вне annotated gesture intervals;
- не материализован автоматически из trimmed `slovo.zip`, потому что trimmed clips содержат жесты, а не явные background windows.

## Materialization

Script:

```text
scripts/materialize_demo_gestures_dataset.py
```

Рекомендуемый запуск через env:

```bash
export SLOVO_DATA_ROOT="/Users/mariaburtseva/Documents/проект грант/mvp1/SuperLuchito--SimpleGesture2Letter-Model-Version-2/backend/data/slovo"
python3 scripts/materialize_demo_gestures_dataset.py --slovo-root "$SLOVO_DATA_ROOT"
```

Вариант с локальным symlink, если так удобнее для повторных запусков:

```bash
mkdir -p data/raw
ln -s "/Users/mariaburtseva/Documents/проект грант/mvp1/SuperLuchito--SimpleGesture2Letter-Model-Version-2/backend/data/slovo" data/raw/slovo
python3 scripts/materialize_demo_gestures_dataset.py --slovo-root data/raw/slovo
```

`data/raw/` находится в `.gitignore`; symlink и heavy dataset files не должны попадать в commit.

Output manifest:

```text
data/demo_gestures/materialized_manifest.json
```

Materialized manifest содержит только metadata, source paths, `byte_size` и `sha256`. Видео и `slovo.zip` не копируются в clean repo.

Если `Slovo` не распакован, script умеет читать `slovo.zip` напрямую. Если передан unpacked root, script ищет `annotations.csv` и `.mp4` под этим root.

## Как отделены live smoke samples

Live smoke bundle из PR #77 остается отдельным downstream QA input:

- PR: `https://github.com/burtsevaM/rsl-sign-recognition/pull/77`;
- branch: `feat/DATA-02-QA-04-live-smoke-10-gestures`;
- manifest: `data/live_samples/manifest.json`.

Все sample IDs из PR #77 перечислены в `manifest.json` в `live_smoke_relation.excluded_sample_ids`. Script также читает `data/live_samples/manifest.json`, если он есть в checkout-е. Exclusion применяется по `sample_id` и короткому `attachment_id`, поэтому clips из PR #77 не попадают в materialized train/validation rows.

## Source / License / Attribution

Основной источник данных:

- upstream repository: `https://github.com/hukenovs/slovo`;
- dataset download: `https://rndml-team-cv.obs.ru-moscow-1.hc.sbercloud.ru/datasets/slovo/slovo.zip`;
- paper: `https://arxiv.org/abs/2305.14527`;
- license: `CC BY-SA 4.0`;
- license URL: `https://creativecommons.org/licenses/by-sa/4.0/`;
- attribution: `Slovo Russian Sign Language Dataset and Models, hukenovs/slovo`.

Dataset content в этом PR не модифицируется. Будущая materialization может копировать выбранные clips под repo-local именами только после checksum/file validation и с сохранением attribution.

## Проверки

Быстрая проверка JSON:

```bash
python3.11 -m json.tool data/demo_gestures/manifest.json
```

Targeted manifest tests:

```bash
python3 -m pytest tests/test_demo_gestures_dataset_manifest.py
```

Полный локальный контур для этого PR:

```bash
python3.11 -m compileall src tests scripts
python3 -m pytest tests/test_demo_gestures_dataset_manifest.py
python3 -m pytest
```

Проверка на реальном local Slovo:

```bash
python3 scripts/materialize_demo_gestures_dataset.py \
  --slovo-root "/Users/mariaburtseva/Documents/проект грант/mvp1/SuperLuchito--SimpleGesture2Letter-Model-Version-2/backend/data/slovo"
```

## Ограничения / риски

- Это manifest + metadata, а не self-contained dataset archive.
- `привет` отсутствует в local `annotations.csv`; единственный known sample `slovo_privet_f17a6060` остается live smoke input и исключен из training.
- После исключения live smoke clips из PR #77 большинство Slovo-backed gestures имеют 19 usable samples вместо target 20.
- `_no_event` остается самым слабым классом: он требуется runtime/model pipeline, но legal no-hand/pause windows нужно материализовать отдельно из original/360p source.
- Возможен domain shift между Slovo train/validation subset и live smoke videos из PR #77.
- Эта задача разблокирует `MODEL-02 / PW-09`, но сама не обучает active classifier pack и не обновляет `artifacts/runtime/active/pose_words`.
