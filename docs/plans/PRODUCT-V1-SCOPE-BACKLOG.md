# PRODUCT-V1-SCOPE-BACKLOG — Frentes de produto em aberto antes do go-live

> Registro vivo das frentes de **produto** (features/UX) que ainda faltam, para
> que o escopo do **v1 público da Nelson** seja uma decisão consciente — não um
> esquecimento. Este doc é o **gate de escopo** do [GO-LIVE-READINESS-PLAN](GO-LIVE-READINESS-PLAN.md):
> o go-live real só dispara quando o "deve entrar no v1" abaixo estiver fechado.

**Status**: 🟢 Corte v1 decidido pelo Pablo (2026-06-26) e revisto por ele em 2026-10-01
([D-017](../coordination/DECISIONS.md)): ficam fora do go-live **só Marketing e B.I.**; entra todo o
resto, explicitamente a entrega por parceiro (TaOn/Machine) e o Concierge. v1 é **amplo** — ver nota de sequenciamento no fim.

---

## Relação com o go-live

- O **GO-LIVE-READINESS-PLAN** cuida do *como* publicar com segurança (gateways,
  migrations-freeze, runbooks, auth, QA).
- Este doc cuida do *o que* publicar (escopo de produto).
- **Importante**: o **Lote A** (WP-GAP-07 prep) **não conflita** com desenvolver
  estas frentes — ele é tooling/docs e só congela schema no go-live. Logo, dá
  para tocar produto e Lote A em paralelo. O que espera este backlog é o
  **go-live em si** (bloqueios externos + reset final).

---

## Frentes (corte v1 decidido em 2026-06-26)

### ✅ v1 — deve entrar antes do go-live

| Frente | O que falta | Origem |
|---|---|---|
| **Gestor de pedidos ao estado da arte** | ✅ **Arcs 1–5 entregues + DEPLOYADO no staging (2026-06-27, gestor.boulangerie.com.br)**. [GESTOR-PEDIDOS-PLAN](completed/GESTOR-PEDIDOS-PLAN.md). Resta QA funcional autenticado | Pablo (2026-06-26) |
| **Canal: Loja online (retirada)** | Base pronta; manter no escopo | existente |
| **Canal: PDV / balcão** | Base pronta; manter no escopo | existente |
| **Canal: Entrega / delivery** | Ativa a frente de **endereço canônico** (busca/geo/ajuste no mapa); taxa por distância já existe. **Entrega por parceiro (TaOn/Machine)** entra no go-live (D-017): adapter no ar (#1345, #1348; `SHOPMAN_COURIER_ADAPTER` e credenciais no painel, [D-020](../coordination/DECISIONS.md)); falta o dono ligar `fulfillment.courier="auto"` no canal `web` | [ADDRESS-UX-PLAN](ADDRESS-UX-PLAN.md); D-017; D-020 |
| **Canal: WhatsApp conversacional (Concierge)** | Plano canônico: [WHATSAPP-CONCIERGE-PLAN](WHATSAPP-CONCIERGE-PLAN.md) (supera o MANYCHAT-CONVERSACIONAL-PLAN). Visão do dono e distância medida em 01/10/2026 estão lá. Entra a **fase 1** do plano; a triagem foi decidida (D32 → [D-018](../coordination/DECISIONS.md)) e implementada (#1347). Ligar segue a sequência "Como ligar" do plano | ROADMAP "Dívida Viva"; dono (01/10/2026) |
| **Sincronização com catálogos externos** | Feed pull Google/Meta e push Meta entregues; faltam homologação externa, vínculo do catálogo Meta ao WhatsApp e eventual push Google apenas se necessário. Plano: [CATALOG-SYNC-EXTERNO-PLAN](CATALOG-SYNC-EXTERNO-PLAN.md) | Revalidado (2026-09-29) |
| **Media persistente (Cloudflare R2)** | Código pronto e desligado (#1337, D-010). Falta o dono criar bucket e token e colar as chaves na DO (D30); depois, `SHOPMAN_MEDIA_STORAGE=r2` | ROADMAP "Dívida Viva"; D6 |
| **Shelf life perecível** | ✅ precedência (shelf_life × batch expiry = AND) explícita + travada por teste (2026-06-26). Resta só decisão de onde validar consistência de lote. Ver ROADMAP | ROADMAP "Dívida Viva" |
| **Revisão reversa do PDV (Fase C)** | ✅ auditoria feita: [POS-FASE-C-REVISION](POS-FASE-C-REVISION.md). POS é maduro; 1 fix aplicado, resto = itens a verificar/decisões | `project_storefront_gaps_review` |
| **Surface convergence** | ✅ Convergência completa (2026-06-27): POS-HTMX removido, KDS no Nuxt | [SURFACE-CONVERGENCE-PLAN](completed/SURFACE-CONVERGENCE-PLAN.md) |
| **Playwright E2E como gate** | ✅ Obrigatória: `Storefront E2E (Playwright)` e `Browser QA (Nuxt store + Django operator)` estão entre os 23 checks obrigatórios de `main` (`.github/required-status-checks.json`, conferido contra o vivo por `make required-checks-drift`) | ROADMAP "Dívida Viva" |

### ⏭️ pós-v1 — fica para depois do go-live

| Frente | Motivo |
|---|---|
| **Concierge além da fase 1** (pedido completo no chat; "o pedido de sempre" proativo) | O Concierge **entra** no go-live (D-017) na fase 1 do [WHATSAPP-CONCIERGE-PLAN](WHATSAPP-CONCIERGE-PLAN.md). A fase 2 depende de dar autoridade de compra a um ingresso do ManyChat sem identificador de mensagem; o "Futuro" depende de template aprovado na Meta. Ver "Fases" no plano |
| **Endereço — teleporte (WP-11 slice 3)** | Bloqueado em URL/campos do serviço; o fluxo base de endereço já cobre entrega |
| **Customer rating** | Nice-to-have; hoje há `Order.data.customer_rating` mínimo |
| **Mudar número de telefone** | Feature de borda ([CHANGE-PHONE-NUMBER-PLAN](CHANGE-PHONE-NUMBER-PLAN.md)) |
| **Marketing** | Fora do go-live por decisão do dono (01/10/2026, D-017) |
| **B.I.** | Fora do go-live por decisão do dono (01/10/2026, D-017) |

---

## Nota de sequenciamento (honesta)

O v1 ficou **amplo** — 11 frentes, várias greenfield (ManyChat conversacional,
catálogos externos) ou dependentes de infra/credencial externa. Isso é legítimo,
mas o go-live só dispara quando **todas** as ✅ estiverem entregues, então a
ordem importa para não travar tudo numa só. Sugestão de ondas dentro do v1:

1. **Operação núcleo** (sem dependência externa): Gestor de pedidos ao estado da
   arte, Revisão reversa do PDV, Surface convergence, Shelf life. São os que mais
   dependem só de código — começar por aqui rende valor cedo.
2. **Infra de produto**: Media persistente (Cloudflare R2), Playwright como gate.
3. **Canais externos** (dependem de credencial/conta — andam junto com os
   bloqueios do Pablo no [GO-LIVE-READINESS-PLAN](GO-LIVE-READINESS-PLAN.md)):
   Entrega/endereço e entrega por parceiro (TaOn/Machine), WhatsApp/ManyChat (Concierge),
   Sincronização de catálogos externos.

Cada frente ✅ precisa virar (ou já tem) plano executável antes de entrar.

---

## Próxima ação

1. ✅ Corte v1 decidido (2026-06-26) e revisto em 2026-10-01 (D-017, abaixo no item 3).
2. Transformar cada frente ✅ em plano executável (ou reusar o existente),
   seguindo as ondas de sequenciamento acima.
3. O go-live (no GO-LIVE-READINESS-PLAN) dispara com **todas** as ✅ entregues.
   Decisão do dono em 01/10/2026 ([D-017](../coordination/DECISIONS.md)): a proposta de
   corte (#1336) foi recusada; **ficam fora só Marketing e B.I.** Entram as onze frentes,
   com destaque para a entrega por parceiro (TaOn/Machine) e o Concierge (WhatsApp
   conversacional). Custo e dependência externa de cada frente em
   [GO-LIVE-SCOPE-CUT-PROPOSTA](GO-LIVE-SCOPE-CUT-PROPOSTA.md).

---

## Referências

- [GO-LIVE-READINESS-PLAN](GO-LIVE-READINESS-PLAN.md)
- [docs/plans/README.md](README.md) — índice de planos
- [docs/ROADMAP.md](../ROADMAP.md) — dívida técnica viva
