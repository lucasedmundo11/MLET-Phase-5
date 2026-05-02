# src/serving/ — FastAPI + LLM Quantizado

API REST que serve o LLM quantizado (GGUF) e o agente ReAct com telemetria Prometheus integrada e guardrails de segurança. Cobre as **Etapas 2, 3 e 4** do Datathon.

---

## Sumário

1. [Visão Geral](#visão-geral)
2. [Endpoints](#endpoints)
3. [Ciclo de Vida de uma Requisição](#ciclo-de-vida-de-uma-requisição)
4. [LLM Quantizado](#llm-quantizado)
5. [Telemetria Prometheus](#telemetria-prometheus)
6. [Segurança Integrada](#segurança-integrada)
7. [Docker](#docker)
8. [Uso](#uso)

---

## Visão Geral

```
src/serving/
├── __init__.py
├── app.py        # FastAPI application + endpoints + middleware
└── Dockerfile    # multi-stage build (builder → runtime)
```

**Porta padrão:** `8000`

---

## Endpoints

| Método | Path | Descrição | Etapa |
|--------|------|-----------|-------|
| `GET` | `/health` | Liveness/readiness check | 2 |
| `GET` | `/metrics` | Prometheus exposition format | 3 |
| `POST` | `/llm/complete` | Completion direta no LLM GGUF | 2 |
| `POST` | `/agent/chat` | Pergunta → guardrail → ReAct → guardrail → resposta | 2/4 |

### `GET /health`

```json
{"status": "ok"}
```

### `POST /llm/complete`

**Request:**
```json
{
  "prompt": "Explique o que é RSI em análise técnica.",
  "max_tokens": 256,
  "temperature": 0.0
}
```

**Response:**
```json
{
  "completion": "RSI (Relative Strength Index) é...",
  "model": "qwen2.5-3b-instruct-q4_k_m.gguf",
  "tokens_used": 128
}
```

### `POST /agent/chat`

**Request:**
```json
{
  "question": "Qual ação teve maior retorno em 2024?"
}
```

**Response:**
```json
{
  "answer": "Em 2024, VALE3.SA teve o maior retorno com 32.10%...",
  "intermediate_steps": 3,
  "guardrail_action": "none"
}
```

**`guardrail_action` possíveis:**

| Valor | Significado |
|-------|-------------|
| `none` | Nenhuma intervenção |
| `blocked` | Input bloqueado pelo `InputGuardrail` |
| `sanitized` | Output sanitizado pelo `OutputGuardrail` (PII removida) |

---

## Ciclo de Vida de uma Requisição

```mermaid
sequenceDiagram
    actor C as Cliente
    participant MW as Middleware Prometheus
    participant IG as InputGuardrail
    participant AG as AgentExecutor
    participant OG as OutputGuardrail
    participant PR as Prometheus

    C->>MW: POST /agent/chat
    MW->>MW: start timer
    MW->>IG: validate(question)

    alt Input inválido (injection · context stuffing)
        IG-->>MW: (False, "Input bloqueado: ...")
        MW->>PR: agent_question_failures_total{reason=input_guardrail}.inc()
        MW-->>C: ChatResponse(guardrail_action="blocked")
    else Input válido
        IG-->>MW: (True, "OK")
        MW->>AG: invoke({"input": question})
        loop ReAct iterations
            AG->>AG: Thought → Action → Observation
        end
        AG-->>MW: {"output": "...", "intermediate_steps": [...]}
        MW->>PR: agent_iterations.observe(steps)
        MW->>PR: agent_tool_calls_total{tool}.inc() por step
        MW->>OG: sanitize(raw_answer)
        OG-->>MW: sanitized_answer
        MW->>MW: http_request_latency_seconds.observe(elapsed)
        MW->>PR: http_requests_total{endpoint, status}.inc()
        MW-->>C: ChatResponse(guardrail_action="none"|"sanitized")
    end
```

---

## LLM Quantizado

O LLM é carregado **uma única vez** por processo via `lru_cache`, satisfazendo o requisito "LLM servido via API com quantização aplicada".

```mermaid
flowchart LR
    ENV[LLM_MODEL_PATH<br/>env variable] --> LOAD[Llama()]
    CONF[configs/llm_config.yaml<br/>n_ctx · n_threads · n_gpu_layers] --> LOAD
    LOAD -->|lru_cache maxsize=1| INST[Instância LLM<br/>na memória]
    INST --> EP1[POST /llm/complete]
    INST -.->|via OpenAI-compat| EP2[POST /agent/chat]
```

**Parâmetros de quantização (`configs/llm_config.yaml`):**

| Parâmetro | Padrão | Descrição |
|-----------|--------|-----------|
| `model_path` | — | Caminho para arquivo `.gguf` |
| `n_ctx` | 4096 | Janela de contexto em tokens |
| `n_threads` | 4 | Threads de CPU para inferência |
| `n_gpu_layers` | 0 | Camadas offloadas para GPU (0 = CPU-only) |

**Modelo padrão:** `Qwen2.5-3B-Instruct-Q4_K_M.gguf`

- Quantização **Q4\_K\_M** reduz o modelo de ~6GB (FP16) para ~1.8GB
- Mantém qualidade aceitável com redução de 70% no uso de memória

---

## Telemetria Prometheus

O middleware HTTP e os endpoints medem automaticamente todas as requisições.

```mermaid
graph LR
    subgraph Métricas Coletadas
        M1[http_requests_total<br/>Counter · endpoint · status]
        M2[http_request_latency_seconds<br/>Histogram · endpoint]
        M3[llm_tokens_total<br/>Counter · endpoint · kind]
        M4[llm_latency_seconds<br/>Histogram · endpoint]
        M5[agent_iterations<br/>Histogram]
        M6[agent_tool_calls_total<br/>Counter · tool]
        M7[agent_question_failures_total<br/>Counter · reason]
        M8[drift_psi_score<br/>Gauge · feature]
        M9[drift_status<br/>Gauge · ok=0 · warning=1 · critical=2]
    end

    M1 & M2 & M3 & M4 & M5 & M6 & M7 & M8 & M9 --> PR[GET /metrics<br/>Prometheus format]
    PR --> PROM[Prometheus :9090]
    PROM --> GF[Grafana :3000]
```

**Alertas configurados em `configs/prometheus_alerts.yml`:**

| Alerta | Condição | Severidade |
|--------|----------|------------|
| `HighLatency` | p99 > 5s por 5min | warning |
| `DriftCritical` | `drift_status == 2` | critical |
| `LowRAGASScore` | faithfulness < 0.6 | warning |
| `SecurityBlock` | failures > 10/min | warning |

---

## Segurança Integrada

```mermaid
flowchart LR
    Q[question] --> IG[InputGuardrail.validate]
    IG -->|6 regex patterns| CHK1{injection?}
    CHK1 -->|Sim| BLK[blocked]
    IG -->|len > 4096| CHK2{context stuffing?}
    CHK2 -->|Sim| BLK
    CHK1 & CHK2 -->|Não| AGENT[AgentExecutor]
    AGENT --> OG[OutputGuardrail.sanitize]
    OG -->|Presidio analyzer| PII{PII found?}
    PII -->|Sim| ANON[anonymize → <PERSON>, <EMAIL>...]
    PII -->|Não| PASS[pass through]
    ANON & PASS --> RESP[ChatResponse]
```

Detalhes completos em [`security/README.md`](../security/README.md).

---

## Docker

### `src/serving/Dockerfile`

Build multi-stage para minimizar tamanho da imagem final:

```mermaid
flowchart LR
    B1[Stage: builder<br/>python:3.11-slim] -->|pip install| B2[Wheels compilados<br/>llama-cpp-python]
    B2 --> B3[Stage: runtime<br/>python:3.11-slim]
    B3 -->|COPY wheels| B4[Imagem final<br/>~800MB]
    B4 -->|CMD| B5[uvicorn src.serving.app:app<br/>--host 0.0.0.0 --port 8000]
```

### Variáveis de Ambiente no Container

```bash
docker run -p 8000:8000 \
  -e LLM_MODEL_PATH=/models/qwen2.5-3b-instruct-q4_k_m.gguf \
  -e MLFLOW_TRACKING_URI=http://mlflow:5000 \
  -e OPENAI_API_BASE=http://llm-server:8001/v1 \
  -v $(pwd)/models:/models \
  mlet-phase5-api
```

---

## Uso

### Desenvolvimento local

```bash
export LLM_MODEL_PATH="models/qwen2.5-3b-instruct-q4_k_m.gguf"
uvicorn src.serving.app:app --reload --port 8000
```

### Via Makefile

```bash
make serve      # inicia a API
make docker-up  # sobe toda a stack (api + mlflow + prometheus + grafana)
```

### Testando os endpoints

```bash
# Health check
curl http://localhost:8000/health

# Completion direta no LLM
curl -X POST http://localhost:8000/llm/complete \
  -H "Content-Type: application/json" \
  -d '{"prompt": "O que é P/L?", "max_tokens": 100}'

# Agente ReAct
curl -X POST http://localhost:8000/agent/chat \
  -H "Content-Type: application/json" \
  -d '{"question": "Compare PETR4 e VALE3 pelo ROE."}'

# Métricas Prometheus
curl http://localhost:8000/metrics
```

### Swagger UI

Acesse `http://localhost:8000/docs` para documentação interativa dos endpoints.
