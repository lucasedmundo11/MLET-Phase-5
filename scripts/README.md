# scripts/ — Scripts de Operações

Scripts de linha de comando para operações offline: indexação RAG, benchmark, avaliação, drift check, red team e retraining.

---

## Sumário

1. [Visão Geral](#visão-geral)
2. [Scripts Disponíveis](#scripts-disponíveis)
3. [Fluxos de Execução](#fluxos-de-execução)
4. [Uso via Makefile](#uso-via-makefile)

---

## Visão Geral

```
scripts/
├── __init__.py
├── build_rag_index.py    # Etapa 2 — indexa PDFs → FAISS
├── run_benchmark.py      # Etapa 2 — benchmark ≥ 3 configurações
├── run_evaluation.py     # Etapa 3 — RAGAS + LLM-judge
├── run_drift_check.py    # Etapa 3 — Evidently + PSI
├── run_red_team.py       # Etapa 4 — 7 cenários adversariais
└── run_retraining.py     # GAP 07 — champion-challenger
```

Todos os scripts são executáveis diretamente como módulos Python (`python scripts/<script>.py`) ou via Makefile.

---

## Scripts Disponíveis

### `build_rag_index.py`

Lê PDFs de `data/raw/reports/`, divide em chunks, gera embeddings e salva o índice FAISS em `data/processed/rag_index/`.

```mermaid
flowchart LR
    PDF[data/raw/reports/<br/>*.pdf] -->|pypdf extract_text| TXT[Texto bruto]
    TXT -->|chunk_text 512c overlap 50| CK[Chunks]
    CK -->|sentence-transformers<br/>paraphrase-multilingual-MiniLM| EMB[Embeddings]
    EMB -->|faiss.IndexFlatL2| IDX[data/processed/rag_index/<br/>index.faiss + metadata.json]
```

**Uso:**
```bash
make rag-index
# ou
python scripts/build_rag_index.py --input data/raw/reports/ --output data/processed/rag_index/
```

---

### `run_benchmark.py`

Avalia o agente em 3+ configurações distintas de LLM e prompt, reportando latência e qualidade.

```mermaid
flowchart TD
    CFG[Configurações<br/>A · B · C] --> FOR[Para cada configuração]
    FOR --> Q[Golden Set queries]
    Q --> AG[Agente com config X]
    AG --> RES[Tempo de resposta<br/>+ resposta gerada]
    RES --> RAGAS2[Avaliação RAGAS rápida]
    RAGAS2 --> RPT[docs/BENCHMARK.md<br/>tabela comparativa]
```

**Configurações benchmarkadas:**

| Config | Modelo | Temperatura | Prompt |
|--------|--------|-------------|--------|
| A | `qwen2.5-3b-instruct` | 0.0 | Padrão Datathon |
| B | `qwen2.5-3b-instruct` | 0.0 | Domain-specific financeiro |
| C | `qwen2.5-3b-instruct` | 0.1 | Domain-specific + CoT |

**Uso:**
```bash
make benchmark
# ou
python scripts/run_benchmark.py --golden-set data/golden_set/golden_set.json
```

---

### `run_evaluation.py`

Executa a avaliação completa (RAGAS + LLM-as-judge) e salva resultados.

```mermaid
flowchart LR
    GS[golden_set.json] --> RAGAS3[ragas_eval.evaluate_rag_pipeline]
    GS --> JUDGE[llm_judge.evaluate_with_judge]

    RAGAS3 --> M1[faithfulness · answer_relevancy<br/>context_precision · context_recall]
    JUDGE --> M2[correctness · faithfulness<br/>actionability · risk_awareness]

    M1 & M2 --> JSON[metrics/evaluation.json]
    JSON --> LOG[MLflow log_metrics]
    JSON --> PROM[Prometheus Gauges<br/>via /metrics]
```

**Uso:**
```bash
make eval
# ou
python scripts/run_evaluation.py \
  --golden-set data/golden_set/golden_set.json \
  --output metrics/evaluation.json \
  --mlflow-uri http://localhost:5000
```

**Saída (`metrics/evaluation.json`):**
```json
{
  "ragas": {
    "faithfulness": 0.82,
    "answer_relevancy": 0.79,
    "context_precision": 0.85,
    "context_recall": 0.71
  },
  "judge": {
    "correctness": 4.2,
    "faithfulness": 4.0,
    "actionability": 3.8,
    "risk_awareness": 3.5
  },
  "timestamp": "2026-05-02T10:00:00Z"
}
```

---

### `run_drift_check.py`

Detecta drift entre os dados de treino (referência) e dados correntes, salva report HTML/JSON e opcionalmente dispara retraining.

```mermaid
flowchart TD
    REF2[prices_features.parquet<br/>dados de treino] --> DRIFT[detect_drift]
    CUR2[dados correntes<br/>últimos N dias] --> DRIFT
    DRIFT --> RESULT[DriftResult<br/>status · PSI · features]

    RESULT -->|status ok| SAVE[Salva report HTML + JSON]
    RESULT -->|status warning| SAVE
    RESULT -->|status critical| SAVE
    RESULT -->|status critical| GH[GitHub repository_dispatch<br/>drift-detected]

    GH --> RET[retraining.yml<br/>champion-challenger]
```

**Uso:**
```bash
make drift
# ou
python scripts/run_drift_check.py \
  --reference data/processed/prices_features.parquet \
  --output data/processed/drift_reports/
```

---

### `run_red_team.py`

Executa os 7 cenários adversariais contra a API em execução e reporta vulnerabilidades encontradas.

```mermaid
flowchart TD
    API2[FastAPI :8000] --> RT1[RT01: Prompt injection]
    API2 --> RT2[RT02: System prompt leak]
    API2 --> RT3[RT03: Context stuffing]
    API2 --> RT4[RT04: PII leakage]
    API2 --> RT5[RT05: Indirect injection RAG]
    API2 --> RT6[RT06: Excessive agency]
    API2 --> RT7[RT07: Misinformation]

    RT1 & RT2 & RT3 & RT4 & RT5 & RT6 & RT7 --> EVAL2{Vulnerabilidade<br/>encontrada?}
    EVAL2 -->|Sim| FAIL[Exit code 1<br/>CI falha]
    EVAL2 -->|Não| PASS2[metrics/red_team.json<br/>Exit code 0]
```

**Uso:**
```bash
# API deve estar no ar: make serve ou make docker-up
make red-team
# ou
python scripts/run_red_team.py --api-url http://localhost:8000
```

**Saída (`metrics/red_team.json`):**
```json
{
  "scenarios": [
    {"id": "RT01", "status": "mitigated", "details": "Input bloqueado pelo guardrail"},
    {"id": "RT02", "status": "mitigated", "details": "System prompt não exposto"},
    {"id": "RT05", "status": "residual_risk", "details": "Risco baixo, não explorado"}
  ],
  "vulnerabilities_found": 0,
  "timestamp": "2026-05-02T10:00:00Z"
}
```

---

### `run_retraining.py`

Implementa o pipeline champion-challenger para decidir se um novo modelo deve ser promovido.

```mermaid
flowchart TD
    START2([Trigger: cron · drift · manual]) --> CHAMP[Carrega champion<br/>do MLflow Registry<br/>stage=Production]
    CHAMP --> DATA2[Carrega features<br/>via DVC]
    DATA2 --> TRAIN2[Treina challenger<br/>LogReg ou MLP]
    TRAIN2 --> REG2[register_model_to_registry<br/>GAP 05 — 9 tags]
    REG2 --> COMP2[Compara AUC holdout<br/>champion vs challenger]

    COMP2 --> DELTA2{Δ AUC ≥ 0.005?}
    DELTA2 -->|Sim| PROMOTE2[mlflow.set_model_version_tag<br/>Staging]
    DELTA2 -->|Não| REJECT2[Mantém champion<br/>log comparação]

    PROMOTE2 --> HUMAN2[Human-in-the-loop<br/>Staging → Production<br/>via MLflow UI]

    style PROMOTE2 fill:#2a9d8f,color:#fff
    style REJECT2 fill:#e63946,color:#fff
    style HUMAN2 fill:#457b9d,color:#fff
```

**Threshold configurável:**
```python
DEFAULT_THRESHOLD = 0.005  # Δ AUC mínimo para promoção
```

**Uso:**
```bash
# Manual
python scripts/run_retraining.py \
  --reason "drift detectado" \
  --challenger-class LogisticRegressionBaseline

# Via workflow (automático)
gh workflow run retraining.yml \
  -f reason="drift-triggered" \
  -f challenger_class="LogisticRegressionBaseline"
```

---

## Fluxos de Execução

```mermaid
flowchart LR
    subgraph Etapa1["Etapa 1"]
        D[make data] --> T[make train]
    end

    subgraph Etapa2["Etapa 2"]
        RI[make rag-index] --> S[make serve]
        S --> BM[make benchmark]
    end

    subgraph Etapa3["Etapa 3"]
        DU[make docker-up] --> EV[make eval]
        DU --> DR[make drift]
    end

    subgraph Etapa4["Etapa 4"]
        DU2[make docker-up] --> RT[make red-team]
    end

    T --> RI
    EV & DR --> RTR[run_retraining.py<br/>automático via workflow]
```

---

## Uso via Makefile

```bash
make data        # python -m src.features.feature_engineering
make train       # python -m src.models.train
make test        # pytest tests/ -x --cov=src --cov-fail-under=60
make serve       # uvicorn src.serving.app:app --port 8000
make rag-index   # python scripts/build_rag_index.py
make benchmark   # python scripts/run_benchmark.py
make eval        # python scripts/run_evaluation.py
make drift       # python scripts/run_drift_check.py
make red-team    # python scripts/run_red_team.py
make docker-up   # docker compose up -d
make docker-down # docker compose down
```
