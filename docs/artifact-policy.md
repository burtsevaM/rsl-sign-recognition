# ART-01 - Active Runtime Artifact Manifest и Load Path

## 1. Назначение документа

Этот документ закрывает docs/policy часть issue `#23 ART-01`.

Его задача:

- зафиксировать **expected active runtime artifact layout** для clean runtime contour;
- определить **manifest contract** для active runtime artifacts;
- развести `active`, `validation` и `bootstrap` artifacts без смешения профилей;
- описать **readiness semantics** для missing artifacts и non-active профилей;
- зафиксировать **primary load path** без обязательной зависимости на draft-only `config.yaml`.

Документ **не** переносит runtime-код, **не** реализует loader и **не** делает вид, что clean repo уже содержит рабочий artifact reader.

## 2. Scope и non-goals

В scope ART-01 входят только policy-границы для clean runtime:

- expected layout для active runtime artifacts;
- manifest fields и markers, нужные для разделения профилей;
- load-path expectations для clean runtime;
- readiness expectations для missing files и non-active profiles;
- явная граница между product-runtime contour и draft bootstrap/validation context.

В ART-01 **не входят**:

- реализация manifest reader;
- реализация loader;
- install/promote workflow;
- validation runners;
- bootstrap scripts;
- dataset preparation;
- перенос operational `config.yaml`-centric path из draft repo.

## 3. Expected artifact layout

Ниже зафиксирован **целевой layout policy**, а не описание уже существующих файлов в clean repo.

```text
artifacts/
  runtime/
    active/
      pose_words/
        manifest.json
        classifier/
          model.onnx
          labels.txt
          runtime_config.json      # optional companion metadata
        segmentation/
          model.onnx
          thresholds.json
          runtime_config.json      # optional companion metadata
  validation/
    pose_words/
      <profile_id>/
        manifest.json
        ...
  bootstrap/
    pose_words/
      <profile_id>/
        manifest.json
        ...
```

Ключевой смысл этого layout:

- только `artifacts/runtime/active/...` является **primary clean runtime path**;
- `artifacts/validation/...` содержит validation outputs и validation manifests, но не primary runtime load root;
- `artifacts/bootstrap/...` допускается как fallback/dev-recovery contour, но не как основной runtime path;
- non-active directories не должны рассматриваться runtime как автообнаруживаемые источники live artifacts.

## 4. Active runtime set для `pose_words`

Для первого clean runtime increment `pose_words` contour считается **единым active runtime set**, который состоит из двух обязательных подгрупп:

### 4.1. Classifier artifacts

- `classifier/model.onnx` - обязательная ONNX model для `pose_words` classifier path;
- `classifier/labels.txt` - обязательный labels file для classifier outputs;
- `classifier/runtime_config.json` - optional companion metadata/validator, если такой файл действительно существует для выбранного active profile.

### 4.2. Segmentation artifacts

- `segmentation/model.onnx` - обязательная ONNX model для BIO segmentation runtime;
- `segmentation/thresholds.json` - обязательный thresholds file для segmentation decode/runtime behavior;
- `segmentation/runtime_config.json` - optional companion metadata/validator, если такой файл существует для выбранного profile.

## 5. Как policy учитывает `segmentation`

`segmentation` в clean repo не считается hidden detail внутри classifier path.

Для `pose_words` contour это означает:

- segmentation artifacts входят в **обязательный active runtime set**, а не в отдельный "вспомогательный хвост";
- они живут в отдельной subtree `segmentation/`, чтобы ownership `segmentation` не смешивался с classifier files;
- отсутствие segmentation model или thresholds означает, что `pose_words` live path не готов даже если classifier model присутствует;
- ART-01 фиксирует только layout/policy для segmentation artifacts, а не переносит сам segmentation runtime code из `PW-02`.

Иначе говоря:

- `pose_words` остается primary contour;
- `segmentation` остается обязательной upstream dependency этого contour;
- policy не превращает `segmentation` в отдельный bootstrap или validation-only path.

## 6. Что относится к active, validation и bootstrap

### 6.1. Active runtime artifacts

К `active runtime artifacts` относятся только:

- manifest в `artifacts/runtime/active/pose_words/manifest.json`;
- classifier files, на которые этот manifest ссылается;
- segmentation files, на которые этот manifest ссылается;
- metadata, достаточная для load path и readiness evaluation live runtime path.

### 6.2. Validation artifacts

К `validation artifacts` относятся:

- outputs validation run-ов;
- validation-specific manifests;
- provenance/quality metadata, нужная для technical validation;
- candidate profiles, которые еще **не стали active runtime set**.

Validation artifacts могут иметь тот же базовый schema shape, что и active manifest, но:

- живут только под `artifacts/validation/...`;
- не являются primary load source для clean runtime;
- не закрывают `active_artifacts` gate, пока не появится отдельный active manifest.

### 6.3. Bootstrap artifacts

К `bootstrap artifacts` относятся:

- fallback/dev-recovery наборы;
- минимальные или dummy-like артефакты, созданные для восстановления контура или локального запуска;
- manifest-профили, которые должны явно маркироваться как `bootstrap`, а не как normal live-ready active profile.

Bootstrap contour может существовать, но:

- не является primary clean runtime path;
- не должен подменять live-ready active profile;
- не должен silently загружаться runtime вместо отсутствующего active profile.

## 7. Expected manifest contract

Active manifest должен быть **самодостаточной точкой правды** для clean runtime path.

Минимальный JSON shape:

```json
{
  "schema_version": 1,
  "contour": "pose_words",
  "profile_id": "runtime_active",
  "profile_role": "active",
  "profile_origin": "runtime",
  "readiness_class": "live_candidate",
  "source_pipeline": "pose_words",
  "files": {
    "classifier_model": {
      "relative_path": "classifier/model.onnx",
      "component": "pose_words_classifier",
      "artifact_kind": "model",
      "required": true,
      "trained": true
    },
    "classifier_labels": {
      "relative_path": "classifier/labels.txt",
      "component": "pose_words_classifier",
      "artifact_kind": "labels",
      "required": true,
      "trained": true
    },
    "classifier_config": {
      "relative_path": "classifier/runtime_config.json",
      "component": "pose_words_classifier",
      "artifact_kind": "runtime_config",
      "required": false
    },
    "segmentation_model": {
      "relative_path": "segmentation/model.onnx",
      "component": "bio_segmentation",
      "artifact_kind": "model",
      "required": true,
      "trained": true
    },
    "segmentation_thresholds": {
      "relative_path": "segmentation/thresholds.json",
      "component": "bio_segmentation",
      "artifact_kind": "thresholds",
      "required": true
    },
    "segmentation_config": {
      "relative_path": "segmentation/runtime_config.json",
      "component": "bio_segmentation",
      "artifact_kind": "runtime_config",
      "required": false
    }
  }
}
```

Этот пример фиксирует **policy shape**, а не обязательный формат будущей Python-модели данных.

## 8. Required manifest markers

Чтобы не смешивать active, validation и bootstrap profiles, manifest или эквивалентный metadata carrier должен хранить как минимум:

- `schema_version` - версия manifest schema;
- `contour` - для какого runtime contour предназначен набор, здесь `pose_words`;
- `profile_id` - конкретный identifier профиля;
- `profile_role` - `active`, `validation` или `bootstrap`;
- `profile_origin` - откуда этот набор произошел: `runtime`, `validation`, `bootstrap`;
- `readiness_class` - допускается ли этот profile к live readiness; для текущего increment ожидаются значения `live_candidate`, `validation_only`, `bootstrap_fallback`;
- `source_pipeline` - какой pipeline является владельцем набора;
- `files.<name>.relative_path` - runtime-relative путь внутри profile root;
- `files.<name>.component` - classifier или segmentation ownership;
- `files.<name>.artifact_kind` - `model`, `labels`, `thresholds`, `runtime_config` и т.д.;
- `files.<name>.required` - является ли файл обязательным для live load path;
- `files.<name>.trained` - marker для trained/non-trained model-like artifacts, где это применимо.

Допустимые дополнительные поля:

- `generated_by`;
- `dataset_kind`;
- checksum/digest поля;
- timestamps и provenance notes.

Полезная адаптация draft context здесь такая:

- draft-поле наподобие `active_artifact_profile` в clean policy раскладывается на `profile_id` + `profile_role` + `profile_origin`;
- поля вроде `artifact_kind`, `trained`, `source_pipeline`, `generated_by`, `dataset_kind` сохраняют архитектурную пользу, но больше не должны быть привязаны к draft-only install/promote workflow.

## 9. Primary load path для clean runtime

Primary load path фиксируется так:

1. clean runtime в `live` path обращается только к `artifacts/runtime/active/pose_words/manifest.json`;
2. все file paths внутри manifest разрешаются **относительно директории manifest**, а не через machine-local absolute paths;
3. runtime не должен сканировать `artifacts/validation/...` или `artifacts/bootstrap/...` в поисках "лучшего" профиля;
4. runtime не должен вычислять active profile через draft-only `config.yaml`;
5. runtime не должен трактовать bootstrap path как default replacement для missing active set.

Следствие:

- manifest является primary runtime pointer;
- layout остается self-contained внутри clean repo policy;
- runtime path не зависит от draft repo topology и machine-local recovery conventions.

## 10. Missing files и readiness semantics

### 10.1. Missing active manifest

Если отсутствует `artifacts/runtime/active/pose_words/manifest.json`, то:

- `active_artifacts = false`;
- `/ready` должен возвращать `HTTP 503`;
- `/health` может оставаться `HTTP 200`, если процесс жив;
- runtime не должен silently переключаться на validation или bootstrap directories.

### 10.2. Missing required files

Если manifest существует, но отсутствует хотя бы один `required: true` file:

- active profile считается **not ready**;
- `/ready` должен возвращать `HTTP 503`;
- причина должна быть видна как missing required active artifacts;
- classifier-only partial state не считается допустимым ready state, если segmentation subgroup неполный;
- optional companion metadata files с `required: false` не должны валить readiness сами по себе.

### 10.3. Missing non-active files

Отсутствие файлов внутри `artifacts/validation/...` или `artifacts/bootstrap/...`:

- не должно влиять на primary live readiness, пока runtime не опирается на эти профили;
- не превращает runtime в ready;
- не должно использоваться как повод менять active load path автоматически.

## 11. Readiness semantics для active и non-active профилей

`profile_role: active` является необходимым, но недостаточным условием live readiness.

Live-ready profile должен одновременно:

- находиться в primary active path;
- иметь `profile_role: active`;
- иметь `readiness_class`, совместимый с live runtime path;
- содержать все required files для classifier и segmentation;
- не требовать обращения к draft-only bootstrap/config fallback path.

Для non-active профилей правило такое:

- `validation` profile может быть полным и полезным для technical validation, но сам по себе не закрывает `active_artifacts` gate;
- `bootstrap` profile может существовать для fallback/dev-recovery, но сам по себе не считается normal live-ready profile;
- `readiness_class: validation_only` и `readiness_class: bootstrap_fallback` не должны переводить live runtime в `ready`, даже если все файлы profile физически на месте;
- наличие non-active manifest не должно превращать `/ready` в `HTTP 200`.

## 12. Статус bootstrap path

Bootstrap path допускается только как **fallback/dev-recovery contour**.

Это означает:

- clean runtime policy не считает bootstrap directories primary load roots;
- bootstrap profile не должен автоматически подставляться, если missing active files;
- manual dev-recovery может использовать bootstrap set только как осознанное исключение, а не как нормальный product path;
- даже если bootstrap set временно materialized рядом с active layout, его metadata должны сохранять `profile_origin: bootstrap` и `readiness_class: bootstrap_fallback`, а не маскироваться под normal live-ready runtime profile.

Иначе clean repo снова смешает reproducible runtime contour с transitional recovery logic из draft repo.

## 13. Почему `config.yaml` не должен стать обязательной опорой

Draft repo использует `config.yaml` и соседние runtime paths как часть смешанного operational/bootstrap контура.

Для clean repo это не должно становиться обязательной policy-опорой без отдельной migration task, потому что:

- `config.yaml` описывает draft-level operational wiring, а не self-contained active artifact manifest;
- dependency на `config.yaml` повторно привязала бы clean runtime к draft topology и machine-local conventions;
- `PW-01` и `PW-02` уже фиксируют, что model-local config files допустимы только как **optional validators**, а не как центральный registry всего runtime contour;
- обязательный `config.yaml` снова смешал бы active path с bootstrap/fallback logic и transitional configuration decisions.

Следовательно:

- model-local `runtime_config.json` может существовать как optional companion metadata;
- draft-only `config.yaml` не является required load root;
- любое решение вернуть config-centric runtime path должно оформляться отдельной migration task.

## 14. Что этот документ намеренно не делает

Этот policy increment:

- не реализует manifest reader;
- не описывает install/promote workflow;
- не обещает, что artifacts уже лежат в репозитории;
- не делает bootstrap главным runtime-сценарием;
- не подменяет собой `PW-01`, `PW-02`, `RT-02` или будущую implementation task.

Он только фиксирует честную target policy, внутри которой следующий implementation increment сможет загружать **active runtime artifacts** без опоры на draft-only `config.yaml` и без превращения bootstrap path в основной clean runtime сценарий.
