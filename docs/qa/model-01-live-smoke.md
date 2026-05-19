# MODEL-01 / PW-07 - Live smoke report

This report records the live e2e smoke evidence for #78 using the active demo gestures classifier pack from `artifacts/runtime/active/pose_words/`.

## Setup

Server:

```bash
python3 -m uvicorn rsl_sign_recognition.asgi:app --app-dir src --host 127.0.0.1 --port 8010
```

Full smoke command:

```bash
python3 scripts/run_live_e2e_smoke.py --base-url http://127.0.0.1:8010 --sample-manifest .cache/live_samples_pr77/manifest.json --max-samples 10 --min-passed 8 --http-timeout-seconds 60
```

Strict production-style command:

```bash
python3 scripts/run_live_e2e_smoke.py --base-url http://127.0.0.1:8010 --sample-manifest .cache/live_samples_pr77/manifest.json --max-samples 10 --http-timeout-seconds 60
```

The manifest used here is a local materialization of the 10-sample PR #77 live smoke bundle. It is not committed because PR #77 is still open and the video files come from local `data/slovo/slovo.zip`. Training/validation data excludes all 10 smoke sample ids.

For #78 the honest minimum acceptance threshold is `8/10 passed`, so the recommended command uses `--min-passed 8`. The pass criteria for every individual sample remain strict: `committed=true` and `actual_label == expected_label`. For production/strict QA, run without `--min-passed` or use `--min-passed 10`; failed samples remain visible in both modes.

## Full Bundle Result

Result: `9/10 passed` in `29.98s`.

With `--min-passed 8`, the runner returns exit code `0` because the #78 threshold is met. In strict mode without `--min-passed`, the same run returns non-zero because not all samples pass. The runner still reports the failed sample explicitly, so the table is the acceptance evidence for the #78 minimum of 8/10 and the #85 quality improvement to 9/10.

| sample_id | expected | actual | committed | confidence | result |
| --- | --- | --- | --- | ---: | --- |
| `slovo_privet_f17a6060` | `привет` | `привет` | true | 0.938670 | PASS |
| `slovo_poka_8ba230dc` | `пока` | `пока` | true | 0.467108 | PASS |
| `slovo_da_2b1b2857` | `да` | `да` | true | 0.941735 | PASS |
| `slovo_horosho_43791c91` | `хорошо` | `хорошо` | true | 0.978893 | PASS |
| `slovo_ploho_27560a7e` | `плохо` | `плохо` | true | 0.991616 | PASS |
| `slovo_utro_c1766b2e` | `утро` | `дом` | true | 0.799179 | FAIL |
| `slovo_ulica_908f133b` | `улица` | `улица` | true | 0.875830 | PASS |
| `slovo_dom_524d6b8f` | `дом` | `дом` | true | 0.295213 | PASS |
| `slovo_voda_90db4617` | `вода` | `вода` | true | 0.999952 | PASS |
| `slovo_rabotat_ffce2323` | `работать` | `работать` | true | 0.991799 | PASS |

All passed samples have `committed=true` and `actual_label == expected_label`. Failed samples are not hidden: `утро` is committed as `дом`. The previous `пока -> привет` live failure is fixed by the updated isolated-gesture window.

## Failed samples analysis

The remaining failed live smoke sample is consistent with the weak-class profile from offline validation. Offline validation accuracy is `0.673077`; the weakest classes include `да`, `утро`, `привет`, `пока`, `вода`, and `работать`. The full offline confusion matrix and failed validation cases are recorded in `docs/model/model-01-demo-gestures-classifier-results.json`.

| sample_id | expected | actual | confidence | committed | analysis |
| --- | --- | --- | ---: | --- | --- |
| `slovo_utro_c1766b2e` | `утро` | `дом` | 0.799179 | true | `утро` remains weak offline (`precision=0.333333`, `recall=0.500000`, `f1=0.400000`). The live confusion with `дом` is plausible given similar upper-body/hand feature summaries on the shortened isolated segment, small train/validation subset size after excluding live smoke samples, deterministic isolated-gesture segmentation, feature extraction or hand-visibility sensitivity, and possible domain shift between train/validation records and the live clip. |

What was not done:

- failed samples were not removed;
- expected/actual labels were not substituted;
- live smoke samples were not used as train data;
- there is no hardcode by `sample_id`, filename, or expected label.

## Per-Sample Evidence

Single-sample diagnostic command template:

```bash
python3 scripts/run_live_e2e_smoke.py --base-url http://127.0.0.1:8010 --sample-manifest .cache/live_samples_pr77/manifest.json --sample-id <sample_id> --http-timeout-seconds 60
```

The table below records the final committed label observed for each sample in the full bundle run. It uses the same strict pass criteria as the runner: `committed=true` and `actual_label == expected_label`.

| sample_id | expected | actual | committed | confidence | result |
| --- | --- | --- | --- | ---: | --- |
| `slovo_privet_f17a6060` | `привет` | `привет` | true | 0.938670 | PASS |
| `slovo_poka_8ba230dc` | `пока` | `пока` | true | 0.467108 | PASS |
| `slovo_da_2b1b2857` | `да` | `да` | true | 0.941735 | PASS |
| `slovo_horosho_43791c91` | `хорошо` | `хорошо` | true | 0.978893 | PASS |
| `slovo_ploho_27560a7e` | `плохо` | `плохо` | true | 0.991616 | PASS |
| `slovo_utro_c1766b2e` | `утро` | `дом` | true | 0.799179 | FAIL |
| `slovo_ulica_908f133b` | `улица` | `улица` | true | 0.875830 | PASS |
| `slovo_dom_524d6b8f` | `дом` | `дом` | true | 0.295213 | PASS |
| `slovo_voda_90db4617` | `вода` | `вода` | true | 0.999952 | PASS |
| `slovo_rabotat_ffce2323` | `работать` | `работать` | true | 0.991799 | PASS |

## Runtime Checks

Verified active runtime state:

- `ActiveArtifactGate(...).evaluate().passed == True`;
- labels loaded from `classifier/labels.txt` are `_no_event` plus all 10 demo gestures;
- `LivePoseWordsRuntimeService.from_settings(...).initialize().status == ready`;
- runtime pipeline uses `clip_frames=32`, `feature_dim=159`, segmentation `window=18`, `step=4`.

## Risks

- The live minimum is met and improved to `9/10`, but not perfect: `утро` remains confused with `дом`.
- The classifier is trained on a small subset and should not be treated as production-quality.
- Follow-up for improving demo classifier quality to `10/10`: #85.
- PR #77 / #76 still need downstream ownership after this active pack gap is closed.
