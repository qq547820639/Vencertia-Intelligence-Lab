.PHONY: test benchmark demo api verify

test:
	PYTHONPATH=src pytest -q

benchmark:
	PYTHONPATH=src python -m vencertia.cli benchmark --path data/benchmarks/v0.2.jsonl

demo:
	PYTHONPATH=src python -m vencertia.cli demo

api:
	PYTHONPATH=src uvicorn vencertia.api:app --host 0.0.0.0 --port 8000

verify: test benchmark
