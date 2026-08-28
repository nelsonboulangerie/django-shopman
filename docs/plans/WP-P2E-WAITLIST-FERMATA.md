# WP-P2E — Fila de espera com confirmação ativa ("fermata")

> Status: PROPOSTA para revisão do dono · Autor: revisão alpha 28/08/2026 (P2-E, decisão B-4a) · Nenhum código alterado ainda.

## 1. Objetivo
Permitir que um item com **lote planejado** (lista de espera / "previsto para hoje") aceite pedidos **até o limite de vagas conhecido** — nunca além — e, quando a produção materializar o lote, **converter** essas reservas em pedidos reais via **confirmação ativa do cliente** com prazo, liberando as vagas não confirmadas de forma **nunca silenciosa** (cliente e loja). Princípios do dono: (a) não prometer o que não se pode cumprir; (b) primeiro interessado é atendido (FCFS); (c) vagas limitadas pela capacidade conhecida + margem.

## 2. Contexto / problema
- Hoje: item com disponibilidade máx 0 (mesmo com lote planejado) **bloqueia** o Finalizar (has_unavailable → can_checkout=False, "Revise itens indisponíveis") — contradiz a promessa "Envie o pedido para garantir a sua prioridade".
- Exceção que já funciona: linha com **hold planejado ativo** (classify_planned_hold_for_session_sku) passa pelo checkout (evidência: WEB-260828-F43).
- Sessão dedicada (memo P2-E) concluiu: **admitir até o limite é trivial** (capacidade = planejado+esperado − margem − holds); o trabalho real é o **ciclo de vida pós-reserva** — que este WP desenha.

## 3. Mecanismo (compra em duas fases)
1. **Reserva (fermata):** o cliente adiciona item com lote planejado; o hold nasce como **fermata** (expires_at=None, metadata.planned=True, target_date=fornada, reference=session:<key>) — **somente até o limite de vagas** (capacidade − margem − outros holds); além disso, 409 honesto ("esgotado — encomende para a próxima fornada"). Nenhuma cobrança na reserva.
2. **Sinal de materialização:** a fornada sai (signal production_changed / work order finished / stock MAKE) → o serviço waitlist abre a janela de **confirmação** para as primeiras N reservas (N = quantidade materializada disponível para a fila, em ordem FCFS).
3. **Confirmação ativa:** notificação (ManyChat template novo + fallback SMS) + estado no tracking ("aguardando confirmação — responda em X") com countdown; X = Shop.defaults waitlist.confirmation_minutes.
4. **Confirmou:** vira pedido real → **cobrança na confirmação** (Pix: QR gerado na hora + janela de pagamento reusando o payment-timeout; Cartão: autorizar→capturar) → preparo/embalagem → tracking normal.
5. **Expirou / recusou:** hold liberado → **próximo da fila** (FCFS) recebe a confirmação; a vaga também fica visível para a loja expor na gôndola. **Liberação nunca silenciosa**: cliente avisado (hold expirado) + **alerta no Gestor** (OperatorAlert + evento no board) + a loja decide gôndola/próxima fila.

## 4. Capacidade e admissão
- Capacidade conhecida: total_promisable = expected + planned (política planned_ok) — o lote é promissível por modelo.
- Margens de segurança: configuradas (availability margin / Shop.defaults) — a admissão usa capacidade − margem.
- Gate de admissão (a mudança de base): o hold da sessão passa a contar **capacidade planejada** (não só ready_physical) no cálculo de max_orderable/available_qty da linha; admite até capacity_available = planned/expected − margin − other_holds.
- FCFS: a fila é a ordem de criação dos holds fermata (priority por created_at).

## 5. Estados e ciclo de vida
Novo estado de fila no pedido/sessão (Order.data / Session.data):
- waitlist_state: none | fermata | confirming | confirmed
- fermata: reserva aguardando lote (sem prazo, sem cobrança).
- confirming: janela aberta (deadline = now + confirmation_minutes); tracking mostra countdown + botão Confirmar.
- confirmed: cliente confirmou → cobrança → fluxo normal (accepted/preparing/…).
- Expirou: volta a fermata? Não — o hold é **liberado** e a vaga vai ao próximo (ou gôndola); o cliente sai da fila (avisado).
Transições: fermata → confirming (sinal materialização, FCFS, N vagas) · confirming → confirmed (cliente) · confirming → released (timeout/recusa) · released → next (FCFS) + alerta loja.

## 6. Pagamento (decisão recomendada: cobrar na confirmação, para todos)
- Pix: intent criado **na confirmação** (QR gerado) + janela de pagamento (reusar payment_expired); se não pagar, vaga liberada (FCFS) + alertas.
- Cartão: autorizar na confirmação e capturar (ou autorizar na reserva como compromisso — otimização posterior).
- Evita estorno (nada cobrado na reserva); o "confirmou e não pagou" cai no timeout já existente.
- Alternativa descartada por segmentar: só-cartão na fila (perde Pix, maioria no BR).

## 7. Mudanças por camada (áreas de arquivo)
- stockman: packages/stockman/.../services/holds.py (_find_quant_for_hold: admitir até capacidade planejada; metadata planned), availability.py (reserve/check com capacidade planejada), scope/shelflife (janela).
- shop: services/availability.py (classify incluir fermata; reserve), services/stock.py (commit adota fermata p/ hoje), services/waitlist.py (NOVO — máquina de estados: open_window / confirm / release / serve_next), handlers/waitlist.py (NOVO — sinal de materialização → janela; release), adapters/notification_manychat.py + _notification_templates.py (template WAITLIST_AVAILABLE/WAITLIST_RELEASED), services/notification.py (contexto waitlist), projections/order_tracking.py (estado confirming + countdown), backstage projections/order_queue.py (seção fila de espera) + alertas.
- storefront: api/tracking.py (POST waitlist-confirm), presentation/order_tracking.py (copy confirming), surfaces/storefront-nuxt (tracking: countdown + Confirmar; sacola: stepper/copy de fila sem "Só temos 0"; finalizar: notice waitlist com linha max-0).
- config: Shop.defaults[waitlist] = {enabled, confirmation_minutes, release_policy, charge_at: confirmation, capacity_margin_q?}; omotenashi copy (WAITLIST_*); docs/reference/data-schemas.md (chaves novas).

## 8. Contratos de API
- POST /api/v1/orders/{ref}/waitlist-confirm/ (cliente confirma a janela; cria a cobrança).
- GET /api/v1/backstage/orders/ (board) ganha seção waitlist: {ref, items, customer, reserved_at, state, deadline}.
- Sinal de materialização: interno (signal production_changed → handler waitlist) — sem API externa.
- Alerta loja: OperatorAlert (tipo waitlist_released / waitlist_confirm_window) + SSE board.

## 9. Config e copy
- Shop.defaults.waitlist: confirmation_minutes (ex. 15), release_policy (serve_next|shelf), charge_at (confirmation).
- Omotenashi: WAITLIST_CONFIRM_TITLE/MESSAGE/CTA, WAITLIST_RELEASED_CUSTOMER, WAITLIST_RELEASED_STORE, WAITLIST_EXHAUSTED (409 honesto).
- ManyChat: template "{order_ref} — sua fornada saiu! Confirme em {minutes} min: {link}" (com fallback SMS).

## 10. Testes
- Django: test_waitlist_*.py (admissão até limite; over-capacity 409; fermata→confirming FCFS; timeout libera p/ próximo; materialização parcial; pagamento na confirmação + payment-timeout; release nunca silencioso → OperatorAlert), projections cart/checkout (max-0 com fermata → can_checkout=True; sem fermata → Esgotado honesto), stockman holds/preorder_demand.
- Nuxt: tracking (countdown + confirmar), sacola (stepper fila), cartPresentation.
- Guardrails: pausado/stock_only continuam recusando; "esgotado sem plano" continua vermelho.

## 11. Validação no alpha
Login SMS debug (43 99999-9999 / Usar código de teste) → item com lote e máx 0 → sacola com badge fila + Finalizar habilitado → pedido entra em fermata → (com o sinal de fornada) janela de confirmação no tracking com countdown → confirmar → Pix QR → pagar → pedido no Gestor; contraprova: expirar a janela → vaga liberada + alerta no Gestor + próximo da fila notificado.

## 12. Riscos / casos de borda
- Fornada que não sai: holds fermata com target_date passado → sweep libera (sacola); pedido confirmado → cancelamento+estorno (fluxo testado) + OperatorAlert.
- Confirmou e não pagou: payment-timeout libera a vaga + alertas.
- Batch parcial: só as primeiras N confirmam; o resto continua na fermata.
- Concorrência: select_for_update do Quant serializa; admissão até o limite é atômica.
- Canal de notificação: ManyChat primário + SMS fallback; tracking como superfície sempre disponível.
- Preço: congelar na reserva (evita surpresa na confirmação).

## 13. Fases
- F1 (desbloqueia P2-E): admissão até o limite com comportamento atual (auto-cobrança) + beco consertado + stepper/copy de fila. Entrega rápida, baixo risco.
- F2 (o mecanismo): fermata + confirmação ativa + timeout + FCFS + nunca-silencioso (cliente e Gestor) + template ManyChat.
- F3: nuances de pagamento (captura em lote, re-tentativas, relatório de fila).

## 14. Decisões em aberto (dono)
1. Pagamento padrão: cobrar na confirmação para todos (recomendado) — confirma?
2. Liberação expirada: servir próximo da fila automaticamente vs pausar para a loja decidir (gôndola)?
3. Preço congelado na reserva: confirma?
4. F1 primeiro (desbloquear P2-E já) e F2 na sequência — ou F1+F2 juntos?
