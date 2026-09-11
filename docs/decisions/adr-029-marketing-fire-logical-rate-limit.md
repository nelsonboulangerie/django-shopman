# ADR-029 — Quota lógica do disparo manual de Marketing

**Status:** Aceito em 2026-09-11

## Contexto

O gate G-H04 limitava `fire` a 3 requests por hora por operador e 10 por dia
por loja. O comando seguro usa ao menos dois POSTs com a mesma idempotency key:
um abre `PUBLICAR <count>` e outro confirma. Assim, o transporte consumia quota
sem representar uma nova intenção e podia bloquear o primeiro fluxo corrigido.

## Decisão

- contar uma idempotency key como uma única operação lógica durante a janela;
- permitir 10 operações lógicas/hora por operador e 30/dia por loja;
- manter 10 commands perigosos/minuto por operador e 30/minuto por loja;
- manter step-up, confirmação tipada, token one-use, RBAC, auditoria, freeze,
  idempotência e a quota durável de 5.000 targets externos/dia;
- não oferecer bypass manual do contador;
- responder `429` com espera estruturada e apresentação em tempo humano.

Repetir a mesma chave não cria uma franquia: payload divergente continua em
conflito e replay idempotente continua devolvendo o receipt original.

## Consequências

O operador consegue corrigir e repetir o protocolo sem ser cobrado por seus
round-trips internos. Intenções novas continuam limitadas por ator e por loja.
A proteção de cache do Django REST Framework permanece uma defesa básica contra
uso excessivo; garantias de segurança continuam pertencendo aos gates
transacionais e às quotas duráveis.

## Referências

- `docs/reports/execution/marketing-human-gates-proposal-20260908-codex.md`
- OWASP Authentication Cheat Sheet — equilíbrio entre threshold, janela,
  duração e risco de denial of service ao usuário legítimo.
- NIST SP 800-63B, seção 3.2.2 — tentativas malsucedidas, espera progressiva e
  reset após autenticação bem-sucedida.
- Django REST Framework, Throttling — política de uso, não proteção completa de
  segurança ou denial of service.
