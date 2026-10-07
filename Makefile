PYTHON ?= python3

FRONTENDS := \
	Patch-Generator/frontend \
	Link-Generator/frontend \
	Links-4TU-NL/patch-map-frontend \
	ITU-Calculator/Python-React/frontend

.PHONY: bootstrap-python bootstrap-frontends test lint build check hygiene verify-artifacts

bootstrap-python:
	$(PYTHON) -m pip install -r Compute-Link-Attenuations/requirements-lock.txt

bootstrap-frontends:
	@for directory in $(FRONTENDS); do npm ci --prefix "$$directory" || exit 1; done

test:
	$(PYTHON) -m unittest discover -s Compute-Link-Attenuations/tests -v
	$(PYTHON) -m unittest discover -s Patch-Generator/backend/tests -v

lint:
	@for directory in $(FRONTENDS); do npm run lint --if-present --prefix "$$directory" || exit 1; done

build:
	@for directory in $(FRONTENDS); do npm run build --prefix "$$directory" || exit 1; done

hygiene:
	$(PYTHON) scripts/check_repository_hygiene.py

verify-artifacts:
	$(PYTHON) scripts/verify_artifact_catalog.py

check: hygiene test lint build
	$(PYTHON) -m compileall -q Compute-Link-Attenuations Patch-Generator/backend \
		Link-Generator/backend Links-4TU-NL ITU-Calculator/Python-React/backend
