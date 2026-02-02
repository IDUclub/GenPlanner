CODE := app

build-and-publish: clean build publish

lint:
	poetry run pylint $(CODE)

format:
	poetry run isort $(CODE)
	poetry run black $(CODE)

install:
	pip install .

install-dev:
	poetry install --with dev

clean:
	rm -rf ./dist