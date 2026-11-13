# ADR-046 — Suporte: helpdesk interno com gate de dev

**Status:** Aceito
**Data:** 2026-11-12
**Escopo:** `shopman/backstage`, `surfaces/hub-nuxt`, `docs/coordination`
**Origem:** decisão do dono em 12/11/2026, na conversa sobre o helpdesk interno

---

## Contexto

Pedidos, queixas e decisões se perdem em chats e em corpos de PR. O operador
não pode preencher contexto que o sistema já tem (pedido, dispositivo, turno,
setor). O dono não pode deixar código mudar sem autorização. O Canny resolve
feedback, mas não tem o pedido, o dispositivo e o turno; um SaaS externo não
enxerga o contexto operacional da casa.

O repo já tem as peças: `backstage` para a superfície de operador, `hub-nuxt`
como home mobile-first autenticada, SSE, permissões por `has_perm`, e o ledger
`docs/coordination/COMMITMENTS.md` com IDs `DEV-`.

## Decisão

1. **Suporte é capability, não kernel.** Vive em `shopman/backstage` (models,
   API, projection, permissões) e numa página `/support` no `hub-nuxt`. Não
   cria 14º pacote nem 12ª surface nesta fase.
2. **O ticket é `HELP-AAAA`.** Tem mensagens, decisão, aprovador, estado, SLA e
   um `ledger_ref` para o compromisso de dev (`DEV-AAAA`).
3. **Contexto automático.** O ticket nasce com o envelope operacional da
   ADR-045: ator, papel, loja, setor, turno, dispositivo, workstation,
   `business_date`, rota, entidade em foco, último erro/request ID, versão e
   conectividade. O operador escreve só a exceção. O contexto carrega refs, não
   PII.
4. **Captura primeiro, classificação depois.** O ticket nasce `NEW` com o texto
   cru. A classificação (tipo, fila, prioridade) é sugestão da IA ou triagem
   humana; se a confiança for baixa, a IA faz **uma** pergunta ao requester.
   Nunca bloqueia a captura.
5. **Tipos:** `question`, `complaint`, `bug`, `request`, `idea`, `decision`.
6. **Estados:** `NEW`, `TRIAGE`, `WAITING_REQUESTER`, `WAITING_OWNER`,
   `APPROVED`, `REJECTED`, `IN_DEV`, `RESOLVED`, `CLOSED`, `DEFERRED`. Cada
   estado tem dono e próximo evento; `DEFERRED` exige `revisar_em`.
7. **Permissões:** `shop.create_support_ticket`,
   `shop.triage_support_tickets`, `shop.view_all_support_tickets`,
   `shop.approve_support_requests` (só dono), `shop.link_support_dev`.
8. **Aprovação.** Pedido explícito do dono é aprovação implícita, registrada
   com `approved_by`, `approved_at` e `approval_basis`. Ideia vai para triagem.
   Ambíguo: a IA pergunta. Só o aprovado gera `DEV-`; o PR cita
   `Pedido: DEV-…` e o CI confere.
9. **Offline-first** no POS/KDS: fila local, UUID idempotente, sincronização
   quando voltar. O pior incidente é o sistema fora do ar.
10. **UI simples:** um campo, contexto no topo, sugestão editável, thread,
    status e aprovação. Sem dois botões "Pedido/Ideia".
11. **Notificações:** SSE no hub. Telegram/WhatsApp são canais (entrada e
    aviso), nunca o banco ou o motor.
12. **Interno primeiro.** O tronco externo (público) vem depois, com auth de
    cliente, antiabuso, LGPD, SLA e time de atendimento; "Ouvidoria" só se for
    canal formal com política própria.

## Consequências

- Models e migrações em `backstage`; API DRF com o dialeto
  `{detail, field, errors}`; permissões; página no hub; testes.
- O ledger `DEV-` continua sendo o contrato de dev; o ticket é o registro do
  Suporte. Dois registros, uma disciplina: ID, dono, estado, prazo e prova.
- A IA (ID3A) é opcional na v1: o ticket funciona sem ela; a triagem pode ser
  humana. A IA sugere, nunca aprova.
- Sem IA paga no caminho de captura. A triagem por IA é assíncrona, orçada e
  medida; o JEV entra como decisão, não como geração.
- Nada é apagado: ticket fechado guarda histórico; `DEFERRED` tem data;
  `REJECTED` tem quem e por quê.

## Invariantes

- Nenhum código muda sem `DEV-` aprovado pelo dono.
- Nenhum ticket existe sem dono e próximo evento.
- Nenhuma captura depende de IA, rede ou provider externo.
- Nenhum dado de cliente sai para provider externo sem redaction e base legal.
- Nenhuma decisão de dinheiro, estoque, fiscal ou pedido é tomada pela IA.
