UV ?= uv

.PHONY: lint create-env create-dev-env

lint:
	$(UV) run --locked python -m pylint *.py

create-env:
	$(UV) sync --locked --no-dev

create-dev-env:
	$(UV) sync --locked
