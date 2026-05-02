# Plano de Conformidade LGPD

## Base Legal

O tratamento de dados pessoais neste sistema é fundamentado em:
- **Legítimo Interesse** (Art. 7º, IX): análise interna de qualidade de atendimento
- **Consentimento** (Art. 7º, I): quando dados pessoais forem coletados de usuários finais

## Dados Tratados

| Categoria       | Dado              | Finalidade                     | Retenção  |
|-----------------|-------------------|-------------------------------|-----------|
| Identificação   | Nome, e-mail      | Personalização de resposta    | 90 dias   |
| Comportamental  | Histórico de query| Melhoria do modelo            | 1 ano     |
| Técnico         | Logs de acesso    | Segurança e auditoria         | 6 meses   |

## Direitos dos Titulares (Art. 18)

- Acesso, correção e exclusão de dados disponíveis via endpoint `/user/data`
- Prazo de resposta: 15 dias corridos

## Medidas Técnicas

- **Pseudonimização:** session_id no lugar de identificadores diretos nos logs
- **Detecção de PII:** Presidio aplicado em inputs e outputs (`src/security/pii_detection.py`)
- **Criptografia em repouso:** dados armazenados em S3 com SSE-S3
- **Criptografia em trânsito:** HTTPS/TLS obrigatório

## DPO e Contato

- DPO responsável: TBD
- Canal de atendimento: privacidade@empresa.com

## Plano de Resposta a Incidentes

1. Detecção → alerta automático (Prometheus + PagerDuty)
2. Contenção → revogar tokens afetados em < 1h
3. Comunicação à ANPD em até 72h (Art. 48)
4. Post-mortem documentado em `docs/`
