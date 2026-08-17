# ALPHA-READINESS — Auditoria de código (2026-08-17)

Auditoria crítica de prontidão para **alpha** (testadores reais no staging, sem
dinheiro real). Complementa [ALPHA-READINESS-AUDIT](ALPHA-READINESS-AUDIT.md),
que cobre o estado de config/simulação do staging — aqui o foco é **corretude e
segurança do código**: dinheiro, concorrência, auth, superfícies públicas,
webhooks e integridade de estoque.

**Método.** 8 auditores paralelos por subsistema + testes de stress executados
de verdade em **PostgreSQL 16 + Redis** (não SQLite — travas de linha reais). A
suíte de runtime (concorrência/segurança, sem skips) passou **141/141**; a suíte
completa (~6.500) passa verde. Cada achado P1 foi **reproduzido de forma
independente** antes de entrar aqui, e os melhores viraram teste canônico.

---

## Veredito: PRONTO para alpha, com ressalvas conhecidas

Não há **nenhum P0**. Em configuração de produção **não existe** caminho para um
atacante marcar pedido como pago sem pagar, nem oversell, nem captura/estorno em
dobro, nem IDOR de pedido/conta — tudo verificado e coberto por teste sob
PostgreSQL. O único bug de dinheiro alcançável na operação normal (composição de
desconto de lote × promoção) foi **corrigido e blindado** nesta auditoria.

Os dois P1 restantes são de **go-live**, não de alpha: um é integridade de
estoque na produção (craftsman) que só diverge num crash no meio do handler; o
outro é o token do webhook Efí — e o alpha roda com pagamento **mock**, então o
webhook real nem está no caminho. Ficam listados abaixo com recomendação.

Antes de chamar testadores, **saiba** (não são bugs, são o desenho do staging):
- O staging **devolve o código OTP na resposta** (login sem SMS). Isso é
  impersonação aberta de qualquer telefone — trate o banco de staging como
  público: **não** carregue PII real, e considere um gate de borda (basic-auth/
  IP allowlist) na frente das superfícies públicas.
- Pagamento é **sintético** (`payment_mock`, auto-confirma em ~8s). "Pago" no
  alpha não moveu dinheiro.
- Oriente a entrada por "Usar outro número" enquanto o ManyChat (F3) não estiver
  no ar.

---

## Corrigido nesta auditoria (com teste canônico)

### P1 — Composição de desconto: lote × promoção/cupom/manual cobrava a MENOS
`shopman/shop/modifiers.py` — `DiscountModifier` (order 20) lia o
`unit_price_q` **já reduzido** pelo `LotDiscountModifier` (order 15) e aplicava o
percentual sobre esse preço, empilhando em vez de "maior desconto ganha". Um item
de liquidação (lote com `nonconformity_percent > 0`) comprado com uma promoção/
cupom percentual sobre o mesmo SKU — ou um desconto manual de PDV por linha —
saía por menos que o melhor desconto isolado.

- **Repro (independente):** lista R$ 10,00; lote 50% → R$ 5,00; promo 30% aplicada
  sobre os R$ 5,00 → **R$ 3,50 cobrado**, quando o correto (maior ganha) é
  **R$ 5,00**. Cobrança a menor de **15%**, silenciosa.
- **Por que o guard não pegava:** a tela e a cobrança leem o mesmo
  `line_total_q` furado, então `_ensure_total_matches` (`expected_total_q`) não vê
  divergência. Vazamento de receita consistente, não um mismatch tela×cobrança.
- **Correção:** o `DiscountModifier` passou a computar candidatos sobre o preço de
  LISTA (`_list_q`), vencer a linha só quando bate o desconto já aplicado
  (`_current_disc_q`) e reconciliar a transparência do desconto substituído
  (`_reverse_prior_pricing`) — a mesma disciplina que `LotDiscountModifier` e
  `_apply_flat_best_wins` (funcionário/happy hour) já usavam.
- **Testes:** `test_lot_pricing.py::TestLotDiscountVsPromotion` (2 casos: lote
  vence sem empilhar; promo maior substitui o lote). Falham no código antigo
  (350/480), passam no corrigido (500/600).

### P2 — Cupom derrubava a elegibilidade de frete grátis
`shopman/shop/modifiers.py` — `DeliveryFeeModifier._effective_fee_q` media o
limiar de frete grátis (`free_delivery_above_q`) sobre o subtotal **pós-desconto**,
sem somar o cupom de volta, enquanto o resto do sistema usa
`threshold_base_q = subtotal + coupon_discount` (projeção do carrinho e gate de
mínimo de entrega). Resultado: a tela dizia "frete grátis", o modifier cobrava a
taxa — e, com `expected_total_q`, o checkout barrava com `total_changed`.

- **Dormente no seed Nelson** (`free_delivery_above_q = 0`), mas ativa no instante
  em que o operador liga o limiar no admin — uma ação típica de pré-alpha.
- **Correção:** o modifier passou a somar `coupon_discount_q` de volta na base do
  limiar, espelhando `threshold_base_q`.
- **Teste:** `test_free_delivery_promotion.py::test_coupon_does_not_cost_the_customer_the_free_delivery_threshold`.

---

## Precisa endereçar antes do GO-LIVE (não bloqueia o alpha mock)

### ~~P1~~ → **P3 latente** (revisado) — `WorkOrder.finish()` grava o ledger fora da transação

> **Revisão 2026-08-17, após verificação independente em PostgreSQL.** Duas
> afirmações abaixo estavam **erradas** e a severidade estava **superestimada**.
> O mecanismo é real (reproduzido: `finish()` retorna OK, insumo consumido,
> vitrine zero, retry em `TERMINAL_STATUS`), mas: (1) o escritor de estoque é o
> receiver **#0**, então nenhum receiver anterior o preempta; (2) só a perna de
> *output* engole — a de insumos **propaga**; (3) todo gatilho de operação normal
> já está fechado (over/under-yield corrigidos com regressão, insumo insuficiente
> barrado no backstage, quant planejado ausente não é caminho de drift), então
> exige falha genuína (queda de DB/deploy no meio do handler).
>
> **O problema real é o silêncio, não a probabilidade.** Quando falha, as unidades
> ficam no quant `started`, que a política `planned_ok` (a do seed Nelson) segue
> vendendo — a loja opera normal e o fechamento *mascara* (produção sai de
> `WorkOrder.finished`). Nada alerta: os engolimentos logam `WARNING` e o Sentry
> só captura `ERROR`. O tipo `stock_discrepancy` existe e nunca é emitido.
>
> Dois achados **novos** da verificação: um receiver *posterior* estourando faz
> uma fornada commitada devolver 400 ao operador (e o retry morre em
> `TERMINAL_STATUS`, porque o backstage não passa `idempotency_key`); e o
> **quick-finish sem partição** não passa pelo guardrail de insumos.
>
> Plano de execução: [WP-ALPHA-FIX-01](WP-ALPHA-FIX-01-producao-e-efi.md).

Descrição original do mecanismo:
`packages/craftsman/.../services/execution.py:324` dispara
`production_changed` (a escrita canônica craftsman→stockman, kind=MAKE)
**depois** do bloco `transaction.atomic()`, e os handlers
(`contrib/stockman/handlers.py`) engolem exceção como "non-fatal". Se o processo
cai/erra no meio do handler: `finish()` já commitou `FINISHED` (idempotente, não
re-emite o signal no retry), os insumos não são baixados e/ou o output não é
realizado — **divergência permanente e silenciosa** de estoque, sem sweep de
reconciliação (ao contrário do lifecycle de pedido, que roda `secure_stock`
dentro do commit + `sweep_stuck_orders`).

**Recomendação:** ou envolver a escrita do MAKE na mesma transação do `finish()`,
ou tornar `_handle_finished` idempotente + um sweep de produção equivalente ao de
pedidos — e **parar de engolir** a exceção (alerta ao operador). É Core
(craftsman): mudar só depois de entender o grafo de receivers de
`production_changed` (alertas/KDS/sync não podem derrubar um `finish`).

### P1/P2 (go-live) — Webhook Efí/iFood-legado: token estático, sem HMAC do corpo, aceito na query
`shopman/shop/webhooks/efi.py:188-200`, `ifood.py:220-232`. Diferente de Stripe
(assinatura) e iFood-events (HMAC-SHA256 do corpo), o Efí usa um token
compartilhado estático que **não** vincula ao payload e é aceito como `?token=`.
Em query string, vaza para logs de LB/proxy/APM; quem o observa uma vez forja
`POST /webhooks/efi/pix/?token=…` com `valor` arbitrário e marca qualquer pedido
como pago (o `confirm_pix` confia no `valor`). Sem timestamp/nonce → replay
eterno (só o guard de idempotência de 30 dias barra duplicata exata). O mTLS é
**logado, não exigido**.

**Mitigado hoje** por: mTLS no proxy (quando presente) e o alpha rodar mock.
**Recomendação:** aceitar o token só por header, exigir mTLS de fato, e mover o
Efí para HMAC do corpo se o provedor permitir.

### P2 — Fail-open de valor no caminho legado do Efí (sem intent)
`shopman/shop/services/pix_confirmation.py:188-191`: no ramo `intent_backed=False`,
`paid_q is None → return True` — webhook autenticado sem `valor` dispara
`on_paid` sem checagem de valor. Estreito (exige o token + `txid` que casa por
`icontains`), mas é fail-open que o caminho com intent (Payman) não tem.

### P2 (verificar intenção) — Template de produção pré-arma o auto-confirm mock
`.do/app.subdomains.yaml:160` traz `SHOPMAN_MOCK_PIX_AUTO_CONFIRM=true`. Inerte
hoje (o check `SHOPMAN_E003` bloqueia `payment_mock` em produção), mas basta
alguém ligar `SHOPMAN_ALLOW_MOCK_PAYMENT_ADAPTERS=true` num deploy para todo PIX
se autoconfirmar de graça. **Recomendação:** default `false` no template de prod.

---

## Hardening recomendado (P2/P3) — por subsistema

**Concorrência**
- P2 `cancellation.cancel()` faz read-modify-write sem trava em `order.data` e
  avalia o guard contra a instância em memória — perde chaves de auditoria
  (`captured_at`/`e2e_id`) numa corrida com webhook PIX tardio. Dinheiro fica
  correto (`verify_gateway_before_timeout_cancel` trava e re-checa). Dar a
  `cancel()` a mesma disciplina `select_for_update` + re-leitura dos irmãos.
- P2 O reaper de directives requeue um handler que legitimamente passa de 10 min
  → dupla execução concorrente. Idempotentes na maioria; risco em não-idempotentes
  (notificação/KDS). Janela de reap por tópico ou heartbeat.
- P3 `_schedule_confirmation_timeout` faz check-then-create não atômico com
  `dedupe_key` vazio → timers redundantes (o 2º no-op). Usar `create_deduped`.
- P3 `StockHolds.hold` não tenta o próximo quant em contenção de trava → rejeita
  hold satisfatível (nunca oversell).

**Superfície pública (storefront)**
- P2 `POST /availability/{sku}/notify/` aceita telefone anônimo sem prova de posse
  → o remetente confiável da loja manda "voltou ao estoque" para número de
  terceiro (spam via reputação da loja). Já deduplica por (sku, telefone). Exigir
  telefone verificado ou cap global por número.
- P2/P3 `reverse_geocode` limitado a 30/m por IP, sem teto global/diário → abuso
  de custo Google via botnet. Teto diário.
- P3 `PasskeyLoginView` testa `request.limited` sem o decorator `@ratelimit`
  (checagem morta; inofensivo — webauthn é cripto).

**Antifraude de entrega**
- P2 `_coordinates_match_claimed_address` (validation.py:250-253): o ramo de
  cidade curto-circuita a checagem de CEP; numa operação de cidade única, a
  cidade sempre casa e o CEP nunca é alcançado, então dá para forjar coordenada
  "perto da loja" e pagar a menor faixa. **Não corrigido de propósito:** a
  correção ingênua (CEP estrito) bloqueia cliente legítimo cujo pin cai num
  prefixo de CEP vizinho na mesma cidade — troca fraude de ~R$ 7 por pedido
  perdido. A correção certa compara a **faixa de distância** do pin com a do CEP
  alegado (bloqueia só spoof que muda a taxa); precisa de decisão de produto
  sobre tolerância. Valor baixo, testador não edita payload — dá para ir ao alpha.

**Operador (backstage) — modelo sólido, itens de hardening**
- P2 `KDSIndexView` exige só `is_staff` (o `required_permission` declarado é
  código morto) — operador sem `operate_kds` enumera estações. Usar
  `HasBackstagePermission`.
- P2 Canais SSE `backstage-*` autorizados por `is_staff`, não pela permissão fina
  do REST equivalente → operador com só `operate_kds` assina `events/orders|
  production|alerts` (metadados). `<scope>` não validado = vazamento cross-store
  latente se virar multi-tenant. Mapear `kind`→permissão em `can_read_channel`.
- P2 PIN de 4 dígitos como 2º fator, sem rate-limit de endpoint em
  `operator/unlock/` e nos overrides de gerente (só lockout). ~1.440
  tentativas/dia/conta. Throttle por IP + política de PIN mais longa para
  `adjust_cashshift`/`manage_operators`.
- **Config:** `SHOPMAN_REQUIRE_ACTIVE_OPERATOR` default **false** → a permissão
  real é a do grupo do usuário de login do device; a camada de operador/PIN é UX
  até o flag ligar. Decidir antes do go-live.

**Deploy/observabilidade**
- P2 `/health/` e `/ready/` públicos, sem throttle, montando `MigrationExecutor`
  por hit (amplificação de DoS + disclosure de estado). Throttle/restringir à
  rede do probe; cachear o plano.
- P2 Sentry com `max_request_body_size` default "medium" → captura telefone/OTP/
  endereço em erros 500, apesar de `send_default_pii=False`. Pôr `"never"` ou
  scrubber.
- P2 Telefone do cliente logado em INFO (`verification.py:217`). LGPD.
- P3 Guards de boot por `assert` (removidos sob `python -O`) — duplicados pelos
  deploy checks, então valem no pipeline.
- P3 `SHOPMAN_ENVIRONMENT` inferido por substring "staging" pode expor debug OTP
  se um domínio de prod contiver "staging". Fixar sempre explícito.

**Auth/doorman — sem P0/P1, bem construído**
- P2 Minting de access-link sem auth quando `DEBUG=True` (`views/access_link.py:
  60-74`) — alcançável se um server DEBUG for tunelado (ngrok). Setar
  `DOORMAN_ACCESS_LINK_API_KEY` mesmo em dev.
- P2 `AccessLink.audience` nunca é exigido (escopo decorativo). Exigir ou remover.
- P2 Link de campanha encaminhado = sessão da conta-alvo (intencional,
  documentado; single-use + TTL curto). Sign-off explícito para alpha.

---

## Áreas verificadas como SÓLIDAS (não assumidas — lidas e/ou testadas)

- **Auth/OTP:** código HMAC-SHA256, `compare_digest`, cap 5/código, 5 códigos/15
  min, cooldown 60s, cap por IP, invalida anteriores. `SHOPMAN_EXPOSE_DEBUG_OTP`
  com tripla guarda (default off, exclui prod em runtime, `E010` no boot).
- **IDOR:** todo endpoint de pedido/conta passa por `get_accessible_order`/escopo
  por `customer.ref`, com 404 uniforme (sem oráculo de existência). Ref de pedido
  tem entropia baixa (~2.400/canal/dia) mas **não é o controle** — segredo do ref
  não abre nada.
- **Dinheiro:** loyalty sem double-spend/replay; cupom `max_uses` global atômico;
  `expected_total_q` guard; tampering de preço bloqueado (política internal
  re-resolve); arredondamento `ROUND_HALF_UP`; totais nunca negativos.
- **Concorrência (PostgreSQL):** oversell/holds/estoque-negativo
  (`select_for_update` + `F()` + `CheckConstraint`); captura/estorno de pagamento
  em dobro impossível (intent travado); replay de webhook barrado por chave =
  event id do gateway; máquina de estado de pedido travada; auto-confirm × cancel
  re-checam `status==NEW` sob trava; idempotência de commit.
- **Webhooks:** Stripe `construct_event` (assinatura), iFood-events HMAC do corpo,
  ambos verificam **antes** de qualquer efeito; subpagamento mantém não-pago;
  timeout consulta o gateway antes de cancelar; alerta de drift em estorno.
- **Backstage:** toda mutação de caixa/fechamento/pedido/produção/catálogo/BI é
  permission-gated; override de gerente server-side com PIN; `DayClosing` único
  (sem double-close); atribuição de caixa server-authoritative; só SessionAuth.
- **Deploy:** SECRET_KEY/ALLOWED_HOSTS/`"*"` bloqueados por assert + deploy check;
  cookies Secure/HSTS/CSP/nosniff sob prod; backend de rate-limit hard-fail se não
  for Redis; contrato de erro `{detail, field, errors}` consistente sem vazar
  traceback; perímetro de API (ViewSets CRUD desmontados).
- **Checkout/fulfillment:** faixa de distância inclusiva correta; slot de retirada
  barra passado/fechado/além do horizonte; lead-time/preorder no commit; oversell
  travado; gate de mínimo de entrega consistente tela×cobrança.

---

## Prioridade sugerida

> Execução detalhada, com as armadilhas que fazem a "correção óbvia" não corrigir
> nada, em [WP-ALPHA-FIX-01](WP-ALPHA-FIX-01-producao-e-efi.md).

1. **(go-live)** Tirar o silêncio do `finish()` de produção: parar de engolir a
   perna de output, marcador durável + sweeper, quick-finish sem partição honrando
   o guardrail de insumos, e `idempotency_key` no finish do backstage.
2. **(go-live)** Webhook Efí header-only (não há proxy mTLS no deploy — o token é a
   autenticação única); fechar o fail-open de valor; default `false` no
   auto-confirm mock do template de prod.
3. **(alpha, opcional)** Gate de borda nas superfícies públicas do staging e
   telefone verificado no stock-alert anônimo.
4. **(hardening)** `cancellation.cancel()` com trava; SSE/KDS por permissão fina;
   throttle em `/health`+`/ready` e nos endpoints de PIN; Sentry sem corpo.

Itens 1–2 encostam no go-live; nada em 1–4 bloqueia um **alpha mock** honesto.
