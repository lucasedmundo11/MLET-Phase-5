"""Testes da API FastAPI da Etapa 2 — health + endpoints com LLM mockado."""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("langchain")

from fastapi.testclient import TestClient


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    from src.serving import app as app_module

    class _StubAgent:
        def invoke(self, payload: dict) -> dict:
            return {
                "output": f"resposta-mock para: {payload['input']}",
                "intermediate_steps": [("tool", "obs")],
            }

    class _StubLLM:
        def __call__(self, prompt: str, max_tokens: int, temperature: float) -> dict:
            return {
                "choices": [{"text": f"echo:{prompt[:32]}"}],
                "usage": {"total_tokens": len(prompt.split())},
            }

    app_module.get_llm.cache_clear()
    app_module.get_agent.cache_clear()
    monkeypatch.setattr(app_module, "get_llm", lambda: _StubLLM())
    monkeypatch.setattr(app_module, "get_agent", lambda: _StubAgent())
    return TestClient(app_module.app)


def test_health(client: TestClient) -> None:
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_llm_complete(client: TestClient) -> None:
    r = client.post("/llm/complete", json={"prompt": "olá", "max_tokens": 16})
    assert r.status_code == 200
    body = r.json()
    assert body["completion"].startswith("echo:")
    assert body["tokens_used"] >= 1


def test_agent_chat(client: TestClient) -> None:
    r = client.post("/agent/chat", json={"question": "Qual ação teve maior retorno em 2024?"})
    assert r.status_code == 200
    body = r.json()
    assert "resposta-mock" in body["answer"]
    assert body["intermediate_steps"] == 1


def test_chat_validation_rejects_empty(client: TestClient) -> None:
    r = client.post("/agent/chat", json={"question": ""})
    assert r.status_code == 422
