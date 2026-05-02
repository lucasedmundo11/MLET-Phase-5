.PHONY: install train serve test lint format clean

install:
	uv pip install -e ".[dev,eval]"

train:
	python -m src.models.train

serve:
	uvicorn src.serving.app:app --host 0.0.0.0 --port 8000 --reload

test:
	pytest tests/ --cov=src --cov-report=term-missing --cov-fail-under=60

lint:
	ruff check src/ tests/ evaluation/
	mypy src/ --ignore-missing-imports

format:
	ruff format src/ tests/ evaluation/

evaluate:
	python evaluation/ragas_eval.py

ab-test:
	python evaluation/ab_test_prompts.py

docker-up:
	docker-compose up --build -d

docker-down:
	docker-compose down

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -name "*.pyc" -delete
	rm -rf .pytest_cache .mypy_cache .ruff_cache htmlcov
