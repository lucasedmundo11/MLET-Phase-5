# System Card

## System Overview

An end-to-end LLM-powered question-answering system using a ReAct agent with RAG, served via FastAPI.

## Capabilities

- Retrieval-augmented generation over a structured knowledge base
- Tool use: knowledge search, arithmetic, external data fetch
- Input/output guardrails (prompt injection, PII redaction)

## Intended Use Cases

- Internal Q&A assistant for structured domain knowledge
- Automated support for data queries within a controlled enterprise context

## Out-of-Scope Uses

- Open-ended internet browsing or arbitrary code execution
- Medical, legal, or financial advice without human review

## Risk Assessment

| Risk                    | Likelihood | Impact | Mitigation                          |
|-------------------------|-----------|--------|-------------------------------------|
| Hallucination           | Medium    | High   | RAG grounding + LLM-as-judge eval   |
| Prompt injection        | Medium    | High   | InputGuardrail pattern matching     |
| PII leakage             | Low       | High   | Presidio PII detection + redaction  |
| Model drift             | Medium    | Medium | Evidently + PSI monitoring          |

## Evaluation

- RAGAS: 4 metrics (faithfulness, answer_relevancy, context_recall, context_precision)
- LLM-as-judge: correctness, completeness, harmlessness (≥ 3 criteria)
- Golden set: ≥ 20 query-answer-context pairs

## Deployment

- FastAPI + Docker + Prometheus metrics
- CI/CD via GitHub Actions (lint → test → build)
- MLflow model registry with champion-challenger tracking
