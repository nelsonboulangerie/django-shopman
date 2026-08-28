# Revisao Alpha - Gestor de Pedidos (Shopman)
**Data:** 28/08/2026 · **Operador-tester:** admin (Dono) + joyce (Gerente) + cliente loja (QA Alfa Teste) · **Ambiente:** alpha online (gestor/central/kds/pdv/mkt/loja .boulangerie.com.br) via navegador real headless (Playwright/Chromium).

## 1. Matriz executada (tudo via UI)

| Canal/cenario | Resultado |
|---|---|
| Login operador (user+senha) | OK - admin/admin aceito; sessao cross-subdominio |
| Board (Entrada/Preparo/Saida), filtros, busca, tabela/colunas, sort, CSV, imprimir | OK - CSV real; tabela completa; busca por codigo/cliente/item |
| Tempo real (SSE) | OK - pedido iFood chegou em ~23s; loja online em ~35s; contador 'Ao vivo' |
| Confirmacao otimista | OK - auto_confirm na abertura + countdown visivel no card |
| PDV E2E | Comanda -> item -> Enviar (Session->KDS) -> Pagamento Dinheiro -> Order PDV-260828-V22 -> auto_confirm -> kds_dispatch -> KDS Finalizar -> Pronto -> Retirado -> Concluido |
| iFood E2E | IFOOD-260828-G95: chegada real (portal dev) -> Aceitar -> Iniciar preparo -> Marcar pronto -> saida para entrega (Pago online·paid) |
| Loja online E2E | WEB-260828-F43: login SMS (debug OTP) -> sacola (desconto Semana do Pao) -> checkout (Retirada · Hoje · 09h · Pix) -> Enviar pedido -> chegou no Gestor em 35s -> Aceitar -> Pix authorized · aguardando pagamento |
| Loja fechada -> agendamento | OK - available_dates = [hoje, amanha]; slot 'A partir das 09h' = quando abrir (confirmacao do dono) |
| Lista de espera (item planejado) | OK - Croissant/Animalzinho 'Previsto para hoje' ACEITOS no pedido ('Itens em lista de espera: avisamos quando ficarem prontos') |
| Substitutos (item esgotado) | OK p/ esgotado (Tabatiere -> modal 'Que tal um destes no lugar?'); NAO dispara p/ item em waitlist (gap) |
| Caixa: troco, sangria, suprimento, relatorio X/Z | OK - troco net-zero auditado; sangria exige Motivo + autorizacao de gerente; suprimento registrado; leitura X/Z com metodos/operador |
| RBAC/antifraude | OK - Caixa sem adjust_shift (2a assinatura), Gerente sem audit_shift (conta cego), Dono audita; ledger imutavel (select_for_update, unique, parent obrigatorio, lancamento tardio rejeitado) |
| Fronteiras | Hub (8 apps), KDS (ticket + nota propagada), Marketing (sem creds de plataforma), Feeds (4) |

## 2. Achados

| Sev | Achado |
|---|---|
| P1 | Feeds vaza URLs de dev - links para http://127.0.0.1:8000 (Admin, Ver feed, Abrir TV) quebrados no ar (idem djangoPublicBaseUrl). |
| P2 | 400 no /sse/orders a cada load - primeira conexao antes do canal; realtime recupera; ruido no console. |
| P2 | 'Maquininha' e item morto - sem rota/acao na barra do Gestor. |
| P2 (ops) | Alertas: '7 directives falharam em definitivo nos ultimos 60 min' + 'Reconciliacao financeira 27/08: 1 erro' - auditar. |
| P2 (UX) | Item em lista de espera nao recebe sugestao de substitutos (diferente do esgotado); e quando max 0, o checkout bloqueia (Finalizar) apesar da promessa 'Envie o pedido para garantir a sua prioridade' - DECISAO DE PRODUTO: reserva em waitlist deve ser aceita mesmo com 0 disponivel? |
| P3/info | Gaveta/comprovante dependem do agente da estacao (ambiente sem hardware). Suprimento entra 'Sem motivo informado' (sugerir motivo obrigatorio em entradas tambem). |
| Nota | Erro meu de automacao: 'Marcar como Retirado' em card de outro pedido (WHATSAPP-260827-V21, teste) - nao e bug. Comanda #1012 residual de teste - limpar. |

## 3. ANEXO PRE-GO-LIVE - Autonomia iFood pelo Gestor (requisito do dono)

| Operacao iFood | Pelo Gestor? | Evidencia |
|---|---|---|
| Receber pedido (ingest) | SIM | ifood.ingest -> 'Novo' no board (verificado ao vivo) |
| Aceitar / Recusar | SIM | Botoes na ENTRADA |
| Avanco de status (preparo/pronto/saida) | SIM | Iniciar preparo -> Marcar pronto -> Marcar saida p/ entrega |
| Cancelar | SIM | Botao Cancelar no detalhe |
| Reflexo no iFood (API) | A VERIFICAR | Status/cancelamento precisam atualizar a API do iFood - confirmar no portal dev |
| Disponibilidade da loja (open/close iFood) | NAO | Sem UI no Gestor |
| Preco/nome/descricao por canal iFood | NAO | Catalogo do Gestor e SOMENTE LEITURA (linha nao abre editor) |
| Disponibilidade de item iFood | NAO | Coluna iFood e indicador; sem toggle |
| Sync de catalogo iFood | PARCIAL | Via comando sync_catalog_ifood / Admin - nao e ferramenta do operador |

**Recomendacao:** fechar (a) reflexo de status/cancelamento na API iFood, (b) editor de catalogo por canal no Gestor, (c) disponibilidade da loja. ANOTAR no escopo pre-go-live.

## 4. Matriz antifraude (canonica - sugestao de testes)

**Verificado:** sangria exige motivo + 2a assinatura (gerente); troco net-zero auditado; leitura X/Z com metodos e operador; divergencia contado x esperado registrada (sobra R$ 93,95 no turno Z #14); lancamento tardio pos-fechamento rejeitado; duplicidade bloqueada (unique); correcao de contagem exige aprovador; Gerente nao audita; Caixa nao assina excecao; reconciliacao financeira diaria com alerta.

**Propostos (pendentes):** desconto acima do teto (PIN gerente); estorno com parent obrigatorio; item cancelado pos-envio a cozinha; comanda 'fantasma'; multiplos pagamentos na mesma comanda; troco p/ 'cliente fantasma'; movimento fora do expediente; reabertura de turno (impossivel - correcao assinada); registro de 'abrir gaveta sem venda'.

## 5. Pendencias
- **CPF na nota/NFC-e, pagamento misto/com troco completo, desconto com PIN:** fluxos existem na UI, nao completei ponta-a-ponta nesta sessao.
- **Fechamento/encerrar turno completo:** nao executei de proposito (turno compartilhado do alpha).
- **WhatsApp E2E:** exige ManyChat (observado no board apenas).
- **Pix do pedido F43:** aguardando captura (sandbox autorizou) - o fluxo pos-pagamento segue o padrao ja validado.

*Screenshots: .alpha-tmp/s-*.png · logs: .alpha-tmp/*.log*

## 6. UX de cancelamento pelo estabelecimento (testado ao vivo)

**Fluxo (Gestor -> cliente):**
- Gestor: dialogo 'Cancelar pedido - O motivo e enviado ao cliente na notificacao de cancelamento' com motivos prontos (Item indisponivel / Sem um dos ingredientes hoje / Problema tecnico no preparo / Fora do horario) + texto livre. Apos confirmar: status Cancelado, historico carimbado (admin · Aceito -> Cancelado).
- Pagamento: Pix 'captured' -> 'refunded' automaticamente (estorno no sandbox).
- Cliente (tracking /pedido/REF): 'Cancelado - Pedido cancelado.' + acoes Repetir pedido / Ajuda (wa.me pre-preenchido com a ref) + timeline completa (Recebido -> Aceito -> Cancelado).
- Cliente (Conta): badge 'Cancelado' + Acompanhar / Refazer.

**Avaliacao de elegância:**
- BOM: motivo estruturado na notificacao, repetir pedido, ajuda contextual, timeline, auto-estorno.
- LACUNAS: (a) tracking NAO mostra o motivo (cliente que perdeu a notificacao ve so 'Pedido cancelado.'); (b) tracking NAO mostra o reembolso (estorno invisivel, sem 'reembolso em X dias'); (c) notificacao real (ManyChat/WhatsApp) nao verificavel no alpha (telefone fake / integracao possivelmente nao configurada).
- SUGESTAO pre-go-live: tracking exibir motivo + status do reembolso; notificacao conter ambos; validar entrega real da notificacao.

## 7. Conformidade iFood vs doc oficial (developer.ifood.com.br) — ANEXO PRE-GO-LIVE

**Implementado (alinhado ao Order Module v1.0 / Catalog v2.0):**
- OAuth2 client_credentials (ifood_auth).
- Poll GET /order/v1.0/events:polling + ack POST /order/v1.0/events/acknowledgment (batch, so apos handled; falha nao ackada = redelivery).
- Acoes: POST /order/v1.0/orders/{id}/confirm (aceitar), /readyToPickup (pronto), /dispatch (saida), /requestCancellation (cancelar, com cancellationCode), GET /cancellationReasons.
- Catalogo v2.0: upsert de item (id/productId/status AVAILABLE|UNAVAILABLE/price/categoryId) + PATCH /catalog/v2.0/merchants/{mid}/items/status (disponibilidade/retract), 429 rate-limit, sync retract-aware (sync_catalog_ifood).

**GAPS (nao conformes / a validar em homologacao):**
- P1: eventos nao-PLACED (CAN/CON/RDS/DSP/DLU/RFN) sao ACKADOS E IGNORADOS em ifood_events.process_events — cancelamento do cliente no app iFood NAO reflete no Gestor (pedido segue ativo para nos).
- P1: cancellationCode e placeholder config (cancellation_default_code) — mapear motivos do Gestor para a lista oficial e validar.
- P2: disponibilidade da LOJA (open/close iFood) nao implementada.
- P2: catalogo por canal e somente leitura no Gestor (sem editor de preco/nome/descricao/disponibilidade).
- P2: reflexo de status/entrega concluida (DELIVERED/pickup) a validar (dispatch e o ultimo push; iFood completa? confirmar).

## 8. Estorno (Pix E cartao) informado ao cliente

- Estorno implementado: payment.refund (idempotente, por intent, gateway Stripe/EFI) + handler payment_refund (retry/backoff) + cash -> pending_cash_refunds (fluxo de caixa).
- GAP confirmado: o tracking do cliente NAO informa reembolso (nem Pix nem cartao) — apos cancelamento pago, o cliente ve so 'Pedido cancelado.', sem 'reembolso em andamento/concluido'. Corrigir (ver prompt de handoff P2).

## 9. Cancelamento pelo cliente (E2E concluido)

- WEB-260828-E86: cliente cancelou ('Cancelar pedido?' -> 'Sim, cancelar') -> tracking 'Cancelado - Pedido cancelado.' + Repetir pedido/Ajuda; Gestor registrou 'customer.self_cancel · Novo -> Cancelado' e Pix refunded.
- Janela: cancelamento do cliente so enquanto pagamento nao capturado (dialogo avisa; apos captura, sumiu o botao e o caminho e 'Ajuda'/WhatsApp).
- Tracking anonimo: 'Nao encontramos este pedido - entre com seu telefone' (privacidade ok).
