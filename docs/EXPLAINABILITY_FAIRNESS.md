# Explicabilidade & Fairness

> Etapa 4 — critério de aceite: **Explicabilidade e fairness documentados**.
> Cobre as duas camadas do sistema: o **baseline preditivo** (LogReg / MLP)
> e o **agente conversacional** (LLM + ReAct).

## 1. Explicabilidade

### 1.1 Camada do baseline (Etapa 1)

O baseline `LogisticRegressionBaseline` é **interpretável por construção**:

* **Coeficientes** indicam direção e magnitude da contribuição de cada feature
  (RSI, MACD, %B, retornos defasados, volatilidade) sobre a probabilidade de
  alta no D+1.
* **Padronização ausente** — features já vêm em escalas comparáveis
  (RSI ∈ [0, 100], retornos log ∈ ℝ pequeno) → coeficientes são lidos
  diretamente sem reescalonamento adicional.
* **Snippet** para inspecionar coeficientes pós-treino:

  ```python
  import mlflow
  from src.models.baseline import FEATURE_COLUMNS

  model = mlflow.sklearn.load_model("runs:/<run_id>/model")
  coefs = dict(zip(FEATURE_COLUMNS, model.coef_[0]))
  # ex.: {'rsi_14': -0.012, 'macd_diff': 0.08, ...}
  ```

O `MLPClassifierTorch` é menos interpretável; em caso de uso, sugerimos:

* **Importância por permutação** (`sklearn.inspection.permutation_importance`)
  como aproximação rápida.
* **SHAP** (`shap.DeepExplainer`) sobre uma amostra representativa, **fora do
  hot path** de produção (alto custo computacional).

### 1.2 Camada do agente (Etapa 2)

O agente **expõe explicabilidade nativa via ReAct**:

* Cada chamada a `POST /agent/chat` devolve `intermediate_steps` (contagem
  de Thought → Action → Observation), e a versão verbose dos passos é
  acessível pelos logs estruturados.
* Cada **tool é determinística** e produz uma observação de texto que pode
  ser auditada — diferente de LLMs *end-to-end* que não expõem o caminho.
* A resposta cita as tools usadas (ex.: `(petr.pdf #3) ...` para o
  `search_reports`), permitindo verificação manual da fonte.

**Exemplo de trace** (formato real do `verbose=True` do AgentExecutor):

```
Thought: preciso comparar dois tickers pelo P/L → uso compare_fundamentals
Action: compare_fundamentals
Action Input: tickers=PETR4,VALE3,metric=pe_ratio
Observation:           pe_ratio
ticker
PETR4.SA       4.20
VALE3.SA       5.85
Thought: já tenho os números, posso responder
Final Answer: PETR4 está com P/L 4,20 e VALE3 com 5,85 ...
```

Esse log é **a explicação** do raciocínio do agente — disponível
imediatamente, sem ferramenta extra.

## 2. Fairness

O domínio (mercado financeiro sobre tickers) **não envolve atributos
protegidos de pessoas** (gênero, raça, idade, etc.). Mesmo assim, fairness
no contexto financeiro tem dois ângulos relevantes:

### 2.1 Paridade entre tickers (não discriminação intra-universo)

Um modelo que sistematicamente acerta para PETR4 e erra para WEGE3 produziria
recomendações enviesadas — investidores de WEGE3 receberiam pior serviço.

**Métrica de monitoramento.** Decompor `auc/precision/recall/f1` **por
ticker** durante a avaliação do baseline:

```python
from sklearn.metrics import roc_auc_score
import pandas as pd

per_ticker = (
    df.assign(pred=model.predict(df[FEATURE_COLUMNS]))
      .groupby("ticker")
      .apply(lambda g: pd.Series({
          "auc": roc_auc_score(g["target"], g["pred"]),
          "n":   len(g),
      }))
)
print(per_ticker)
```

**Limiar adotado.** A diferença entre o melhor e o pior AUC entre tickers
deve ser **≤ 0,05**. Caso contrário, o ticker mais fraco recebe um aviso na
resposta do agente ("a confiança do sinal técnico para WEGE3 é menor que a
média do universo").

### 2.2 Paridade setorial

Setores (Energy, Materials, Financial Services, Industrial) têm regimes de
volatilidade muito distintos — ITUB4 e BBDC4 são quase colineares (ver
notebook EDA). Isso pode fazer o agente **subestimar risco** de carteiras
mal diversificadas.

**Mitigação.** A tool `portfolio_risk` **sempre** devolve a matriz de
correlação junto com a volatilidade — força o agente a apresentar a
informação relevante para diversificação, mesmo sem ser perguntado
explicitamente.

### 2.3 Auditabilidade da fairness

* Monitorada offline em `make eval` (LLM-as-judge analisa resposta por
  resposta).
* O critério `actionability` do judge tende a penalizar respostas que
  **omitem risco** ou que **recomendam concentração** — funciona como
  proxy de fairness setorial.

## 3. Tag obrigatória `fairness_checked`

Conforme o guia (GAP 05, p. 6), o registro do modelo no MLflow deve incluir
a tag booleana `fairness_checked`. Recomendação operacional:

* **Setar `True`** quando o run for aprovado pelo procedimento desta seção
  (decomposição por ticker + revisão da matriz de correlação).
* **Setar `False`** caso contrário; o `OutputGuardrail` pode então acrescentar
  ressalva automática à resposta do agente.

## 4. Limitações reconhecidas

* Não existe ainda **decomposição por regime de mercado** (alta/baixa/lateral)
  — mercados em pânico podem ter performance específica não capturada por
  esta análise.
* Fairness setorial é proxied por correlação; não substitui análise de risco
  fatorial completa (ex.: Fama-French).
* SHAP para o MLP **não é executado em produção**, apenas sob demanda em
  notebook — custo computacional desproporcional ao ganho explicativo no MVP.

## 5. Próximos passos sugeridos (pós-Datathon)

1. Adicionar métrica de fairness no Grafana
   (`baseline_auc_per_ticker{ticker="..."}`).
2. Habilitar SHAP automatizado quando o MLP for promovido a champion.
3. Estender a análise para janelas de 3 meses (regime drift).
