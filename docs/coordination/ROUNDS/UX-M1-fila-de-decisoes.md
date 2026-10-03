# UX-M1 — Marketing: a casa do app vira a fila de decisões por prazo

- **id:** UX-M1
- **sessão:** executor UX-M1 (Claude, subagente da coordenação SUITE-UX, onda 1)
- **branch:** claude/ux-m1-fila-de-decisoes
- **PR:** #1420
- **estado final:** PR aberto #1420, auto-merge DESLIGADO pela coordenação até o e2e de a11y do "Marketing — cadeia completa" passar (o `npm audit` vermelho por node-forge/braces é esperado e não é desta frente)
- **início / fim (UTC):** 2026-10-03 14:00 / 2026-10-03 15:00

## O que mudou

**(1) Inventário das decisões que o Marketing pede hoje** (só tipos que existem no sistema):

| decisão | onde mora hoje | leitura / comando |
|---|---|---|
| revisar anúncio (sim / não / quando), com prazo | `/announcements/:id#review` (`AnnouncementCard`) | `pending_review` + `expires_at`; `POST announcements/:id/approve/` e `reject/` |
| repetir falha segura | painel de resultado do anúncio | `DeliveryTarget.failed_retryable` (só volta por comando, o worker não repete); `POST retry-deliveries/` |
| consultar resultado incerto | painel de resultado do anúncio | `DeliveryTarget.unknown`; `POST reconcile-deliveries/` |
| aviso de anúncio para revisar (sino e push) | `MarketingNotificationsBell` e push | `notifications/v2/`, condição `announcement_review` (a mesma decisão da 1ª linha) |
| anúncio agendado | não havia lista; só "+ recentes" no painel | `approved` com `publish_at` futuro; cancelar mora no resultado do anúncio |

Falha final (`failed_final`) não é decisão: não há ação para ela. Ficou fora da fila (ver abaixo).

**(2) Backend (backstage + orquestrador, nada no Core).**
- `shopman/backstage/projections/marketing_decisions.py` (nova): `build_decision_queue()` junta
  `review`, `retry_failed` e `reconcile_unknown`, ordenados por prazo (sem prazo no fim), com alcance
  separado em `reach.posts` e `reach.people`, motivo por plataforma (`failures[].reason_code`), `href`
  do lugar exato da decisão, mais `automatic_checks`, `scheduled`, `scheduled_today_count` e
  `active_campaign_count`. Sem copy, sem texto do anúncio, sem PII.
- `GET /api/v1/backstage/marketing/decisions/` (`MarketingDecisionQueueView`, `shop.view_marketing`,
  `Cache-Control: private, no-store`). SSE: o app já usa o canal pessoal só para invalidar; a fila
  escuta a mesma revisão (ADR-016) e refaz o fetch. Não há canal SSE próprio de Marketing, e não foi
  criado.
- Registrada no gate Unfold (`scripts/check_unfold_canonical.py`, superfície headless) e na métrica
  `marketing_projection_seconds` (rótulo `decisions`).

**(4) "Marketing confere o incerto sozinho": não existia; foi implementado (pequeno e seguro).** A
reconciliação existia só por comando do operador. Agora `request_automatic_reconciliations`
(`shopman/shop/services/marketing_delivery_recovery.py`) roda na passada `process_marketing_delivery
--with-reconciliation` do `maintenance-worker`, antes de executar as consultas: cria a consulta de
cada tentativa `unknown` que ainda não teve nenhuma, com recibo de sistema (`actor` nulo,
`actor_ref=system:marketing-reconciliation`, auditoria `automatic_reconcile_unknown`), só para
plataformas com provedor registrado no ciclo. Idempotência: chave determinística por seleção e a
regra "uma consulta automática por tentativa" (qualquer reconciliação anterior daquela tentativa, do
sistema ou do operador, bloqueia). Nada reenvia: a consulta usa `lookup`, que não tem `send`, e
`unknown` nunca volta para a fila de envio. Se a plataforma responder "não sei" de novo, o destino
vira `reconcile_unknown` na fila e consultar de novo é gesto do operador.

**(3) Nuxt (`surfaces/marketing-nuxt`).**
- `/` deixou de redirecionar para `/v2?area=today`: é a fila (`MarketingDecisionQueue.vue`), cartões
  por prazo, o mais urgente em destaque (borda e botão cheio), um gesto só, **Revisar**, que abre
  `/announcements/:id#review` ou `#result` (âncora `id="result"` nova no painel de resultado); linha
  automática "Google: resultado incerto. O sistema consultou sem reenviar: publicado às 09:58 ·
  automático"; linha "+N agendados hoje · M campanhas ligadas" que leva a `/scheduled`.
- `/scheduled` (rota nova, em inglês): aprovados com hora marcada, com "Envia / Publica / Dispara
  hoje às HH:MM" (vocabulário fechado: o sistema não "sai") e "Abrir" para o anúncio, onde cancelar
  já mora.
- Seções: **Decisões** (`/`), **Agendados** (`/scheduled`), **Enviados** (`/history`), **Ajustes**
  (`/v2?area=campaigns`), com segunda linha em Ajustes (Campanhas, Modelos, Ofertas e cupons,
  Plataformas). No celular, barra do polegar no pé da tela; a do topo fica com o sino. Nenhuma rota
  removida; `/v2?area=today` continua acessível pela URL.
- O sino virou link para `/` com o número de decisões; continua dono do SSE e do poll da caixa
  pessoal e registra os avisos como vistos quando a fila está na tela. O painel próprio do sino saiu
  (decisão do dono: o sino abre a mesma lista).
- Copy: "Voltar ao painel" / "Ver o painel" viraram "Voltar às decisões" / "Ver as decisões".
- `docs/reference/marketing-surface-contract.md` e `surfaces/marketing-nuxt/README.md` atualizados.

## Prova

- `pytest shopman/backstage/tests/test_marketing_decisions.py` (7 testes novos: ordem por prazo,
  postagens × pessoas, falha com motivo e prazo, incerto como conferência automática até a consulta
  falhar, resultado da consulta, agendados/campanhas, 403 sem capability e sem copy):
  `7 passed`. `shopman/shop/tests/test_marketing_delivery_recovery.py` com 3 testes novos (uma
  consulta por tentativa, nunca `send`, não repete após "não sei"; respeita consulta do operador;
  ignora plataforma sem provedor): `17 passed`.
- Suíte de Marketing/campanha (backstage + shop, `-k "marketing or campaign"`, `-n 8`):
  `1342 passed, 3 skipped in 688.31s`.
- `scripts/check_marketing_docs.py` (= `make marketing-docs`): `Marketing docs match HEAD: 8 Nuxt
  routes, 33 Django routes, 2 deploy specs.`
- `scripts/check_unfold_canonical.py --maturity`: `Unfold canonical template check passed.`;
  `test_vocabulario_de_tela.py` + `test_unfold_canonical_templates.py`: `2266 passed`;
  `check_canonical_docs.py`: `canonical docs: OK`; `check_silent_swallow.py`: OK; `ruff`: limpo.
- marketing-nuxt (depois do merge com o `main`): `vitest` `Tests 433 passed (433)` (inclui
  `tests/decisions.test.ts`, `tests/components/MarketingDecisionQueue.test.ts` e o teste do sino
  reescrito; `operatorLanguage` e `securityDelivery` verdes); `eslint .` limpo; `nuxi typecheck`
  exit 0; `npm run build` ok.
- operator-kit: `Tests 1073 passed (1073)` (inclui `guardrails.vocabulary` e `guardrails.appBar`).
- SSR conferido contra o backend hermético (`tests/visual/mock_backend.py`): `/`, `/scheduled`,
  `/v2?area=offers` e `/history` respondem 200 com a fila, os agendados, a segunda linha de Ajustes e
  a barra do pé.
- Envelope de segurança (ADR-026): `nuxt.config.ts` e `server/` não foram tocados.

## O que ficou de fora

- **(c) digital do dispositivo e segunda pessoa: só desenho, abaixo.** Decisão do brief.
- **Matriz visual (job "Marketing — cadeia completa", não obrigatório):** a barra de seções mudou em
  todas as telas, então os retratos existentes vão divergir, e os novos (`decisions__*`,
  `scheduled__list`) não têm baseline. Só regera quem tem o browser da CI (macOS-15 + Chromium do
  Playwright); aqui o download do Chromium é bloqueado pelo proxy. Os retratos do painel do sino
  (`notifications__*`, `panel__sse-disconnected`) foram removidos com o painel. E2E e a11y foram
  atualizados mas NÃO rodaram localmente pelo mesmo motivo; a prova deles é a CI.
- **Falha final na fila:** não há gesto para ela (não se repete), então não é decisão. A pergunta
  "mostrar falhas finais do dia como aviso, sem gesto?" fica para o dono.
- **Push abre o anúncio, não a lista:** o push continua em `/announcements/:id#review`, que é o
  "Revisar" do cartão daquele anúncio (um toque a menos que abrir a lista). Se o dono quiser o push
  caindo na lista, é trocar o `action_url` em `user_notifications`.
- **Plataforma desligada com destino `unknown`:** não ganha consulta automática (não há quem leia) e
  aparece como "consultando" até a plataforma voltar.
- **Reagendar (M15) e trocar foto (M06):** fora do escopo; o "Revisar" abre onde a decisão já é
  tomada hoje.

### (c) Desenho curto: digital do dispositivo + segunda pessoa acima do limiar

O que existe: a cerimônia por consequência (`marketing_ceremony.py`/`marketing_security.py`, ADR
031-033) já devolve `confirmation.mode`, `step_up` (`password`/`totp`) e `dual_control`; a frase
`ENVIAR <pessoas>` vale sempre que há mensagem direta; acima do limiar pede senha e, acima de
`× múltiplo`, TOTP + duplo controle. O endpoint `POST security/dual-control/`
(`approve_second_actor`) já aprova um token aberto por OUTRA pessoa (recusa `dual_control_same_actor`),
mas o Nuxt nunca o chama e nada avisa a segunda pessoa. WebAuthn existe só para CLIENTE
(`packages/doorman/.../services/passkey.py` + `models/passkey.py`, `py_webauthn`, desafio na sessão,
chave `customer_id`). Operador tem PIN (`pin_credential`), `TrustedDevice` e TOTP. O mínimo de público
do WhatsApp (M38) é `Shop.defaults["marketing"]["whatsapp_minimum_audience"]`, padrão 1, editado no
Admin.

Como faria, em três PRs:
1. **Passkey de operador (doorman):** modelo `OperatorPasskey` (ou `Passkey` com dono polimórfico
   `user_id`), mesmos serviços `registration_options`/`verify_*` com desafio na sessão;
   cadastro no dispositivo confiável (`TrustedDevice`) depois do login forte.
2. **Digital como prova de presença no selo:** a cerimônia ganha `step_up = "device"` como
   equivalente da senha (não do TOTP); `record_step_up(level="device")` só depois de
   `verify_authentication` com `userVerification: required`. A frase digitada continua como
   alternativa visível ("Usar o meu código"). A frase `ENVIAR N` não some sem decisão: a digital
   prova presença, a frase prova leitura do número; proposta: digital substitui a frase até o
   limiar, e acima dele a frase volta.
3. **Segunda pessoa com push:** ao abrir um token com `dual_control`, criar `UserNotification`
   (condição `marketing_dual_control`) para quem tem `approve_marketing_announcements` menos o autor,
   com push e deep link para uma tela de confirmação que chama `security/dual-control/` com a digital
   dela; o selo do autor espera por SSE no canal pessoal. Limiar de segunda pessoa: hoje é
   `× múltiplo` do limiar; a prévia fala em "acima de 200 clientes", que é decisão do dono (vira
   campo em "Cerimônia do disparo", no Admin).

## Perguntas ao dono

1. Falha final do dia aparece na fila como aviso sem gesto (sim) ou só no histórico, como hoje (não)?
2. O push de anúncio para revisar abre o anúncio direto, como hoje (1), ou a lista de decisões (2)?
3. (c) A digital substitui a frase `ENVIAR N` até o limiar e a frase volta acima dele (sim), ou a
   digital entra junto com a frase sempre (não)? E o limiar da segunda pessoa é um número fixo de
   pessoas no Admin (sim) ou continua sendo `× múltiplo` do limiar proporcional (não)?

### Correção da barra do pé (regressão pega pela CI)

O e2e `a11y.spec.ts` ("fluxo autenticado…", 320×568) não conseguia tocar em "Tema escuro" no
pé do rail: a barra do polegar era `fixed inset-x-0` (largura da janela), cobria o rail, e a
pílula interceptava o ponteiro. Correção: a barra saiu da `CampaignTopBar` para
`MarketingSectionBar.vue`, montada pelo `app.vue` no fim da COLUNA de conteúdo, depois da
página, com `sticky bottom-0 mt-auto` e `data-focus-obstruction` (a régua do kit para o que
flutua na base). Ela agora só ocupa a largura do conteúdo, nunca a do rail, e o conteúdo
termina acima dela pelo fluxo (o `padding` reservado na coluna saiu). As seções viraram
`useMarketingSections` (fonte única das duas barras). Trava nova `tests/sectionBar.test.ts`
(barra não é `fixed`, mora depois da página e fora do rail, declara o obstáculo). O e2e não
rodou aqui (proxy bloqueia o Chromium); a prova é o job da CI.

### Retratos visuais

Os retratos novos (`decisions__pending` 390 e 1280, `decisions__empty` 390, `scheduled__list`
390) e todos os que mudaram com a barra de seções precisam ser gerados pela **sessão que tem o
browser da CI** (macOS-15 + Chromium pinado pelo Playwright). Não foram regenerados aqui.

## Armadilhas novas

- A fila (`/marketing/decisions/`) é uma leitura FORA do contrato gerado `marketing.v2` (sem JSON
  Schema nem cliente gerado); o tipo TS mora à mão em `app/types/decisions.ts`. Mudou a projeção,
  muda o tipo junto.
- Só a instância do sino (`useMarketingDecisions({ live: true })`) escuta a revisão do SSE; quem
  ler a fila em outro lugar não deve ligar `live`, senão cada aviso vira um fetch por leitor.
- O recibo da consulta automática avança a versão do anúncio (mesmo contrato do comando do
  operador). Um gesto de recuperação aberto antes dela recebe 409 uma vez e recarrega.
- `guardrails.appBar` agora tem `navLocalDeclarada`: a barra do pé do Marketing é navegação local
  declarada. Quando outro app quiser a barra do pé, ela vira peça da layer.
