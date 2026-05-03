"""Guardrails de segurança para input e output do agente.

Referência: OWASP Top 10 for LLM Applications (2025)
            https://owasp.org/www-project-top-10-for-large-language-model-applications/

Implementação replicada da seção *Guardrails de Input e Output (Etapa 4)* do
guia oficial do Datathon — Fase 05.
"""

import logging
import re

logger = logging.getLogger(__name__)


class InputGuardrail:
    """Valida e sanitiza input do usuário antes de enviar ao LLM."""

    # Padrões comuns de prompt injection
    INJECTION_PATTERNS = [
        r"ignore\s+(all\s+)?previous\s+instructions",
        r"you\s+are\s+now\s+a",
        r"system:\s*",
        r"<\|im_start\|>",
        r"\[INST\]",
        r"forget\s+(everything|all|your\s+instructions)",
    ]

    def __init__(self, allowed_topics: list[str] | None = None):
        self.allowed_topics = allowed_topics or []
        self._compiled_patterns = [re.compile(p, re.IGNORECASE) for p in self.INJECTION_PATTERNS]

    def validate(self, user_input: str) -> tuple[bool, str]:
        """Valida input do usuário.

        Args:
            user_input: Texto do usuário.

        Returns:
            Tupla (is_valid, reason).
        """
        # Check 1: Prompt injection detection
        for pattern in self._compiled_patterns:
            if pattern.search(user_input):
                logger.warning("Prompt injection detectado: %s", user_input[:100])
                return False, "Input bloqueado: padrão suspeito detectado."

        # Check 2: Tamanho máximo (evitar context stuffing)
        if len(user_input) > 4096:
            return False, "Input bloqueado: excede tamanho máximo (4096 chars)."

        return True, "OK"


class OutputGuardrail:
    """Valida e sanitiza output do LLM antes de retornar ao usuário."""

    def __init__(self, language: str = "pt"):
        from presidio_analyzer import AnalyzerEngine
        from presidio_anonymizer import AnonymizerEngine

        self.analyzer = AnalyzerEngine()
        self.anonymizer = AnonymizerEngine()
        self.language = language

    # Entities supported by Presidio's default English NLP engine.
    # BR_CPF and PHONE_NUMBER require custom recognizers; EMAIL_ADDRESS and
    # PERSON work out of the box with the en_core_web_lg/sm spaCy model.
    _SUPPORTED_ENTITIES = ["PERSON", "EMAIL_ADDRESS", "PHONE_NUMBER"]

    # Regex fallback patterns for entities not covered by the default engine.
    _REGEX_PATTERNS: list[tuple[re.Pattern, str]] = [
        (re.compile(r"\d{3}\.\d{3}\.\d{3}-\d{2}"), "<CPF_REDACTED>"),
        (re.compile(r"\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}"), "<CNPJ_REDACTED>"),
        (re.compile(r"\(?\d{2}\)?[\s-]?9?\d{4}[\s-]?\d{4}"), "<PHONE_REDACTED>"),
    ]

    def sanitize(self, llm_output: str) -> str:
        """Remove PII do output do LLM.

        Args:
            llm_output: Texto gerado pelo LLM.

        Returns:
            Texto sanitizado.
        """
        text = llm_output

        # Step 1: Presidio for NER-based entities (falls back gracefully).
        try:
            # Use "en" — the default AnalyzerEngine ships English recognizers only.
            results = self.analyzer.analyze(
                text=text,
                language="en",
                entities=self._SUPPORTED_ENTITIES,
            )
            if results:
                logger.warning("PII detectado no output: %d entidades", len(results))
                text = self.anonymizer.anonymize(
                    text=text,
                    analyzer_results=results,  # type: ignore[arg-type]
                ).text
        except Exception as exc:
            logger.warning("Presidio analyze falhou (%s); usando regex fallback.", exc)

        # Step 2: Regex for BR-specific patterns (CPF, CNPJ, phone).
        for pattern, replacement in self._REGEX_PATTERNS:
            text = pattern.sub(replacement, text)

        return text
