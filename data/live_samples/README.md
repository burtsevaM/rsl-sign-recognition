# Live sample bundle для DATA-02 / QA-04

Эта директория хранит переносимый bundle реального video input для live e2e smoke через текущий active runtime/model setup.

## Содержимое

- `manifest.json` - machine-readable metadata bundle-а;
- `videos/` - real-video samples из `Slovo`.

Текущий bundle содержит `10` проверяемых gestures:

| sample_id | expected_label | upstream source |
| --- | --- | --- |
| `slovo_privet_f17a6060` | `привет` | public example video из `hukenovs/slovo` |
| `slovo_poka_8ba230dc` | `пока` | trimmed dataset archive |
| `slovo_da_2b1b2857` | `да` | trimmed dataset archive |
| `slovo_horosho_43791c91` | `хорошо` | trimmed dataset archive |
| `slovo_ploho_27560a7e` | `плохо` | trimmed dataset archive |
| `slovo_utro_c1766b2e` | `утро` | trimmed dataset archive |
| `slovo_ulica_908f133b` | `улица` | trimmed dataset archive |
| `slovo_dom_524d6b8f` | `дом` | trimmed dataset archive |
| `slovo_voda_90db4617` | `вода` | trimmed dataset archive |
| `slovo_rabotat_ffce2323` | `работать` | trimmed dataset archive |

Из исходного базового списка удалось подтвердить `привет`, `пока`, `да`, `хорошо`, `плохо`. Для остальных нужных слов в выбранном legal source не нашлись те же labels, поэтому bundle дополнен разрешенными запасными словами `утро`, `улица`, `дом`, `вода`. Из запасного варианта `работа` в source подтвердился только отдельный upstream label `работать`; он добавлен как десятый sample без ручной подгонки label.

## Правила использования

- bundle должен оставаться доступен по относительному пути `data/live_samples/`;
- sample-файлы внутри этой директории являются live input source: их нужно декодировать в JPEG frames перед отправкой в `WS /ws/stream`;
- при повторном использовании sample-а нужно сохранять attribution, указанную в `manifest.json`;
- synthetic clips, pre-segmented feature clips и mock responses не считаются заменой содержимого этой директории;
- при замене или расширении bundle-а нужно обновить `manifest.json`, checksum и связанную документацию;
- в репозиторий нельзя складывать большие видео, тяжелые датасеты, model dumps и artifact dumps; если bundle станет тяжелым, нужен внешний источник, checksum и инструкция размещения вместо прямого добавления больших файлов в Git.

## Быстрые проверки

```bash
python3 -m json.tool data/live_samples/manifest.json
python3 scripts/run_live_e2e_smoke.py --base-url http://127.0.0.1:8000 --sample-manifest data/live_samples/manifest.json --max-samples 10 --min-passed 8 --http-timeout-seconds 60
python3 scripts/run_live_e2e_smoke.py --base-url http://127.0.0.1:8000 --sample-id slovo_privet_f17a6060
```

`QA-04` не обучает новую модель. Bundle нужен, чтобы честно показать, какие gestures текущий active runtime/model setup распознает уже сейчас, а какие пока остаются live smoke gap.

Текущий полный live smoke на `2026-05-19` с active MODEL-01 classifier pack дал `8/10 passed` при пороге `--min-passed 8`. Failed samples остаются видимыми: `пока` и `утро` оба committed как `привет`. Это закрывает минимальный acceptance threshold для `#76`, но не является production-quality доказательством качества модели.

Подробное назначение, source mapping, замены слов и smoke-ограничения описаны в [docs/qa/live-sample-bundle.md](../../docs/qa/live-sample-bundle.md).
