# DATA-03 / PW-08 - train/validation subset для demo gestures

## Назначение

Эта директория фиксирует воспроизводимый train/validation subset contract для 10 demo gestures. Он нужен, чтобы следующая задача `MODEL-02 / PW-09` обучала classifier не на одном live smoke sample на слово, а на отдельном наборе train/validation данных.

Эта задача не обучает модель, не экспортирует artifact, не меняет decoder thresholds и не закрывает `#76` напрямую.

## Содержимое

- `manifest.json` - machine-readable manifest dataset subset-а;
- этот `README.md` - report по источникам, splits, ограничениям и связи с downstream задачами.

Полный `Slovo` archive в Git не добавлен: основной trimmed archive занимает около 16 GB. Поэтому текущий PR хранит external-source manifest и правила materialization, а не тяжелые dataset archives.

## Финальный demo dictionary

| gesture | train count | validation count | source | notes |
| --- | ---: | ---: | --- | --- |
| `привет` | 15 | 5 | Slovo trimmed archive | live smoke sample `slovo_privet_f17a6060` исключается из train/validation |
| `пока` | 15 | 5 | Slovo trimmed archive | upstream spelling `Пока`, runtime label lowercase |
| `да` | 15 | 5 | Slovo trimmed archive | live smoke sample из PR #77 исключается |
| `хорошо` | 15 | 5 | Slovo trimmed archive | live smoke sample из PR #77 исключается |
| `плохо` | 15 | 5 | Slovo trimmed archive | upstream spelling `Плохо`, runtime label lowercase |
| `утро` | 15 | 5 | Slovo trimmed archive | live smoke sample из PR #77 исключается |
| `улица` | 15 | 5 | Slovo trimmed archive | live smoke sample из PR #77 исключается |
| `дом` | 15 | 5 | Slovo trimmed archive | live smoke sample из PR #77 исключается |
| `вода` | 15 | 5 | Slovo trimmed archive | live smoke sample из PR #77 исключается |
| `работать` | 15 | 5 | Slovo trimmed archive | подтвержденный upstream label, не заменен на `работа` |

Дополнительно зафиксирован runtime-required background class:

| class | train count | validation count | source | notes |
| --- | ---: | ---: | --- | --- |
| `_no_event` | 10 | 4 | Slovo original/360p non-gesture intervals | требуется current `pose_words` label set; должен быть материализован локально из legal no-hand/pause windows |

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
- не материализован в Git в этом PR, потому что для честного выделения нужны large original/360p source files.

## Как отделены live smoke samples

Live smoke bundle из PR #77 остается отдельным downstream QA input:

- PR: `https://github.com/burtsevaM/rsl-sign-recognition/pull/77`;
- branch: `feat/DATA-02-QA-04-live-smoke-10-gestures`;
- manifest: `data/live_samples/manifest.json`.

Все sample IDs из PR #77 перечислены в `manifest.json` в `live_smoke_relation.excluded_sample_ids`. Они не должны использоваться как единственная обучающая база и не должны попадать в train/validation materialization. После MODEL-02 / PW-09 они нужны для честного возврата к `#76` / PR #77.

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

Если полный Slovo archive доступен локально, MODEL-02 / PW-09 должен дополнительно проверить materialization против `annotations.csv`, физических `.mp4` файлов, checksums и исключения live smoke sample IDs.

## Ограничения / риски

- Это external-source manifest, а не self-contained dataset archive.
- Локальный `/Users/mariaburtseva/Documents/проект грант/RSL_slovo` сейчас пуст, поэтому физические train/validation clips не добавлены.
- Counts в manifest являются target source-group counts для materialization из Slovo annotations; они должны быть подтверждены перед training.
- `_no_event` остается самым слабым классом: он требуется runtime/model pipeline, но legal no-hand/pause windows нужно материализовать отдельно из original/360p source.
- Возможен domain shift между Slovo train/validation subset и live smoke videos из PR #77.
- Эта задача разблокирует `MODEL-02 / PW-09`, но сама не обучает active classifier pack и не обновляет `artifacts/runtime/active/pose_words`.
