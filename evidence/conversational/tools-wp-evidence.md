# WP04 / WP05 / WP06 / WP08 — fronteira de ferramentas

Base revalidada: `1138c95eee0862630330328cf3bfe2f0b6424796`. Trabalho na branch/worktree exclusivos da implementação; nenhum checkout principal alterado por esta frente. Evidência é sintética/local, PostgreSQL e Redis isolados; não certifica fornecedor, esforço humano, piloto ou rollout.

## Alterações e regressões

| WP / achado | Implementação | Prova selecionada em test_concierge_authority.py |
|---|---|---|
| WP04 D04 | Revisão factual com sessão/rev/identidade/pagamento/notas/total; Message aceita pelo provider oferece token; nova inbound v2 com event_id e aceite inequívoco. Qualificação “sim, mas...” e timestamp anterior à oferta não confirmam. | `test_d04_*`, `test_out_of_order_confirmation_timestamp_cannot_accept_later_revision`, `test_review_includes_notes_before_acceptance_and_rejects_new_note_on_purchase` |
| WP04 D05 | Autoridade antes de receipt; remote_mutations conserva fingerprint, erro definitivo e sucesso. Checkout+receipt locais atômicos; consulta precede sacola; mesma intenção devolve mesmo Order. | `test_d05_receipt_precedes_cart_and_rejects_payload_change` |
| WP04 D06 | Geocoding/validação antecedem escrita; pacote de fulfillment muda sob lock/revisão única. | `test_d06_invalid_fulfillment_preserves_all_fields` |
| WP04 D07 | Parser/unidades de `utils.units`; bool, NaN, infinito, sinal negativo e precisão além SessionItem recusados; quantidade fracionária válida mantém Decimal nos services/projection e string exata no envelope. | `test_d07_*`, `test_quantity_more_precise_than_canonical_storage_is_rejected_without_rounding` |
| WP04 H02 | Lock de Conversation e Session, identidade/fence/base rechecadas; checkout.process_ops compara total sob lock. Callback só roda depois de receipt commitado. | `test_c04_provider_callback_runs_after_local_receipt_and_outside_transaction`, `test_c04_two_postgres_confirmation_workers_create_one_order_and_receipt` (transaction=True, duas conexões/barreira, 1 Order + 1 receipt) |
| WP04 H03 | Listing comercial explícito; preço/revisão final completa comparados antes do commit. Preservada linha canônica de frete do DeliveryFeeModifier. | `test_h03_review_channel_price_and_concurrent_catalog_change_never_buy`, `test_h03_delivery_fee_is_in_review_order_and_payment_once` (review=Order.total_q=Payman.amount_q=780; uma linha fee) |
| WP04 D13 | Renderer determinístico para resultados; sem texto/modelo como fonte de preço/prazo/Pix. Rótulos de escolhas ausentes e pagamento selecionado. | testes engine de preâmbulo inventado; `test_review_renderer_names_missing_choices_and_selected_payment` |
| WP05 D12/H08 | Transferência e mint locais atômicos, com recibo. Liberação e nova reserva dentro da mesma transação; falha restaura origem. Carrinho web existente não é abandonado. Quantidade/contexto preservados e diferença de preço recusa troca. | `test_d12_mint_failure_rolls_back_transfer_and_preserves_slot`, `test_h08_exact_stock_transfer_preserves_all_quantity_and_fulfillment` (saldo=quantidade=10) |
| WP05 D15 | Cardápio não move sacola; pedido exige alvo autorizado explícito; transferência repete receipt/destino sem copiar novamente. `transfer_enabled` false por default. | `test_d15_menu_does_not_move_cart`, `test_d15_transfer_retry_returns_same_destination_without_recopied_cart`; engine testa alvo explícito |
| WP04/05 H11 | Dados completos da Session passam à fachada de checkout; endereço/defaults são os efetivos do Order. | `test_h11_delivery_defaults_and_address_are_saved_from_session` inspeciona Order, Guestman CustomerAddress e CheckoutDefaults reais |
| WP06 D10/H09 | Falha de projection preserva alvo e informa indisponibilidade; payload conserva Actions canônicas. Timeout usa mesma façade de consulta do Storefront antes de projection. | `test_d10_projection_error_preserves_existing_order`; ensaio específico de clock H09 pertence à integração, não foi alegado por este teste |
| WP08 D16 | Disclosure canônico oferecido em Message + novo aceite v2 precedem subscribe; Message liga subscription_ref e disclosure_message_id. A inscrição existente continua fonte única. | `test_d16_disclosure_alone_never_subscribes_and_real_acceptance_links_proof` |

## Achado adicional comprovado

Canal longo válido podia exceder IdempotencyKey.scope no CommitService (`commit:canal:session`). O teste PostgreSQL falhou em `varchar(64)`. Owner core corrigido para digest determinístico somente quando comprimento supera o campo; escopos curtos mantidos. `test_purchase_receipt_scope_accepts_long_commercial_channel` confirma compra e replay únicos. Nenhuma migração/core field novo.

A hipótese inicial de frete ausente de Order.total_q foi **retirada após reconsulta**, sem alteração artificial no core total: `DeliveryFeeModifier._sync_fee_line` já materializa `__DELIVERY_FEE__`; ADR-019 e `test_delivery_fee_charged.py` protegem essa solução madura. `data-schemas.md` tinha texto “nunca vira OrderItem” divergente da implementação/ADR, comunicado à frente responsável pelos documentos.

## Execuções

Runtime: `.venv/bin/python` do checkout original, runner `evidence/conversational/run.py` reposicionando imports para esta worktree. `config.settings_test`; AI/provider reais inertes. PostgreSQL `127.0.0.1:56419`, usuário `concierge_test`; Redis `127.0.0.1:56420`, DBs 4–6. Bancos de teste próprios desta frente.

- `tools-tests.txt`: **109 passed**, sem skips. Engine, autoridade, checkout side effects/customer link/error paths/concurrent checkout, cart context pricing e delivery fee charged. Warning de teardown: banco de teste ainda com 5 conexões; não foi omitido.
- `tools-boundaries-tests.txt`: **50 passed**, sem skips. Autoridade após limites/timestamp + core test_commit_branches + concurrent_checkout. Warning de teardown: 3 conexões ainda abertas no banco de teste; não representa prova de cleanup completo.
- `tools-notes-tests.txt`: resultado separado das duas regressões de observação revisada.
- Ruff dos arquivos de propriedade: passou. Resultados se sobrepõem; **não somar reruns como testes distintos**. Master integração posterior é a prova consolidada do candidato.

## Limites e recuperação

- Validade da revisão: `session_open_and_current_policy`; Session não possui expires_at nesta base. Não foi inventado TTL. Revalida revisão, identidade, total, data/slot e guards canônicos de estoque no commit. Validade comercial temporal adicional permanece G05.
- G05 mantém transferência desligada; cenários de conflito recusam com origem intacta. Mint falho reverte; receipt retomado preserva AccessLink/destino. Token já usado/expirado continua sujeito ao resgate/autenticação canônicos.
- Rollback desta fatia contém admissão/novas mutações; conserva Orders, receitas/receipts, Messages e AccessLinks. Não apaga intenção nem recompra. Esquema expandido/rollback geral pertencem WP10.
- Testes de callbacks e provider fake distinguem retorno local de entrega efetiva. Não houve WhatsApp/ManyChat, pagamento, consentimento, contato, migração ou alteração de produção.
- Nenhuma medição humana foi feita; ganhos de J01/J03/J07/J09/J11/J12 são comportamento local verificado, não métricas de campo. Gates G01–G07 e homologação/piloto/rollout continuam próprios.
