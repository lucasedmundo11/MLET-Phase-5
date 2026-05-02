# Retraining Automatizado — GAP 07

> Fechamento do **GAP 07 — Ausência de Retraining Automatizado** do guia
> oficial (p. 7-8). Implementa as 4 recomendações textuais:
>
> 1. *Retraining agendado (cron) como baseline.*
> 2. *Retraining event-driven (drift detectado → trigger pipeline).*
> 3. *Validação champion-challenger antes de promover.*
> 4. *Human-in-the-loop: approval gate antes de produção.*

## 1. Visão geral dos triggers

```
┌────────────────────┐  cron weekly  ┌────────────────────────────┐
│ retraining.yml     │ ◄──────────── │ schedule '0 6 * * 1'       │
│ (champion-         │               └────────────────────────────┘
│  challenger)       │  manual       ┌────────────────────────────┐
│                    │ ◄──────────── │ workflow_dispatch          │
│                    │               └────────────────────────────┘
│                    │  event-driven ┌────────────────────────────┐
│                    │ ◄──────────── │ repository_dispatch        │
└────────────────────┘               │ types=[drift-detected]     │
                                     └─────────────┬──────────────┘
                                                   │
                                     ┌─────────────┴──────────────┐
                                     │ drift-watch.yml (daily)    │
                                     │ status=critical → dispatch │
                                     └────────────────────────────┘
```

| Trigger | Cadência | Origem | Onde |
|---------|----------|--------|------|
| Scheduled (baseline) | Toda segunda 06:00 UTC | GitHub Actions `schedule` | [retraining.yml](../.github/workflows/retraining.yml) |
| Event-driven (drift) | Quando `drift_psi_max ≥ 0.20` | drift-watch dispara `repository_dispatch` | [drift-watch.yml](../.github/workflows/drift-watch.yml) → [retraining.yml](../.github/workflows/retraining.yml) |
| Manual | Sob demanda | `workflow_dispatch` no GitHub UI ou `gh workflow run` | [retraining.yml](../.github/workflows/retraining.yml) |
| Local (dev) | Sob demanda | `make retrain` ou `python -m scripts.run_retraining` | [scripts/run_retraining.py](../scripts/run_retraining.py) |

Todo trigger registra `RETRAINING_REASON` na variável de ambiente — virando
campo `trigger` no relatório JSON de saída (audit trail).

## 2. Champion-challenger — regras

Implementadas em [scripts/run_retraining.py](../scripts/run_retraining.py)
conforme texto literal do guia (p. 8):

1. **Carregar champion** do MLflow Model Registry (stage = `Production`).
2. **Treinar challenger** com dados novos (parquet recém-gerado pelo
   `feature_engineering.py`).
3. **Comparar métricas em holdout** — `auc` no test split estratificado
   `random_state=42`.
4. **Promover apenas se Δauc ≥ 0.005** (0,5 % de melhoria, valor exato do
   guia). Caso contrário, `decision = REJECT`.

A regra é encapsulada em `_decide(challenger_auc, champion, threshold)`
para facilitar teste/auditoria.

## 3. Human-in-the-loop — gate Staging → Production

O script **nunca promove para `Production` automaticamente**. O fluxo é:

| Stage | Quem move | Critério |
|-------|-----------|----------|
| `None` → `Staging` | Script automatizado | Δauc ≥ 0.005 |
| `Staging` → `Production` | **Humano** (MLflow UI ou `gh` script revisado) | Validação manual de fairness ([EXPLAINABILITY_FAIRNESS.md](EXPLAINABILITY_FAIRNESS.md)), drift ([MONITORING.md](MONITORING.md)) e métricas de negócio ([BUSINESS_METRICS.md](BUSINESS_METRICS.md)) |
| `Production` → `Archived` | Humano | Após nova promoção |

O campo `human_action_required` no relatório indica explicitamente o próximo
passo manual.

## 4. Estrutura do relatório (`metrics/retraining_<ts>.json`)

```json
{
  "timestamp": "2026-05-04T06:01:13Z",
  "trigger": "scheduled",
  "model_name": "baseline_logreg",
  "champion": {
    "version": "3",
    "run_id": "abcd1234...",
    "metrics": { "auc": 0.612, "f1": 0.594, "precision": 0.601, "recall": 0.587 }
  },
  "challenger": {
    "run_id": "efgh5678...",
    "version": "5",
    "metrics": { "auc": 0.624, "f1": 0.607, "precision": 0.612, "recall": 0.601 }
  },
  "delta_auc": 0.012,
  "promotion_threshold": 0.005,
  "decision": "PROMOTE_TO_STAGING",
  "human_action_required": "REVIEW: abrir MLflow Registry → Staging e ..."
}
```

Quatro decisões possíveis:

| `decision` | Significado | Próximo passo |
|------------|-------------|---------------|
| `FIRST_CHALLENGER_TO_STAGING` | Não havia champion em Production | Humano valida e promove |
| `PROMOTE_TO_STAGING` | Δauc ≥ 0,005 | Humano valida e promove |
| `REJECT` | Δauc < 0,005 | Champion mantido; nenhuma ação |
| `*_FAILED` | Stage transition falhou | Verificar permissões no Tracking Server |

## 5. Reproduzir localmente

```bash
# 1. (uma única vez) treinar baseline e mover manualmente para Production
make data && make train
# → no MLflow UI, mova baseline_logreg v1 para Production

# 2. Simular um ciclo de retraining
make retrain
# → metrics/retraining_<ts>.json com decision=REJECT (challenger igual)

# 3. Forçar drift sintético + retraining event-driven (offline)
python -m scripts.run_drift_check --window-days 5     # menor janela = mais drift
python -m scripts.run_retraining --reason drift_critical
```

## 6. Como o gate humano lê o resultado

1. Acessa MLflow UI (`http://localhost:5000`).
2. Vai em **Models** → `baseline_logreg` → **Staging**.
3. Compara métricas vs Production (gráfico nativo do MLflow).
4. Revisa `metrics/retraining_<ts>.json` (uploaded como artifact pelo workflow).
5. Confere [EXPLAINABILITY_FAIRNESS.md](EXPLAINABILITY_FAIRNESS.md) §2.1
   (paridade por ticker) e [docs/MONITORING.md](MONITORING.md) (drift
   recente).
6. Se ok: clica **Transition → Production** + arquiva versão antiga.
7. Se não: deixa em Staging para investigação.

## 7. Encadeamento com Etapa 3 (drift)

```
[FAISS+yfinance fresh] ─► run_drift_check.py ──► drift_psi_max ≥ 0.20?
                                                          │
                                                          ├─ Não: monitora
                                                          └─ Sim: dispatch
                                                                    │
                                                          ┌─────────▼──────────┐
                                                          │ run_retraining.py  │
                                                          │ (champion vs       │
                                                          │  challenger)       │
                                                          └─────────┬──────────┘
                                                                    │
                                                          ┌─────────▼──────────┐
                                                          │ Δauc ≥ 0.005?      │
                                                          ├─ Não: REJECT       │
                                                          └─ Sim: STAGING ──►  │
                                                                    │ humano  │
                                                                    ▼         │
                                                              PRODUCTION  ◄───┘
```

## 8. Auditoria — onde tudo fica registrado

| Item | Onde |
|------|------|
| Decisão de promoção | `metrics/retraining_<ts>.json` (commit no DVC se aplicável) |
| Métricas + tags GAP 05 | MLflow run do challenger (tags `model_name`, `model_version`, `training_data_version`, `metrics_json`, `risk_level`, `fairness_checked`, `git_sha`) |
| Trigger | Campo `trigger` no JSON ∈ {scheduled, manual, drift_critical} |
| Identidade do humano que promoveu | MLflow Registry (`current_stage_user`) |
| Relatório de drift que disparou | Artifact `drift-report` do workflow `drift-watch.yml` |

Esses artefatos cobrem o requisito de **lineage** do Nível 2 de Model
Management (p. 2-3 do guia) — *"Model Registry com versionamento e
metadata obrigatória"*.
