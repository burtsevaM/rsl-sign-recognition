# DATA-03 / PW-08 - train/validation subset для demo gestures

## Назначение

Эта директория фиксирует воспроизводимый train/validation subset contract для 10 demo gestures и runtime-required class `_no_event`. Subset нужен, чтобы следующая задача `MODEL-02 / PW-09` могла обучать classifier на отдельных train/validation данных, а не на live smoke samples.

Эта задача не обучает модель, не экспортирует artifact, не меняет decoder thresholds и не закрывает `#76` напрямую.

## Содержимое

- `manifest.json` - source contract, target counts, split policy и правила canonicalization;
- `materialized_manifest.json` - фактически найденные sample records с `sha256`, `byte_size`, `source_path` и status по class;
- этот `README.md` - report по источникам, splits, ограничениям и связи с downstream задачами.

Локальный `Slovo` найден в старом проекте `mvp1`:

```text
/Users/mariaburtseva/Documents/проект грант/mvp1/SuperLuchito--SimpleGesture2Letter-Model-Version-2/backend/data/slovo
```

Внутри найден `slovo.zip` с `annotations.csv`, `15300` train videos и `5100` test videos. Полный archive занимает около 15 GB и в Git не добавляется.

## Что найдено

`привет` найден в `Slovo` как source label `Привет!`: 15 train / 5 validation до exclusion. Это orthographic/runtime canonicalization, а не semantic remap: sample records сохраняют `source_label = "Привет!"`, а canonical `label = "привет"`.

`_no_event` найден в `Slovo` как source label `no_event`: 300 train / 100 validation до target selection. Materialization берет 10 train / 4 validation и сохраняет `source_label = "no_event"`, canonical `label = "_no_event"`.

Semantic synonyms не подгоняются вручную. Например, `здравствуйте` не remap-ится в `привет`, а `работа` не remap-ится в `работать`.

## Расширенный поиск

Перед materialization проверены обязательные локальные источники:

- `backend/data/slovo` и `backend/data/slovo/slovo.zip` в старом `mvp1` project - найден `annotations.csv`, videos, source label `Привет!` и source label `no_event`;
- `backend/data/slovo_repo` - найден upstream example video `f17a6060...mp4`, который соответствует live smoke sample и остается excluded;
- `backend/data/pose_words_validation`, `backend/artifacts`, `backend/artifacts/validation/pose_words`, `backend/artifacts/runtime/active/pose_words` - найдены labels/configs и synthetic validation context, но они не использованы как train/validation source для этого subset;
- текущий clean repo `data/live_samples`, `data/demo_gestures`, `artifacts`, `docs` - найден live smoke bundle и active labels; heavy videos/archives не добавлялись.

Отдельный `slovo_full360.zip` в проверенных локальных путях не найден, но для этой доработки он больше не нужен: `_no_event` обнаружен как явный label `no_event` в уже доступном `slovo.zip`.

## Итоговые counts

| class | target train | target validation | materialized train | materialized validation | status | notes |
| --- | ---: | ---: | ---: | ---: | --- | --- |
| `привет` | 15 | 5 | 14 | 5 | `shortage` | source label `Привет!`; `slovo_privet_f17a6060` исключен как live smoke |
| `пока` | 15 | 5 | 14 | 5 | `shortage` | source label `Пока`; один train sample исключен |
| `да` | 15 | 5 | 14 | 5 | `shortage` | один train sample исключен |
| `хорошо` | 15 | 5 | 14 | 5 | `shortage` | один train sample исключен |
| `плохо` | 15 | 5 | 14 | 5 | `shortage` | source label `Плохо`; один train sample исключен |
| `утро` | 15 | 5 | 15 | 4 | `shortage` | один validation sample исключен |
| `улица` | 15 | 5 | 14 | 5 | `shortage` | один train sample исключен |
| `дом` | 15 | 5 | 14 | 5 | `shortage` | один train sample исключен |
| `вода` | 15 | 5 | 14 | 5 | `shortage` | один train sample исключен |
| `работать` | 15 | 5 | 14 | 5 | `shortage` | source label `работать`; один train sample исключен |
| `_no_event` | 10 | 4 | 10 | 4 | `ok` | source label `no_event`; fake samples не создаются |

Нет classes со status `missing` или `blocked`. Все 10 demo gestures имеют `train > 0` и `validation > 0`; `_no_event` также материализован.

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
- собирается только из явных `Slovo` rows с source label `no_event`;
- не создается из random slices, dummy videos или placeholder clips.

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

## Как проверить status

```bash
python3 - <<'PY'
import json
from pathlib import Path

manifest = json.loads(Path("data/demo_gestures/materialized_manifest.json").read_text(encoding="utf-8"))
for label, item in manifest["class_status"].items():
    print(label, item["materialized_train"], item["materialized_validation"], item["status"])
PY
```

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
python3.11 -m json.tool data/demo_gestures/materialized_manifest.json
```

Targeted tests:

```bash
python3 -m pytest tests/test_demo_gestures_dataset_manifest.py
python3 -m pytest tests/test_materialize_demo_gestures_dataset.py
```

Полный локальный контур для этого PR:

```bash
python3.11 -m compileall src tests scripts
python3 -m pytest
```

Проверка на реальном local Slovo:

```bash
python3 scripts/materialize_demo_gestures_dataset.py \
  --slovo-root "/Users/mariaburtseva/Documents/проект грант/mvp1/SuperLuchito--SimpleGesture2Letter-Model-Version-2/backend/data/slovo"
```

## Готовность для MODEL-02 / PW-09

`#79` можно закрывать через `Closes #79`: все 10 demo gestures имеют реальные train/validation records, `_no_event` подготовлен из явных Slovo `no_event` rows, live smoke samples исключены, heavy videos/archives не попадают в Git.

Остающееся ограничение: после exclusion live smoke clips большинство gesture classes имеют 19 usable samples вместо target 20. Это честно отражено status `shortage` и не маскируется как full 15/5.
