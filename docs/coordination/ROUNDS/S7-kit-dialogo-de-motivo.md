# S7 — Kit: OperatorReasonDialog, no cancelar do PDV e no Gestor; S7b: motivos prontos no balcão (P7)

- **id:** S7
- **sessão:** coordenacao-pedidos-4f89d4 (Claude; subagente em worktree próprio)
- **branch:** claude/kit-dialogo-de-motivo · claude/pdv-motivos-prontos-no-balcao
- **PR:** #1390 · #1392
- **estado final:** mergeados #1390 e #1392
- **início / fim (UTC):** 2026-10-02 19:05 / 2026-10-02 20:40

## O que mudou
S7: `surfaces/operator-kit/app/components/OperatorReasonDialog.vue` + `app/types/reason.ts` (motivos em grupos, "Outros" exige texto, confirmar destrutivo, descarte perguntado dentro do diálogo; o `window.confirm` saiu do diálogo de motivo do Gestor). `orders-nuxt/.../OrderReasonDialog.vue` e `pos-nuxt/.../PosPreorderCancelDialog.vue` viraram adaptadores finos. S7b: `shopman/backstage/projections/order_queue.py:565` deixa de zerar `cancellation_presets` no balcão; o PDV lê `_cancellation_presets()` (a mesma do Gestor, fonte `Shop.cancellation_presets`); `[ref].vue` passa a lista; `data-schemas.md` atualizado.

## Prova
Kit 7 testes novos; Gestor 19 mantidos (os 2 de descarte reprovam com o componente antigo); PDV 3 reprovam com o antigo; Django `test_order_detail_context.py::test_o_cancelar_do_balcao_le_os_mesmos_motivos_prontos_do_gestor` reprova sem / passa com. Kit 1036, Gestor 496, PDV 1480 passed; CI obrigatória verde nos dois.

## O que ficou de fora
Os outros `window.confirm` do Gestor (página do pedido, catálogo, feeds, canais) seguem: fora do escopo. Os chips de motivo seguem com `aria-pressed` (o kit não tem peça de escolha única em linha).

## Perguntas ao dono
nada

## Armadilhas novas
nada

## Próximo passo
nada
