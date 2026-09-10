# Revisão alpha do PDV — 2026-08-28 (resumo para o time)

> Teste E2E de alpha tester contra `pdv.boulangerie.com.br` (amb. alpha DO, pagamentos MOCK): UI real via Playwright + validação de contrato via API com os mesmos endpoints da UI.

## Veredito
Espinha dorsal operacional e segura. Caminho feliz, pagamentos, RBAC/aprovação gerencial, entrega, fiscal, turno e fronteiras (KDS/gestor/central) **passaram**. 6 achados (2 P2, 4 P3), nenhum bloqueante. Ver prompt de correções em `docs/reports/alpha-pos-fix-prompt-2026-08-28.md`.

## Cobertura (destaques)
- **UI (Playwright):** login com senha; provisionamento da estação "PDV principal"; lock PIN (Admin/Fran/Joyce — RBAC correto; crachá hex 12); board de comandas (24 tabs, filtros, F2, "Próxima livre"); grid ~110 produtos/15 coleções com selo ESGOTADO; carrinho (qtd, obs, desconto %); **venda UI completa: 2× Croissant + Café Coado = R$ 38,00 → Pagamento (Dinheiro D/Pix P/Cartão C, numpad, cédulas 2–100, CPF na nota F9, resumo) → Validar → "Venda concluída PDV-260828-D06"** com "A gaveta não abriu: o agente da estação não está rodando." (mensagem calma); tela de sessão/turno (vendas hoje, contas na casa, pedido de troco, movimentos, fechamento cego); KDS UI (estações, filas); Central (8 tiles).
- **API (mesmo contrato da UI):** venda completa, fire→KDS, PIX mock (QR+confirm), split, troco, pagamento a menor (422), excedente não-dinheiro (warning), desconto com aprovação joyce, cancelamento auditado, sangria 2 assinaturas, suprimento, change request (serve com PIN), entrega COD (18 slots), CPF na nota (fiscal_expected), idempotência (mesmo client_request_id → mesmo order_ref), SKU desconhecido → price override → gerente, mover linhas, renomear, limpar, gaveta sem venda, lock de sessão, **fechamento de turno cego + reabertura (shift 15)**.
- **Fronteiras:** pedidos PDV na zona prep do gestor; tickets KDS por comanda fireada (close NÃO encerra ticket — cozinha marca done; `order_ref` do ticket = ref da comanda); central com tiles.

## Achados
| # | Sev | Título | Estado |
|---|---|---|---|
| F1 | P2 | `review_sale` total 0 sem `unit_price_q` + troco errado (carimbo `_list_q` inerte) | a corrigir |
| F2 | P2 | Cancelamento POS dispara `order_cancelled` sem destinatário → alerta `notification_failed` | a corrigir |
| F3 | P3 | SSE: ciclo 200→400→200 na reconexão em estados de gate (autenticado = 200 estável) | a corrigir |
| F4 | P3 | `meta._list_q` ausente nas sessões POS (raiz da F1) | a corrigir |
| F5 | P3 | Aviso de hidratação Vue no console | a corrigir |
| F6 | P3 | ERR_CONNECTION_REFUSED no health do agente local — UI já trata com mensagem calma | validar/silenciar |

## Limpeza feita no alpha
Comandas de teste (1199–1215) unfireadas/limpas; tickets KDS dos tabs de teste marcados done; shift 15 aberto (fundo R$ 200) com `admin`; movimentos de teste (sangria 50, suprimento 30, change request 170) registrados no livro do turno — o time pode mantê-los como histórico de teste ou pedir estorno via Admin.
