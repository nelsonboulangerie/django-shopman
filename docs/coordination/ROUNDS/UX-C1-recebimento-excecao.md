# UX-C1 — Recebimento por exceção, validade incontornável

- **id:** UX-C1
- **sessão:** reforma SUITE-UX, onda de Compras (Claude, subagente em worktree próprio). Dono: "recebimento por exceção, sim; validade é incontornável" (03/10)
- **branch:** claude/ux-c1-recebimento-excecao
- **PR:** #1409
- **estado:** pronto, na fila (auto-merge)
- **início / fim (UTC):** 2026-10-03 / 2026-10-03

## Objetivo
Na conferência do recebimento (Compras › Receber), as linhas que batem com a nota entram sem o
"ok" linha a linha, mediante um ato físico ("Contei os volumes N de N"). Validade continua pedida
para todo perecível, uma linha por vez, com atalhos. Só o item que não bate pede atenção (nota ×
chegou × diferença, motivo). "Confirmar entrada" nunca fica morto. Plano: SUITE-UX-FUNCTION-PLAN
§4.2, §5.1 ("Recebimento por exceção"), §10; fichas C10 a C16.

## O que mudou
- **Servidor** (`shopman/backstage/services/purchase.py`): a validação que exigia o ok por linha
  (`receipt_line_unchecked` dentro de `_resolve_receipt_line`) saiu de lá e virou
  `_receipt_attestation`, depois de todas as linhas resolvidas. Linha sem ok só entra se **bate com
  a nota** (quantidade = `invoicePurchaseQty`, valor = `invoiceTotal`, embalagem confere com a
  sugestão da nota, sem ocorrência) **e** a entrada traz `volumes.counted` igual ao esperado
  (`receipt_expected_volumes`: `qVol` da nota, ou soma das embalagens; a diferença das linhas de
  embalagem desconta). Códigos novos: `receipt_volumes_required`, `receipt_volumes_mismatch`,
  `receipt_difference_reason_required` (toda diferença nota × chegou pede motivo, conferida ou não).
  `expiry_required` e `conversion_required` intocados. Entrada sem NF continua com ok por linha.
- **Auditoria**: cada `Move` BUY grava `purchase_line_attested_by` (`line_check`/`volume_count`) e
  `purchase_volumes_counted`/`purchase_volumes_expected`; quem contou é o `Move.user`
  (`docs/reference/data-schemas.md`).
- **Leitor de NF-e** (`shop/adapters/purchase_invoice_nfe.py`): `invoicePurchaseQty` por linha e
  `invoiceVolumes` (soma de `transp/vol/qVol`) no rascunho; projection repassa.
- **Projection**: `Material.lastDeliveryExpiry` (validade do lote da última entrega, só enquanto
  não venceu). "Típica: +N dias" sai de `shelfLifeDays` do insumo. Nada inventado: sem histórico e
  sem vida útil, nenhum atalho.
- **purchase-nuxt**: `ReceiptExceptionFlow.vue` (tudo bate · contei os volumes com stepper de 48px ·
  falta só a validade k de n, um perecível por vez, atalhos + "Outra data" com o
  `OperatorDayPicker` do kit, "Trocar" · para resolver), `ReceiptDifference.vue` na gaveta (nota ×
  chegou × diferença, motivo Faltou/Avariado/Trocado/Outro com `UiRadioGroup` do kit, consequência
  escrita). Presentation: `receiptExceptionView`, `receiptExpectedVolumes`,
  `receiptLineMatchesInvoice`, `receiptExpiryShortcuts`, `receiptVolumesStep`; estado "Bate com a
  nota" na lista; o selo do "Confirmar entrada" aponta para a contagem (`data-receipt-anchor="volumes"`).

## Prova
- `pytest` de 22 arquivos de compras/recebimento (backstage + shop): `277 passed, 1 skipped`.
  Novo `test_purchase_recebimento_por_excecao.py` (12): bate tudo + volumes → entra; volumes
  errados → `receipt_volumes_mismatch`; sem contagem → bloqueia; perecível sem validade →
  `expiry_required`; diferença sem motivo → bloqueia; com motivo + ok → entra e a contagem desconta;
  valor/embalagem divergente → pede ok; sem NF → pede ok; granel só com `qVol`; atalho da última
  entrega some quando vence. Adapter: 3 testes novos (`42 passed`).
- `purchase-nuxt`: vitest `121 passed` (17 novos: presentation + componente), `nuxi typecheck` e
  `eslint` limpos. Kit: `1049 passed` (travas de vocabulário inclusas). `test_vocabulario_de_tela.py`:
  `2231 passed`. `ruff` limpo.

## O que ficou de fora
- **Bipar cada volume**: a tela de receber só lê o QR/código da NF, não o código de cada volume
  casado com o item. Só o stepper.
- **"Ler da embalagem"** (câmera lendo data e lote, GS1-128): não existe leitor de data/lote; próximo passo.
- **"Preços dentro do último pago"**: "bate" usa o valor da própria nota; comparar com o último custo
  pago pede uma tolerância que é decisão do dono.
- **Rascunho da conferência no servidor**: não existe hoje (o recibo vive no estado da tela); nada
  regrediu, mas recarregar ainda perde a conferência.
- **"Devolver só este item"** (recusa parcial): não existe hoje; continua a devolução da entrega inteira.
- **Barra de confirmar fixa no rodapé do celular**: o "Confirmar entrada" segue no painel
  "Conferência", que no celular fica abaixo da lista.
- Não verificado em navegador real (só testes de componente).

## Perguntas ao dono
nada bloqueante; a tolerância de preço contra o último pago fica para quando ele quiser.

## Próximo passo
Leitor de data/lote pela câmera ("Ler da embalagem"); rascunho da conferência no servidor (L7).
