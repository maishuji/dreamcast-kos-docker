UV ?= uv

.PHONY: lint test create-env create-dev-env

lint:
	$(UV) run --locked python -m pylint *.py

test:
	$(UV) run --locked python -m unittest discover -s tests -v

create-env:
	$(UV) sync --locked --no-dev

create-dev-env:
	$(UV) sync --locked
