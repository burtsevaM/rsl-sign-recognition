# PW-01 — `pose_words` inference wrapper migration scope

## 1. Назначение документа

Этот документ закрывает planning/migration-scope часть issue `#21 PW-01`.

Его задача:

- зафиксировать **source scope** для переноса `pose_words` inference wrapper из `gesture-recognition-draft`;
- определить **target scope** в clean layout `rsl-sign-recognition`;
- отделить runtime-required inference layer от segmentation layer, runtime glue/orchestration и draft-only research/validation/bootstrap контуров;
- перечислить **manual checks** и ограничения для первого code migration increment.

Документ **не** переносит код и **не** объявляет, что clean repo уже содержит рабочий runtime.

## 2. Зависимости и архитектурная привязка

PW-01 опирается на уже зафиксированные planning-границы:

- `RT-01` задаёт target layout и правило, что `inference` хранит model runtime wrappers и model-near postprocessing, `segmentation` остаётся отдельным runtime layer, а `runtime`/`pipelines` отвечают за orchestration и composition;
- `CTR-01` уже фиксирует внешний transport/contract surface, поэтому PW-01 не меняет WebSocket contract и не смешивает wrapper с API payload logic.

Следовательно, scope PW-01 ограничен только тем runtime surface, который нужен для загрузки `pose_words` ONNX wrapper и вызова inference на уже подготовленном clip.

## 3. Source context

### 3.1. Канонические source-файлы

- `gesture-recognition-draft/backend/app/pose_words/model_onnx_pose.py`
- `gesture-recognition-draft/backend/app/pose_words/segment_utils.py`
- `gesture-recognition-draft/backend/app/main.py`

### 3.2. Source responsibilities по файлам

| Source file | Что есть в draft repo | Как трактуется в PW-01 |
| --- | --- | --- |
| `model_onnx_pose.py` | `PoseWordOnnxModel` с model loading, labels loading, optional config loading, path checks, config-vs-ONNX validation, ONNX session init, input/output validation, finite-value sanitization, output normalization, `infer_probs` | **Основной source scope PW-01**. Это и есть runtime-required inference wrapper candidate |
| `segment_utils.py` | `resample_to_fixed_T`, а также buffer/index helpers `clamp_indices`, `_as_buffer_array`, `extract_segment` | В PW-01 кандидатом является только `resample_to_fixed_T` как model-near clip normalization. Buffer slicing и segment extraction в scope PW-01 не входят |
| `main.py` | path resolution, init `PoseWordOnnxModel`, missing-artifact checks, health/readiness state, `SessionProcessor`, вызов wrapper после segmentation | Используется как **source context для boundaries**, но не как объект прямого копирования. Отсюда в target scope переходят только обязанности runtime glue, а не весь код |

## 4. Что именно является source scope для PW-01

### 4.1. Runtime-required inference layer

В **source scope PW-01 входят** следующие обязанности из `model_onnx_pose.py`:

- создание `PoseWordOnnxModel` по переданным путям к ONNX model, labels и optional runtime config;
- fail-fast проверки существования файлов;
- загрузка labels и проверка, что labels file не пустой;
- optional parsing `config_path` как JSON object;
- извлечение из config ожидаемых `labels_total`, `clip_frames`, `input_dim`, если эти поля присутствуют;
- инициализация `onnxruntime.InferenceSession` с CPU provider и runtime options;
- чтение и валидация input shape ONNX model как rank-3 `[B, T, F]`;
- сохранение ожидаемых `clip_frames` и `feature_dim`, если ONNX возвращает статические размеры;
- runtime validation входа в `infer_probs` для shape `[T, F]`;
- sanitization `NaN`/`Inf` перед inference;
- нормализация output в probability vector и проверка размера output против labels;
- helper `find_no_event_index`, потому что это model-label-adjacent логика, а не transport/orchestration.

### 4.2. Model-near preprocessing candidate

Из `segment_utils.py` в **узкий source scope PW-01** входит только:

- `resample_to_fixed_T(seg, T, method="linear")` как подготовка уже готового segment clip к фиксированной длине, требуемой ONNX wrapper.

Почему это относится к PW-01:

- функция не определяет boundaries сегмента;
- не владеет streaming state;
- не читает thresholds или segmentation config;
- не работает с session orchestration;
- решает локальную model-near задачу: преобразовать уже выделенный `[Tseg, F]` в `[T, F]`.

### 4.3. Runtime glue context, который нужно учесть, но не переносить как есть

Из `main.py` PW-01 должен унаследовать только понимание следующих обязанностей:

- runtime layer обязан разрешать artifact paths до передачи их wrapper;
- wrapper init должен вызываться из runtime/orchestration слоя, а не из API/transport;
- init/runtime ошибки wrapper должны быть видимы runtime layer и не должны теряться;
- pipeline вызывает wrapper только на уже подготовленном feature clip, а не на raw frame buffer;
- segmentation и orchestration вызывают wrapper как downstream capability, но не сливаются с ним в один модуль.

Это **context for migration boundaries**, а не scope на перенос `RuntimeContext`, `SessionProcessor`, `health()`, WebSocket handlers или artifact-state логики.

## 5. Что не входит в source scope PW-01

### 5.1. Segmentation layer

Следующие обязанности относятся к `PW-02`, а не к PW-01:

- `StreamingBioSegmenter`, `BioSegmenterOnnxModel`, thresholds loading;
- segment boundary detection и decoder logic;
- buffer management и segment slicing;
- `segment_utils.clamp_indices`;
- `segment_utils._as_buffer_array`;
- `segment_utils.extract_segment`;
- `pose_segmenter.update(...)`, `get_feature_span(...)`, active segment progress, sign/phrase state;
- segmentation-specific debug payload и threshold semantics.

### 5.2. Runtime glue/orchestration вне PW-01

Следующие части `main.py` не входят в PW-01:

- `SessionProcessor` целиком как orchestration unit;
- WebSocket/session flow, `build_inference_message`, text state, cooldown/hold machine;
- metrics, perf aggregation, VLM integration, event logging;
- `health()`/`ready` и full readiness assembly;
- full artifact-state reporting, active profile detection и manifest lookup;
- pose extraction pipeline, worker management и frame-to-feature orchestration.

PW-01 только фиксирует, что такой glue существует и позже должен использовать wrapper как dependency.

### 5.3. Draft-only и out-of-scope контуры

PW-01 не включает:

- training/export scripts;
- validation runners и validation utilities;
- bootstrap/fallback path;
- active artifact manifest/policy;
- `config.yaml` как основной runtime path;
- baseline `words`;
- `letters`;
- unrelated draft modules;
- массовый перенос директорий, configs, artifacts или scripts.

## 6. Target scope в clean repo

### 6.1. Target layer mapping

| Source responsibility | Target layer в clean repo | Входит в PW-01? | Почему |
| --- | --- | --- | --- |
| `PoseWordOnnxModel` init, labels/config loading, ONNX session init, input/output validation, `infer_probs` | `inference` | Да | Это model runtime wrapper и model-near validation |
| `find_no_event_index` | `inference` | Да | Логика привязана к labels/model output, а не к contract или session flow |
| `resample_to_fixed_T` | `inference` как узкий helper, вызываемый из `pipelines/pose_words` или runtime wrapper adapter | Да, как narrow candidate | Это clip normalization для classifier input, а не segment boundary logic |
| path resolution для wrapper artifacts | `runtime` | Да, как boundary requirement, но не как копия `main.py` | Runtime должен создавать dependency, а не wrapper искать пути самостоятельно |
| wrapper init/error propagation в orchestration | `runtime` | Да, как boundary requirement | Ошибки wrapper должны быть видны readiness/runtime layer |
| вызов wrapper из `pose_words` path на уже готовом clip | `pipelines/pose_words` + `runtime` | Да, как target interaction | Pipeline/composition владеет моментом вызова, а не transport |
| `extract_segment`, buffer slicing, segment boundaries | `segmentation` | Нет | Это отдельный runtime layer и scope `PW-02` |
| manifest/profile logic, active artifacts state | `runtime`/artifact policy | Нет | Это scope `ART-01`, а не inference wrapper |
| WebSocket payload assembly и session state machine | `api`/`runtime` | Нет | Это orchestration/transport surface, не model wrapper |

### 6.2. Что должен содержать первый code migration increment

Первый implementation issue после PW-01 должен переносить только такой surface:

- clean `pose_words` ONNX wrapper в слое `inference`;
- узкий helper для fixed-length clip normalization, если clean runtime решит сохранить его рядом с wrapper;
- минимальный runtime-facing interface для создания wrapper по уже разрешённым путям;
- вызов wrapper на уже подготовленном `[T, F]` clip внутри `pose_words` composition path.

Первый increment **не должен** переносить:

- segmentation runtime;
- full session/runtime orchestration;
- transport/API handlers;
- artifact manifest и active profile policy;
- validation/research scaffolds;
- baseline/reference paths `words` и `letters`.

## 7. Runtime-required части vs. остальной draft context

### 7.1. Что относится именно к runtime-required inference layer

К runtime-required inference layer относятся:

- ONNX model loading;
- labels loading;
- optional config loading только как validator, а не как policy/manifest source;
- ONNX session init;
- validation expected input rank/dims;
- sanitization model input/output;
- output normalization;
- probability inference на clip формы `[T, F]`.

### 7.2. Что относится к segmentation layer

К segmentation layer относятся:

- выбор границ сегмента;
- накопление feature buffer;
- slicing buffer по `(start, end)`;
- thresholds, decode state, active segment progress;
- sign/phrase segmentation decisions.

### 7.3. Что относится к runtime glue/orchestration

К runtime glue/orchestration относятся:

- resolution runtime paths;
- dependency construction и lifecycle;
- readiness/error propagation;
- pipeline ordering: pose extraction -> segmentation -> fixed-length clip -> wrapper inference -> decoder;
- session state, payload assembly и integration with transport.

### 7.4. Что относится к training/export, validation, bootstrap и baseline/reference

За пределами PW-01 остаются:

- export/training artifacts and scripts;
- validation-only helpers и reports;
- bootstrap/dummy/fallback active paths;
- active manifest/profile logic;
- baseline `words` и `letters`;
- любые unrelated draft modules, даже если они технически импортируются рядом.

## 8. Manual checks для first migration increment

Ниже перечислены **конкретные ручные проверки**, которые должны сопровождать первый code migration increment по wrapper.

### 8.1. Проверки wrapper init и artifact handoff

- проверить, что `model_path` существует до init wrapper;
- проверить, что `labels_path` существует до init wrapper;
- если `config_path` передан, проверить, что он существует; если не передан, wrapper должен оставаться работоспособным без него;
- проверить, что labels file не пустой после загрузки;
- проверить, что `config_path`, если используется, парсится только как JSON object, а не как произвольный payload;
- проверить, что `labels_total` из config, если поле присутствует, совпадает с числом labels;
- проверить, что `clip_frames` и `input_dim` из config, если поля присутствуют, совпадают со статическими параметрами ONNX input;
- проверить, что init-путь явно падает с понятной ошибкой при отсутствии `onnxruntime`.

### 8.2. Проверки ONNX input contract внутри wrapper

- проверить, что ONNX input rank равен ровно `[B, T, F]`; любой другой rank должен приводить к явной ошибке init;
- проверить, что wrapper корректно сохраняет `T` и `F`, если ONNX input задаёт статические размеры;
- проверить, что runtime input для `infer_probs` имеет форму ровно `[T, F]`;
- проверить, что `infer_probs` отклоняет пустой clip без молчаливого fallback;
- проверить, что при статическом `clip_frames` wrapper отвергает clip другой длины;
- проверить, что при статическом `feature_dim` wrapper отвергает clip с другим `F`.

### 8.3. Проверки data sanitization и output normalization

- проверить, что `NaN`/`Inf` во входном clip заменяются на `0.0` до ORT inference;
- проверить, что output shape `[1, C]` и `[1, T', C]` нормализуются к вектору `[C]` предсказуемо;
- проверить, что unsupported output rank приводит к явной ошибке runtime;
- проверить, что длина итогового output vector совпадает с размером labels;
- проверить, что если output уже похож на probability vector, он не пересчитывается некорректно;
- проверить, что logits-подобный output переводится в probabilities через softmax-подобную нормализацию;
- проверить, что невалидные значения в output тоже sanitizятся до нормализации.

### 8.4. Проверки failure modes, которые должны быть видимы runtime layer

- проверить, что missing model file, labels file или optional config file дают различимые init-errors;
- проверить, что config-vs-ONNX mismatch по `clip_frames`/`input_dim` не скрывается и не превращается в silent fallback;
- проверить, что input mismatch в `infer_probs` даёт явную runtime error surface;
- проверить, что output-vs-labels mismatch виден как runtime failure;
- проверить, что runtime glue не проглатывает эти ошибки и может отдать их дальше в readiness/orchestration слой.

### 8.5. Проверки, которые не относятся к PW-01

Следующие проверки нужны позже, но не входят в manual checks PW-01:

- корректность segment boundaries;
- корректность buffer slicing по `(start, end)`;
- thresholds и quality segmentation decisions;
- active artifact profile, manifest resolution и readiness gating по non-dummy artifacts;
- WebSocket payload semantics и session-level text assembly.

Эти проверки относятся соответственно к `PW-02`, `ART-01`, `RT-02` и integration-level задачам.

## 9. Ограничения и риски первого increment

- `config_path` в wrapper должен оставаться **optional validator**, а не превращаться в обязательный центр artifact policy;
- clean repo не должен копировать `main.py` монолитом: из него нужны только boundary decisions;
- если fixed-length normalization будет перенесена, она не должна потянуть за собой buffer extraction helpers и segmentation state;
- первый increment не должен создавать впечатление, что clean repo уже закрывает весь `pose_words` runtime path end-to-end;
- readiness, active artifacts и transport surface остаются зависимостями от других issues, даже если wrapper уже перенесён.

## 10. Non-goals

PW-01 не решает и не должен частично реализовывать:

- code migration segmentation runtime;
- перенос `RuntimeContext` или `SessionProcessor`;
- artifact manifest/load path;
- contract changes;
- baseline/reference migration;
- validation/research scaffolds;
- bootstrap/dummy/fallback runtime path.

## 11. Вывод для следующего implementation issue

Следующий implementation issue должен делать ровно следующее:

- перенести в clean repo `PoseWordOnnxModel` как отдельный inference wrapper;
- при необходимости вынести рядом узкий helper для fixed-length clip normalization;
- подключить wrapper к `pose_words` composition path только через уже подготовленный `[T, F]` clip и уже разрешённые runtime paths;
- оставить segment extraction, boundary detection, artifact policy, readiness assembly, transport/API и baseline/reference paths за пределами этого increment.

Именно такой scope позволит перенести только runtime-required слой `pose_words` и не притащит в clean repo research, validation и bootstrap хвосты из `gesture-recognition-draft`.
