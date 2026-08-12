PYTHON ?= python3
export PYTHONPATH := src

.PHONY: install test benchmark benchmark-binding benchmark-all demo api lint ci verify release

install:
	$(PYTHON) -m pip install -e ".[dev]"

test:
	$(PYTHON) -m pytest -q

benchmark:
	$(PYTHON) -m vencertia.cli benchmark run --level L0

# GAP-04: independent Synthetic Claim Binding Benchmark (NOT real-world accuracy).
benchmark-binding:
	$(PYTHON) -m vencertia.cli benchmark run --level CLAIM_BINDING

# L0 + Claim Binding benchmark.
benchmark-all: benchmark benchmark-binding

demo:
	$(PYTHON) examples/demo_b2b_saas_mvp.py

api:
	$(PYTHON) -m uvicorn vencertia.api:app --host 0.0.0.0 --port 8000

lint:
	$(PYTHON) -m ruff check src tests examples

ci: lint test benchmark api-smoke cli-smoke

api-smoke:
	$(PYTHON) -c "from vencertia.api import app; print('API import OK')"

cli-smoke:
	$(PYTHON) -c "from vencertia.cli import app; print('CLI import OK')"

verify: test benchmark
	$(PYTHON) -c "from vencertia.cli import app; print('CLI import OK')"
	$(PYTHON) -c "from vencertia.api import app; print('API import OK')"

release:
	$(PYTHON) scripts/make_release.py
