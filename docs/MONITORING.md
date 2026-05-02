# Observabilidade & Drift — Etapa 3

Este documento descreve as três camadas de observabilidade exigidas pelo
guia do Datathon (Fase 05) e detalha a implementação no repositório.

## 1. Métricas operacionais — Prometheus + Grafana

| Camada            | Componente                                   | Onde                                            |
|-------------------|----------------------------------------------|-------------------------------------------------|
| Coleta            | `prometheus_client` em FastAPI               | [src/serving/app.py](../src/serving/app.py)     |
| Definição         | Counters / Gauges / Histograms padronizados  | [src/monitoring/metrics.py](../src/monitoring/metrics.py) |
| Scrape            | Prometheus 2.52                              | [configs/prometheus.yml](../configs/prometheus.yml) |
| Visualização      | Grafana 10.4 com dashboard provisionado      | [configs/grafana/dashboards/agent_dashboard.json](../configs/grafana/dashboards/agent_dashboard.json) |

### Métricas expostas (`/metrics`)

| Nome                                    | Tipo      | Labels                | O que mede                                |
|-----------------------------------------|-----------|-----------------------|-------------------------------------------|
| `agent_http_requests_total`             | Counter   | `endpoint, status`    | Throughput por endpoint                   |
| `agent_http_request_latency_seconds`    | Histogram | `endpoint`            | Latência (p50/p95) por endpoint           |
| `agent_tool_calls_total`                | Counter   | `tool`                | Uso de cada ferramenta do agente          |
| `agent_iterations`                      | Histogram | —                     | Iterações ReAct por pergunta              |
| `agent_question_failures_total`         | Counter   | `reason`              | Falhas (timeout, parse, etc.)             |
| `llm_tokens_total`                      | Counter   | `endpoint, kind`      | Tokens consumidos pelo LLM                |
| `llm_latency_seconds`                   | Histogram | `endpoint`            | Latência do LLM                           |
| `drift_share_of_drifted_columns`        | Gauge     | —                     | Resultado mais recente do Evidently       |
| `drift_psi_max`                         | Gauge     | —                     | Maior PSI observado entre features        |
| `ragas_metric`                          | Gauge     | `metric`              | Última medida RAGAS (4 métricas)          |
| `judge_metric`                          | Gauge     | `criterion`           | Última nota média do LLM-as-judge         |

### Como subir end-to-end

```bash
make docker-up
# → http://localhost:8000/docs    Swagger
# → http://localhost:9090         Prometheus
# → http://localhost:3000         Grafana (admin/admin)
#   Dashboard "Datathon Fase 5 — Agente Financeiro" já provisionado.
```

## 2. Telemetria de qualidade do LLM — RAGAS + Judge

Conforme o guia (Etapa 3), são exigidas:

* **RAGAS — 4 métricas:** faithfulness, answer_relevancy, context_precision,
  context_recall — replicado em [evaluation/ragas_eval.py](../evaluation/ragas_eval.py).
* **LLM-as-judge — ≥ 3 critérios** (incluindo critério de negócio):
  `correctness`, `faithfulness`, `actionability` (negócio), `risk_awareness`
  (negócio) — em [evaluation/llm_judge.py](../evaluation/llm_judge.py).

Ambos são executados pelo script:

```bash
python -m scripts.run_evaluation --url http://localhost:8000/agent/chat
# Saídas:
#   metrics/evaluation.json        # snapshot completo
#   gauges Prometheus atualizados  # ragas_metric{metric=...}, judge_metric{criterion=...}
```

## 3. Drift detection — Evidently + PSI

Conforme **GAP 06** do guia, drift é critério de aceite explícito.
Replicamos o snippet padronizado em
[src/monitoring/drift.py](../src/monitoring/drift.py):

* `Report(metrics=[DataDriftPreset()])` calcula
  `share_of_drifted_columns` e drift por coluna.
* Adicionalmente, calculamos o **PSI** por feature numérica (não coberto
  pelo preset por padrão), com bins por quantis da referência.

### Thresholds

| Faixa de PSI       | Status     | Ação                                    |
|--------------------|------------|-----------------------------------------|
| `< 0.10`           | `ok`       | nenhuma                                 |
| `0.10 ≤ PSI < 0.20`| `warning`  | revisar features, alertar               |
| `≥ 0.20`           | `critical` | **trigger de retraining** do baseline   |

Configurável em [configs/monitoring_config.yaml](../configs/monitoring_config.yaml).

### Como rodar

```bash
python -m scripts.run_drift_check --window-days 30
# Saídas:
#   data/processed/drift_reports/drift_<ts>.html  # report Evidently
#   data/processed/drift_reports/drift_<ts>.json
#   metrics/drift.json
#   gauges Prometheus: drift_share_of_drifted_columns, drift_psi_max
```

A janela `current` corresponde aos últimos N dias do parquet de features
(`data/processed/prices_features.parquet`); o restante é a `reference`.
Este corte representa "concept drift" no domínio financeiro: a distribuição
recente de RSI / MACD / volatilidade vs. o histórico que treinou o baseline.

## 4. Encadeamento com MLflow

Conforme recomendação do guia, o resultado de drift é logado no mesmo run
MLflow do baseline através do snippet padrão (replicado abaixo, presente
em `src/monitoring/drift.py::detect_drift`):

```python
from evidently.report import Report
from evidently.metric_preset import DataDriftPreset

report = Report(metrics=[DataDriftPreset()])
report.run(reference_data=train_df, current_data=prod_df)
drift_result = report.as_dict()
drift_share = drift_result["metrics"][0]["result"]["share_of_drifted_columns"]
```

`drift_share` e `psi_max` podem ser logados via `mlflow.log_metric(...)`
no próximo retraining para manter a *lineage* "dados → drift → modelo".
