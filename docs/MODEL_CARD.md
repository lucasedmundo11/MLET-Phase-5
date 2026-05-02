# Model Card — Baseline de Direção Diária (Datathon Fase 5)

> Estrutura conforme Mitchell et al. (2019), *Model Cards for Model
> Reporting*, FAT* — referência citada no guia oficial. Cobre o **baseline
> da Etapa 1** (LogReg + MLP em PyTorch) que alimenta o agente conversacional
> da Etapa 2.

## 1. Detalhes do modelo

| Campo | Valor |
|-------|-------|
| Nome | `baseline_logreg` (champion) e `baseline_mlp_torch` (challenger) |
| Versão | `0.1.0` (Etapa 1) — versionada no MLflow Registry |
| Data de treino | Reproduzível em qualquer momento via `make train` |
| Tipo | Classificação binária (direção do retorno em D+1) |
| Arquiteturas | scikit-learn `LogisticRegression`; PyTorch MLP (3 camadas, 128→64→1) |
| Frameworks | `scikit-learn>=1.5`, `torch>=2.3`, `mlflow>=2.13` |
| Entradas | 9 features técnicas calculadas em [src/features/feature_engineering.py](../src/features/feature_engineering.py): RSI(14), MACD/MACD signal/MACD diff, %B Bollinger, retornos log 1d/5d/21d, volatilidade 21d |
| Saída | `int` ∈ {0, 1} — 1 = preço fecha em alta no D+1 |
| Owner | `grupo-XX` (tag obrigatória no MLflow) |
| Licença | Definida pelo grupo no Demo Day |
| `git_sha` | Logado em cada run (tag MLflow) |

## 2. Uso pretendido

* **Uso primário.** Gerar um sinal probabilístico de direção para PETR4,
  VALE3, ITUB4, BBDC4 e WEGE3 em janela diária, **consumido como uma das
  ferramentas do agente conversacional** (`technical_signal`).
* **Usuário primário.** Investidor pessoa física que conversa com o agente
  pedindo análise antes de tomar decisões próprias.
* **Usuário secundário.** Equipe de ML/MLOps que monitora drift e qualidade
  via dashboards (Etapa 3).

### Fora de escopo

* **Execução de ordens de compra/venda.** O agente não tem ferramenta para
  isso (LLM06 — Excessive Agency, ver [OWASP_MAPPING.md](OWASP_MAPPING.md)).
* **Universos fora dos 5 tickers.** Para qualquer outro ticker, a tool falha
  explicitamente em vez de extrapolar (RT07 do
  [Red Team Report](RED_TEAM_REPORT.md)).
* **Janelas intradiárias.** O baseline é treinado em fechamento diário; sinais
  de minutos / segundos não são suportados.
* **Aconselhamento financeiro regulado.** O sistema não substitui consultor
  habilitado (CVM).

## 3. Fatores

| Fator | Por quê monitorar | Como monitorar |
|-------|-------------------|----------------|
| Ticker | Distribuição de retornos varia muito entre setores | Métricas `auc/precision/recall/f1` decompostas por ticker em [EXPLAINABILITY_FAIRNESS.md](EXPLAINABILITY_FAIRNESS.md) |
| Regime de mercado (alta/baixa/lateral) | Modelo lineares performam diferente em cada regime | Drift detection (Etapa 3) — `make drift` |
| Janela temporal | O comportamento de RSI/MACD muda com a volatilidade | PSI por feature (`drift_psi_max`) |
| Setor (Financeiro × Commodities × Industrial) | Correlações intra-setor altas (ITUB4/BBDC4) | Matriz de correlação no notebook EDA |

## 4. Métricas

Conforme [docs/BUSINESS_METRICS.md](BUSINESS_METRICS.md):

| Métrica técnica | Limiar de aceite | Métrica de negócio mapeada |
|-----------------|------------------|----------------------------|
| `auc` | ≥ 0,55 | Hit-rate direcional acima do "cara-ou-coroa" |
| `precision` | ≥ 0,55 | Sinal acionável (long-only precision) |
| `recall` | ≥ 0,50 | Cobertura de oportunidades de alta |
| `f1` | ≥ 0,52 | Robustez em mercado lateral |

Todas registradas em `mlflow.log_metrics(...)` com tags padronizadas
`{model_type, framework, owner, phase}` — replicado verbatim do guia em
[src/models/train.py:61-79](../src/models/train.py#L61-L79).

## 5. Dados de avaliação

* **Origem:** mesmo parquet versionado por DVC
  (`data/processed/prices_features.parquet`) — split estratificado
  `test_size=0.2, random_state=42`.
* **Pré-processamento:** descarte de linhas com `NaN` (warm-up de janelas RSI/MACD/BB).
* **Volume:** ~6 200 linhas (5 tickers × ~5 anos × ~252 pregões/ano − warm-up).
* **Distribuição do alvo:** target ≈ 50% por design (direção é
  aproximadamente equiprovável — ver insight nº 3 do notebook EDA).

## 6. Dados de treinamento

* **Origem:** yfinance via `yfinance>=0.2.40` ([src/features/feature_engineering.py::download_prices](../src/features/feature_engineering.py)).
* **Janela:** 5 anos a contar da data de execução.
* **Universo:** PETR4.SA, VALE3.SA, ITUB4.SA, BBDC4.SA, WEGE3.SA.
* **Sem PII por construção** — dados de mercado público.

## 7. Análises quantitativas

Decomposição por ticker e considerações de fairness em
[EXPLAINABILITY_FAIRNESS.md](EXPLAINABILITY_FAIRNESS.md). Resumo:

* O baseline atinge AUC similar entre tickers (delta < 0,05) — não há ticker
  sistematicamente desfavorecido.
* MLP marginalmente acima de LogReg em F1; LogReg vence em interpretabilidade.

## 8. Considerações éticas

* O modelo **não usa dados pessoais**, eliminando vieses ligados a
  características protegidas.
* Risco principal: **overreliance** (LLM09) — investidor decide com base
  exclusiva na recomendação. Mitigado por:
  * Mensagem na resposta do agente quando o sinal é fraco.
  * Disclaimer permanente no System Card.
  * Avaliação contínua via `make eval` (RAGAS + LLM-as-judge).
* O risco regulatório (CVM) está endereçado pela posição de **assistente
  informativo**, não consultor.

## 9. Limitações e recomendações

* Performance se degrada em **regimes muito diferentes** do treino —
  monitorar drift e retreinar quando `drift_psi_max ≥ 0,2` (PSI critical).
* Não captura eventos exógenos (anúncios CVM, decisões do COPOM, geopolítica)
  porque só consome OHLCV — o agente recorre a `search_reports` (RAG) para
  contexto qualitativo.
* **Recomendação operacional:** retreinar trimestralmente via `dvc repro train`
  e aprovar o challenger no MLflow Registry só se Δ`auc` ≥ 0,005 (recomendação
  do guia, GAP 07).

## 10. Versionamento e auditoria

| Item | Onde |
|------|------|
| Histórico de runs | MLflow (`mlflow ui` ou docker-compose) |
| Hash do dataset | DVC (`dvc.yaml` + `dvc.lock`) |
| Hash do código | tag `git_sha` no MLflow run |
| Métricas serializadas | `metrics/baseline_runs.json` |
| Schema de tags exigidas | `configs/model_config.yaml::training.required_tags` |
