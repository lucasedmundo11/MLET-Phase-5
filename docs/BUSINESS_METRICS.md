# Mapeamento — Métricas de Negócio × Métricas Técnicas

> Etapa 1 — Datathon Fase 5. Este documento traduz cada pergunta/objetivo de
> negócio do agente financeiro em uma métrica técnica observável e logada no
> MLflow durante o treino do baseline.

## 1. Problema da empresa

A entrega final é um **agente conversacional** que ajuda investidores a
responder perguntas sobre o universo PETR4, VALE3, ITUB4, BBDC4, WEGE3:

- *"Qual ação teve maior retorno em 2024?"*
- *"Compare PETR4 e VALE3 pelo P/L"*
- *"Gere um relatório de risco da carteira X"*

O **baseline da Fase 1** atende ao bloco preditivo desse agente: estimar a
**direção do preço em D+1** (alta vs. queda) por ticker, a partir de
indicadores técnicos. As respostas descritivas (retorno acumulado,
comparativos, fundamentos) são servidas diretamente pelos dados versionados.

## 2. Tabela de mapeamento

| Métrica de negócio | Pergunta que responde | Métrica técnica logada no MLflow | Threshold de aceite |
| --- | --- | --- | --- |
| **Hit rate direcional** — % de dias em que o sistema acerta a direção da próxima sessão | "O modelo é melhor que o cara-ou-coroa em prever D+1?" | `auc` (`roc_auc_score`) e acurácia derivada | AUC ≥ 0,55 (sinal econômico mínimo); chance trivial ≈ 0,50 |
| **Sinal acionável (Long-only precision)** — quando o sistema diz "alta", quantas vezes acerta | "Posso confiar nas recomendações de compra do agente?" | `precision` (`precision_score`) | Precision ≥ 0,55 |
| **Cobertura de oportunidades** — quantas das altas reais o sistema captura | "O agente está deixando passar oportunidades de alta?" | `recall` (`recall_score`) | Recall ≥ 0,50 |
| **Equilíbrio acerto/cobertura** — robustez geral em janelas com classes desbalanceadas | "O modelo se mantém útil em períodos de mercado lateral?" | `f1` (`f1_score`) | F1 ≥ 0,52 |
| **Reprodutibilidade da resposta** — duas execuções do agente devem dar a mesma resposta para os mesmos dados | "A recomendação é auditável?" | Determinismo dos baselines (testado em `tests/test_models.py::test_mlp_torch_is_deterministic`) | 100% de igualdade entre runs com mesmo `random_state` |
| **Cobertura do universo** — todos os tickers da carteira-alvo precisam ter dado válido | "O agente cobre toda a carteira ou tem lacunas?" | `n_samples_train`, `n_features` (params) e contagem de tickers únicos no parquet processado | 5/5 tickers presentes em `data/processed/prices_features.parquet` |

## 3. Como cada métrica é capturada

- **AUC, Precision, Recall, F1** são logadas em `mlflow.log_metrics(...)`
  dentro de `train_and_log` (replicado do guia oficial em
  `src/models/train.py`).
- **Reprodutibilidade** é validada em CI por `pytest tests/test_models.py`
  (cobertura mínima `--cov-fail-under=60` no `Makefile`).
- **Cobertura do universo** é garantida pelo estágio `prepare` do
  `dvc.yaml`, cujas saídas (`data/processed/prices_features.parquet`,
  `data/processed/fundamentals.parquet`) são versionadas pelo DVC.

## 4. Decisão de promoção do baseline

Um modelo da Fase 1 só é considerado **apto a virar champion** quando, em
cima do conjunto de teste:

1. `auc ≥ 0,55` **e**
2. `precision ≥ 0,55` (controla risco de recomendação errada de compra) **e**
3. As métricas estão registradas no MLflow com as **tags padronizadas**
   (`model_type`, `framework`, `owner`, `phase`) — exigência do guia para
   atingir Nível 2 de maturidade em *Experiment Management* / *Model
   Management*.

Caso o baseline fique abaixo desses limiares, o agente da Etapa 2 **não
deve** expor a ferramenta de previsão direcional — apenas as ferramentas
descritivas (retornos históricos, comparativos de fundamentos, métricas de
risco da carteira), evitando recomendar ação com base em sinal sem
significância.
