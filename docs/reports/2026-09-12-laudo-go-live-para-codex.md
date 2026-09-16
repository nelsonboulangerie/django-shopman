> **Registro histórico — reconciliação em 15/09/2026.** O laudo abaixo descreve
> exclusivamente a base `786f3cc0a`, auditada em 12/09. Seus números, linhas e
> afirmações sobre o ambiente não representam o estado atual. O texto original
> foi preservado integralmente após esta nota; esta matriz registra o tratamento
> posterior, sem transformar merge de código em prova de configuração externa.

## Reconciliação dos achados em 15/09/2026

| Itens originais | Tratamento posterior | Estado e limite da conclusão |
|---|---|---|
| A1, B1 — captura antes da entrega; dados fiscais no nascimento | [#642](https://github.com/nelsonboulangerie/django-shopman/pull/642), continuidade em [#680](https://github.com/nelsonboulangerie/django-shopman/pull/680)/[#684](https://github.com/nelsonboulangerie/django-shopman/pull/684) | Correções integradas. A preparação Efí [#690](https://github.com/nelsonboulangerie/django-shopman/pull/690) é passiva: flip do adapter e validação OAuth/GET continuam pendentes; não houve ativação de cobrança real por esse PR. |
| A2, B6 — identidade e meios de pagamento do checkout | [#641](https://github.com/nelsonboulangerie/django-shopman/pull/641) | Correções integradas; o diagnóstico histórico de checkout anônimo não deve ser apresentado como estado atual. |
| A3 — credenciais Maps | [#686](https://github.com/nelsonboulangerie/django-shopman/pull/686), incorporando #613/#656 | Separação e guardas de código integradas. A restrição efetiva de credenciais no provedor exige evidência operacional própria; esta reconciliação não repete a sonda histórica nem declara o provedor validado. |
| A4 — Admin/2FA/limite de login | [#689](https://github.com/nelsonboulangerie/django-shopman/pull/689); [#655](https://github.com/nelsonboulangerie/django-shopman/pull/655) | Piloto individual de 2FA publicado, **inscrição ainda pendente**; não equivale a todo o Admin protegido. #655 permanece **retido**: `REMOTE_ADDR` produz bucket coletivo atrás do proxy, e o helper de XFF não autentica a origem. Experimento [#671](https://github.com/nelsonboulangerie/django-shopman/pull/671) continua interrompido, sem novas sondas. |
| B2 — desconto da prévia | [#644](https://github.com/nelsonboulangerie/django-shopman/pull/644) | Correção integrada. |
| B3 — recuperação da venda já criada | [#643](https://github.com/nelsonboulangerie/django-shopman/pull/643), continuidade #680/#684 | Correção integrada; fluxo posterior preserva recuperação e fechamento incerto. |
| B4 — revisão das comandas | [#645](https://github.com/nelsonboulangerie/django-shopman/pull/645) | Correção integrada. |
| B5 — pausa ao adotar reservas | [#646](https://github.com/nelsonboulangerie/django-shopman/pull/646) | Correção integrada. |
| B7 — autoria da pausa em massa | [#649](https://github.com/nelsonboulangerie/django-shopman/pull/649) | Correção integrada; não reconstrói autoria desconhecida de eventos anteriores. |
| B8 — telefone humano ambíguo | [#687](https://github.com/nelsonboulangerie/django-shopman/pull/687), continuidade de #650; [#673](https://github.com/nelsonboulangerie/django-shopman/pull/673) | Recusa de entrada ambígua e identidade verificada dos alertas integradas. |
| B9 — recuperação fiscal/estorno | [#686](https://github.com/nelsonboulangerie/django-shopman/pull/686), incorporando #651 | Janela de recuperação integrada. |
| B10 — fallback após recusa explícita | #686, incorporando #652 | Classificação de recusa e fallback integrados; resultado incerto continua sem repetição automática. |
| B11 — alerta crítico externo | #686, incorporando #653 | E-mail durável com debounce integrado; entrega depende de configuração operacional. Ativação de Sentry não é comprovada por esta nota. |
| B12 — heartbeat dos workers | #686, incorporando #654 | Readiness dos dois workers integrada, com grace de startup. |
| B13, B14 — guardas de ambiente e runbooks | #686, incorporando #656/#657 | Guardas e documentação integradas. Isso não prova conversão do ambiente para produção nem autoriza aplicar o spec versionado sobre o vivo. |
| B15 — smoke e catálogo canônico | [#648](https://github.com/nelsonboulangerie/django-shopman/pull/648) | Correção integrada; smoke posterior ao #689 passou. |
| Latentes — estação/caixa; validade de certificado | [#647](https://github.com/nelsonboulangerie/django-shopman/pull/647), [#670](https://github.com/nelsonboulangerie/django-shopman/pull/670); #686 incorporando #657 | Correções integradas. Validação local de validade não equivale a credencial aceita pelo provedor. |

### Decisões da seção C e evidência de publicação

- **C1:** o titular autorizou o piloto individual implementado em #689. Global OFF:
  a coordenação confirmou ausência de `SHOPMAN_ADMIN_REQUIRE_2FA` no spec global e
  dos serviços, correlacionada ao default `False` do código; não houve consulta
  por execução no runtime. Antes da inscrição, um operador com console autorizado
  deve executar `python manage.py setup_admin_totp <usuario-confirmado>`.
  A tentativa de console retornou 403; a identidade genérica `admin` não comprova
  vínculo com Pablo. Só depois da preparação o titular conclui
  [o assistente privado](https://admin.boulangerie.com.br/admin/2fa/enroll/),
  guardando e testando a recuperação, sem compartilhar QR, senha ou códigos.
- **C2:** resolvida pela [decisão registrada em 15/09](https://github.com/nelsonboulangerie/django-shopman/pull/638#issuecomment-5677842084):
  manter confirmação explícita para CPF/e-mail novos, com “Cadastrar e vincular”
  ou “Usar dados só neste pedido”. Não restaurar salvamento pré-marcado.
- **C3:** não encerrada por este documento. Nome do ambiente, configuração de
  produção e flip Pix são decisões/configurações distintas da integração dos PRs.

O #689 entrou em `main` no commit `1f447506bfaf90d157f1e00795c86007a98d117c`:
[build 34992175799](https://github.com/nelsonboulangerie/django-shopman/actions/runs/34992175799)
e [smoke 34992417428](https://github.com/nelsonboulangerie/django-shopman/actions/runs/34992417428)
concluíram com sucesso. O smoke confirmou o deployment
`723cf37c-1cf2-46ba-a722-474702e8272e` ACTIVE com a imagem publicada.
A coordenação confirmou nos logs de release `backstage.0068` e
`otp_static.0001/0002/0003` aplicadas. O
[roteiro do piloto](2026-09-15-admin-2fa-pilot.md) detalha inscrição e recuperação.

A seção E abaixo permanece como pedido histórico de apreciação, atendido pelas
frentes e PRs discriminados nesta matriz; não é uma nova ordem de execução.
As ressalvas operacionais acima continuam abertas. Nenhuma alteração de código,
credenciais, spec, seed ou infraestrutura faz parte desta reconciliação.

---

# Laudo adversarial de go-live — achados confirmados e pedido de apreciação

**Para:** Codex (agente externo)
**De:** sessão Claude de análise adversarial, 12/09/2026
**Base auditada:** `origin/main 786f3cc0a` (o #629 entrou depois e não foi auditado)
**Método:** 6 frentes de busca + 3 céticos independentes, tudo de leitura. Só o que resistiu à refutação está aqui. Régua: P0 perde dinheiro / corrompe dado / viola segurança / impede a tarefa central sem contorno, alcançável no alpha hoje; P1 dano real com contorno, ou P0 que depende de configuração ainda não ligada; P2 degrada ou é risco latente.
**Laudo completo:** https://claude.ai/code/artifact/3a954c54-b6df-40f5-a7ba-de1cf93cf743

Resultado: **0 P0, 4 P1, 22 P2.** Nenhum fato dos auditores foi refutado; o que caiu foi severidade.

---

## A. Os quatro P1

### A1 · PDV: Pix no balcão fecha a venda como `COMPLETED` antes de qualquer captura
- **Onde:** `shopman/shop/lifecycle.py:757` (`timing == "external"` → `_requires_payment_before_physical_work` devolve `False`); `shopman/shop/services/order_helpers.py::customer_holds_the_goods` exclui só `link`; canal `pdv` do seed tem `timing: external` (`config/management/commands/seed.py:5880`); `customer_orders.py:314` (timeout de Pix só em `NEW`/`ACCEPTED`).
- **Cadeia:** Finalizar → commit → `immediate` → `ACCEPTED` → `stock.fulfill` → `_counter_handoff` → `COMPLETED` → `_on_completed` (NFC-e via `eletronic_payment`, `loyalty.earn`) → só depois `_settle_pos_sale` cria intent `pending`. Nada desfaz um Pix nunca pago.
- **Alcançável hoje:** sim (toda venda Pix do PDV no alpha). Com Efí ligada: cliente sai com o pão, NFC-e válida, ninguém avisado.
- **Conserto:** `customer_holds_the_goods` devolve `False` para método digital antecipado sem captura (reusar `payment_gate.UPFRONT_DIGITAL_PAYMENT_METHODS`); `PaymentTimeoutHandler` alcança pedidos do PDV além de `accepted` (ou o PDV não avança para `COMPLETED` antes de `captured`).
- **Aceite:** teste com `transaction=True`: PDV + Pix + Finalizar → pedido fica `ACCEPTED` com intent `pending`; sem NFC-e nem pontos; timeout do Pix cancela e libera. O comentário em `lifecycle.py:746-754` (que explica por que `link` saiu do atalho) passa a valer para Pix.

### A2 · Storefront: `POST /api/v1/checkout/` não exige sessão e não amarra `phone` à identidade
- **Onde:** `shopman/storefront/api/views.py:89` (`AllowAny`), `:162` (lê `phone` do payload), `:348-360` (normaliza e grava) — nenhuma comparação com `request.customer`; `shopman/shop/services/checkout.py:55-60` (`assign_phone_handle(abandon_existing=True)` antes de `process_ops`); `sessions.py:126-141` abandona qualquer `Session(open, handle_type="phone")` daquele número e libera holds; `commit.py:357` herda o handle; `notification.py:783` notifica o telefone do payload.
- **Efeito:** com o número de B, o pedido entra no histórico de B, a notificação vai ao WhatsApp/SMS de B, o endereço digitado entra no caderno de B e, se B tinha checkout em curso, a sacola de B é derrubada. A projection promete `requires_authentication=True` (`presentation/checkout.py:457`); a API não impõe.
- **Alcançável hoje:** sim, por request forjado (a UI preenche o telefone da sessão). Por isso P1, não P0.
- **Conserto:** na view, exigir sessão autenticada (403 `authentication_required`, dialeto canônico); com sessão, **ignorar** `phone` do payload; `abandon_existing` só quando o principal coincide.
- **Aceite:** anônimo → 403; logado com `phone` ≠ sessão → pedido usa o da sessão; ajustar `test_checkout_cash_change_for.py`, `test_checkout_cash_no_intent.py`, `test_checkout_card_web.py`, `test_checkout_hold_adoption_login.py` (hoje commitam anônimo e esperam 201).

### A3 · Storefront: chave do Google Maps pública e sem restrição
- **Onde:** `shopman/storefront/presentation/home.py:274` serve `google_maps_api_key` em `/api/v1/storefront/home/`; a mesma env alimenta `geocoding.py:126,179` e o PDV.
- **Prova (sonda GET):** a chave publicada responde `OK` no Geocoding sem Referer → não tem restrição de referrer nem de IP.
- **Em voo:** #613 (`codex/google-maps-credential-split-20260911`) separa browser/server **com fallback para a chave antiga**; o spec vivo só tem `GOOGLE_MAPS_API_KEY`. Sozinho não resolve.
- **Conserto:** (dono) restringir a chave atual por referrer e criar a de servidor restrita por IP; (código) #613 sem fallback silencioso: em produção, ausência da chave de servidor deve falhar fechado (check E0xx), não cair na chave de browser.

### A4 · Admin público, sem 2FA e sem lockout
- **Onde:** `admin.boulangerie.com.br/admin/login/` → 200 público; `SHOPMAN_ADMIN_REQUIRE_2FA` ausente do spec (`middleware_2fa.py:35` devolve `False`); nenhum `ratelimit`/`axes` sobre o login do Admin (só sobre `OperatorLoginView`).
- **Contexto:** a app do alpha é a antiga `shopman-staging` renomeada; a regra de 03/07 mantém `admin/admin` + PIN `1234` ali. O código não semeia essa senha; se existe, foi reposta à mão. **Sobe a P0 se um POST confirmar que autentica.**
- **Conserto (decisão do Pablo, não do Codex):** ligar 2FA ou allowlist de IP no ingress. Do lado do código: rate limit no login do Admin (mesma família do `OperatorLoginView`) é PR pequeno e não depende da decisão.

---

## B. P2 que pedem mudança de código (ordenados por dano)

| # | Achado | Onde | Conserto |
|---|---|---|---|
| B1 | **CPF "na nota" descartado na NFC-e de balcão paga em Pix/cartão.** Os callbacks de `on_commit` enfileiram `fiscal.emit_nfce` com `order.data` ainda sem `fiscal`; `_mark_tab_committed` (`pos.py:392`) copia depois. Vira P1 com `FOCUS_NFE_ENVIRONMENT=producao`. | `services/pos.py:340-392`; `orderman/services/commit.py:326-333` (lista sem `fiscal`/`receipt`); teste existente usa `captureOnCommitCallbacks` em volta do `close_sale` inteiro (ordem invertida) | incluir `fiscal` e `receipt` na lista de `_do_commit` (ou gravar dentro da transação); teste balcão + Pix + CPF com `transaction=True` afirmando `payload["customer"]["tax_id"]` |
| B2 | **Desconto % de pedido: tela e livro divergem 1–3 centavos** (provado por script: 3×3,33 a 10% → 8,99 vs 9,00; 6×1,50 a 5% → 8,55 vs 8,58). | `services/pos.py:2334` (HALF_UP no subtotal) vs `modifiers.py:1460` (`_spread_order_discount(..., at_least=False)`) | review roda `_spread_order_discount` sobre cópia dos itens, como já faz para desconto de linha; teste `review.total_q == order.total_q` com qty > 1 |
| B3 | **Replay do "Finalizar" após falha na liquidação devolve 200 sem linha no livro**; a tela descarta o `recovery` do 409 (`"NÃO refaça a venda"`) e o 500 pós-commit diz "pedido não foi fechado" (falso). | `services/pos.py:339-350` (replay sem settle), `:386` (settle fora do atomic); `usePosSale.ts:2295-2331` (catch genérico só mostra `detail`) | no replay sem linha/intent, reliquidar (`_record_sale`/`settle_terminal_tenders` são idempotentes); catch genérico exibe `detail + recovery`; pós-commit embrulhado em 409 que nomeia o pedido |
| B4 | **Mesma comanda em duas abas: última gravação vence, sem aviso.** | `services/pos.py:2126` (`_replace_session_ops`), `:1058-1108` (`save_pos_tab` sem revisão) | `last_touched_at` lido na abertura → 409 `tab_stale` no save; cliente recarrega e avisa (padrão `fiscal_revision` de `services/orders.py`) |
| B5 | **`/finalizar` aceita "Enviar pedido" com item pausado**; adoção de hold ignora pausa; `check_on_commit=False` no web. | `presentation/checkout.py:401` (ignora `cart.can_checkout`); `services/stock.py:145-160` (`_adopt_holds_for_qty`) | `_checkout_actions` herda `cart.can_checkout`/`checkout_block_reason`; adoção de hold recusa SKU pausado |
| B6 | **API de checkout aceita `payment_method` fora do canal, inclusive vazio** (`cash` num canal só Pix/cartão vira COD; `""` gera pedido sem bloco `payment`). | `api/serializers.py:34` (`allow_blank=True`); `api/views.py:385-400` | campo obrigatório e validado contra `checkout_context.payment_methods(CHANNEL_REF)` → 400 com `field` |
| B7 | **Pausa em massa sem rastro** (`.update()` deliberado, mas `actor` da assinatura é ignorado). Hoje 28 SKUs pausados e o banco não sabe quem. | `backstage/services/catalog.py:196,250` | evento de auditoria com ator/superfície/coleção/SKUs; "pausado por X às HH:MM" no card |
| B8 | **Reparo de 9º dígito vivo** em login, Avise-me, presente (e também no Nuxt, `authPhone.ts:53`); um dígito a menos vira o celular de outra pessoa. | `packages/utils/shopman/utils/phone.py:58-61` | reparo só na porta do ManyChat; entrada de cliente recusa 10 dígitos com 9 e pede confirmação |
| B9 | **Directives esgotam em ~30 s** (`MAX_ATTEMPTS=5`, `2^n`) e `failed` é definitivo; só fiscal tem requeue manual; alerta só com ≥5 falhas/60 min. Irmão: `_alert_cancel_failed` cria alerta crítico e o emit terminal não. | `orderman/dispatch.py:24,36`; `handlers/fiscal.py:104-116` vs `:276-293` | backoff com piso/teto para topics com provedor externo; alerta com threshold 1 para directive terminal fiscal/financeira |
| B10 | **Cadeia de notificação não cai para o próximo canal em 4xx** (ManyChat 400/3011 janela fechada, SMTP recusa, Comtele 4xx → `outcome_unknown` e para). | `adapters/notification_manychat.py:175-186`; `notification_email.py:213-215`; `services/notification.py:439-442` | classificar 4xx e recusa SMTP como `provider_rejected`; `unknown` só para timeout/5xx/`URLError` |
| B11 | **Alerta crítico não sai do app** (só `UserNotification` + SSE); `SENTRY_DSN` ausente. | `observability.py:219-236`; `user_notifications.py:442-449` | `critical` → `deliver_notification` ao dono por e-mail (SMTP já entrega) com debounce por tipo; ligar Sentry (opt-in, scrub pronto) |
| B12 | **`maintenance-worker` grava heartbeat que ninguém lê**; `/ready/` `queue: ok` significa "nenhuma directive vencida", não "worker vivo". | `maintenance_worker.py:198`; `health.py:148-151` | `/ready/` lê `last_beat` dos dois workers; batimento conhecido envelhecido → `fail` |
| B13 | **Job `release` não chama o perfil de produção**; `check --deploy` não vê `EFI_SANDBOX`/`FOCUS_NFE_ENVIRONMENT`/`sk_live`. Quem barra é `make production-readiness`, fora do deploy. | `shopman/shop/checks.py` (grep = 0); `scripts/check_release_readiness.py:263-300` | release de produção executa `check_release_readiness --profile=production`, ou um `SHOPMAN_E022` que converte `status=="error"` da readiness em `Error` quando `is_production()` |
| B14 | **Runbooks de cutover errados:** zero `SHOPMAN_ENVIRONMENT`; "Autodeploy OFF" é falso (`deploy_on_push` ligado nos 12 componentes); job `bootstrap-staging` não existe; preflight diz `STRIPE_CAPTURE_METHOD=automatic` (vivo é `manual`); `ativar-focus-nfe.md:46` atribui ao `check --deploy` guarda que só a readiness tem. | `docs/runbooks/go-live-cutover.md:78-79`, `go-live-preflight.md:30,50`, `ativar-focus-nfe.md:46` | `SHOPMAN_ENVIRONMENT=production` como primeira linha do cutover, junto de `SENTRY_DSN`, remoção de `EXPOSE_MOCK_CAPTURE`/`EXPOSE_DEBUG_OTP`; apagar as linhas falsas |
| B15 | **Alpha Smoke mistura curadoria com quebra** (vermelho desde 12/09 19:42 UTC por 28 SKUs pausados à mão; sem deploy entre o último verde e o primeiro vermelho). | `.github/workflows/alpha-smoke.yml` (`assert len(sellable) >= 10`) | 1 nó por SKU (hoje 93 nós/43 SKUs), `pausados` contados à parte, piso relativo aos ativos, "tudo pausado" continua vermelho |

Latentes, sem gatilho hoje: duas gavetas ativas fazem a venda escolher turno sem `terminal_ref` (`operations.py:526-532`, seed cria um terminal só); certificado e-CNPJ A1 com vencimento anotado para 10/09/2026 só em comentário YAML e sem sonda de validade (`integration_readiness.py:411-416` só checa presença).

---

## C. Decisões reservadas ao Pablo (não implementar sem a palavra dele)

1. **Admin:** 2FA ligada ou allowlist de IP (A4).
2. **CPF novo na nota:** o #619 selou em teste (`receiptOfferEntryPoints.test.ts`) o oposto da decisão de 05/09 ("salvar já marcado, sem bloquear a venda"). Hoje: modal bloqueante por venda com CPF desconhecido, sem padrão; `PosReceiptSaveOffer.vue` ficou órfão. Qual vale?
3. **Nome do ambiente:** o alpha se declara `staging` atendendo cliente real (travas destrutivas abertas). Virar `production` exige trocar `EXPOSE_MOCK_CAPTURE` por `MOCK_PIX_AUTO_CONFIRM` (E015 aborta o deploy) — é a política do único Pix do alpha.

---

## D. O que resistiu ao ataque (não reabrir sem dado novo)

Duplo submit da venda (claim no banco) · oversell no commit (`select_for_update` no Quant) · pedido web nunca vai à cozinha sem captura · cancelamento/estorno com lock duplo e verbo de leitura no gateway · livro-caixa imutável com constraints · PIN no servidor e lock coordenado entre abas · webhooks todos fail-closed · IDOR gateado por identidade · debug de OTP inerte sem token · `DeliveryZoneRule` registrado no boot · total visto = total cobrado · checks E0xx abortam o deploy · 23 checks obrigatórios com Gate da meia-correção bloqueante · PR #619 não pôs passo a mais na venda de balcão (provado por teste).

Já corrigido no `main` que a memória dava como pendente: comanda reaberta recupera `customerLookup`; portão "CPF + taxa" removido; `receipt_email` deixou de ser identidade; Avise-me por ocorrência; authorize/capture do Stripe e da Efí alertam em vez de engolir.

---

## E. Pedido de apreciação

Peço ao Codex que:

1. **Confirme ou conteste cada item de A e B**, com arquivo:linha. Contestar é bem-vindo: este laudo já derrubou 6 de 10 P1 na própria refutação, e quer ser derrubado onde estiver errado. Vale especialmente: A1 (há alguma intenção de produto para Pix de balcão fechar antes da captura?), A2 (o checkout anônimo pela API é desejado? quatro testes dizem que sim, a projection diz que não) e B1 (a ordem `on_commit` × `_mark_tab_committed` foi escolhida em `5647a78da`; o efeito fiscal foi previsto?).
2. **Diga o que já está tratado em branch sua**: conferi `codex/pdv-*`, `codex/pos-*`, `codex/receipt-*`, `codex/customer-*`, `codex/preorder-payment-mode`, `codex/print-layouts-20260912` por `git diff origin/main...<branch> --stat` e não vi nenhum destes sites; se houver, aponte a branch e o commit.
3. **Proponha a divisão em PRs**, respeitando: PDV (A1, B1, B2, B3, B4) separado de Storefront (A2, B5, B6, B7, B8) separado de operação (B9–B15); cada PR com teste `transaction=True` onde a ordem de callbacks importa; nada de C sem a palavra do Pablo; zero residuals; `git add` por arquivo nomeado; migrações com `uniq -d` antes de abrir.
4. **Não toque** no spec vivo da DO, em credenciais, no seed do alpha nem nas decisões de C.

Os relatórios completos das seis frentes e dos três céticos, com todas as linhas citadas e as guardas procuradas, estão em `~/.claude/projects/-Users-pablovalentini-Dev-Claude-django-shopman/memory/handoff-2026-09-12-laudo-go-live.md`.
