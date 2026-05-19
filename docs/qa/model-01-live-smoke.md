# MODEL-01 / PW-07 - Live smoke report

This report records the live e2e smoke evidence for #78 using the active demo gestures classifier pack from `artifacts/runtime/active/pose_words/`.

## Setup

Server:

```bash
python3 -m uvicorn rsl_sign_recognition.asgi:app --app-dir src --host 127.0.0.1 --port 8010
```

Full smoke command:

```bash
python3 scripts/run_live_e2e_smoke.py --base-url http://127.0.0.1:8010 --sample-manifest .cache/live_samples_pr77/manifest.json --max-samples 10 --http-timeout-seconds 60
```

The manifest used here is a local materialization of the 10-sample PR #77 live smoke bundle. It is not committed because PR #77 is still open and the video files come from local `data/slovo/slovo.zip`. Training/validation data excludes all 10 smoke sample ids.

## Full Bundle Result

Result: `8/10 passed` in `21.86s`.

The runner still reports each failed sample explicitly. It returns non-zero when any sample fails, so the table is the acceptance evidence for the #78 minimum of 8/10.

| sample_id | expected | actual | committed | confidence | result |
| --- | --- | --- | --- | ---: | --- |
| `slovo_privet_f17a6060` | `привет` | `привет` | true | 0.963399 | PASS |
| `slovo_poka_8ba230dc` | `пока` | `привет` | true | 0.551401 | FAIL |
| `slovo_da_2b1b2857` | `да` | `да` | true | 0.988729 | PASS |
| `slovo_horosho_43791c91` | `хорошо` | `хорошо` | true | 0.978083 | PASS |
| `slovo_ploho_27560a7e` | `плохо` | `плохо` | true | 0.926392 | PASS |
| `slovo_utro_c1766b2e` | `утро` | `привет` | true | 0.778988 | FAIL |
| `slovo_ulica_908f133b` | `улица` | `улица` | true | 0.909317 | PASS |
| `slovo_dom_524d6b8f` | `дом` | `дом` | true | 0.351575 | PASS |
| `slovo_voda_90db4617` | `вода` | `вода` | true | 0.999998 | PASS |
| `slovo_rabotat_ffce2323` | `работать` | `работать` | true | 0.993223 | PASS |

All passed samples have `committed=true` and `actual_label == expected_label`. Failed samples are not hidden: `пока` and `утро` are both committed as `привет`.

## Single-Sample Runs

Single-sample command template:

```bash
python3 scripts/run_live_e2e_smoke.py --base-url http://127.0.0.1:8010 --sample-manifest .cache/live_samples_pr77/manifest.json --sample-id <sample_id> --http-timeout-seconds 60
```

| sample_id | expected | actual | committed | confidence | single-sample result |
| --- | --- | --- | --- | ---: | --- |
| `slovo_privet_f17a6060` | `привет` | `привет` | true | 0.963399 | 1/1 PASS |
| `slovo_poka_8ba230dc` | `пока` | `привет` | true | 0.551401 | 0/1 FAIL |
| `slovo_da_2b1b2857` | `да` | `да` | true | 0.988729 | 1/1 PASS |
| `slovo_horosho_43791c91` | `хорошо` | `хорошо` | true | 0.978083 | 1/1 PASS |
| `slovo_ploho_27560a7e` | `плохо` | `плохо` | true | 0.926392 | 1/1 PASS |
| `slovo_utro_c1766b2e` | `утро` | `привет` | true | 0.778988 | 0/1 FAIL |
| `slovo_ulica_908f133b` | `улица` | `улица` | true | 0.909317 | 1/1 PASS |
| `slovo_dom_524d6b8f` | `дом` | `дом` | true | 0.351575 | 1/1 PASS |
| `slovo_voda_90db4617` | `вода` | `вода` | true | 0.999998 | 1/1 PASS |
| `slovo_rabotat_ffce2323` | `работать` | `работать` | true | 0.993223 | 1/1 PASS |

## Runtime Checks

Verified active runtime state:

- `ActiveArtifactGate(...).evaluate().passed == True`;
- labels loaded from `classifier/labels.txt` are `_no_event` plus all 10 demo gestures;
- `LivePoseWordsRuntimeService.from_settings(...).initialize().status == ready`;
- runtime pipeline uses `clip_frames=32`, `feature_dim=159`, segmentation `window=20`, `step=4`.

## Risks

- The live minimum is met but not perfect: `пока` and `утро` remain confused with `привет`.
- The classifier is trained on a small subset and should not be treated as production-quality.
- PR #77 / #76 still need downstream ownership after this active pack gap is closed.
