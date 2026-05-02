.PHONY: install install-serve install-eval install-security data train test lint format \
        dvc-repro rag-index serve benchmark eval drift red-team \
        docker-up docker-down clean

install:
	uv pip install -e ".[dev]"

install-serve:
	uv pip install -e ".[dev,serve]"

install-eval:
	uv pip install -e ".[dev,serve,eval,monitor]"

install-security:
	uv pip install -e ".[dev,serve,eval,monitor,security]"
	python -m spacy download pt_core_news_sm

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

# ---------- Etapa 3 — avaliação + observabilidade ----------
eval:
	python -m scripts.run_evaluation --url http://localhost:8000/agent/chat

drift:
	python -m scripts.run_drift_check --window-days 30

# ---------- Etapa 4 — segurança + governança ----------
red-team:
	python -m scripts.run_red_team --url http://localhost:8000/agent/chat

# ---------- qualidade ----------
test:
	pytest tests/ --cov=src --cov-report=term-missing --cov-fail-under=60

lint:
	ruff check src/ tests/ evaluation/
	mypy src/ --ignore-missing-imports

format:
	ruff format src/ tests/ evaluation/

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
