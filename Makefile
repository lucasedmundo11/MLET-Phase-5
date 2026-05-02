.PHONY: install install-serve data train test lint format dvc-repro \
        rag-index serve benchmark docker-up docker-down clean

install:
	uv pip install -e ".[dev]"

install-serve:
	uv pip install -e ".[dev,serve]"

# ---------- Etapa 1 — dados + baseline ----------
data:
	python -m src.features.feature_engineering

train:
	python -m src.models.train

# ---------- Etapa 2 — LLM + agente ----------
rag-index:
	python -m scripts.build_rag_index

serve:
	uvicorn src.serving.app:app --host 0.0.0.0 --port 8000 --reload

benchmark:
	python -m scripts.run_benchmark --config A

# ---------- qualidade ----------
test:
	pytest tests/ --cov=src --cov-report=term-missing --cov-fail-under=60

lint:
	ruff check src/ tests/
	mypy src/ --ignore-missing-imports

format:
	ruff format src/ tests/

dvc-repro:
	dvc repro

docker-up:
	docker-compose up --build -d

docker-down:
	docker-compose down

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -name "*.pyc" -delete
	rm -rf .pytest_cache .mypy_cache .ruff_cache htmlcov
