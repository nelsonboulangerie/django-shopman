# Inventário estático de writers — laboratório de Pedidos

Candidatos encontrados por AST em services/handlers/lifecycle. Não prova ausência de outros writers:
aliases, QuerySet.update, core e chamadas indiretas exigem inspeção adicional. Lock aqui significa
apenas ocorrência textual dentro da função, não cobertura da escrita nem ordem global comprovada.

| Fonte | Função | Saves (linhas) | select_for_update (linhas) |
|---|---|---|---|
| shopman/shop/services/waitlist.py | _write_state | 390 | não observado na função |
| shopman/shop/services/pos.py | reopen_recent_order_for_correction | 1682 | não observado na função |
| shopman/shop/services/pos.py | _reconcile_order_payment_to_total | 2754 | não observado na função |
| shopman/shop/services/pos.py | _mark_tab_committed | 3339 | não observado na função |
| shopman/shop/services/courier.py | _save_block | 59 | não observado na função |
| shopman/shop/services/cancellation.py | cancel | 65 | não observado na função |
| shopman/shop/services/fulfillment.py | create | 38 | não observado na função |
| shopman/shop/services/stock.py | hold | 237 | não observado na função |
| shopman/shop/services/stock.py | revert_fulfilled | 361 | não observado na função |
| shopman/shop/services/pix_confirmation.py | _record_pix_receipt | 520 | 504 |
| shopman/shop/services/pix_confirmation.py | _claim_paid_dispatch | 542 | 533 |
| shopman/shop/services/customer.py | ensure | 80 | não observado na função |
| shopman/shop/services/operator_orders.py | advance_order | 279 | não observado na função |
| shopman/shop/services/operator_orders.py | mark_equipment_returned | 392 | não observado na função |
| shopman/shop/services/operator_orders.py | settle_delivery_cash | 674 | não observado na função |
| shopman/shop/services/operator_orders.py | save_kitchen_note | 720 | não observado na função |
| shopman/shop/services/operator_orders.py | assign_order | 738 | não observado na função |
| shopman/shop/services/operator_orders.py | unassign_order | 752 | não observado na função |
| shopman/shop/services/payment.py | _persist_intent | 218 | não observado na função |
| shopman/shop/services/payment.py | _persist_tender_intents | 394 | não observado na função |
| shopman/shop/services/payment.py | capture | 426 | não observado na função |
| shopman/shop/services/payment.py | settle_from_gateway | 1193 | 1183 |
| shopman/shop/services/payment.py | _stamp_gateway_check | 1242 | não observado na função |
| shopman/shop/services/payment.py | mock_confirm | 1382 | não observado na função |
| shopman/shop/services/payment.py | _ensure_payment_idempotency_key | 1448 | não observado na função |
| shopman/shop/services/payment.py | _record_initiate_error | 1574 | não observado na função |
| shopman/shop/services/production.py | _merge_committed_order_links | 1084 | 1074 |
| shopman/shop/handlers/returns.py | initiate_return | 88 | 43 |
| shopman/shop/handlers/returns.py | handle | 199 | não observado na função |
| shopman/shop/handlers/production_order_sync.py | _reconcile_pending_links | 245 | 173,190 |
| shopman/shop/handlers/production_order_sync.py | reconcile_production_order_links | 437 | 297,298 |
| shopman/shop/handlers/production_order_sync.py | _unlink_voided_work_order | 620 | 614,618 |
| shopman/shop/handlers/production_order_sync.py | _unlink_inactive_order | 649 | 635,634 |
| shopman/shop/handlers/production_order_sync.py | _resolve_finished_work_order | 673 | 658,660 |
| shopman/shop/handlers/fiscal.py | _send_receipt_email | 161 | 157 |
| shopman/shop/handlers/fiscal.py | _record | 224 | 213 |
| shopman/shop/handlers/fiscal.py | handle | 258 | não observado na função |
| shopman/shop/lifecycle.py | _mark_phase_complete | 325 | não observado na função |
| shopman/shop/lifecycle.py | _record_coupon_use | 349 | não observado na função |
| shopman/shop/lifecycle.py | _release_coupon_use | 371 | não observado na função |
| shopman/shop/lifecycle.py | _record_availability_decision | 1051 | não observado na função |
