.PHONY: install data train test lint format dvc-repro docker-up docker-down clean

install:
	uv pip install -e ".[dev]"

data:
	python -m src.features.feature_engineering

train:
	python -m src.models.train

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
