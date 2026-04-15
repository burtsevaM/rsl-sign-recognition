# PW-02 — `segmentation` runtime migration scope

## 1. Назначение документа

Этот документ закрывает planning/migration-scope часть issue `#22 PW-02`.

Его задача:

- зафиксировать **source context** для переноса `segmentation` как отдельного runtime layer вокруг `pose_words`;
- определить **target scope** в clean layout `rsl-sign-recognition`;
- отделить runtime-required `decoder`, streaming state, model execution и feature-span extraction от validation/research, artifact/profile logic и mixed draft glue;
- перечислить **manual checks** и smoke expectations для первого code migration increment.

Документ **не** переносит код и **не** объявляет, что clean repo уже содержит working segmentation runtime.

## 2. Зависимости и архитектурная привязка

PW-02 опирается на уже зафиксированные planning-границы:

- `RT-01` задает target layout, в котором `segmentation` отделен от `runtime`, `pipelines` и `inference`;
- `RT-02` уже формализует `/health` и `/ready`, поэтому PW-02 не описывает readiness как artifact policy или active manifest;
- `PW-01` фиксирует downstream boundary для `pose_words` classifier wrapper и оставляет `segmentation` отдельным runtime layer.

Следовательно, scope PW-02 ограничен только тем runtime surface, который нужен для:

- BIO model execution;
- streaming buffer/state;
- decode правил для segment boundaries;
- materialization feature span для downstream `pose_words` inference path.

PW-02 **не** меняет WebSocket contract, не переносит classifier wrapper и не формализует artifact manifest/load path.

## 3. Source context

### 3.1. Актуальная source branch и фактические пути

Пути из issue `#22` подтверждены **не в `gesture-recognition-draft/main`**, а в ветке:

- `gesture-recognition-draft:burtseva_ma_mvp_words`

Проверка показала:

- в `main` директория `backend/app/segmentation/` по указанному пути отсутствует;
- в `burtseva_ma_mvp_words` присутствуют:
  - `backend/app/segmentation/decoder.py`
  - `backend/app/segmentation/streaming.py`
  - `backend/app/segmentation/model_onnx.py`
  - `backend/app/main.py`

Именно эта ветка является **реальным source context** для PW-02. Документ не делает вид, будто source scope живет в `main`, если это не так.

### 3.2. Канонические source-файлы

- `gesture-recognition-draft/backend/app/segmentation/decoder.py`
- `gesture-recognition-draft/backend/app/segmentation/streaming.py`
- `gesture-recognition-draft/backend/app/segmentation/model_onnx.py`
- `gesture-recognition-draft/backend/app/main.py`

### 3.3. Дополнительный boundary context рядом с source scope

Для честного отделения runtime scope дополнительно использовались соседние файлы:

- `gesture-recognition-draft/backend/app/pose_words/segment_utils.py`
- `gesture-recognition-draft/backend/app/segmentation/__init__.py`
- `gesture-recognition-draft/backend/app/segmentation/metrics.py`

Они нужны только для boundary analysis:

- `segment_utils.py` показывает, что `extract_segment` сейчас живет рядом с `pose_words`, хотя по ответственности относится к `segmentation`;
- `segmentation/__init__.py` показывает смешанный draft boundary через re-export `PoseWordOnnxModel` и metrics helpers;
- `segmentation/metrics.py` показывает validation/analysis helpers, которые не входят в runtime scope.

## 4. Source responsibilities по файлам

| Source file | Что есть в draft repo | Как трактуется в PW-02 |
| --- | --- | --- |
| `decoder.py` | `_validate_probs`, `_segment_score`, `_merge_with_gap`, `decode_segments` | **Основной source scope PW-02**. Это runtime-required decoder logic для BIO segment boundaries |
| `streaming.py` | `BioSegment`, `StreamingBioResult`, `StreamingBioSegmenter`, buffer state, inference cadence, aggregation, active segment state, `get_feature_span` | **Основной source scope PW-02**. Это и есть streaming segmentation runtime candidate |
| `model_onnx.py` | `BioSegmenterOnnxModel`, `_to_probs`, optional config validation, ONNX session init, `infer`, `BioThresholdConfig`, `load_bio_thresholds` | Входит в PW-02 как segmentation-specific model runtime. При этом threshold loading имеет узкую boundary и не должен превратиться в artifact policy |
| `main.py` | artifact path resolution, init `BioSegmenterOnnxModel`, init `StreamingBioSegmenter`, threshold handoff, `pose_segmenter.update(...)`, `get_feature_span(...)`, downstream call в `pose_words` path, debug payload, readiness/artifact state | Используется как **source context для boundaries**, но не как объект прямого копирования. В target scope переходят только integration responsibilities вокруг segmentation |

## 5. Что именно является source scope для PW-02

### 5.1. Runtime-required decoder logic

В **source scope PW-02 входят** следующие обязанности из `decoder.py`:

- runtime validation BIO probabilities как массива формы `[T, 3]`;
- sanitization `NaN`/`Inf` перед decode;
- frame-level decode rules:
  - start on `P(B) >= th_B`;
  - end on `P(O) >= th_O`;
  - early close на новом `B`;
- merge adjacent segments по `merge_gap`;
- фильтрация по `min_len`;
- ограничение по `max_len`;
- segment score как mean confidence по `max(P(B), P(I))` внутри сегмента.

Это относится к clean runtime scope, потому что:

- decoder определяет segment boundaries для live pipeline;
- decoder не зависит от transport/API;
- decoder не относится к training/export;
- decoder нужен независимо от validation reports и metrics.

### 5.2. Streaming state и segment lifecycle

В **source scope PW-02 входят** следующие обязанности из `streaming.py`:

- хранение feature buffer и global monotonic frame indices;
- накопление окна `window`, cadence `step` и решение, когда запускать BIO inference;
- aggregation overlapping BIO outputs по global frame indices;
- повторный decode по текущему buffer snapshot;
- вычисление completed segments, active segments и progress для текущего окна;
- cool-off suppression для повторных emitted segments;
- возврат runtime-facing segment outputs как `BioSegment`-подобных сущностей;
- materialization feature span по `(start, end)` через `get_feature_span(...)`.

Это и есть core streaming runtime layer для segmentation.

### 5.3. Segmentation-specific model runtime

В **source scope PW-02 входят** следующие обязанности из `model_onnx.py`:

- создание `BioSegmenterOnnxModel` по уже разрешенным runtime paths;
- fail-fast проверка существования ONNX model;
- optional parsing `config_path` только как runtime validator;
- чтение `input_dim` из config, если поле присутствует;
- инициализация `onnxruntime.InferenceSession` с CPU provider;
- валидация rank-3 input `[B, T, F]`;
- чтение output names для `sign_probs` и `phrase_probs`;
- runtime validation feature dim во входе `infer(...)`;
- нормализация logits/probs в матрицы BIO probabilities формы `[T, 3]`;
- возврат sign/phrase probabilities и latency.

Это остается внутри `segmentation`, а не уходит в shared `inference`, потому что:

- wrapper специфичен именно для BIO segmentation model;
- он возвращает segmentation-specific dual output (`sign`, `phrase`);
- downstream classifier wrapper уже выделен отдельным scope в `PW-01`.

### 5.4. Feature-span extraction как часть segmentation boundary

PW-02 отдельно фиксирует boundary для `feature-span extraction`.

В draft repo `StreamingBioSegmenter.get_feature_span(...)` вызывает:

- `pose_words.segment_utils.extract_segment(...)`

Для clean repo это **неправильная ownership-boundary**. В target scope PW-02:

- feature-span extraction относится к `segmentation`, а не к `pose_words`;
- helper для buffer slicing должен мигрировать вместе с segmentation layer или быть инкапсулирован внутри него;
- import `segmentation -> pose_words.segment_utils` не должен сохраняться в clean runtime.

Иначе clean repo заново смешает upstream segmentation state с downstream classifier helper-слоем.

### 5.5. Runtime glue context, который нужно учесть, но не копировать

Из `main.py` PW-02 должен унаследовать только понимание следующих обязанностей:

- `runtime` resolve-ит paths для segmentation artifacts до передачи их в `BioSegmenterOnnxModel`;
- `runtime` создает `StreamingBioSegmenter` и передает в него уже выбранные thresholds/runtime params;
- `pipelines/pose_words` вызывает segmentation на каждом `feature_vec`, а не на raw frames;
- `pipelines/pose_words` использует segmentation как upstream dependency:
  - `update(feature_vec)`
  - получить completed sign segment
  - materialize feature span
  - передать span дальше в `resample_to_fixed_T` и `PoseWordOnnxModel.infer_probs(...)`;
- init/runtime errors segmentation должны быть видимы orchestration layer и не должны теряться в transport glue.

Это **context for migration boundaries**, а не scope на перенос `RuntimeContext`, `SessionProcessor`, WebSocket handlers, payload builders, readiness assembly или artifact-state reporting.

## 6. Target scope в clean repo

### 6.1. Место `segmentation` относительно `runtime`, `pipelines`, `pose_words` и `inference`

Разделение для clean repo фиксируется так:

- `runtime`:
  - resolve runtime paths;
  - создает segmentation dependencies;
  - владеет lifecycle/init-errors/readiness integration.
- `pipelines/pose_words`:
  - определяет порядок вызовов `segmentation -> resample -> pose_words inference wrapper -> word decoder`;
  - не владеет internal segmentation state.
- `segmentation`:
  - владеет BIO model runtime;
  - владеет decoder и streaming state;
  - владеет feature-span extraction;
  - отдает runtime-facing segment outputs.
- `inference`:
  - не владеет segmentation decode;
  - хранит downstream classifier wrapper из `PW-01`, если он переезжает отдельным increment.

Иначе говоря:

- `segmentation` находится **между** feature-producing pose path и downstream `pose_words` classifier;
- `segmentation` не является подмодулем `pose_words`;
- `segmentation` не подменяет `runtime` orchestration;
- `segmentation` не превращается в shared artifact policy layer.

### 6.2. Target layer mapping

| Source responsibility | Target layer в clean repo | Входит в PW-02? | Почему |
| --- | --- | --- | --- |
| `decode_segments`, `_validate_probs`, `_merge_with_gap`, `_segment_score` | `segmentation` | Да | Это segmentation-specific decoder/runtime logic |
| `BioSegmenterOnnxModel`, `_to_probs`, `infer` | `segmentation` | Да | Это model runtime для BIO segmentation, а не общий inference layer |
| buffer state, frame indices, aggregation, active segment state, cool-off | `segmentation` | Да | Это streaming runtime surface |
| `get_feature_span` и buffer slicing helper | `segmentation` | Да | Это bridge от segment boundaries к downstream clip, ownership должна быть у segmentation |
| threshold values как параметры `StreamingBioSegmenter` | `segmentation` | Да | Thresholds влияют на decoder behavior и входят в runtime semantics слоя |
| threshold path resolution и выбор активного threshold source | `runtime` | Да, только как boundary requirement | Runtime должен передавать thresholds в segmentation, но не смешивать это с manifest/promotion policy |
| path resolution, init errors, readiness visibility | `runtime` | Да, как boundary requirement | Это orchestration responsibility, а не код для копирования из `main.py` |
| downstream `resample_to_fixed_T` и `PoseWordOnnxModel.infer_probs` | `pipelines/pose_words` + `inference` | Нет | Это уже scope `PW-01` и downstream classifier path |
| debug payload assembly, WebSocket message building, text state | `runtime` / `api` | Нет | Это transport/orchestration glue, не segmentation layer |
| artifact profile, manifest lookup, `dummy`/`validation` metadata | `runtime` / `ART-01` | Нет | Это отдельный artifact-policy scope |

## 7. Explicit in-scope / out-of-scope

### 7.1. Что входит в первый migration scope PW-02

PW-02 подготавливает перенос только следующих частей:

- segmentation-specific ONNX runtime wrapper;
- decoder rules для BIO probabilities;
- streaming state и cadence;
- completed/active segment state;
- feature-span extraction для уже emitted segment bounds;
- runtime-facing thresholds semantics как параметры segmentation layer;
- integration boundary между segmentation и downstream `pose_words` path.

### 7.2. Что явно не входит

PW-02 **не включает**:

- code migration в clean repo;
- `pose_words` classifier wrapper migration;
- downstream `resample_to_fixed_T` как часть segmentation ownership;
- artifact loader и active manifest;
- `config.yaml` как обязательный runtime path;
- WebSocket payload building и session-level text assembly;
- readiness policy целиком;
- validation/research scripts;
- synthetic dataset / training logic;
- baseline/reference paths `words` и `letters`;
- unrelated draft runtime noise.

### 7.3. Что остается в draft validation/research contour

В draft contour остаются:

- `segmentation/metrics.py` целиком как validation/analysis helper surface;
- mixed re-export boundary из `segmentation/__init__.py`, включая `PoseWordOnnxModel` и metrics helpers;
- active artifact profile logic (`runtime_active`, `validation_active`, `dummy_fallback`, `mixed_active`);
- manifest lookup и metadata fields вроде `artifact_kind`, `dataset_kind`, `generated_by`, `trained`;
- debug payload parity ради UI/diagnostics, если она не нужна для первого runtime increment;
- historical fallback behavior при missing/invalid thresholds/config beyond minimal runtime defaults.

Эти вещи не должны мигрировать как часть clean segmentation runtime, даже если они находятся рядом с source modules.

## 8. Boundary для thresholds, model loading и feature-span extraction

### 8.1. Model loading boundary

Граница model loading фиксируется так:

- `runtime` решает, **какой artifact path** передается в segmentation model wrapper;
- `segmentation` отвечает только за:
  - file existence checks;
  - optional config validation;
  - ORT session init;
  - input/output validation;
  - runtime inference;
- active profile selection, manifest semantics и policy выбора artifacts не входят в segmentation scope.

### 8.2. Threshold boundary

Граница threshold semantics фиксируется так:

- сами thresholds (`sign_th_b`, `sign_th_o`, `phrase_th_b`, `phrase_th_o`) относятся к `segmentation`, потому что определяют decoder behavior;
- источник этих threshold values не должен автоматически тянуть в clean repo:
  - manifest lookup;
  - `config.yaml`-centric fallback policy;
  - validation/dummy profile semantics;
  - metadata про dataset/source/training;
- для первого increment допустим только **узкий runtime handoff**:
  - либо `runtime` передает уже рассчитанные threshold values;
  - либо используется маленький segmentation-specific loader, который читает только четыре runtime threshold fields.

`load_bio_thresholds(...)` из draft repo трактуется как **узкий helper-кандидат**, но не как начало artifact-policy слоя.

### 8.3. Feature-span extraction boundary

Граница feature-span extraction фиксируется так:

- emitted segment bounds принадлежат `segmentation`;
- materialization `[Tseg, F]` span по `(start, end)` тоже принадлежит `segmentation`;
- downstream fixed-length resampling принадлежит `PW-01` / classifier path;
- поэтому clean repo не должен оставлять chain:
  - `segmentation -> pose_words.segment_utils.extract_segment -> pose_words inference`

Правильный chain для clean runtime:

- `segmentation.update(feature_vec)`
- `segmentation.get_feature_span(start, end)`
- `pipelines/pose_words` передает span в downstream resample/inference path

## 9. Runtime-required части vs. mixed draft logic

### 9.1. Runtime-required для первого increment

К runtime-required surface относятся:

- BIO ONNX init/infer;
- BIO probabilities normalization;
- decoder thresholds и boundary rules;
- global frame-index buffer;
- active/completed segment lifecycle;
- completed segment dedup и cool-off;
- feature-span extraction по emitted bounds;
- error propagation в orchestration layer.

### 9.2. Mixed draft logic, которую нельзя переносить как есть

К mixed draft logic относятся:

- импорт `extract_segment` из `pose_words`;
- объединение threshold files с runtime config fallback из `main.py`;
- debug payload blocks `segments` и `debug.bio` как часть transport response assembly;
- readiness/artifact-state wiring рядом с segmentation init;
- re-export `PoseWordOnnxModel` из `segmentation/__init__.py`.

Эти куски дают useful context, но не являются clean target shape.

### 9.3. Validation/research contour вне PW-02

За пределами PW-02 остаются:

- segmentation metrics и stability helpers;
- quality/false-positive analysis;
- validation reports;
- synthetic or dataset-driven threshold tuning;
- training/export concerns;
- dummy/validation fallback profiles;
- unrelated manual experiment scaffolds.

## 10. Manual checks для первого migration increment

Ниже перечислены **конкретные ручные проверки**, которые должны сопровождать первый code migration increment по segmentation runtime.

### 10.1. Проверки segmentation model init

- проверить, что missing ONNX model file дает явную init-error surface;
- проверить, что optional segmentation config, если передан, валидируется как JSON object;
- проверить, что mismatch `input_dim` между config и ONNX не превращается в silent fallback;
- проверить, что отсутствие `onnxruntime` видно как явная init error;
- проверить, что output contract требует именно два BIO outputs: `sign` и `phrase`.

### 10.2. Проверки decoder logic

- проверить, что decoder принимает только shape `[T, 3]`;
- проверить, что `NaN`/`Inf` sanitizятся до decode;
- проверить, что новый `B` закрывает предыдущий segment и открывает новый;
- проверить, что `O >= th_O` завершает активный segment;
- проверить, что `merge_gap`, `min_len` и `max_len` работают предсказуемо;
- проверить, что score сегмента считается по `max(P(B), P(I))`, а не по внешнему debug/pipeline state.

### 10.3. Проверки streaming state

- проверить, что inference не запускается до набора `window` frames;
- проверить, что после набора окна inference запускается только по cadence `step`;
- проверить, что frame indices монотонны и глобальны, а не локальны к window;
- проверить, что completed segments эмитятся один раз и не дублируются после cool-off;
- проверить, что `active_sign` / `active_sign_progress` обновляются без ложного completed segment;
- проверить, что invalid span вне текущего buffer не materialize-ится молча как невалидный clip.

### 10.4. Проверки feature-span extraction

- проверить, что `get_feature_span(start, end)` возвращает ровно `[Tseg, F]` для валидного диапазона;
- проверить, что span extraction работает на global frame indices, а не на локальных offsets;
- проверить, что пустой или out-of-buffer range возвращает controlled empty/none result;
- проверить, что span extraction не зависит от `pose_words` package ownership.

### 10.5. Проверки integration boundary с `pose_words`

- проверить, что completed sign segment можно передать downstream в `resample_to_fixed_T` и `PoseWordOnnxModel.infer_probs(...)`;
- проверить, что при отсутствии completed sign segment downstream classifier path не вызывается преждевременно;
- проверить, что segmentation runtime errors не проглатываются и доступны orchestration layer;
- проверить, что segmentation increment не требует одновременно переносить classifier wrapper, transport payload assembly или artifact manifest.

## 11. Smoke expectations для segmentation path

Первый segmentation increment должен подтверждать только следующий smoke surface:

- segmentation dependencies успешно инициализируются при наличии корректных runtime artifacts;
- live pose feature stream можно подавать в `StreamingBioSegmenter.update(...)` без `segmentation error`;
- до набора окна path честно остается в состоянии “segment not ready”, а не имитирует результат;
- после накопления достаточного окна path может отдать completed sign segment или active segment state;
- для completed sign segment можно получить feature span и передать его downstream classifier path;
- отсутствие segment event не должно создавать ложное слово или притворяться успешным end-to-end recognition.

Smoke expectations **не требуют**:

- доказанной segmentation quality;
- validation metrics parity;
- artifact manifest;
- readiness green по policy уровня `ART-01`;
- полного websocket/debug payload parity с draft repo.

## 12. Ограничения и риски первого increment

- текущий draft source branch не совпадает с `main`, поэтому будущий code migration должен снова проверять source branch перед переносом;
- в draft repo ownership `extract_segment` проведен неудачно: если перенести код механически, clean repo снова смешает `segmentation` и `pose_words`;
- thresholds в draft repo сейчас живут на стыке model config, отдельного thresholds JSON и общего runtime config, поэтому первый increment должен избегать скрытого fallback behavior;
- dual output `sign`/`phrase` присутствует в source model, но downstream `pose_words` classifier path зависит прежде всего от completed `sign_segments`;
- draft debug payload и metric helpers могут создавать ложное впечатление, будто они нужны для минимального runtime surface, хотя это не так.

## 13. Non-goals

PW-02 не решает и не должен частично реализовывать:

- перенос segmentation-кода в clean repo в этом planning issue;
- `pose_words` classifier wrapper;
- artifact manifest/load path;
- validation/research scripts и metrics;
- synthetic dataset / training logic;
- readiness/artifact-profile policy;
- transport/API payload semantics.

## 14. Вывод для следующего implementation issue

Следующий implementation issue после PW-02 должен делать ровно следующее:

- перенести segmentation-specific ONNX wrapper;
- перенести BIO decoder rules;
- перенести streaming state и emitted-segment lifecycle;
- перенести feature-span extraction под ownership `segmentation`;
- подключить segmentation к `pose_words` pipeline только как upstream provider segment bounds и feature span;
- не переносить metrics, manifest/profile logic, classifier wrapper, validation helpers и transport glue.

Именно такой scope позволяет перенести только runtime-required segmentation surface и не затянуть в clean repo validation/research/mixed draft logic из `gesture-recognition-draft`.
