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

## 10. DOC-OBSOLETA: modelo de deploy DO mudou (anotado para correcao)

- OBSOLETO: docs/guides/deploy-digitalocean.md (linhas ~49-55) instrui redeploy via doctl apps create-deployment e descreve blueprint com git.repo_clone_url.
- ATUAL: .github/workflows/deploy-images.yml publica imagens no DOCR (registry.digitalocean.com/nelsonboulangerie/shopman) e o App Platform usa deploy_on_push por tag — publicar a tag E o deploy; merge em main = deploy automatico no alpha (build seletivo, concurrency sem cancel).
- IMPLICACAO: corrigir o trecho do doc (instrucao de deploy) mantendo os avisos validos (nunca doctl apps update --spec so para subir codigo — sobrescreve spec vivo/secrets; para topologia, partir de doctl apps spec get preservando secrets).
- IMPLICACAO DE RISCO: merge em main redeploya o alpha automaticamente — revisao de PR + gates de CI (runtime-gate, surfaces-gate, omotenashi-gate, alpha-smoke) sao a protecao.

- CONFIRMACAO (28/08): .do/app.alpha-subdomains.yaml usa image: {registry_type: DOCR, repository: shopman} em TODOS os componentes (web + surfaces Nuxt) — sem blocos git; o modelo de imagens com deploy_on_push e o vigente.

## 11. Decisoes do dono + ensaio cego do prompt

- Ensaio cego (subagente lendo so o prompt): veredito quase, falta X — corrigiu P1-E (env ausente no spec, nao bug de codigo), P2-C (mecanismo ResumeNotAllowedError / last-event-id error), P2-D (chip deliberado de custodia, decisao) e inseriu a regra merge=deploy na execucao. Prompt v2/v3 incorpora tudo.
- Decisoes (28/08): B-1 P1-E aprovado (base api.boulangerie.com.br); B-2 P2-C aprovado (seam); B-3 P2-D aprovado (navegar ao pedido); B-4a P2-E PENDENTE (sessao dedicada, nao implementar); B-4b P1-C aprovado (open/close loja iFood no Gestor).

## 12. Correcao pos-ensaio: P1-E (env) — diagnostico refinado

- Spec committed (.do/app.alpha-subdomains.yaml, HEAD b462dcf7f): orders-nuxt JA TEM NUXT_PUBLIC_DJANGO_BASE_URL (RUN_AND_BUILD_TIME, linha 605). Quem NAO tem e bi-nuxt (bloco 783+; avaliar se BI precisa).
- Conclusao: o alpha vivo mostra 127.0.0.1 porque roda SPEC/BUILD ANTIGO (env no repo, nao aplicada no DO / imagem orders buildada antes). Acao real: aplicar a env no App Platform vivo + REBUILD da imagem orders (B-1 aprovado). No repo: validacao de config + guard opcional. O diff do ensaio (adicionar a env em orders-nuxt) NAO e necessario — ja existe.

## 13. Status de execucao (branch fix/alpha-rev-2026-08-28, sincronizada com main 97c7a62cd)

- Sincronizacao: rebase em origin/main sem conflitos; uniao preservada com o #381 (verificado: pix_pending_note, pix_auto_update_note, fulfillment_wait_kind/until, 25 chaves TRACKING_PAYMENT_PIX_* vivas).
- Commitado (5 commits sobre main): P2-C (seam SSE + client + teste 9/9), P2-D (chip maquininha navegavel), P2-H (doc deploy por imagens), P2-A (motivo + reembolso no tracking, Pix E cartao), P1-A (evento CAN do iFood refletido no Order, actor system:ifood, guard anti-eco, 3 testes).
- LICAO (perda silenciosa): os campos cancellation_reason/refund_status_key do TrackingData sumiram no caminho commit/rebase (construcao ok, declaracao nao) — o alerta do coordenador estava certo; restaurado + serializer mirror + fix de tipografia (font-medium 500 banido -> font-semibold).
- Validacao: pytest storefront 1244 passed/3 skipped; test_ifood_direct 44 passed; vitest storefront 396/396 (5 suites de componente nao carregam no worktree por erro de mock-transform do $fetch — ambientais; CI confirma).
- Pendente: lote 3 (P1-B codigos de cancelamento iFood, P1-D reflexo de status, P2-B notificacoes, P2-F substitutos waitlist); P1-E aplicar env no DO vivo + rebuild (dono); P2-E sessao dedicada.

## 14. Lote 3 (parcial) — P1-B/P1-D commitados; P2-B e P2-F verificados

- P1-B: resolve_cancellation_code (motivo do Gestor -> cancellationCode, config-driven SHOPMAN_IFOOD[cancellation_reason_codes], fallback para cancellation_default_code; default vazio ate homologacao) + send_for_status usa o code do motivo. Testes: mapping + fallback + uso no requestCancellation.
- P1-D: testes travam o reflexo — action_for_status (accepted->confirm, ready->readyToPickup, dispatched->dispatch, cancelled->requestCancellation) e o handler enfileira o callback de aceite.
- P2-B (verificado, sem mudanca): falha controlada e visivel (adapter sms loga Comtele nao configurado; handler retry/backoff e escala OperatorAlert em 5 tentativas; painel de Alertas expoe; fallback console em DEBUG); template order_cancelled inclui {reason_note} e o lifecycle passa reason=note — o motivo chega ao cliente quando ha provedor.
- P2-F (parcial): SubstituteSheet ja trata is_planned (pre-reserva) e substitutos (servidor-driven via 409); o gap observado no alpha (checkout com item waitlist max 0 sem substitutos) e o caso do Finalizar bloqueado — amarrado a decisao P2-E (sessao dedicada).
