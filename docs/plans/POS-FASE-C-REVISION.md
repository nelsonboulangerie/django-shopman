# POS — Fase C (revisão reversa do PDV)

> Revisão reversa (a partir do código) da superfície de PDV `surfaces/pos-nuxt`
> + backend headless. Frente **v1** (Onda 1). Cada achado abaixo tem **status de
> verificação** — claims não confirmados no código não viram "gap".

**Status**: ✅ Reconciliação concluída em 2026-09-29. Os achados técnicos desta
revisão foram revalidados no código atual; nenhuma lacuna adicional segura foi
confirmada para execução autônoma.

---

## Método (e uma lição)

A primeira passada (agente de exploração) listou vários "gaps" que **não
resistiram à verificação no código** — coerente com a regra do projeto:
*confirmar no código antes de reportar gap*. Por isso este doc separa
**confirmado** de **a verificar**.

Exemplos de claims **derrubados na verificação**:
- *"Atalhos de teclado não implementados (WP-1)"* → **falso**: há handlers de
  teclado em `app/app.vue`, `app/components/PosTabHeader.vue`,
  `app/components/PosCartPanel.vue`, `app/composables/useOperatorLock.ts`.
- *"Seletor de fulfillment ausente no checkout"* → **não confirmado**:
  `fulfillment` aparece em `app/components/PosPaymentWorkspace.vue`,
  `app/composables/usePosSale.ts`, `app/presentation/payment.ts`. Precisa de
  verificação funcional antes de declarar gap.

Conclusão honesta: **o POS está mais completo do que uma leitura de superfície
sugere.** Uma Fase C real é uma auditoria item-a-item verificada, não uma lista
de suspeitas.

---

## Arquitetura (confirmada)

- **Superfície ativa**: `surfaces/pos-nuxt` (Nuxt, desktop-first).
  `app.vue` orquestra `usePosTerminal` (read) + `usePosSale` (write) +
  `useOperatorLock`. Presentation pura em `app/presentation/` (payment, tabBoard,
  moveLines, cash, kitchen, …).
- **Backend headless**: `shopman/backstage/api/operations.py` (POSView + ações),
  `shopman/backstage/projections/pos.py`, `shopman/shop/services/pos.py`
  (open/review/close/move/fire/cancel), `shopman/backstage/services/pos.py`
  (caixa).
- **Sem POS-HTMX legado ativo** (confirmado: superfície é só Nuxt).

## O que funciona (confirmado por testes existentes)

Comanda (abrir/tocar/renomear), itens, **move_lines** (split/transfer/merge,
preço congelado, kernel atômico), **fire-to-kitchen** progressivo, pagamento
(dinheiro/PIX/cartão/misto, troco derivado), **caixa cego**, **manager-PIN**,
cancelamento. Backend com cobertura robusta (`test_pos_*` extenso); vitest no
surface cobre intent/payment math/operator lock.

---

## Achados

### ✅ Corrigido nesta sessão

- **move_lines: rollback de cleanup mascarava o erro original**
  ([`shopman/shop/services/pos.py`](../../shopman/shop/services/pos.py)) — quando
  o split criava a comanda destino e o move falhava, o `abandon_session` de
  rollback era desprotegido; se ele lançasse, o erro original do move sumia.
  Agora o cleanup é best-effort (try/except + log), e o erro `move_failed`
  original sempre chega ao operador. Teste:
  `test_split_rollback_failure_does_not_mask_move_error`.

### ✅ Achados revalidados em 2026-09-29

- **Cédulas de dinheiro**: o contrato canônico já expõe
  `cash_tender_delta_presets_q`; `cashNotesQ()` consome o contrato e mantém a
  lista BRL apenas como fallback. Cobertura em
  `surfaces/pos-nuxt/tests/presentation.test.ts`.
- **Fulfillment no checkout**: retirada e delivery, inclusive endereço, taxa e
  regras condicionais, estão no contrato de `shopman/backstage/projections/pos.py`
  e no workspace de pagamento da superfície Nuxt.
- **Dados fiscais e operação NFC-e**: o perfil fiscal de produto, validação,
  status, DANFE e reprocessamento existem no pipeline atual. O smoke real ainda
  depende das credenciais/homologação externas do gate de go-live; isso não é
  lacuna de implementação desta revisão.
- **Teclado e foco**: o mapa operacional está implementado em
  `surfaces/pos-nuxt/app/pages/index.vue` e coberto por testes de apresentação,
  componentes e páginas.
- **Fire → KDS → cancelamento/fechamento**: há fluxo explícito para cancelar
  linhas já disparadas, refazer o fire e manter a consistência do fechamento,
  com cenários em `shopman/backstage/tests/test_pos_fire.py`.

### ⚪ Decisões de produto (suas — não autônomas)

- **Aviso "dinheiro abaixo do total" é warning, não erro** (review_sale) — pode
  ser intencional (pagamento parcial/fiado). Mudar para erro é decisão de regra.
- **Labels de operação hardcoded** ("Dinheiro"/"PIX"/"Balcão") — config via
  Omotenashi é a frente de *surface convergence/config*, não um fix pontual.
- **Health de terminal nunca bloqueia** (impressora obrigatória vs. recibo) —
  decisão operacional.

---

## Recomendação

A Fase C **não** deve virar um refactor amplo do POS: os itens técnicos levantados
em 2026-06 foram resolvidos ou derrubados pela verificação no produto atual.

O único bloco estrutural ainda aberto é **WP-9, offline-first e contingência**,
registrado em `POS-FIRST-CLASS-PLAN.md`. Ele exige decisão de política fiscal,
conflito/replay e operação em contingência; não é uma correção pequena nem deve
ser executado autonomamente. As decisões de produto acima continuam com o dono.

---

## Referências

- [PRODUCT-V1-SCOPE-BACKLOG](PRODUCT-V1-SCOPE-BACKLOG.md) · [POS-FIRST-CLASS-PLAN](POS-FIRST-CLASS-PLAN.md) · [POS-UITHING-REDESIGN-PLAN](POS-UITHING-REDESIGN-PLAN.md)
- `surfaces/pos-nuxt/` · `shopman/shop/services/pos.py` · `shopman/backstage/projections/pos.py`
