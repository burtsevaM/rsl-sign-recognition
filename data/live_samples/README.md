# Live sample bundle для DATA-01

Эта директория хранит минимальный переносимый bundle реального video input для будущего `QA-03` smoke через live runtime path.

## Содержимое

- `manifest.json` - machine-readable metadata bundle-а;
- `videos/slovo-privet-f17a6060.mp4` - короткий реальный MP4 sample для label `привет`.

## Правила использования

- bundle должен оставаться доступен по относительному пути `data/live_samples/`;
- sample-файлы внутри этой директории являются live input source: их нужно декодировать в JPEG frames перед отправкой в `WS /ws/stream`;
- при повторном использовании sample-а нужно сохранять attribution, указанную в `manifest.json`;
- synthetic clips, pre-segmented feature clips и mock responses не считаются заменой содержимого этой директории;
- при замене или расширении bundle-а нужно обновить `manifest.json`, checksum и связанную документацию;
- в репозиторий нельзя складывать большие видео, тяжелые датасеты, model dumps и artifact dumps; если bundle станет тяжелым, нужен внешний источник, checksum и инструкция размещения вместо прямого добавления больших файлов в Git.

Подробное назначение, связь с `QA-03` и ограничения описаны в [docs/qa/live-sample-bundle.md](../../docs/qa/live-sample-bundle.md).
