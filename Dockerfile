FROM python:3.11-slim

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends git build-essential curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
RUN pip install --no-cache-dir uv \
    && uv pip install --system -e ".[dev]"

COPY src/ src/
COPY configs/ configs/
COPY dvc.yaml ./

ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    MLFLOW_TRACKING_URI=http://mlflow:5000

CMD ["bash", "-lc", "python -m src.features.feature_engineering && python -m src.models.train"]
