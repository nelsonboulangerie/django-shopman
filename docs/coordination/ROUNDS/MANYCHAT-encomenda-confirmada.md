# MANYCHAT: encomenda confirmada sai com a data

- **id:** MANYCHAT-encomenda-confirmada
- **branch:** claude/liga-encomenda-confirmada
- **estado:** PR na fila de merge
- **início (UTC):** 2026-10-20

## O que entrou
- `MANYCHAT_FLOW_MAP["order_accepted_preorder"] = "content20261020201824_274658"`
  (`config/settings.py`): o modelo `pedido_encomenda_confirmada` foi aprovado pela Meta em
  20/10/2026 (Utility) e o flow "Aviso: encomenda confirmada" existe na conta.
- `docs/reference/whatsapp-templates-meta.md`: estado do modelo passa de "em análise" a
  "aprovado e ligado"; `pedido_confirmado` fica só com o pedido do dia.

## Prova
- `pytest shopman/shop/tests -k manychat` na worktree: 233 passed, 10 skipped.

## Fora (próxima ordem)
- 4 modelos a submeter (`pontos_fidelidade`, `pedido_entregue_v2`, `fila_vaga_disponivel_v2`,
  `produto_chegou_v2`); `pagamento_falhou` em análise; flows de `pedido_em_preparo` e
  `reembolso_processado`.
