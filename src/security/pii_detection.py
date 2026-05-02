"""Detecção e anonimização de PII com Presidio — Etapa 4.

Wrapper fino sobre ``presidio-analyzer`` / ``presidio-anonymizer`` que adiciona:

* lista padrão de entidades relevantes ao domínio brasileiro
  (PERSON, EMAIL_ADDRESS, PHONE_NUMBER, CREDIT_CARD, IP_ADDRESS, BR_CPF);
* fallback regex para CPF/CNPJ caso o reconhecedor BR do Presidio falhe;
* método ``contains_pii`` para uso em pipeline de logs (LGPD).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from presidio_analyzer import AnalyzerEngine
from presidio_anonymizer import AnonymizerEngine

logger = logging.getLogger(__name__)


DEFAULT_ENTITIES: tuple[str, ...] = (
    "PERSON",
    "EMAIL_ADDRESS",
    "PHONE_NUMBER",
    "CREDIT_CARD",
    "IP_ADDRESS",
    "BR_CPF",
)

# CPF e CNPJ — fallback caso o reconhecedor BR do Presidio não esteja disponível
# (depende do modelo spaCy carregado).
CPF_REGEX = re.compile(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b")
CNPJ_REGEX = re.compile(r"\b\d{2}\.?\d{3}\.?\d{3}/?0001-?\d{2}\b")


@dataclass
class PIIFinding:
    entity_type: str
    start: int
    end: int
    text: str
    score: float


class PIIDetector:
    """Detecta e anonimiza PII conforme exigências da LGPD."""

    def __init__(self, language: str = "pt", entities: tuple[str, ...] = DEFAULT_ENTITIES):
        self.language = language
        self.entities = list(entities)
        self.analyzer = AnalyzerEngine()
        self.anonymizer = AnonymizerEngine()

    def detect(self, text: str) -> list[PIIFinding]:
        """Devolve a lista de entidades PII encontradas em ``text``."""
        if not text:
            return []
        results = self.analyzer.analyze(text=text, language=self.language, entities=self.entities)
        findings = [
            PIIFinding(
                entity_type=r.entity_type,
                start=r.start,
                end=r.end,
                text=text[r.start : r.end],
                score=float(r.score),
            )
            for r in results
        ]

        # Fallback regex (CPF / CNPJ): garante cobertura mesmo sem o
        # reconhecedor nativo do Presidio.
        for label, regex in (("BR_CPF", CPF_REGEX), ("BR_CNPJ", CNPJ_REGEX)):
            for m in regex.finditer(text):
                if not any(f.start == m.start() and f.end == m.end() for f in findings):
                    findings.append(
                        PIIFinding(
                            entity_type=label,
                            start=m.start(),
                            end=m.end(),
                            text=m.group(0),
                            score=1.0,
                        )
                    )
        return findings

    def contains_pii(self, text: str) -> bool:
        """Boolean utilitário — útil para gate de logs."""
        return bool(self.detect(text))

    def anonymize(self, text: str) -> str:
        """Anonimiza PII detectado em ``text``."""
        if not text:
            return text
        results = self.analyzer.analyze(text=text, language=self.language, entities=self.entities)
        if not results:
            text_out = text
        else:
            text_out = self.anonymizer.anonymize(text=text, analyzer_results=results).text  # type: ignore[arg-type]

        # Pós-processamento: máscara dos padrões regex que escaparam ao Presidio.
        text_out = CPF_REGEX.sub("<BR_CPF>", text_out)
        text_out = CNPJ_REGEX.sub("<BR_CNPJ>", text_out)
        return text_out
