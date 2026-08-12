PYTHON ?= /Users/panhao/.workbuddy/binaries/python/envs/default/bin/python
export PYTHONPATH := src

.PHONY: install test benchmark demo api verify

install:
	$(PYTHON) -m pip install -e ".[dev]"

test:
	$(PYTHON) -m pytest -q

benchmark:
	$(PYTHON) -m vencertia.cli benchmark run --level L0

demo:
	$(PYTHON) examples/demo_b2b_saas_mvp.py

api:
	$(PYTHON) -m uvicorn vencertia.api:app --host 0.0.0.0 --port 8000

verify: test benchmark
	$(PYTHON) -c "from vencertia.cli import app; print('CLI import OK')"
	$(PYTHON) -c "from vencertia.api import app; print('API import OK')"
