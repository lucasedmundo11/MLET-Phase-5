# MLET-Phase-5

## Ambiente de Desenvolvimento

**Pré-requisitos:** Python 3.11+, [uv](https://github.com/astral-sh/uv), Docker

```bash
# 1. Clone e entre no diretório
git clone <repo-url> && cd MLET-Phase-5

# 2. Crie e ative o virtualenv
uv venv .venv
source .venv/bin/activate

# 3. Instale as dependências
uv pip install -e ".[dev,eval]"

# 4. Configure as variáveis de ambiente
cp .env.example .env
# edite .env e preencha ANTHROPIC_API_KEY

# 5. Instale os hooks de qualidade
pre-commit install

# 6. Suba os serviços locais (MLflow, Prometheus, Grafana)
docker-compose up -d

# 7. Verifique que tudo está funcionando
make test
```

| Serviço    | URL                      |
|------------|--------------------------|
| API        | <http://localhost:8000>  |
| MLflow     | <http://localhost:5000>  |
| Prometheus | <http://localhost:9090>  |
| Grafana    | <http://localhost:3000>  |

## Testes Locais

**Suite completa com cobertura:**

```bash
make test
# equivalente a: pytest tests/ --cov=src --cov-report=term-missing --cov-fail-under=60
```

**Por arquivo ou módulo:**

```bash
pytest tests/test_features.py       # features de engenharia
pytest tests/test_models.py        # baseline + MLP
pytest tests/test_agent.py         # tools do agente ReAct
pytest tests/test_api.py           # endpoints FastAPI
pytest tests/test_guardrails.py    # guardrails de segurança
```

**Um teste específico:**

```bash
pytest tests/test_guardrails.py::TestInputGuardrail::test_prompt_injection_blocked -v
```

**Lint e tipagem:**

```bash
make lint          # ruff + mypy
make format        # auto-corrige estilo com ruff
```
