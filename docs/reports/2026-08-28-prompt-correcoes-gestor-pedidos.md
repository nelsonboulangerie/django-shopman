# PROMPT DE HANDOFF — Execução de correções (revisão alpha · Gestor de Pedidos) · v2 (pós-ensaio cego)

Você é um agente de código com acesso ao repositório Django Shopman. Sua missão: ANALISAR e EXECUTAR as correções abaixo, com testes, seguindo as convenções do repo. Trabalhe com autonomia; onde houver DECISÃO DE PRODUTO marcada, não invente: registre a pergunta para o dono e siga com o que não depende dela.

## 0. Leitura obrigatória (nesta ordem)
1. CLAUDE.md (raiz do repo) — convenções, estrutura, regra de WORKTREE (entre num worktree antes de qualquer escrita!), make test/admin, integridade do Core.
2. docs/reports/2026-08-28-revisao-alpha-gestor-pedidos.md — relatório completo da revisão (evidências, fluxos, achados, anexo iFood/estorno, §10 deploy DOC-obsoleta).
3. Para mudanças em JSONFields: docs/reference/data-schemas.md.
4. ADRs: docs/decisions/ (ADR-003 directives, ADR-016 SSE, ADR-015 pós-prod).
5. Arquivos citados em cada correção (ler ANTES de alterar).

## 1. Ambiente de validação (alpha online)
- Apps: gestor.boulangerie.com.br (Gestor), central, kds, pdv, mkt, alpha.nelsonboulangerie.com.br (loja).
- Operador: 'admin' / 'admin' (qualquer app de operador). Loja/cliente: login SMS com debug OTP — /entrar -> 'Não consigo usar WhatsApp' -> telefone (43 99999-9999) -> 'Receber por SMS' -> botão 'Usar código de teste'. Nome: 'QA Alfa Teste'.
- Criar pedido de teste: adicionar itens disponíveis (ex.: Água /produto/AG) e finalizar (Retirada · Hoje · slot 09h · Pix). iFood: pedido de teste no portal dev (pedir ao dono).
- REGRAS do alpha: NÃO completar fechamento/encerrar turno (turno compartilhado); NÃO cancelar/marcar pedidos alheios (identificar 'QA Alfa Teste'/refs criadas por você); limpar resíduos que criar.
- Harness de validação da revisão: .alpha-tmp/mega.mjs captura response/requestfailed (status>=400) e console — útil para o critério do P2-C (recarregar 5x e exigir ZERO 400).
- Testes das superfícies: vitest por app — 'npm test' em surfaces/orders-nuxt e surfaces/operator-kit (e npm run test:component para componente).

## 2. REGRAS DE EXECUÇÃO (críticas)
- MERGE EM MAIN = DEPLOY NO ALPHA (workflow deploy-images.yml: build no Actions -> imagens DOCR -> App Platform deploy_on_push por tag). Nenhum merge sem: revisão do dono + gates de CI (runtime-gate, surfaces-gate, omotenashi-gate, alpha-smoke).
- WORKTREE antes de qualquer escrita; git add só por arquivo nomeado; sem stash; sem checkout/reset no principal (hook guard-paralelo).
- NUNCA aplicar spec/doctl no App Platform vivo a partir do arquivo do repo: .do/*.yaml é espelho de referência, não fonte aplicada; para mudar env/spec: doctl apps spec get <app> -> editar -> doctl apps update (preserva secrets). Sem credenciais DO, devolver ao dono.
- Rodar make test (alvo) e make admin (se tocar Admin/Unfold) antes de concluir. Zero resíduos em renames; zero aliases. Entregar: um diff por correção + teste + como validar no alpha.

## 3. Correções — prioridade, arquivos exatos, critério de aceite

### P1-A · iFood: eventos não-PLACED ignorados
- Arquivo: shopman/shop/services/ifood_events.py — process_events acka e ignora code fora de _PLACED_CODES={PLC,PLACED}.
- Impacto: cancelamento do cliente no app iFood (CAN) não reflete no nosso Order.
- Correção: tratar CAN (avaliar CON/RDS/DSP/DLU/RFN) mapeando para status interno (CAN -> cancelled, actor system:ifood, motivo), preservando idempotência (claim por event id), sem ackar falhas. Doc oficial: developer.ifood.com.br.
- Critério: teste de integração com evento CAN (mock do gateway) prova transição para cancelled + ack; PLC continua ingerindo; falha não acka.

### P1-B · iFood: códigos de cancelamento
- Arquivo: shopman/shop/services/ifood_callbacks.py — request_cancellation usa cancellation_default_code (placeholder).
- Correção: mapear motivos do diálogo do Gestor (Item indisponível / Sem um dos ingredientes / Problema técnico / Fora do horário) para os cancellationCode oficiais (GET /order/v1.0/orders/{id}/cancellationReasons); validar em homologação.
- Critério: tabela motivo->code config-driven com fallback; teste unitário do mapeamento.

### P1-C · iFood: disponibilidade da LOJA (open/close) — DECISÃO DE PRODUTO
- Sem controle de abertura/fechamento da loja iFood no Gestor. Avaliar endpoint oficial (merchant status/operating) e expor toggle consistente com business_calendar; se não existir endpoint, documentar limitação/workaround. DECISÃO: devolver ao dono o aceite de escopo.
- Critério (se aprovado): toggle persiste e chama o endpoint certo (mock); UI reflete.

### P1-D · iFood: reflexo de status na API
- Confirmar que Aceitar/Iniciar/Marcar pronto/Saída/Cancelar disparam confirm/readyToPickup/dispatch/requestCancellation via handler ifood_status (Directive deduplicada).
- Correção: teste de integração mockado do gateway; corrigir mapeamentos faltantes.
- Critério: cada transição enfileira o Directive certo, exatamente uma vez.

### P1-E · Feeds vaza URLs de dev — NÃO é bug de código; é ENV AUSENTE NO SPEC DE DEPLOY
- Diagnóstico confirmado (ensaio cego): surfaces/orders-nuxt/nuxt.config.ts:12-16 usa djangoPublicBaseUrl com fallback http://127.0.0.1:8000; feeds.vue:15-16 e catalog.vue:208 montam os links com ele — código CORRETO. Causa raiz: .do/app.alpha-subdomains.yaml — o serviço orders-nuxt (envs ~557-573) é o ÚNICO dos operadores SEM 'NUXT_PUBLIC_DJANGO_BASE_URL' (os 7 irmãos pos/kds/production/purchase/hub/marketing/bi têm RUN_AND_BUILD_TIME=https://api.boulangerie.com.br).
- Correção PRIMÁRIA (deploy, não diff): adicionar ao serviço orders-nuxt no spec: env NUXT_PUBLIC_DJANGO_BASE_URL scope RUN_AND_BUILD_TIME value https://api.boulangerie.com.br (espelhar irmãos). Procedimento: doctl apps spec get -> merge env -> doctl apps update (NUNCA spec do repo). ENV RUN_AND_BUILD_TIME é assada no bundle client -> exige REBUILD da imagem orders (redeploy), não basta env runtime.
- Defesa em profundidade (opcional, código): guard em feeds.vue/catalog.vue — se djangoPublicBaseUrl resolver para host local fora de dev, renderizar link relativo; e/ou nuxt.config.ts manter fallback localhost só quando NODE_ENV !== 'production'.
- Critério: no alpha, Admin/TV/feed abrem https://api.boulangerie.com.br/... com 200; teste de config: script/CI que valida que todo serviço de operador nos .do/*.yaml declara NUXT_PUBLIC_DJANGO_BASE_URL (hoje falha em orders-nuxt). Sem credenciais DO, aplicar env = devolver ao dono (B-1).

### P2-A · UX de cancelamento e estorno (Pix E cartão)
- Arquivo: shopman/shop/projections/order_tracking.py + copy omotenashi.
- Hoje o cliente vê só 'Pedido cancelado.' — sem motivo (cancellation_reason em order.data) e sem status de reembolso (payment.refund estorna, tracking não informa).
- Correção: seção de cancelamento/reembolso: motivo (quando o estabelecimento cancelou) + status do estorno (em andamento/concluído, derivado de PaymentIntent/refund) para Pix e Cartão; chaves REEMBOLSO_*/CANCELAMENTO_* em omotenashi; registrar chaves novas em docs/reference/data-schemas.md se entrar em JSON.
- Critério: pedido pago cancelado mostra motivo + 'reembolso concluído'; cancelado antes do pagamento não mostra reembolso; teste de projection.

### P2-B · Notificações falhando no alpha
- Evidência: order_received/payment_requested/payment_confirmed/order_cancelled falharam 5x ('Adapter sms returned False').
- Correção: falha controlada/visível com fallback (console/whatsapp quando configurado); adapter sms não retornar False sem log.
- Critério: sem provedor, falha loga com contexto + alerta; com provedor, entrega.

### P2-C · 400 em /sse/orders a cada load — mecanismo identificado
- Mecanismo (confirmado no ensaio): a única fonte de HTTP 400 na view clássica do django-eventstream 5.3.3 é ResumeNotAllowedError com 'Last-Event-ID: error' ('Can't resume session after stream-error'); o BFF surfaces/operator-kit/server/utils/eventStream.ts:43-44 repassa last-event-id verbatim; o client conecta no onMounted (surfaces/orders-nuxt/app/composables/useOrdersBoard.ts:51-68 e useOrderEvents.ts:10-32). Evidência: .alpha-tmp/mega.log '400 /sse/orders' + 'FAILED /sse/orders' a cada load; realtime recupera.
- Correção PRIMÁRIA (seam, corrige todas as superfícies): em eventStream.ts, NÃO repassar last-event-id === 'error' (ou, se upstream 400 com lastEventId, refazer o fetch sem o header). Fix SECUNDÁRIO (client): conectar EventSource só após o primeiro fetch 2xx do board (watch pending/error, once).
- Critério: estender surfaces/operator-kit/tests/eventStream.test.ts (last-event-id 'error' não é repassado; upstream 400 -> retry sem header); npm test em operator-kit e orders-nuxt; no alpha, recarregar 5x com ZERO 400/requestfailed (harness mega.mjs) e pedido chega <10s sem F5.

### P2-D · Item 'Maquininha' — DECISÃO DE PRODUTO (não é item morto)
- Diagnóstico: 'Maquininha' na barra é o CHIP DELIBERADO de custódia de aparelho (surfaces/orders-nuxt/app/pages/index.vue:287-294, data-equipment-out; 'na rua com o pedido DLV-NARUA · João Oliveira'; label de EQUIPMENT_LABELS em shopman/backstage/projections/order_queue.py:746) — informativo de propósito (quadro responde onde está a maquininha). Não é item morto; 'remover' apaga funcionalidade deliberada.
- DECISÃO: implementar (tornar o chip clicável -> /<order_ref> do detalhe, que já tem histórico de custódia) vs remover. Recomendação do ensaio: IMPLEMENTAR (navegar ao pedido). Devolver ao dono.
- Critério (se aprovado): chip clicável abre o detalhe DLV-NARUA; volta ao board ok; sem chip quando equipment_out vazio.

### P2-E · Lista de espera com máx 0 bloqueia checkout — DECISÃO DE PRODUTO
- Item planejado com 'Máximo disponível: 0' deixa Finalizar desabilitado, contrariando 'Envie o pedido para garantir a sua prioridade'. Hoje: ≥1 unidade planejada é aceita como waitlist; 0 bloqueia.
- DECISÃO ao dono: aceitar reserva em waitlist com 0 disponível? Se sim, ajustar regra de disponibilidade do checkout (cart projection) e aviso.
- Critério (se aprovado): pedido com waitlist máx 0 é aceito com aviso de lista de espera.

### P2-F · Substitutos não disparam para item em lista de espera
- Modal de substitutos dispara para item ESGOTADO, não para item em LISTA DE ESPERA. Avaliar disparar também (mesmos candidatos), sem quebrar waitlist.
- Critério: sacola com item waitlist oferece substitutos.

### P2-G · Alertas do alpha (ops)
- '14 directives falharam em definitivo' + 'Reconciliação financeira 27/08: 1 erro'. Investigar directives falhadas (Admin -> Diretivas) e o erro da reconciliação (services/financial_reconciliation.py).
- Critério: relatório do que falhou e por quê; correções pontuais ou dívida registrada.

### P2-H · DOC OBSOLETA — modelo de deploy DO
- docs/guides/deploy-digitalocean.md (~49-55) instrui redeploy via doctl apps create-deployment e blueprint git.repo_clone_url — OBSOLETO. Atual: imagens DOCR + deploy_on_push (deploy-images.yml); merge em main = deploy no alpha.
- Correção: reescrever o trecho de deploy/rollout para o modelo de imagens, mantendo os avisos de nunca sobrescrever spec vivo/secrets (doctl apps update --spec) e de preservar secrets em mudança de topologia (doctl apps spec get). Conferir .do/app.alpha-subdomains.yaml (CONFIRMADO: image DOCR em todos os componentes).
- Critério: doc sem create-deployment como caminho normal; descreve workflow + tags + deploy_on_push e os avisos de secrets.

### P3 · Higiene
- Limpar no alpha: comanda #1012 (1x Animalzinho, 'A enviar'); remover .alpha-tmp quando não precisar.

## 4. Decisões de produto em aberto (devolver ao dono — não decidir sozinho)
- B-1 (P1-E): aplicar env nova no App Platform vivo — quem aplica (executor com creds DO ou dono)? confirmar base pública correta (https://api.boulangerie.com.br).
- B-2 (P2-C): fix só no seam (retry silencioso) vs deferir no client (Ao vivo demora um instante) — recomendação: seam + mínimo no client; escopo: operator-kit resolve kds/pos também.
- B-3 (P2-D): navegar ao pedido vs remover — recomendação: navegar.
- B-4: P2-E (waitlist máx 0) e P1-C (open/close loja iFood) — aceite de escopo.

## 5. DECISOES DO DONO (28/08 — resolvidas, prompt v3)

- B-1 (P1-E): APROVADO — base publica confirmada https://api.boulangerie.com.br; aplicar env NUXT_PUBLIC_DJANGO_BASE_URL (RUN_AND_BUILD_TIME) no servico orders-nuxt + rebuild da imagem orders; procedimento doctl apps spec get -> update (preserva secrets). Aplicacao pratica pode exigir o dono (credenciais DO).
- B-2 (P2-C): APROVADO recomendacao — fix no seam (operator-kit eventStream.ts: nao repassar last-event-id == error) + minimo no client (deferir connectSse ate primeiro fetch 2xx).
- B-3 (P2-D): APROVADO — implementar navegacao do chip Maquininha para /<order_ref> (nao remover).
- B-4a (P2-E waitlist max 0): PENDENTE — estudar em sessao dedicada; NAO implementar agora (manter comportamento atual + anotar).
- B-4b (P1-C iFood open/close loja): APROVADO — implementar disponibilidade da loja iFood no Gestor (escopo).

## 6. CORRECAO POS-ENSAIO (P1-E)
- O spec committed JA TEM NUXT_PUBLIC_DJANGO_BASE_URL para orders-nuxt (.do/app.alpha-subdomains.yaml linha 605); quem falta e bi-nuxt (avaliar se precisa).
- P1-E real = aplicar a env no App Platform VIVO + rebuild da imagem orders (spec/build antigo no alpha) — B-1 aprovado; executar com o dono (creds DO) via doctl apps spec get -> update.
- No repo: adicionar validacao de config (todo servico de operador nos .do/*.yaml declara NUXT_PUBLIC_DJANGO_BASE_URL) + guard opcional em nuxt.config.ts. NAO adicionar a env de novo em orders-nuxt (ja existe).
