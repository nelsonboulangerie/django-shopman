# PROMPT DE HANDOFF — Execução de correções (revisão alpha · Gestor de Pedidos)

Você é um agente de código com acesso ao repositório Django Shopman. Sua missão: ANALISAR e EXECUTAR as correções abaixo, com testes, seguindo as convenções do repo. Trabalhe com autonomia; onde houver DECISÃO DE PRODUTO marcada, não invente: registre a pergunta para o dono e siga com o que não depende dela.

## 0. Leitura obrigatória (nesta ordem)
1. CLAUDE.md (raiz do repo) — convenções, estrutura, regra de WORKTREE (entre num worktree antes de qualquer escrita!), make test/admin, integridade do Core.
2. docs/reports/2026-08-28-revisao-alpha-gestor-pedidos.md — relatório completo da revisão (evidências, fluxos, achados, anexo iFood e estorno).
3. Para qualquer mudança em JSONFields: docs/reference/data-schemas.md (inventário de chaves).
4. ADRs relevantes: docs/decisions/ (especialmente ADR-003 directives, ADR-016 SSE, ADR-015 pós-prod).
5. Arquivos citados em cada correção (ler ANTES de alterar).

## 1. Ambiente de validação (alpha online)
- Apps: gestor.boulangerie.com.br (Gestor), central, kds, pdv, mkt, alpha.nelsonboulangerie.com.br (loja).
- Operador: usuario 'admin' / senha 'admin' (login em qualquer app de operador).
- Loja (cliente): login por SMS com debug OTP — /entrar -> 'Não consigo usar WhatsApp' -> telefone (ex.: 43 99999-9999) -> 'Receber por SMS' -> botão 'Usar código de teste' (ou codigo exibido na tela 'AMBIENTE DE TESTE'). Nome sugerido: 'QA Alfa Teste'.
- Para criar pedido de teste da loja: adicionar itens com DISPONIBILIDADE (ex.: Água /produto/AG) e finalizar (Retirada · Hoje · slot 09h · Pix). Itens com max 0 entram em lista de espera.
- Para testar iFood: pedido de teste no portal dev do iFood (pedir ao dono apertar o botão) e observar o board em tempo real.
- ⚠️ REGRAS do alpha: NÃO completar fechamento/encerrar turno (turno compartilhado); NÃO cancelar/marcar pedidos que não sejam seus (identificar por 'QA Alfa Teste' ou refs criadas por você); limpar resíduos que criar.
- Screenshots e logs de referência da revisão: .alpha-tmp/s-*.png e .alpha-tmp/*.log (podem ser removidos depois).

## 2. Correções — por prioridade, com critério de aceite

### P1-A · iFood: eventos não-PLACED são ignorados
- Arquivo: shopman/shop/services/ifood_events.py — em process_events, todo code fora de _PLACED_CODES={PLC,PLACED} recebe ACK e é ignorado.
- Impacto (evidência da revisão): cancelamento do cliente no app iFood (evento CAN) NÃO reflete no nosso Order — o Gestor segue tratando o pedido como ativo.
- Correção: tratar CAN (e avaliar CON/RDS/DSP/DLU/RFN) mapeando para o status interno (ex.: CAN -> transition para cancelled com actor system:ifood e motivo), preservando idempotência (claim por event id), sem ackar o que falhar. Consultar a doc oficial: developer.ifood.com.br (Order Module / events).
- Critério de aceite: teste de integração com evento CAN (mock do gateway) prova que o Order transiciona para cancelled e o evento é ackado; evento PLC continua ingerindo; falha não acka.

### P1-B · iFood: códigos de cancelamento
- Arquivo: shopman/shop/services/ifood_callbacks.py — request_cancellation usa cancellation_default_code (placeholder config).
- Correção: mapear os motivos do diálogo do Gestor (Item indisponível no momento / Sem um dos ingredientes hoje / Problema técnico no preparo / Fora do horário de atendimento) para os cancellationCode oficiais (GET /order/v1.0/orders/{id}/cancellationReasons); a lista oficial deve validar os códigos (homologação).
- Critério: tabela de mapeamento motivo->code config-driven, com fallback explícito quando o code não existe; teste unitário do mapeamento.

### P1-C · iFood: disponibilidade da LOJA (open/close)
- Hoje não há controle de abertura/fechamento da loja no iFood pelo Gestor (a disponibilidade de ITEM existe via catalog_projection_ifood; a da LOJA não).
- Correção: avaliar o endpoint oficial (merchant status / operating) e expor no Gestor um toggle de loja aberta/fechada para o iFood, consistente com o business_calendar. Se a API oficial não tiver endpoint, documentar a limitação e o workaround.
- Critério: com mock, alternar aberto/fechado chama o endpoint certo e o estado persiste; a UI do Gestor reflete.

### P1-D · iFood: reflexo de status na API
- Confirmar que Aceitar/Iniciar preparo/Marcar pronto/Saída para entrega/Cancelar disparam os callbacks (confirm, readyToPickup, dispatch, requestCancellation) via handler ifood_status (Directive deduplicada).
- Correção: cobrir com teste de integração mockado do gateway; corrigir o que faltar (ex.: mapeamento de status interno -> ação).
- Critério: cada transição de status de um pedido iFood enfileira o Directive certo, exatamente uma vez.

### P1-E · Feeds vaza URLs de dev
- Página Feeds do Gestor renderiza links http://127.0.0.1:8000 (Admin, Ver feed, Abrir TV).
- Correção: localizar onde a superfície monta esses links (surfaces/*-nuxt + operator-kit; djangoPublicBaseUrl) e usar a base real do deployment via variável de ambiente; nunca expor 127.0.0.1 fora de dev.
- Critério: no alpha, os links de Feeds apontam para o host real e abrem.

### P2-A · UX de cancelamento e estorno (Pix E cartão)
- Arquivo: shopman/shop/projections/order_tracking.py + copy em omotenashi.
- Hoje: o cliente vê apenas 'Pedido cancelado.' — sem o MOTIVO escolhido pelo estabelecimento (cancellation_reason em order.data) e sem o status do REEMBOLSO (payment.refund estorna Pix/cartão, mas o tracking não informa).
- Correção: seção de cancelamento/reembolso no tracking: motivo (quando o estabelecimento cancelou), status do estorno (em andamento/concluído — derivar de PaymentIntent/refund) para Pix e Cartão; copy nova em omotenashi (chaves REEMBOLSO_* / CANCELAMENTO_*); registrar chaves novas em docs/reference/data-schemas.md se entrar em JSON.
- Critério: pedido pago cancelado pelo estabelecimento mostra motivo + 'reembolso concluído'; cancelado antes do pagamento não mostra reembolso; teste de projection.

### P2-B · Notificações falhando no alpha
- Evidência: order_received/payment_requested/payment_confirmed/order_cancelled falharam 5x ('Adapter sms returned False') — o SMS sem provedor falha em silêncio (só aparece no painel de Alertas).
- Correção: garantir que falha de notificação seja controlada, visível e com fallback (console/whatsapp quando configurado); revisar o adapter sms para não retornar False sem log.
- Critério: com adapter sms desconfigurado, a falha loga com contexto e o alerta aparece; com provedor, entrega.

### P2-C · Gestor — /sse/orders 400
- A cada load, /sse/orders dispara 400 + requestfailed (primeira conexão antes do canal pronto).
- Correção: conectar o EventSource após a sessão/canal prontos (ou tratar o 400 como retry silencioso).
- Critério: zero 400 no console ao carregar o board; tempo real continua funcionando.

### P2-D · Gestor — item 'Maquininha' sem ação
- Na barra do Gestor, 'Maquininha' não tem rota/ação (dead item). Remover ou implementar.
- Critério: o item some ou navega para uma tela funcional.

### P2-E · Lista de espera com máx 0 bloqueia checkout (DECISÃO DE PRODUTO)
- Item planejado com 'Máximo disponível: 0' deixa o botão Finalizar desabilitado, contrariando a promessa 'Envie o pedido para garantir a sua prioridade'. Hoje: item com pelo menos 1 unidade planejada é aceito como waitlist; 0 bloqueia.
- DECISÃO DE PRODUTO (perguntar ao dono): aceitar reserva em waitlist mesmo com 0 disponível? Se sim, ajustar a regra de disponibilidade do checkout (cart projection) e o aviso.
- Critério (se aprovado): pedido com item waitlist máx 0 é aceito com o aviso de lista de espera.

### P2-F · Substitutos não disparam para item em lista de espera
- O modal de substitutos dispara para item ESGOTADO, mas não para item em LISTA DE ESPERA. Avaliar disparar também nesse caso (com os mesmos candidatos).
- Critério: sacola com item waitlist oferece substitutos, sem quebrar o fluxo de waitlist.

### P2-G · Alertas do alpha (ops)
- '14 directives falharam em definitivo' + 'Reconciliação financeira 27/08: 1 erro'. Investigar as directives falhadas (Admin -> Diretivas, status 'falhou') e o erro da reconciliação (service financial_reconciliation).
- Critério: relatório do que falhou e por quê; correções pontuais ou registro como dívida conhecida.

### P3 · Higiene
- Limpar no alpha: comanda #1012 (1x Animalzinho, 'A enviar') deixada por teste; remover .alpha-tmp quando não precisar.

## 3. Regras e restrições
- WORKTREE antes de escrever (CLAUDE.md). Nunca commitar no checkout principal.
- Não criar migração para dados contextuais (usar JSONFields); atualizar docs/reference/data-schemas.md.
- Rodar make test (ou alvo específico) e make admin (se tocar Admin/Unfold) antes de concluir.
- Zero resíduos em renames; zero aliases.
- Entregar: um diff por correção + teste + como validar no alpha (passo a passo).
- DECISÕES DE PRODUTO em aberto: devolva a pergunta ao dono, não decida sozinho (ver P2-E e P1-C).
