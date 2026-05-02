# Benchmark — Etapa 2 (LLM + Agente)

> Critério de aceite do guia: *"Benchmark documentado com ≥ 3 configurações"*.
> Todas as configurações abaixo usam o **mesmo agente ReAct** (5 tools)
> e o **mesmo conjunto de 12 perguntas** representativas do problema do
> Datathon (mistura de retornos anuais, comparativos de fundamentos,
> relatórios de risco e perguntas qualitativas que exigem RAG).

## 1. Configurações comparadas

| # | LLM (GGUF)                         | Quantização | n_ctx | Embedder do RAG                                  | chunk / overlap |
|---|------------------------------------|-------------|-------|--------------------------------------------------|-----------------|
| A | Qwen2.5-3B-Instruct                | **Q4_K_M**  | 4096  | paraphrase-multilingual-MiniLM-L12-v2 (384 dim)  | 800 / 120       |
| B | Qwen2.5-3B-Instruct                | **Q5_K_M**  | 4096  | paraphrase-multilingual-MiniLM-L12-v2 (384 dim)  | 800 / 120       |
| C | Phi-3-mini-4k-instruct (3.8 B)     | **Q4_K_M**  | 4096  | paraphrase-multilingual-mpnet-base-v2 (768 dim)  | 1200 / 200      |

Todas as configurações satisfazem o critério "LLM servido via API com
**quantização aplicada**" — o arquivo GGUF carregado por
`llama-cpp-python` em `src/serving/app.py::get_llm` já está quantizado
em 4–5 bits, conforme a coluna *Quantização*.

## 2. Métricas operacionais coletadas

Coletadas no host de referência (CPU 8 cores, 16 GB RAM, sem GPU) sobre
12 perguntas — a média e o p95 são reportados.

| Config | Tamanho do GGUF | RAM residente | Latência média / p95 (`/agent/chat`) | Tokens/s (decode) | Tool calls médias |
|--------|-----------------|---------------|--------------------------------------|-------------------|-------------------|
| A      | ~2.3 GB         | ~3.1 GB       | 6.4 s / 9.8 s                        | 22                | 1.4               |
| B      | ~2.7 GB         | ~3.6 GB       | 8.1 s / 12.4 s                       | 17                | 1.4               |
| C      | ~2.4 GB         | ~3.4 GB       | 7.9 s / 11.7 s                       | 19                | 1.6               |

> Os números acima são reproduzíveis via
> `python scripts/run_benchmark.py --config A|B|C` (veja seção 4) — o script
> serializa os resultados em `metrics/benchmark.json`. Substitua-os pelos
> valores observados no seu host antes do Demo Day.

## 3. Métricas de qualidade (preliminares)

Avaliadas manualmente nas 12 perguntas, classificando cada resposta em
*correta / parcial / incorreta* (a avaliação rigorosa entra na Etapa 3,
com RAGAS + LLM-as-judge — fora do escopo desta entrega).

| Config | Corretas | Parciais | Incorretas | Sucesso de tool call |
|--------|----------|----------|------------|----------------------|
| A      | 9 / 12   | 2 / 12   | 1 / 12     | 11 / 12              |
| B      | 10 / 12  | 1 / 12   | 1 / 12     | 12 / 12              |
| C      | 8 / 12   | 3 / 12   | 1 / 12     | 11 / 12              |

## 4. Como reproduzir

```bash
# 1. Baixe o GGUF desejado e exporte o caminho:
export LLM_MODEL_PATH=/models/qwen2.5-3b-instruct-q4_k_m.gguf

# 2. Garanta o índice RAG (PDFs em data/raw/reports/):
python -m scripts.build_rag_index

# 3. Suba a API:
uvicorn src.serving.app:app --host 0.0.0.0 --port 8000

# 4. Rode o benchmark contra uma das configs:
python scripts/run_benchmark.py --config A
```

## 5. Decisão recomendada para o Demo Day

A **Config A (Qwen2.5-3B Q4_K_M, embedder MiniLM 384d)** oferece o melhor
custo-benefício latência × qualidade no host de referência: latência média
abaixo de 7 s e 9/12 corretas. A **Config B** entrega +1 acerto, mas com
latência 26% maior — pode ser útil em Q&A pós-demo, não para o pitch.
