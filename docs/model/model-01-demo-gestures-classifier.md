# MODEL-01 / PW-07 - Demo gestures active classifier pack

Этот отчет фиксирует training/export active `pose_words` classifier pack для demo dictionary из #78 поверх dataset subset из #79 / PR #83. Pack подключен как текущий runtime active pack:

- manifest: `artifacts/runtime/active/pose_words/manifest.json`;
- classifier: `artifacts/runtime/active/pose_words/classifier/model.onnx`;
- labels: `artifacts/runtime/active/pose_words/classifier/labels.txt`;
- config: `configs/demo_gestures_classifier.json`;
- machine-readable report: `docs/model/model-01-demo-gestures-classifier-results.json`.

## Dataset

Использован materialized manifest `data/demo_gestures/materialized_manifest.json`, подготовленный из `data/demo_gestures/manifest.json`. Local Slovo source на этой машине: `data/slovo/slovo.zip`. Archive не хранится в Git и остается под `.gitignore`.

Final runtime labels:

| id | label |
| ---: | --- |
| 0 | `_no_event` |
| 1 | `привет` |
| 2 | `пока` |
| 3 | `да` |
| 4 | `хорошо` |
| 5 | `плохо` |
| 6 | `утро` |
| 7 | `улица` |
| 8 | `дом` |
| 9 | `вода` |
| 10 | `работать` |

Source labels are preserved in the materialized records. Canonical output labels are read from the materialized manifest. Explicit aliases are limited to `Привет! -> привет` and `no_event -> _no_event`; there is no manual semantic remap for `работать`.

Train/validation counts:

| label | train | validation | total | status |
| --- | ---: | ---: | ---: | --- |
| `_no_event` | 10 | 4 | 14 | ok |
| `привет` | 14 | 5 | 19 | shortage: train -1 |
| `пока` | 14 | 5 | 19 | shortage: train -1 |
| `да` | 14 | 5 | 19 | shortage: train -1 |
| `хорошо` | 14 | 5 | 19 | shortage: train -1 |
| `плохо` | 14 | 5 | 19 | shortage: train -1 |
| `утро` | 15 | 4 | 19 | shortage: validation -1 |
| `улица` | 14 | 5 | 19 | shortage: train -1 |
| `дом` | 14 | 5 | 19 | shortage: train -1 |
| `вода` | 14 | 5 | 19 | shortage: train -1 |
| `работать` | 14 | 5 | 19 | shortage: train -1 |

Live smoke samples from PR #77 are excluded from train/validation:

`slovo_da_2b1b2857`, `slovo_dom_524d6b8f`, `slovo_horosho_43791c91`, `slovo_ploho_27560a7e`, `slovo_poka_8ba230dc`, `slovo_privet_f17a6060`, `slovo_rabotat_ffce2323`, `slovo_ulica_908f133b`, `slovo_utro_c1766b2e`, `slovo_voda_90db4617`.

## Training

Command:

```bash
python3 scripts/train_demo_gestures_classifier.py --config configs/demo_gestures_classifier.json --slovo-root data/slovo
```

The first uncached run used the same command with `--refresh-cache` to regenerate `.cache/demo_gestures_classifier/features`. The committed report was regenerated from cache.

Model:

- feature extractor: MediaPipe pose/hand feature service, `clip_frames=32`, `feature_dim=159`;
- feature projection: temporal summary `mean + std + delta`;
- classifier: standardized linear ridge classifier exported to ONNX;
- class weighting: balanced;
- `ridge_alpha=1.0`, `logit_scale=6.0`;
- segmentation artifact: deterministic isolated-gesture segmenter for one-gesture smoke clips, `window_size=20`, `step=4`.

Rejected records after feature extraction:

| sample_id | split | label | feature_frames | reason |
| --- | --- | --- | ---: | --- |
| `slovo_dom_5ba073a9` | validation | `дом` | 2 | `too_few_feature_frames` |
| `slovo_rabotat_24c6530e` | train | `работать` | 0 | `too_few_feature_frames` |
| `slovo_rabotat_3f59dd19` | train | `работать` | 4 | `too_few_feature_frames` |

## Offline Validation

Overall:

- train accuracy: `1.000000` on 447 prepared train windows;
- validation accuracy: `0.653846` on 52 prepared validation windows.

Validation metrics:

| label | precision | recall | f1 | validation count | notes |
| --- | ---: | ---: | ---: | ---: | --- |
| `_no_event` | 0.571429 | 1.000000 | 0.727273 | 4 | background only |
| `привет` | 0.200000 | 0.200000 | 0.200000 | 5 | weak |
| `пока` | 0.666667 | 0.800000 | 0.727273 | 5 | weak |
| `да` | 0.666667 | 0.400000 | 0.500000 | 5 | weak |
| `хорошо` | 1.000000 | 0.400000 | 0.571429 | 5 | weak recall |
| `плохо` | 1.000000 | 1.000000 | 1.000000 | 5 | strongest validation class |
| `утро` | 0.400000 | 0.500000 | 0.444444 | 4 | weak |
| `улица` | 0.666667 | 0.800000 | 0.727273 | 5 | weak |
| `дом` | 1.000000 | 0.750000 | 0.857143 | 4 | validation shortage |
| `вода` | 0.600000 | 0.600000 | 0.600000 | 5 | weak |
| `работать` | 0.800000 | 0.800000 | 0.800000 | 5 | weak |

Weak classes are not hidden. The weakest validation classes are `привет`, `утро`, `да`, `хорошо`, and `вода`. Full failed validation cases and confusion matrix are in `docs/model/model-01-demo-gestures-classifier-results.json`.

Baseline comparison: the previous active pack knew only `_no_event`, `привет`, and `пока`, so it could not satisfy #78 for the 10-gesture smoke bundle. The new pack contains all required runtime labels and is loaded by `LivePoseWordsRuntimeService`.

## Artifact

| artifact | path | size | sha256 |
| --- | --- | ---: | --- |
| classifier model | `artifacts/runtime/active/pose_words/classifier/model.onnx` | 25855 | `cc09bdba1bc29666a2f09992c24c736b7cc832e56e2be767f018b013c95a4e2a` |
| labels | `artifacts/runtime/active/pose_words/classifier/labels.txt` | 114 | `4a396fadf60f00e6f58ad7a3dafa49ae05fc1c93e039dec12b2cce59df76635f` |
| classifier config | `artifacts/runtime/active/pose_words/classifier/runtime_config.json` | 929 | `3d7413035aed77f5b7dc04fc2bd0657b406f67e7cd0925c5beb86c7bad22dbbe` |
| segmentation model | `artifacts/runtime/active/pose_words/segmentation/model.onnx` | 815 | `2d79af54e10ae38c158a7ace3a83effce0e311b5a9ca8e75a96050ff517a1c4b` |
| thresholds | `artifacts/runtime/active/pose_words/segmentation/thresholds.json` | 382 | `ea5bd4b3b3386b0666ca9e58442a37da4760ac9de142bfd37f8a92abedf17cf0` |
| segmentation config | `artifacts/runtime/active/pose_words/segmentation/runtime_config.json` | 652 | `cfdf592e15b562f8dc23c7a69a2c730f4b9bb9ca233fce4ef965b67cb96eafeb` |

The artifact files are lightweight and committed in the existing active runtime layout. The Slovo archive and cache are not committed.

## Runtime

Runtime loads the new active pack through `artifacts/runtime/active/pose_words/manifest.json`. The active labels check returns all 10 demo gestures plus `_no_event`; `ActiveArtifactGate` passes; `LivePoseWordsRuntimeService` initializes as `ready`.

`PoseWordsLiveSession` also flushes a short isolated segment on a no-hand boundary when the clip ends before the standard segmentation window. This is needed for short one-gesture smoke samples and does not change the WebSocket contract or per-sample pass criteria.

## Links

- Closes scope: #78, #80, #81, #82 when paired with the smoke evidence in `docs/qa/model-01-live-smoke.md`.
- Related: #79 / PR #83 for dataset subset, #76 / PR #77 for live smoke bundle, PR #75 for the previous `привет` baseline.

## Limitations

- Small dataset: most gesture classes have only 19 materialized records after live-smoke exclusions.
- Validation accuracy is modest; `привет` and `утро` remain weak offline/live classes.
- Follow-up for improving demo classifier quality to `9/10` or `10/10` live smoke: #85.
- The segmentation artifact is deterministic for isolated one-gesture clips and is not a production sign boundary model.
- This closes the active classifier pack gap for #78; broader QA around #76 / PR #77 should still update downstream smoke ownership separately.
