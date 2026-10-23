# Laudo adversarial de go-live (23/10/2026)

- **Base:** `origin/main` em `b09d20cf0`, só leitura, worktree limpa.
- **Método:** seis auditorias em paralelo (dinheiro e fiscal; segurança; pedido e estoque;
  operação e virada; superfícies Nuxt; adotabilidade como produto). Cada achado P1 foi
  reproduzido de novo pela coordenação antes de entrar aqui.
- **Provas executáveis:** [`evidence/glr-2026-10-23/`](../../evidence/glr-2026-10-23/). São
  testes que **passam no código atual**, e por isso provam o defeito. Quem consertar
  transforma a prova em teste de regressão (assert invertido) dentro da suíte do app.
- **Tese desafiada:** a §10 da [coordenação](../plans/COORDENACAO-GO-LIVE.md) diz
  "nenhum bloqueio de código conhecido". O laudo discorda: não há P0 de código provado,
  mas há **19 P1** (falhas prováveis no uso real do Dia 1) e **1 bloqueio a provar em
  homologação** (forma de pagamento cartão na NFC-e).

Como rodar uma prova (na raiz de uma worktree):

```bash
PP=".:$(ls -d packages/*/ | tr '\n' ':')"
PYTHONPATH="$PP" /Users/pablovalentini/Dev/Claude/django-shopman/.venv/bin/python \
  -m pytest -c pyproject.toml --rootdir . -p no:cacheprovider -q evidence/glr-2026-10-23/<arquivo>
```

## 1. Veredito

O núcleo endurecido nos laudos anteriores está sólido. Confirmação Pix, idempotência
de webhook, assinaturas, livro-caixa, IDOR da loja, SSE por permissão, commit
concorrente, SKIP LOCKED e settings de produção foram conferidos e estão corretos. Os
defeitos novos moram nas **bordas de tempo** (reserva que vence e revive, encomenda
longa, retry fiscal em processamento), na **queda parcial de rede** (PDV e SSE) e na
**escada de identidade do cliente** (sessão fraca que vira forte).

Para produto adotável por outra empresa, a tese "tenant = config + dados + marca, zero
código" vale no backend do orquestrador e **não vale** nas superfícies Nuxt, no fiscal,
nos canais e nas integrações. E o repositório é público **sem arquivo de licença**.

## 2. Achados verificados

| ID | Sev. | Achado | Onde | Prova |
|---|---|---|---|---|
| E1 | P1 | Mexer na sacola revive reserva vencida e o mesmo item é vendido duas vezes (até 5 min de janela) | `shop/services/availability.py:61-94` (`bump_session_hold_expiry` sem `expires_at >= now`); `stockman/services/holds.py:537` (`extend`) | `test_glr_dom_bump.py` |
| E2 | P1 | Fechamento da loja online recusa por "indisponível" quando o estoque está dividido entre saldos (vitrine + depósito, lote de ontem + hoje) | `shop/services/stock.py:294-316` (ramo `require_all` usa `create_hold`, não reparte) | `test_glr_dom_split.py` (o commit levanta `insufficient_supply` com 4 disponíveis) |
| E3 | P1 | Encomenda com 3+ dias perde a reserva de estoque físico em 48 h; no dia, `fulfill` falha e o item já foi vendido | `shop/services/stock.py:283-298`, `shop/adapters/stock.py:184-192` | `test_glr_dom_preorder_ttl.py` |
| F1 | P1 | NFC-e "processando" na SEFAZ: o retry re-POSTa, cai em conflito de referência e vira falha terminal; pedido fica sem chave | `shop/handlers/fiscal.py:160-162`, `:304-315` | `test_glr_money_fiscal.py` |
| F2 | **Bloqueio a provar** | Formas de pagamento da NFC-e sem grupo de cartão (`tipo_integracao`), `99` sem descrição (todo iFood), Pix de balcão como `17` e não `20`, sem `valor_troco`. Rejeição 391 provável em toda venda no cartão. Não há no repositório NFC-e de cartão nem de iFood autorizada em homologação | `shop/adapters/fiscal_focusnfe.py:706-748` | leitura; falta emissão em homologação |
| F3 | P2 | Cancelamento de NFC-e salva `order.data` lido antes da chamada à Focus e apaga escrita concorrente | `shop/handlers/fiscal.py:550-553` | `test_glr_money_fiscal.py` |
| F4 | P2 | `fiscal_emit` não confere ambiente: em produção emite nota real e roda fora da fila | `shop/management/commands/fiscal_emit.py` | leitura |
| M1 | P1 | "Devolvi em dinheiro" concorrente grava duas saídas no livro-caixa para um estorno no Payman; fechamento cego acusa sobra falsa | `shop/services/payment.py:1322-1365` | `test_glr_money_cashrefund.py` |
| M2 | P2 | Webhook Stripe depois do vencimento do intent não liquida e abre alerta crítico falso | `shop/adapters/payment_stripe.py:1182-1219` | leitura |
| M3 | P2 | Estorno Efí usa `pix_list[0]` da cobrança e ignora o `e2e_id`; devolução de Pix pago após cancelamento falha | `shop/adapters/payment_efi.py:700-717` | plausível |
| M4 | P2 | Mix por método do fechamento soma `amount_q`, não o capturado | `backstage/services/closing.py:612` | leitura |
| M5 | P2 | Corrida estorno Stripe x `charge.refunded` gera alerta falso de divergência | `shop/adapters/payment_stripe.py:449-480`, `:1245-1259` | plausível |
| S1 | P1 | Sessão "só conhece o número" (link encaminhado) chama `trust-device`, ganha cookie de 30 dias e vira identidade forte (passkey liberada) | `storefront/api/auth.py:603-627` | `test_glr_sec_probe.py` |
| S2 | P1 | Troca de telefone sem step-up nem cerca de força: tomada permanente de conta | `storefront/api/account.py:1308-1431`, `:66` | `test_glr_sec_probe.py` |
| S3 | P1 | Login por WhatsApp é "device-code" pescável; "Não foi você?" não revoga passkey, troca de telefone nem sessão nova | `storefront/api/whatsapp_verify.py:31-128`, `doorman/views/access_link.py:207-295`, `shop/services/access.py:192-225` | leitura |
| S4 | P2 | Admin responde em `api.` e lá a sessão sai com `Domain=.boulangerie.com.br` | `config/urls.py:113-115`, `shop/middleware.py:265-298` | `test_glr_sec_admin_host.py` |
| S5 | P2 | OpenAPI/Swagger públicos (347 KB, mapa das ~470 rotas) | `config/urls.py:117-118` | `test_glr_sec_probe.py` |
| S6 | P2 | PIN de 4 dígitos: lockout fixo 5/5 min (força bruta em dias, DoS trivial do PIN do gerente); balde do crachá global 5/min | `doorman/conf.py:40-41`, `backstage/api/operations.py:917-933`, `:1068`, `:1144` | leitura |
| S7 | P2 | DANFE de qualquer pedido para qualquer staff | `shop/views/fiscal_danfe.py:395-405` | leitura |
| S8 | P2 | Cupom sem limite próprio e com oráculo de estado | `storefront/api/surface.py:915-955` | leitura |
| S9 | P2 | Webhook iFood legado (`/ifood/`) segue roteado, autentica por token na URL e cria pedido com preço do corpo | `shop/webhooks/urls.py:16`, `webhooks/ifood.py:229-253` | leitura |
| U1 | P1 | PDV só entra no modo sem conexão se `navigator.onLine === false`. Wi-fi de pé com link caído trava o balcão em "resultado incerto" venda após venda | `pos-nuxt/app/composables/usePosSale.ts:251`, `:3307` | conferido |
| U2 | P1 | Falha transitória (502 de deploy, timeout) no fechamento trava o PDV até conferência manual; nenhuma chamada tem timeout | `usePosSale.ts:3310-3317`, `usePosAction.ts:34`, `operator-kit/server/utils/djangoProxy.ts:306`, `storefront-nuxt/server/utils/djangoProxy.ts:264` | leitura |
| U3 | P1 | SSE cru sem reconexão depois de 502 no PDV, no Gestor (alertas, detalhe), nas notificações do kit e no acompanhamento da loja | `pos-nuxt/.../usePosEvents.ts:67-74`, `orders-nuxt/.../useAlerts.ts:42`, `useBackstageEvents.ts:18-36`, `operator-kit/.../useUserNotifications.ts:22-27`, `storefront-nuxt/.../useOrderTrackingStream.ts:33-42` | leitura |
| U4 | P1 | Pix copia-e-cola sem try/catch nem plano B; código truncado | `storefront-nuxt/app/components/PaymentBlock.vue:37-41`, `:89-98` | leitura |
| U5 | P1 | Caminho do Dia 1 da loja não roda em navegador na CI (`criticalFlow.spec.ts` com `skip` fixo; happy-path do alpha em nenhum workflow) | `surfaces/contracts.json:17-21`, `storefront-nuxt/tests/e2e/` | leitura |
| U6 | P2 | "Esta tela se resolve sozinha" no checkout incerto, mas a recuperação roda uma vez | `storefront-nuxt/app/pages/finalizar.vue:1285-1288` | leitura |
| U7 | P2 | HTML personalizado da loja (`/pedido/*`, `/conta/*`) sem `Cache-Control: private` | `storefront-nuxt/server/utils/storefrontSecurity.ts:52-60` | plausível |
| U8 | P2 | Prazo do Pix no PDV fixo em 10 min no cliente | `usePosSale.ts:544`, `utils/pendingPixStore.ts:16` | leitura |
| U9 | P2 | Alvos de toque de 20 px no checkout; imagem de capa de 313 KB no celular | `finalizar.vue:1541,1551`, `HomeHeroThing.vue:42` | leitura |
| O1 | P1 | Depois da tag `go-live-v1`, todo `AlterField` (mudar `choices`) recusa o deploy; a esteira para | `shop/migration_safety.py:52-54`, `:188-198` | conferido |
| O2 | P1 | `SHOPMAN_MIGRATION_BACKUP_REF` não vence: usado uma vez, a trava fica desarmada para sempre | `shop/migration_safety.py:130-135`, `docs/runbooks/backup-e-restore.md:189-200` | conferido |
| O3 | P1 | Alerta de "worker de tarefas parado" sai como `Directive`, que só o próprio worker parado entrega | `shop/services/critical_alerts.py:46`, `check_directive_health.py:124-134` | conferido |
| O4 | P1 | Runbooks de incidente mandam `make deploy-up/ps/logs` e `make diagnose-*`, que agem no docker local, não na DO | `docs/runbooks/directive-worker-parado.md`, `redis-fora.md`, `webhook-falhando.md`, `security-readiness.md`; `Makefile:601-722` | conferido |
| O5 | P1 | Worker pendurado (sem cair) não se recupera: sem sonda, reaper dentro do próprio processo, ~45 comandos em série no ciclo de manutenção | `orderman/.../process_directives.py`, `shop/management/commands/maintenance_worker.py:76-240` | plausível |
| O6 | P1 | "Dia D · dados" sem passo de fechar canais e parar workers; ensaio do purge roda DELETE no banco vivo segurando locks | `docs/runbooks/go-live-cutover.md:35`, `config/synthetic_purge.py:472-532` | leitura |
| O7 | P2 | Tag `go-live-v1` nasce antes do GO/NO-GO; rollback não a desfaz | `go-live-cutover.md:37` | leitura |
| O8 | P2 | `check_adr015.py` compara `DEPRECATED(remove by)` com `date.today()` num check obrigatório: bomba-relógio | `scripts/check_adr015.py:369-395` | leitura |
| O9 | P2 | Rollback de dado não limpa o Valkey nem atualiza o `cluster_name` do spec | `go-live-cutover.md` §0b | plausível |
| O10 | P2 | Banco de um nó, 1 GB, 5 conexões de servidor no PgBouncer, sem standby; fora da matriz | `config/settings.py:615-627` | decisão de custo |
| O11 | P2 | Imagens base sem digest | `Dockerfile:6`, `surfaces/Dockerfile.*` | leitura |
| O12 | P2 | Security Gate, Production Contract, build dos grupos de operador e `operator-router` fora dos checks obrigatórios | `.github/required-status-checks.json` | leitura |
| H1 | P2 | 214 alertas CodeQL abertos (166 stack-trace-exposure, 7 log sensível, 1 SSRF no Marketing, 4 redirect) e 23 Dependabot *high* de runtime nos lockfiles Nuxt (`node-forge`, `braces`) | GitHub Security | `gh api` |
| A1 | P0 produto | Repositório público sem `LICENSE`; README promete MIT; 8 dos 13 `pyproject` sem `license` | raiz, `packages/*/pyproject.toml` | `gh repo view` |
| A2 | P0 produto | Marca da Nelson compilada na loja: logo SVG à mão, manifesto PWA, ícones, `nelsonFallback.ts` (`default_city: 'Londrina'`), status-nuxt | `storefront-nuxt/app/components/ShopLogo.vue`, `server/utils/pwaManifest.ts:67-69`, `pwa-assets.config.ts:9`, `utils/nelsonFallback.ts` | leitura |
| A3 | P1 produto | Fiscal só Simples Nacional em dataclass; regra RICMS/PR no fluxo; só Focus | `fiscalman/classification.py:94-111`, `shop/services/fiscal.py:195` | leitura |
| A4 | P1 produto | Fuso `America/Sao_Paulo` cravado em 7 arquivos Nuxt apesar de `Shop.timezone` | `operator-kit/app/presentation/dates.ts:66` e outros | leitura |
| A5 | P1 produto | 40 comparações `channel_ref == "ifood"`, 115 `"whatsapp"`: canal é nome mágico, não papel | `shop/lifecycle.py:83,944,985`, `services/operator_orders.py` e outros | leitura |
| A6 | P1 produto | Um provedor real por integração (Stripe, Focus, iFood, Machine/TaOn, ManyChat); nome "TaOn" em copy do serviço genérico | `shop/services/courier.py`, `pos-nuxt/app/types/preorders.ts` | leitura |
| A7 | P1 produto | Termos e privacidade da padaria em `.vue`; versão legal em constante Python; prompt do concierge "de padaria" | `storefront-nuxt/app/pages/termos.vue`, `storefront/presentation/legal.py:43-44`, `storefront/concierge/prompt.py` | leitura |
| A8 | P2 produto | Sem caminho de adoção: único seed é Nelson (10.210 linhas), descritor sem seção para posições e KDS, nenhum guia do `instance_descriptor`; README/CHANGELOG incoerentes (Django 6.0, ~5.000 testes, `pablondrina/*`, CHANGELOG parado em julho) | `config/management/commands/seed.py`, `config/instances/`, `README.md` | leitura |

Conferido e correto (não reabrir sem dado novo): confirmação Pix por valor, idempotência
dos webhooks, assinatura Stripe, tokens Efí e Machine com `compare_digest`, livro-caixa
com lock, total esperado do PDV, IDOR de pedido na loja, SSE por permissão, BFF (Origin,
path traversal, gêmeas públicas sem cookie), duplo clique no checkout e no PDV,
commit concorrente, SKIP LOCKED no worker, `on_commit` no lifecycle, settings de
produção, purge que recusa com `SHOPMAN_GO_LIVE`.

## 3. Tarefas para delegar

Regras para todas: as 14 regras comuns da §2 da
[coordenação](../plans/COORDENACAO-GO-LIVE.md); uma tarefa = um branch = um PR (ou uma
pilha curta de PRs do mesmo agente); a prova em `evidence/glr-2026-10-23/` vira teste de
regressão na suíte do app; ao mergear, apagar a prova correspondente.

A coluna **Arquivos** é o perímetro exclusivo da tarefa. Duas tarefas da mesma onda não
compartilham arquivo; onde há encosto, a ordem está escrita.

### Onda 1: antes do go-live (todas em paralelo)

| Tarefa | Achados | Arquivos (perímetro) | Pronto quando |
|---|---|---|---|
| **T1 Reserva no tempo certo** | E1, E2, E3 + baixa dupla concorrente tratada como sucesso | `shop/services/availability.py`, `shop/services/stock.py`, `shop/adapters/stock.py`, `stockman/services/holds.py` (só o guarda do `extend`), testes de hold | bump ignora vencido; commit reparte entre saldos tudo-ou-nada; backstop medido a partir da data da encomenda; `INVALID_STATUS` com status FULFILLED não gera alerta |
| **T2 Retry fiscal honesto** | F1, F3, F4 | `shop/handlers/fiscal.py`, `shop/management/commands/fiscal_emit.py`, `shop/tests/test_fiscal_handlers.py` | consulta em processamento levanta transiente; cancel relê com `select_for_update`; `fiscal_emit` recusa fora de homologação |
| **T3 Formas de pagamento da NFC-e** | F2 | `shop/adapters/fiscal_focusnfe.py`, `shop/tests/test_fiscal_focusnfe.py` | grupo de cartão, `xPag` no 99, troco; **emissão em homologação** de uma nota por forma (03, 04, 17, 99) com evidência. A emissão no alpha pede a palavra do dono; a questão 17 x 20 vai na leva do contador |
| **T4 Estorno sem fantasma** | M1, M2, M3, M4, M5 | `shop/services/payment.py` (só `refund_cash`), `shop/adapters/payment_stripe.py`, `shop/adapters/payment_efi.py`, `backstage/services/closing.py` e testes desses | lock antes do saldo no estorno em dinheiro; webhook vencido reconcilia; Efí devolve por `e2e_id`; fechamento soma capturas; corrida de estorno sem alerta falso |
| **T5 Escada de identidade do cliente** | S1, S2 (+ PATCH de e-mail) | `storefront/api/auth.py` (só `TrustDeviceView`), `storefront/api/account.py`, `shop/services/account.py`, tela Nuxt da troca de número, testes de força de identidade | sessão `number` não confia dispositivo; troca de telefone e de e-mail exigem step-up no número atual |
| **T6 Superfície HTTP fechada** | S4, S5, S6, S7, S8, S9 | `shop/middleware.py`, `config/urls.py`, `config/settings.py` (só `SPECTACULAR_SETTINGS`), `shop/webhooks/urls.py`, `shop/webhooks/ifood.py`, `shop/views/fiscal_danfe.py`, `storefront/api/surface.py` (cupom), `doorman/conf.py`, `doorman/.../pin_credential.py`, `backstage/api/operations.py` (só PIN e crachá) | Admin só no host do Admin; schema só para staff; rota iFood legada fora; DANFE por permissão; cupom com limite e mensagem única; lockout progressivo e balde do crachá por estação |
| **T7 PDV que não trava** | U1, U2, U8 | `pos-nuxt/app/composables/usePosSale.ts`, `usePosOfflineSales.ts`, `usePosAction.ts`, `utils/pendingPixStore.ts`, `operator-kit/app/composables/useConnectivity.ts` (ou `useReachability` novo), `operator-kit/server/utils/djangoProxy.ts` | queda de link sem queda de wi-fi entra na fila; "Conferir agora" reenvia a mesma chave; timeout com `AbortSignal`; BFF distingue upstream inalcançável (502/503); prazo do Pix vem do `expires_at`; e2e que corta só a rota do `api` |
| **T8 SSE resiliente nos operadores** | U3 (operador) | `pos-nuxt/app/composables/usePosEvents.ts`, `pos-nuxt/.../usePosPreorders.ts` (só o stream), `orders-nuxt/app/composables/useAlerts.ts`, `useBackstageEvents.ts`, `operator-kit/app/composables/useUserNotifications.ts` | todos em `openResilientEventSource`, com teste de reconexão após 502 |
| **T9 Checkout da loja à prova de borda** | U3 (loja), U4, U6, U7, U9 + timeout do BFF da loja | `storefront-nuxt/app/components/PaymentBlock.vue`, `pages/finalizar.vue`, `sacola.vue` (alvo de toque), `composables/useOrderTrackingStream.ts`, `server/utils/storefrontSecurity.ts`, `server/utils/djangoProxy.ts`, `HomeHeroThing.vue` e imagens | copia-e-cola com plano B; recuperação com backoff; `private, no-store` em documento; toque ≥ 24 px; SSE resiliente; timeout no proxy. Checklist D1 a D12 |
| **T10 Travas de migração e alerta que sai** | O1, O2, O3, O8 | `shop/migration_safety.py`, `scripts/check_adr015.py`, `shop/services/critical_alerts.py`, `check_directive_health.py`, testes | `AlterField` só de `choices`/`help_text` não bloqueia (ou marcador expand-contract aceito); ref de backup com data e validade curta; alerta de worker parado e de backlog sai síncrono; prazo vencido só reprova o diff que toca o arquivo |
| **T11 Worker que se cura** | O5 + reaper que processa duas vezes | `orderman/.../management/commands/process_directives.py`, `shop/management/commands/maintenance_worker.py`, spec `.do/` (só os workers) | watchdog sai do processo quando o heartbeat envelhece (a DO reinicia); timeout por comando no ciclo; `done` com compare-and-set |
| **T12 Runbooks que agem no vivo** | O4, O6, O7, O9, O10 (registro) | `docs/runbooks/*.md` citados, `Makefile` (alvos `deploy-*`/`diagnose-*`), `docs/plans/GO-LIVE-READINESS-PLAN.md` (linha nova para O10) | cada comando de incidente age na DO ou diz quem age; Dia D fecha canais e para workers antes do purge, e o ensaio roda numa cópia; tag só depois do GO; §0b limpa Valkey e atualiza o spec |

Encostos dentro da Onda 1: T7 e T9 mexem em BFFs diferentes (`operator-kit` x
`storefront-nuxt`); T8 e T7 mexem em composables diferentes do PDV; T11 e T12 tocam
`.do/` e `Makefile` em linhas diferentes: **T11 mergeia primeiro**.

### Onda 2: depois da Onda 1 (dependem de arquivos dela)

| Tarefa | Achados | Arquivos | Depende de |
|---|---|---|---|
| **T13 E2E do Dia 1 na CI** | U5 | `surfaces/contracts.json`, `storefront-nuxt/playwright.config.ts`, `tests/e2e/`, `.github/workflows/surfaces-gate.yml` | T9 (mesmo app) |
| **T14 Higiene de segurança do GitHub** | H1, O11 | arquivos apontados pelo CodeQL fora dos perímetros da Onda 1, lockfiles Nuxt, Dockerfiles | T6 e T7 mergeados (`operations.py`, BFFs). Triar: consertar o real (log de lat/lng, `str(exc)` em resposta), dispensar falso positivo com motivo escrito |
| **T15 Checks obrigatórios completos** | O12 | `.github/required-status-checks.json` + branch protection | qualquer momento; confirmar antes que os quatro checks rodam em `pull_request` e `merge_group` (senão travam a fila) |

### Onda 3: produto adotável (depois do go-live, uma frente por agente)

| Tarefa | Achados | Perímetro |
|---|---|---|
| **P1 Licença e vitrine pública** | A1, A8 (README/CHANGELOG) | `LICENSE` na raiz e em `packages/*`, `pyproject` dos 13 pacotes, `README.md`, `CHANGELOG.md`, `.env.example`. **A licença é decisão do dono** e pode ir antes do go-live (o repo já é público) |
| **P2 Marca vinda da Shop** | A2 | `storefront-nuxt` (logo, PWA, ícones, `nelsonFallback.ts` vira fallback neutro), `status-nuxt` por env, default do Marketing |
| **P3 Fuso da Shop no front** | A4 | os 7 arquivos Nuxt; o fuso chega pela projeção |
| **P4 Canal por papel** | A5 | `ChannelConfig` ganha papel/capability (`marketplace`, `conversational`); as 155 comparações migram. Toca `lifecycle.py` e muitos services: **sozinha na janela**, sem outra frente nesses arquivos |
| **P5 Fiscal por regime e UF** | A3 | `fiscalman` (perfil vira dado), `Shop` (CRT/regime), regras por UF. Mexe no Core: plano curto antes do código |
| **P6 Nome do provedor vem do adapter** | A6 | `services/courier.py`, `pos-nuxt/app/types/preorders.ts`, registro do WhatsApp Cloud direto |
| **P7 Texto legal e voz configuráveis** | A7 | `termos.vue`, `privacidade.vue`, `legal.py`, `concierge/prompt.py`, `house_rules.py` |
| **P8 Kit de adoção** | A8 | descritor inicial genérico, seções de posições e KDS no descritor, guia "como adotar", seed de demo neutro separado do seed da Nelson |

## 4. Decisões do dono

1. **Licença do repositório público:** MIT, como o README já promete? (A1)
2. **Login por WhatsApp (S3):** antes de liberar a aba, a resposta do WhatsApp pede
   "Entrar em Safari/iPhone? SIM"; ou a aba entra só com força `number` até um código.
   Em qualquer caso, "Não foi você?" passa a derrubar todas as sessões, dispositivos e
   passkeys criadas na janela.
3. **Banco sem standby (O10):** aceitar o risco no Dia 1 ou subir o plano.

## 5. O que este laudo não cobriu

Concorrência real em Postgres (corridas vieram de leitura e de simulação); lógica por
objeto dentro do `operations.py` e do POS; financeiro e cancelamento do iFood;
Admin/Unfold campo a campo; spec vivo, painel do Sentry e alertas da DO; resposta real
da Focus/SEFAZ; navegador real (clipboard, toque); Produção, Compras e Central só por cima.
