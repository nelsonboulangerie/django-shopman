# ADR-044 — Substituibilidade vive na borda de capability; kernel é substituível só por quem implementa o contrato

**Status:** Aceito
**Data:** 2026-11-10
**Escopo:** packages/* (kernels), shopman/shop (orquestrador), integrações
**Origem:** auditoria v5/v6 + questão Q6 do dono (2026-11-10)

## Contexto

A suíte foi separada em kernels independentes por dois motivos que se confundiam: (a) reuso
independente em projetos distintos e (b) substituição de um app por agente externo (planilha,
ERP, SaaS). A auditoria (Q6) revelou que os dois motivos pedem mecanismos diferentes, e que
"substituível por planilha" não é meta realista para kernel que possui invariante próprio.

## Decisão

1. **Reuso independente = kernel como pacote pip.** Já realizado; ADR-001. Cada kernel tem
   migração, admin e testes próprios e não importa outro kernel.
2. **Substituível na BORDA (capability):** pagamento, fiscal, notificação, courier, marketing,
   OTP — provedores de efeito externo. Já seguem Protocol/Adapter (ADR-001). Substitui-se o
   provedor (Efí↔Stripe↔mock, Focus, Twilio↔Comtele↔ManyChat, Machine↔mock).
3. **Substituível no NÚCLEO (kernel) apenas por agente que implemente o MESMO contrato
   semântico** (hold atômico com expiração, livro imutável, máquina de estados). O teste é
   "implementa o contrato?", nunca "é externo?". Planilha não implementa reserva atômica;
   um ERP real pode, se expuser o contrato — e, se expuser, o slot (ex.: INVENTORY_BACKEND)
   já o aceita.
4. **Aposenta-se o anti-padrão:** backend de ESCRITA plugável onde um signal basta (a dívida
   do InventoryProtocol morto). Porto/adapter só nasce para variação real ou retorno síncrono
   necessário.

## Consequências

- Integrações agrupadas por capability→provider, selecionadas por settings, import lazy.
- Não criar port para estoque/fulfillment/produção (signal basta).
- Não criar kernel nem port vazio "para o futuro"; o gatilho de extração é 2 distribuições
  reais fora do mesmo orquestrador, não a quantidade de condições.
