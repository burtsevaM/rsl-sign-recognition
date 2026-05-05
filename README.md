# rsl-sign-recognition

`rsl-sign-recognition` — clean repository для ML-модуля распознавания РЖЯ в сценарии sign-to-text. Его задача — стать местом для воспроизводимого runtime-контура, интеграционного контракта, runtime-facing документации и поэтапной миграции из draft-репозитория в более чистую долгоживущую структуру.

На текущем этапе репозиторий уже содержит **минимальный FastAPI runtime shell** для `/health`, `/ready` и transport-level `WS /ws/stream`, не подключенный к transport слой `PW-05` для pose extraction / normalization / feature composition, изолированный `PW-04` segmentation runtime layer для BIO boundaries поверх feature vectors, изолированный `PW-03` classifier wrapper для `pose_words` feature clips и `ART-02` active artifact manifest reader / loader для clean runtime path. Репозиторий по-прежнему не содержит полного end-to-end inference/runtime-контура, реальных активных артефактов, live inference pipeline, моделей, training/export-кода и operational scripts.

## Что это за репозиторий

Этот репозиторий нужен как clean home для воспроизводимого ML runtime, который позже будет использоваться для интеграции с веб-платформой и других product-oriented сценариев.

Сюда будет переноситься только то, что соответствует этим требованиям:

- относится к целевому runtime-контуру, а не к исследовательской среде;
- имеет понятные границы, контракт и назначение;
- может поддерживаться через issue-based процесс;
- не зависит от скрытой локальной магии, черновых bootstrap-путей и случайных артефактов.

## Scope clean repo

Целевой scope этого репозитория:

- versioned integration contract для sign-to-text runtime;
- skeleton и сервисные границы будущего runtime;
- `pose_words` как основной pipeline для word recognition;
- policy для active runtime artifacts, readiness и smoke/integration checks;
- handoff-документация и reproducible process для дальнейшей миграции.

На текущем этапе здесь уже есть:

- `README.md`;
- `CONTRIBUTING.md`;
- архитектурная, roadmap и backlog-документация;
- зафиксированные границы runtime skeleton и минимальный FastAPI runtime shell;
- app factory и ASGI entrypoint для probe-level runtime surface;
- `PW-05` слой `pipelines/pose_words` для decoded RGB -> validated pose -> feature vector boundary без подключения к `/ws/stream`;
- `PW-04` слой `segmentation` для BIO decoder, streaming segmentation state, feature-span extraction и segmentation-specific ONNX wrapper без подключения к `/ws/stream`;
- `PW-03` слой `inference.pose_words` для ONNX classifier inference поверх уже подготовленного feature clip `[T, F]` без подключения к `/ws/stream`;
- `ART-02` слой `runtime.artifacts` для чтения active manifest, проверки обязательных classifier/segmentation files и безопасного разрешения artifact paths без запуска ONNX sessions;
- foundation CI skeleton для `push` и `pull_request`;
- PR template и issue templates;
- каноническая система milestones, epics, labels и task-кодов.

## Что остаётся в draft repo

Репозиторий `gesture-recognition-draft` остаётся местом для:

- экспериментов и research-веток;
- validation path и technical validation;
- bootstrap/fallback сценариев;
- training/export scripts и датасетных утилит;
- transitional logic во время миграции;
- исторического и технического задела, который еще не выделен в clean runtime.

Именно там пока продолжают жить смешанные runtime/training/validation/experimental части. Clean repo не должен притворяться, что этот контур уже перенесен.

## Текущее архитектурное направление

Для словарного распознавания целевым основным pipeline зафиксирован `pose_words`.

Это означает:

- `pose_words` рассматривается как основной будущий product path для word recognition;
- `words` сохраняется как baseline/reference до закрытия validation и integration условий;
- `words` не считается равноправным долгосрочным product path в clean architecture;
- `letters` не является равноправным word-oriented runtime path для clean repo и может рассматриваться только отдельной продуктовой задачей.

Наличие этого решения не означает, что clean repo уже содержит рабочий runtime или production-ready реализацию. На текущем этапе зафиксированы только foundation-границы и migration path.

## Документация

- [docs/architecture.md](docs/architecture.md) — назначение clean repo, целевая архитектура и границы миграции
- [docs/runtime-skeleton.md](docs/runtime-skeleton.md) — target module structure
  и границы runtime skeleton для clean repo
- [docs/artifact-policy.md](docs/artifact-policy.md) — target policy для active runtime artifact manifest, profiles и clean load path
- [docs/mig-02-runtime-required-migration-governance.md](docs/mig-02-runtime-required-migration-governance.md) — governance guardrails и source-to-target mapping для future runtime-required migration issues
- [docs/qa-01-smoke-test-strategy.md](docs/qa-01-smoke-test-strategy.md) — минимальная smoke test strategy для contract, mock, backend smoke и manual checks
- [docs/int-01-web-team-handoff-notes.md](docs/int-01-web-team-handoff-notes.md) — минимальные handoff notes для web team вокруг clean runtime surface
- [docs/contracts/websocket-contract-v1.md](docs/contracts/websocket-contract-v1.md) — versioned WebSocket contract v1 для sign-to-text runtime
- [docs/contracts/mock-protocol-mode.md](docs/contracts/mock-protocol-mode.md) — mock protocol mode поверх contract v1 для web team и smoke-checks без live runtime
- [docs/roadmap.md](docs/roadmap.md) — milestones `M0`-`M3`, зависимости и критерии завершения
- [docs/backlog.md](docs/backlog.md) — epics, стартовые задачи, recommended labels и acceptance criteria
- [CONTRIBUTING.md](CONTRIBUTING.md) — правила работы через issues, branches и PR

## Процесс разработки и migration approach

- Перенос из draft repo идет не массовым копированием, а через milestones, epics и отдельные issues.
- Любой перенос кода, документации или контрактов из `gesture-recognition-draft` должен иметь явную задачу, scope и acceptance criteria.
- Изменения архитектуры, интеграционного контракта или artifact policy должны сопровождаться обновлением документации в том же PR.
- Даже после RT-03 этот репозиторий остается честным минимальным runtime shell, а не полным working ML runtime.

Следующие шаги уже зафиксированы в backlog как issue-scoped migration path, а не как массовый перенос файлов:

- `CTR-01` и `CTR-02` — integration contract и mock protocol mode;
- `RT-01` и `RT-02` — runtime skeleton и health/readiness semantics;
- `PW-01` и `PW-02` — перенос `pose_words` runtime wrapper и segmentation runtime;
- `ART-01` / `ART-02` — active artifact manifest/load path policy и runtime reader/loader;
- `MIG-02` — controlled migration governance для `PW-05`, `PW-03`, `PW-04` и `ART-02`;
- `QA-01` и `INT-01` — smoke/integration strategy и handoff notes.

Текущий clean contour ограничен минимальным probe-level shell, изолированным `PW-05` pose feature layer, изолированным `PW-04` segmentation layer, изолированным `PW-03` pose_words classifier wrapper и `ART-02` active artifact loader/readiness gate. Validation workflows, bootstrap/fallback path, локальные active artifact profiles, реальные model artifacts и machine-local operational runbooks остаются в `gesture-recognition-draft` до отдельных migration tasks.

## PW-05 Pose Feature Runtime Layer

В clean repo появился изолированный слой `rsl_sign_recognition.pipelines.pose_words`:

- strict datatypes для `PoseFrame` и landmark groups;
- lazy MediaPipe wrapper для уже decoded RGB `numpy.uint8` кадров;
- shoulder normalization, leg hiding, 3D hand normalization и deterministic feature composition;
- синхронный dependency-injected service boundary `RGB -> PoseFrame -> feature vector`.

Этот слой не подключен к `WS /ws/stream`, не меняет `/health` или `/ready`, не загружает модели и не отправляет `recognition.result`. Downstream classifier wrapper существует как отдельный изолированный `PW-03` слой; `ART-02` active artifact loader существует отдельно и пока только возвращает resolved artifact paths для будущей сборки runtime.

## PW-04 Segmentation Runtime Layer

В clean repo появился изолированный слой `rsl_sign_recognition.segmentation`:

- BIO decoder для `[T, 3]` probabilities с sanitization `NaN` / `Inf`, `min_len`, `max_len` и `merge_gap`;
- runtime-facing `BioSegment` и `StreamingBioResult` dataclasses с global frame indices;
- `StreamingBioSegmenter`, который принимает feature vectors из будущего `PW-05` stream boundary, агрегирует overlapping BIO outputs и возвращает completed/active sign и phrase segments;
- `get_feature_span(start, end)` внутри segmentation layer без импорта downstream `pose_words` helpers;
- segmentation-specific `BioSegmenterOnnxModel` с ленивым `onnxruntime` import и optional extra `segmentation`.

Этот слой пока не подключен к `WS /ws/stream`, не запускает end-to-end recognition, не отправляет `recognition.result` и не делает `/ready` green. Он задает internal runtime boundary: `PW-05 feature vector -> PW-04 segment bounds/span -> PW-03 classifier`.

## PW-03 Pose Words Inference Wrapper

В clean repo появился изолированный слой `rsl_sign_recognition.inference.pose_words`:

- `PoseWordOnnxModel`, который создается только по уже разрешенным `model_path`, `labels_path` и optional `config_path`;
- lazy `onnxruntime` import и optional extra `pose-words-inference`;
- validation для labels/config, ONNX input rank `[B,T,F]`, static `clip_frames` / `input_dim`, входного feature clip `[T,F]` и classifier output size;
- sanitization `NaN` / `Inf`, normalization logits/probs в probability vector и `find_no_event_index`;
- narrow helper `pipelines.pose_words.clip.resample_to_fixed_T` для already extracted segment clip.

Wrapper сам не ищет active artifacts, не читает manifest, не занимается segmentation, не работает с raw frames, не импортирует WebSocket/API и не отправляет `recognition.result`. `ART-02` теперь отдельно читает active manifest и возвращает resolved paths для будущей сборки runtime, но wrapper пока не подключен к `WS /ws/stream`, не запускает end-to-end recognition и не делает `/ready` green.

## ART-02 Active Artifact Loader

В clean repo появился runtime-facing loader для active `pose_words` artifacts:

- primary manifest path: `artifacts/runtime/active/pose_words/manifest.json`;
- manifest schema version `1` с `profile_role: active`, `readiness_class: live_candidate` и `source_pipeline: pose_words`;
- обязательный live set: `classifier/model.onnx`, `classifier/labels.txt`, `segmentation/model.onnx`, `segmentation/thresholds.json`;
- optional companions: `classifier/runtime_config.json` и `segmentation/runtime_config.json`.

Loader валидирует JSON shape, profile markers, descriptors и безопасно резолвит `relative_path` относительно директории manifest. Absolute paths, empty paths и path traversal через `..` отклоняются controlled runtime failure. Optional files с `required: false` не валят readiness, если физически отсутствуют.

Этот слой не создает ONNX sessions, не импортирует `onnxruntime` или MediaPipe, не копирует bootstrap files, не читает draft `backend/config.yaml` и не сканирует `artifacts/validation/...` или `artifacts/bootstrap/...` как fallback. Даже если `active_artifacts=true`, `/ready` остается `503`, пока `transport_surface=false` из-за отсутствующего live runtime pipeline.

## Minimal Runtime Shell

В clean repo теперь есть минимальный FastAPI runtime shell:

- app factory: `rsl_sign_recognition.create_app()`;
- ASGI entrypoint: `rsl_sign_recognition.asgi:app`;
- probes: `/health` и `/ready`;
- transport endpoint: `WS /ws/stream` для binary JPEG packets и JSON control messages по `contract v1`;
- явные integration boundaries для future runtime services, artifact gates и live transport surface.

Что этот shell **не** делает:

- не выполняет live inference поверх `WS /ws/stream`;
- не загружает `pose_words`, `words` или `letters`;
- не подключает segmentation или classifier inference к live transport path;
- не реализует training/export или draft-only fallback logic;
- не объявляет `/ready = 200`, пока не закрыты `runtime_shell`, `active_artifacts` и `transport_surface`;
- не имитирует `recognition.result`, если live runtime pipeline отсутствует.

`/ready` уже использует active artifact gate: missing manifest, invalid manifest, non-active profile или missing required files переводят `active_artifacts` в `false`. Валидный manifest с placeholder required files может закрыть только этот gate; `LiveTransportSurface.evaluate()` по-прежнему возвращает `live_runtime_pipeline_unavailable`.

Пример локального запуска:

```bash
python3 -m uvicorn rsl_sign_recognition.asgi:app --app-dir src
```

## Foundation CI

`Foundation CI` запускается на `push` и `pull_request` и сейчас проверяет foundation-level контур репозитория, а также минимальный runtime shell contour: наличие ключевых root docs, process templates, самого workflow-файла, `compileall` для `src/tests` и `pytest` для shell-level и focused artifact-loader тестов.

Этот workflow по-прежнему намеренно не запускает full contract suite, live inference WebSocket smoke, ONNX inference, dataset checks или backend tests beyond текущего shell/transport/artifact-reader surface. Такие направления будут добавляться поэтапно отдельными задачами, когда в clean repo действительно появятся соответствующие runtime capabilities.

Итоговая идея проста: `rsl-sign-recognition` — это clean repo для воспроизводимого product-oriented ML runtime, а `gesture-recognition-draft` остается исследовательским и переходным контуром до поэтапной миграции.
