# MIG-02 — Runtime-required migration governance

## 1. Назначение

Этот документ закрывает governance/mapping часть issue `#32 MIG-02`.

MIG-02 нужен перед code migration issues, чтобы future runtime перенос из
`gesture-recognition-draft` оставался управляемым:

- зафиксировать source-to-target mapping для runtime-required модулей;
- заранее отделить implementation issues друг от друга;
- перечислить excluded draft areas;
- описать guardrails против массового копирования;
- задать manual migration checks для последующих PR.

Важно:

- `#32` **не реализует runtime-код**;
- `#32` **не переносит inference, segmentation, pose extraction или artifact loader**;
- `#32` **не меняет** поведение `/health`, `/ready` и `WS /ws/stream`;
- clean repo после `#32` остается clean runtime shell, а не полным ML runtime.

## 2. Boundary после RT-04

После RT-04 clean repo содержит только честный минимальный runtime surface:

- FastAPI app factory и ASGI entrypoint;
- `/health` как liveness probe;
- `/ready` как readiness probe для `live_runtime_path`;
- transport-level `WS /ws/stream`, который принимает binary JPEG packets и JSON control messages по `contract v1`;
- contract-shaped transport errors и `control.ack`.

После RT-04 clean repo по-прежнему **не содержит**:

- live inference pipeline;
- pose extraction и feature composition runtime layer;
- segmentation runtime layer;
- `pose_words` classifier wrapper;
- active artifact loader / manifest reader;
- model artifacts, training/export code, validation runners или bootstrap runtime path.

Следствие для MIG-02:

- readiness не должна становиться green из-за одного docs PR;
- `WS /ws/stream` не должен начинать отдавать `recognition.result`;
- shell-level behavior должен остаться таким же, как после RT-04.

## 3. Source context

MIG-02 использует `gesture-recognition-draft` только как read-only source context.
Ни один файл draft repo не должен изменяться или копироваться целиком.

Из draft repo были изучены:

- `README.md`;
- `docs/current-state.md`;
- `docs/target-architecture.md`;
- `docs/pose_words_technical_validation.md`;
- `docs/validation-gates.md`;
- `backend/docs/pose_words_artifacts.md`;
- `backend/app/main.py`;
- `backend/app/pose/extractor.py`;
- `backend/app/pose/datatypes.py`;
- `backend/app/pose/normalization.py`;
- `backend/app/pose/pipeline_worker.py`;
- `backend/app/pose_words/model_onnx_pose.py`;
- `backend/app/pose_words/segment_utils.py`;
- `backend/app/segmentation/decoder.py`;
- `backend/app/segmentation/model_onnx.py`;
- `backend/app/segmentation/streaming.py`.

## 4. Controlled migration order

MIG-02 не заменяет implementation issues. Он задает guardrail для них.

Логичный следующий code issue после merge MIG-02:

1. `#34 PW-05` — pose extraction / normalization / feature composition runtime layer.
2. `#29 PW-04` — segmentation runtime layer, после появления feature stream из `PW-05`.
3. `#28 PW-03` — `pose_words` inference wrapper, после появления feature clip boundary из `PW-05`.
4. `#30 ART-02` — active artifact loader / manifest reader, после согласования wrapper и segmentation artifact requirements.

`PW-03` и `PW-04` могут уточнять очередность между собой, но оба должны опираться
на `PW-05` как на declared feature input boundary. `ART-02` не должен подменять
собой wrapper или segmentation migration.

## 5. Source-to-target mapping

### 5.1. `#34 PW-05` — pose extraction / normalization / feature composition

Canonical source files:

- `gesture-recognition-draft/backend/app/pose/extractor.py`;
- `gesture-recognition-draft/backend/app/pose/datatypes.py`;
- `gesture-recognition-draft/backend/app/pose/normalization.py`;
- `gesture-recognition-draft/backend/app/pose/pipeline_worker.py`;
- `gesture-recognition-draft/backend/app/main.py` only as boundary context.

Runtime-required source responsibilities:

- MediaPipe Holistic wrapper for decoded RGB frames;
- pose runtime datatypes and validation for body, hands and optional face landmarks;
- finite-value and shape validation for pose frames;
- shoulder normalization and safe fallback semantics;
- optional hand 3D normalization;
- leg hiding / upper-body feature selection where it is part of clean feature composition;
- `compose_features` / `compose_features_sequence` style feature vector composition;
- optional realtime worker/service boundary for frame -> pose -> normalized pose -> feature vector.

Clean target modules for the implementation issue:

- `src/rsl_sign_recognition/pipelines/pose_words/pose_types.py` for runtime pose datatypes;
- `src/rsl_sign_recognition/pipelines/pose_words/pose_extraction.py` for extractor boundary;
- `src/rsl_sign_recognition/pipelines/pose_words/features.py` for normalization and feature composition;
- `src/rsl_sign_recognition/pipelines/pose_words/worker.py` only if the live path really needs a background worker;
- `src/rsl_sign_recognition/runtime/...` only for thin dependency construction/lifecycle wiring.

Allowed interaction boundary:

- `api` / RT-04 supplies decoded transport input, not ML logic;
- `PW-05` emits validated `float32` feature vectors and pose debug objects;
- `PW-04` consumes feature stream for segmentation;
- `PW-03` consumes prepared feature clips/spans, not raw frames.

Explicit non-goals for `PW-05`:

- do not move segmentation decoder/streaming/model code;
- do not move `PoseWordOnnxModel`;
- do not move active artifact loader/manifest reader;
- do not copy frontend/offline helpers or validation scripts;
- do not use `backend/app/main.py` as a target module.

### 5.2. `#28 PW-03` — `pose_words` inference wrapper

Canonical source files:

- `gesture-recognition-draft/backend/app/pose_words/model_onnx_pose.py`;
- `gesture-recognition-draft/backend/app/pose_words/segment_utils.py` only for `resample_to_fixed_T`;
- `gesture-recognition-draft/backend/app/main.py` only as boundary context.

Runtime-required source responsibilities:

- ONNX classifier model loading;
- labels loading and empty-label validation;
- optional runtime config loading as validator, not as artifact policy;
- config-vs-ONNX shape validation for `clip_frames` and `input_dim`;
- ONNXRuntime CPU session init;
- `[T, F]` input validation;
- `NaN` / `Inf` sanitization;
- output rank normalization and probability normalization;
- output-size validation against labels;
- no-event label helper;
- fixed-length clip resampling for an already extracted segment clip.

Clean target modules for the implementation issue:

- `src/rsl_sign_recognition/inference/pose_words.py` for the classifier wrapper;
- `src/rsl_sign_recognition/pipelines/pose_words/clip.py` for `resample_to_fixed_T` if it stays pipeline-owned;
- `src/rsl_sign_recognition/pipelines/pose_words/classifier.py` only as a thin adapter between pipeline composition and the inference wrapper.

Allowed interaction boundary:

- wrapper receives already resolved model/labels/config paths from runtime or `ART-02`;
- wrapper receives already prepared `[T, F]` feature clip from `PW-05` / `PW-04`;
- wrapper does not own segmentation, frame processing, transport payloads or active profile selection.

Explicit non-goals for `PW-03`:

- do not move pose extraction, normalization or feature composition;
- do not move `StreamingBioSegmenter`, `BioSegmenterOnnxModel` or BIO decoder;
- do not move buffer slicing helpers except the narrow fixed-length resampling helper;
- do not implement artifact manifest reader;
- do not copy `backend/app/pose_words/` as a directory.

### 5.3. `#29 PW-04` — segmentation runtime layer

Canonical source files:

- `gesture-recognition-draft/backend/app/segmentation/decoder.py`;
- `gesture-recognition-draft/backend/app/segmentation/model_onnx.py`;
- `gesture-recognition-draft/backend/app/segmentation/streaming.py`;
- `gesture-recognition-draft/backend/app/pose_words/segment_utils.py` only for feature-span extraction ownership analysis;
- `gesture-recognition-draft/backend/app/main.py` only as boundary context.

Runtime-required source responsibilities:

- BIO probability validation and finite-value sanitization;
- decoder rules for `B`, `I`, `O`, `min_len`, `max_len` and `merge_gap`;
- segmentation-specific ONNX wrapper for BIO model execution;
- segmentation thresholds as runtime parameters;
- streaming feature buffer with global frame indices;
- inference cadence and aggregation across overlapping windows;
- active/completed sign and phrase segment state;
- emitted-segment dedup / cool-off;
- feature-span extraction for emitted segment bounds.

Clean target modules for the implementation issue:

- `src/rsl_sign_recognition/segmentation/decoder.py`;
- `src/rsl_sign_recognition/segmentation/model_onnx.py`;
- `src/rsl_sign_recognition/segmentation/streaming.py`;
- `src/rsl_sign_recognition/segmentation/types.py`;
- `src/rsl_sign_recognition/runtime/...` only for thin construction, path handoff and readiness visibility.

Allowed interaction boundary:

- `PW-04` consumes feature vectors from `PW-05`;
- `PW-04` exposes completed/active segment objects and feature spans;
- downstream `PW-03` receives a segment clip after `PW-04` emits a completed segment;
- threshold source selection remains outside segmentation policy unless explicitly scoped.

Explicit non-goals for `PW-04`:

- do not move `segmentation/metrics.py`;
- do not move synthetic BIO dataset builders or training/export code;
- do not move `PoseWordOnnxModel`;
- do not move feature extraction or normalization;
- do not copy `backend/app/segmentation/` as a directory.

### 5.4. `#30 ART-02` — active artifact loader / manifest reader

Canonical source files:

- `gesture-recognition-draft/backend/docs/pose_words_artifacts.md`;
- `gesture-recognition-draft/backend/app/main.py` artifact/readiness sections only;
- `gesture-recognition-draft/docs/pose_words_technical_validation.md` only as validation/bootstrap context.

Runtime-required source responsibilities to preserve as policy context:

- there is a complete active set for `pose_words` classifier and BIO segmentation;
- missing required files make live runtime not ready;
- validation and bootstrap profiles are different from active live runtime;
- active profile metadata is useful for readiness diagnostics;
- artifact errors must be runtime-friendly and visible to readiness/orchestration.

Clean target modules for the implementation issue:

- `src/rsl_sign_recognition/runtime/artifacts.py` for manifest reader and active artifact resolution;
- `src/rsl_sign_recognition/runtime/readiness.py` for readiness gate integration;
- `src/rsl_sign_recognition/runtime/services.py` for service construction handoff;
- tests under `tests/` for missing manifest, missing files, non-active profiles and path resolution.

Clean target policy:

- primary load path is `artifacts/runtime/active/pose_words/manifest.json`;
- file paths in manifest resolve relative to the manifest directory;
- loader does not scan validation/bootstrap directories as automatic fallback;
- loader does not require draft-only `backend/config.yaml`;
- loader does not treat `pose_words_active_manifest.json` from draft as the clean manifest contract unless `ART-02` explicitly updates `docs/artifact-policy.md`.

Explicit non-goals for `ART-02`:

- do not move validation artifact generation;
- do not move bootstrap/install/promote scripts as live runtime path;
- do not move model wrappers;
- do not move segmentation implementation;
- do not change `/ready` to green until real `runtime_shell`, `active_artifacts` and `transport_surface` gates are closed.

## 6. Explicit exclusions

The following draft areas stay out of MIG-02 and out of default runtime migration:

- `words` RGB baseline/reference pipeline;
- `letters` retrieval pipeline;
- training/export scripts;
- validation runners;
- dataset preparation;
- synthetic dataset logic;
- frontend and offline/browser helpers;
- bootstrap-only paths and dummy model generators;
- operational scripts and machine-local runbooks;
- metrics-only helpers;
- runtime logs and validation outputs;
- gallery, nested Slovo repo and local datasets;
- VLM/retrieval glue unrelated to `pose_words` live path;
- unrelated draft glue that exists only because `backend/app/main.py` is monolithic.

If any excluded area becomes product-required later, it needs its own explicit
issue, source scope, target scope and non-goals.

## 7. Guardrails against mass copying

Future migration PRs must follow these guardrails:

- do not copy `gesture-recognition-draft/backend/app` as a whole;
- do not copy `gesture-recognition-draft/backend/app/main.py` as a monolith;
- do not copy `pose/`, `segmentation/` or `pose_words/` directories without issue-scoped filtering;
- do not pull `backend/config.yaml` as an obligatory clean runtime path;
- do not turn validation/bootstrap artifacts into live runtime artifacts;
- do not import from `gesture-recognition-draft` at runtime;
- do not add draft repo paths, absolute machine-local paths or fallback discovery into clean runtime;
- do not make `/ready` pass just because draft validation/bootstrap files exist locally;
- do not change `contract v1` payload semantics as a side effect of runtime migration.

The correct pattern is selective reconstruction inside clean boundaries, not
directory transfer.

## 8. Manual migration checks for future PRs

Every future implementation PR for `PW-05`, `PW-03`, `PW-04` or `ART-02`
must include a manual migration checklist in the PR body.

Minimum checklist:

- source files from `gesture-recognition-draft` are listed explicitly;
- target modules in `rsl-sign-recognition` are listed explicitly;
- non-goals are repeated in the PR body;
- tests/checks match the declared issue scope;
- diff contains no unrelated draft files;
- no large draft directory was copied wholesale;
- readiness does not become green without the gates required by `docs/runtime-skeleton.md` and `docs/artifact-policy.md`;
- docs are updated synchronously when boundaries, readiness, artifact policy or integration behavior change;
- source-context files are treated as read-only and `gesture-recognition-draft` is not modified.

Recommended local checks before merge:

- inspect `git diff --name-only` for unrelated draft files, artifacts, configs and scripts;
- inspect imports for references to draft-only modules or paths;
- inspect tests to ensure they verify only the current issue scope;
- inspect `/health`, `/ready` and `WS /ws/stream` behavior when a PR claims runtime readiness.

## 9. Hidden dependency rule

If a future migration uncovers a dependency on draft-only code, config, script,
artifact or local path, do **not** pull it ad hoc.

Required handling:

1. Stop the direct transfer.
2. Describe the dependency in the PR or issue discussion.
3. Decide whether it is:
   - already inside the current issue scope;
   - a separate follow-up issue;
   - an explicit scope expansion that needs agreement before implementation.
4. Update docs/checklists if the dependency changes clean runtime boundaries.

This rule applies even when the dependency is small or easy to copy. Hidden
draft dependencies are exactly how a clean repo becomes another draft repo.

## 10. Completion criteria for MIG-02

MIG-02 is complete when:

- source-to-target mapping exists for `PW-05`, `PW-03`, `PW-04` and `ART-02`;
- excluded draft areas are listed explicitly;
- guardrails and manual migration checks are documented;
- hidden dependency handling is documented;
- README / architecture / backlog navigation points to this governance document;
- no runtime code was moved and no clean runtime behavior changed.

After MIG-02, implementation issues must migrate only their declared scope.
The next logical code issue is `#34 PW-05`.
