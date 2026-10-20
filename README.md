# GenPlanner

[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

GenPlanner REST API interface. Interactive documentation is available on /docs.

## Development

```
poetry install
poetry run pytest tests -q
poetry run black --check .
poetry run pylint app
poetry run pylint --rcfile=tests/.pylintrc tests
```

`tests/.pylintrc` relaxes pytest-fixture-related rules (e.g. `redefined-outer-name`) that
don't apply to test code; it isn't auto-discovered, so `pylint tests` must be run with
`--rcfile=tests/.pylintrc` explicitly or it silently falls back to the root config.
## Текстовые отчёты сервиса

После выполнения операции чат дополнительно возвращает событие `file` с
`name: "report"`, `role: "report"`, `mime_type: "text/plain"`, `filename: "report.txt"`.
Обычный текстовый ответ остаётся в потоке. Ссылка на отчёт сохраняется рядом с ним
в истории ChatStorage как часть `kind: "file"`; содержимое файла в историю не копируется.

Дескриптор содержит две долговечные ссылки относительно базы `source_service`:

- `url`: `GET /genplanner/reports/id` — UTF-8 текст для просмотра (`Content-Disposition: inline`).
- `download_url`: тот же адрес с `?download=true` — скачивание (`attachment; filename="report.txt"`).

В SSE `event: file` поля дескриптора находятся непосредственно в JSON `data`.
Отчёт выдаётся после успешной генерации как по сценарию, так и по загруженной территории. Он включает полный ответ, количество зон и дорог и выбранные параметры.

Фронтенду следует читать отчёт как текст, не как GeoJSON и не как HTML. Для показа
достаточно `fetch(url).text()` и текстового компонента с сохранением переносов строк.
Ссылки проходят через API сервиса: доступ к внутреннему MinIO браузеру не нужен.
При сбое хранилища выдаётся `warning` с `stage: store_report`; ответ и результаты операции сохраняются.
