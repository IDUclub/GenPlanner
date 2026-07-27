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