# Laudo adversarial da missão CORE-SOVEREIGNTY (2026-10-18)

> **Natureza:** auditoria SÓ LEITURA da missão executada por agente externo (PRs #1842–#1870).
> Nenhum código de produção foi alterado e o alpha não foi tocado.
> **Base auditada:** `origin/main @ 1efd07787`. Para comparação, o pai do merge do #1846
> (`f037515f4^1`) e `35d95104d`.
> **Método:** para cada WP, tentar provar que **não** foi cumprido, com código, sonda executável
> ou saída de comando. Quando o documento contradiz o código, vale o código. As sondas vivem fora
> do repositório, no scratchpad da sessão (`csadv/`). Este laudo descreve cada uma o bastante para
> reproduzi-la.
> **Ambiente de teste:** worktree com `-o "pythonpath=. packages/<todos>"`, porque o `.venv` da raiz
> aponta os editable installs para a árvore principal. SQLite de `config.settings_test`.

---

## 1. Placar

| WP | PRs | Veredito | Pior achado |
|---|---|---|---|
| WP-1/9 lei e governança | #1843, #1844 | **CUMPRIDO** | (nenhum que derrube) |
| WP-8 mapa de camadas | #1845 | **PARCIAL** | Leitura (GET) que grava continua como dívida aceita (6 entradas, 7 chamadas) |
| WP-2 promessa (stockman) | #1846, #1848, #1850 | **PARCIAL** | P1: o read-side e o ingresso do checkout recalculam a promessa e divergem do Stockman |
| WP-3 preço | #1851, #1852, #1855, #1856 | **PARCIAL** | P1: a revisão do PDV recalcula o desconto de linha; venda determinística travada em `total_changed` |
| WP-4 identidade (doorman) | #1853 | **PARCIAL** | **P0**: o número antigo continua abrindo a conta depois da troca de telefone |
| WP-7 unidades do orquestrador | #1858, #1860, #1861 | **PARCIAL** | P1: 8 constantes de instância pendentes; a decisão de promoção ainda tem 3 implementações |
| WP-11 Admin × superfícies | #1859 | **CUMPRIDO** (prova declarativa) | P2: classificação manual sem cruzamento |
| WP-10 topologia | #1862, #1863 | **PARCIAL** (menor) | P2: falta a ADR de topologia |
| WP-6 Instância | #1864–#1869 | **PARCIAL** | P1: `seed --flush` cria duas `Shop`; o apply apaga, sem avisar, o que o operador mudou |
| WP-12 renascimento | #1870 | **PARCIAL** | P1: o gate de docs e o teste puro do piloto não rodam na CI |

**Contagem:** 1 P0 · 18 P1 · P2 listados por WP (detalhe nas seções 2.3 e 3).

**Desempenho:** consultas subiram em catálogo (+1), produto (+2), PDV (+2) e checkout (+23). Nenhum
caminho piora mais de 10%, e nenhum orçamento foi afrouxado (seção 2.3).

### Critérios de aceite globais (plano §7)

| # | Critério | Veredito | Evidência curta |
|---|---|---|---|
| 1 | Soberania: o wheel instala em ambiente limpo e passa a suíte | **FALSO** | Nenhum job constrói wheel. A suíte de soberania instala 3 de 12 kernels com `--no-deps` e só faz `import`. A suíte do doorman importa guestman 40×, shop 5× e storefront 1×. |
| 2 | Um dono por decisão | **FALSO** | 4 decisões com 2+ implementações, provadas: promessa (A2-1), desconto de linha do PDV (A3-1), elegibilidade de promoção (A7-4) e resolução de identidade no dispositivo confiável (A4-2) |
| 3 | Contrato explícito, sem sentinela | **PARCIAL** | `reserve()` devolve `dict` com `error_code` aberto (`hold_failed`, `product_not_found`, código cru do hold). `not_in_listing` usa `available_qty=Decimal("0")`. |
| 4 | Fronteira kernel→kernel e ingresso que não decide | **PARCIAL** | Os gates de import estão verdes, mas não veem `apps.get_model` em código de domínio. Exemplo: o orderman consulta `guestman.Customer` por ORM no commit. O ingresso do checkout bloqueia por um falso "faltou estoque". |
| 5 | Localidade (métrica do piloto) | **PARCIAL** | A métrica "3→2" foi declarada à mão em `.md`, sem cálculo. Mutantes de segunda implementação passam pelo gate. |
| 6 | Regime de corte, zero legado | **PARCIAL** | Resíduos vivos: o alias `price_q` no ingresso do PDV; o fallback `is_tracked ← positions`; o leitor velho de `hold_ids` em `diagnose_remote_order`; a fixture autouse `_legacy_unit_channel_config` em toda a suíte |

---

## 2. Regressões e desempenho

### 2.1 Suítes executadas (na worktree, código de `origin/main`)

| Suíte | Resultado |
|---|---|
| stockman | 357 passed, 14 skipped |
| offerman | 300 passed, 1 skipped |
| orderman | 332 passed, 1 skipped |
| craftsman | 523 passed, 2 skipped |
| payman | 189 passed, 2 skipped |
| cashman | 80 passed, 1 skipped (exige `-o pythonpath=". ../utils ../refs"`; o `pyproject` do cashman só declara `.`, então na worktree ele carrega o `utils` da árvore principal) |
| buyman · fiscalman · refs · utils | 87 · 34 · 177 · 160 passed |
| doorman · guestman | 395 passed, 2 skipped · 528 passed, 14 skipped |
| framework focado (209 arquivos de estoque, preço, promoção, PDV, checkout, grupo, Xepa, frete e catálogo) | 2660 passed, 25 skipped, 1 falha de harness |
| framework completo (shop + storefront + backstage + config, `-n 8`) | sem nenhuma falha até 94%; depois o xdist travou (`OSError: cannot send`) e o run foi encerrado |
| gates (arquitetura, imports, Admin, registro de superfícies) | 54 passed |
| unidades do orquestrador + piloto puro (`-p no:django`) | 104 passed |
| contratos e descritores de Instância | 23 passed; checker rc=0; 7 passed |
| regressões de #1867/#1868 (13 arquivos) | 297 passed |
| auth/OTP/identidade (37 arquivos) | 445 passed, 1 skipped |

A falha de harness é `test_pos_headless_surface_contract::test_products_exclude_a_listing_outside_its_canonical_validity`:
`execnet DumpError: can't serialize datetime.date`, um subtest sob xdist. Isolado, o teste passa
(`1 passed, 3 subtests passed`).

**Tudo verde, e mesmo assim o P0 e quatro P1 deste laudo existem.** O verde não prova a missão.
Para cada caso, a seção 3 diz qual teste faltou.

### 2.2 Entregas recentes que a missão poderia ter quebrado

- **Preço por grupo (#1784)** e **desconto por grupo no PDV (#1766):** as suítes passam
  (`test_persona_2_group_pricing`, `test_pos_desconto_por_grupo`). O `PriceTier` continua resolvido
  em `modifiers.py:628`. Não achei regressão.
- **Xepa só no balcão (#1760)** e **loja paga ao pedir (#1769):** `test_xepa_so_no_balcao.py` e
  `test_loja_paga_ao_pedir.py` passam. O #1867 mexeu nos dois testes, mas só no encanamento (o
  descritor), sem tirar nenhuma asserção.
- **Frete grátis no PDV (#1775):** o piloto trocou a borda de `test_free_delivery_promotion.py` de
  `qty=5` (exatamente o mínimo) para `qty=6` (`git diff a86537795^1 a86537795`). O comportamento
  continua equivalente, e a borda está coberta no teste puro. Só que o teste de banco deixou de
  exercitar a borda, o que é parte de como a métrica caiu (A7-6).
- **Watchman (#1782/#1788/#1807):** `shopman.watchman` não está instalado no `.venv`. O gate de
  Admin só roda com `sys.path` explícito. Fora isso, não achei regressão.
- **Fechamento do PDV com desconto de linha:** é regressão **comportamental** do #1856, descrita
  em A3-1. Antes do selo, a diferença era de 1 centavo de troco, calada. Depois, a venda é recusada.

### 2.3 Desempenho

**Método.**

- **Mesmo arquivo de medição nos dois commits:** BASE `f35b1875d`, pai do merge do #1846, contra AGORA `1efd07787`.
- **Banco:** SQLite em memória.
- **Dados:** 30 produtos, listings `web` e `vip`, `PriceTier` VIP e cliente VIP logado.
- **PDV:** 6 comandas, 3 estações e turno aberto.
- **Medição:** 2 aquecimentos e depois N=15 com `CaptureQueriesContext`.
- **Tempo:** a máquina estava com load average entre 7 e 25, por isso a parede não discrimina (o mesmo commit variou de 21 a 67 ms). A medida estável é a contagem de chamadas por request no cProfile.
- **Integridade:** o próprio teste confere que os pacotes vêm da worktree.

| Caminho | Consultas base → agora | Chamadas por request |
|---|---|---|
| GET menu / home / catalog (anônimo) | 22 → **23** | +4,8% a +5,5% |
| GET produto (anônimo / VIP) | 58 → **60** / 76 → **78** | +5,0% / +4,2% |
| GET menu, VIP | 40 → **41** | +4,5% |
| GET sacola / PUT item (VIP) | 32 → 32 / 97–105 → 97–105 | +0,2% / +0,7% |
| **POST checkout** (retirada, dinheiro) | 257 → **280 (+23)** | +6,9% |
| **GET backstage/pos/** | 43 → **45** | +6,9% |

Nenhum caminho piora mais de 10%. Nenhum orçamento de consulta foi afrouxado: em 69 arquivos
com orçamento, só houve acréscimos. Também não apareceu N+1 novo.

**AP-1 · P2 · Preço de vitrine: +1 consulta por chamada.**

- O `listing_price_map` (`shopman/shop/projections/catalog_context.py:431-455`) agora delega para `CatalogService.unit_prices`.
- Lá dentro (`packages/offerman/shopman/offerman/service.py:148-166`) sai um SELECT de `Product`, só para o fallback de `base_price_q`, com um `ORDER BY name` inútil. Depois vem o SELECT de `ListingItem`.
- `test_cart_query_budget.py` passou a **consagrar** as 2 consultas.
- **Correção:** trazer `product__base_price_q` no join do `ListingItem`, buscar `Product` só para os não listados e usar `.order_by()`.

**AP-2 · P2 · PDV: +2 consultas.**

- `backstage/projections/pos.py:1212-1245` já tem os `ListingItem` com `select_related` em memória e mesmo assim chama `unit_prices`, que lê tudo de novo.

**AP-3 · P2 · Checkout: +23 consultas (+9%).**

- O novo efeito `session_takeover` (`shop/services/checkout.py:573-605`) custa uma Directive, uma idempotência dupla e 4 SAVEPOINTs.
- O selo e a reconsulta de idempotência do #1856 também entram na conta. Esse é custo de correção, aceitável.
- **Correção:** ler as 4 Directives num único `dedupe_key__in`. Não criar Directive para `session_takeover` sem sessão superada, que é o caso comum.

---

## 3. Achados

Severidade: **P0** bloqueia go-live · **P1** corrigir antes do go-live · **P2** depois.

### WP-4 · Identidade

**A4-1 · P0 · O número antigo continua abrindo a conta depois da troca de telefone (regressão do WP-4).**

- **Mecanismo:**
  - Desde o #1853, o `IdentityResolver.resolve()` lê `CustomerIdentifier` (`packages/guestman/shopman/guestman/adapters/auth.py:29-35`).
  - O login OTP grava esse identificador (`auth.py:158-171`, `bind_verified_handle` → `get_or_create`).
  - A troca de número no orquestrador (`shopman/shop/services/account.py:280-300`, `_set_primary_phone`) só apaga ContactPoints, nunca o identificador.
  - A troca de e-mail tem a mesma lacuna (`account.py:401-450`).
  - Antes do WP-4, o login resolvia por `get_by_phone`, que só olha ContactPoint. O identificador esquecido ficava inerte. A fusão das duas fontes o reativou.
- **Prova (reexecutada por mim):** sonda pytest `csadv/wp4_test_old_phone_after_change.py`, com o fluxo: login OTP com OLD, depois `_set_primary_phone(NEW)`, depois login OTP com OLD.
  ```
  customer.phone: +5543999996662
  identifiers after change: [('phone', '+5543999996661')]
  resolve(OLD) -> True
  login with OLD number after change: success= True same account= True None
  ```
  É o sequestro por número reciclado que o próprio código diz impedir. Quem recebe o número antigo da operadora entra na conta.
- **Por que o verde não pegou:** `test_entrar_pelo_numero_antigo_nao_abre_a_conta_de_quem_o_deixou`
  (`shopman/storefront/tests/api/test_troca_de_telefone.py:427`) entra com `force_login`. Sem OTP
  real, o identificador nunca é criado.
- **Correção proposta:**
  - A troca ou remoção de contato vira operação do Guestman, exposta pela bridge. Essa operação retira junto o `CustomerIdentifier` do mesmo valor (phone/whatsapp e email).
  - O teste de regressão faz login OTP real antes da troca, nos dois canais.

**A4-2 · P1 · O orquestrador resolve identidade fora do porto, sem falhar fechado.**

- **Onde:** `shopman/shop/services/auth.py:361-363`. O `trusted_device_login` usa `customer_by_phone` → `get_by_phone`, que escolhe o dono por ordenação.
- **Prova:** sonda `csadv/wp4_test_trusted_device_divergence.py`. A cliente A tem ContactPoint WHATSAPP X; a cliente B tem CustomerIdentifier phone X. O porto levanta `IdentityConflict`, enquanto o orquestrador devolve A. É a mesma decisão com dois donos.
- **Correção:** chamar `get_adapter().resolve_identity("phone", ...)` e tratar `IdentityConflict` como "dispositivo não confiável".

**A4-3 · P1 · A origem da verificação é falsa na troca de número.**

- `account.py:290` grava fixo `OTP_WHATSAPP`, mas a cadeia de produção é `sms,email` (`config/settings.py:1177-1180`).
- A linha é anterior à missão; o WP-4 reescreveu a função e a manteve.
- **Correção:** gravar o `delivery_method` real do `VerificationCode`.

**P2 do WP-4:**

- Mensagens novas do porto ("This handle belongs to another account.", "Identity ownership is conflicting.") chegam em inglês ao cliente, porque `verify_error_message` (`shop/services/auth.py:321-333`) não as traduz.
- `identity_by_customer_ref` (`auth.py:28-42`) instancia `IdentityResolver()` direto, ignorando a setting, e engole `Exception`.
- O conflito na bridge do ManyChat fala dois dialetos: `ValueError` e `IdentityConflict`.
- O G3 do Guestman (`gates.py:147-153`) não conhece `otp_email`.
- O teste com fake (`doorman/tests/test_identity_port.py:98-129`) afirma constantes do próprio fake.
- Há telefone em claro em log em `shop/adapters/otp_manychat.py:65` e em `otp_sms_twilio.py:69`, fora da cadeia padrão.

**O que tentei derrubar e não consegui:**

- **Import de kernel no doorman:** zero em produção, verificado por AST, inclusive imports tardios e `get_model`.
- **O inverso:** `guestman/adapters/auth.py` só importa o doorman de forma tardia e carrega com o doorman bloqueado.
- **Legado:** zero `hasattr`, `target_kind`, `AuthCustomerInfo` ou `# DEPRECATED`.
- **Conflito:** falha fechado em todas as entradas do doorman.
- **`revoke_device`:** preso ao sujeito.
- **`OTP_EMAIL`:** só choices, sem dual-read.
- **Soberania em tempo de execução:** com 12 namespaces de kernel bloqueados em `sys.meta_path`, o doorman importa 48 módulos e completa `request_code`/`verify` por handle secundário com um resolver fake.

### WP-2 · Promessa

**A2-1 · P1 · O read-side e o ingresso do checkout recalculam a promessa e divergem do Stockman.**

- **Onde a regra foi copiada.** As cópias leem o `dict` cru de `availability_for_sku` e refazem a regra: `demand_ok` ilimitado, pausado recusa, `qty` comparado com `total_promisable`. Ficam em:
  - `shopman/shop/projections/checkout.py:54-56`;
  - `shopman/shop/projections/cart.py:594-622` (`_line_availability`);
  - `shopman/shop/projections/catalog_context.py:893-990` (`_merge_waitlist_availability`, `bundle_availability_from_components`).
- **O que a cópia do checkout ignora:** `is_tracked`. Ela ainda trunca kg com `int(...)`.
- **Por que isso decide:** o ingresso `shopman/storefront/intents/checkout.py:143-155` usa esse resultado para recusar o checkout (`errors["stock"]`).
- **Prova:** sonda `csadv/test_csadv_untracked_checkout.py`, com um produto vendável e publicado, sem Quant.
  ```
  RAW {'is_tracked': False, 'total_promisable': Decimal('0'), 'availability_policy': 'planned_ok', 'is_paused': False}
  STOCKMAN_DECISION approved= True is_tracked= False
  SHOP_CHECK ok= True
  CHECKOUT_PROJECTION shortfalls= (StockShortfallProjection(... requested_qty=2, available_qty=0),)
  ```
  O Stockman e o `availability.check` aprovam, mas o checkout da loja recusa com "faltou estoque". A cópia é anterior à missão (`git log` de `projections/checkout.py`). Mesmo assim, o aceite do WP-2 ("produção chama o Stockman", "um dono") não se sustenta enquanto ela decide.
- **Correção:** o read-side e o ingresso consomem `decision_from_availability` (ou `availability.check`), somando o hold próprio como entrada da decisão. Apagar as três cópias.

**A2-2 · P2 · O aceite "produção chama o Stockman" é grep de texto.**

- `shopman/shop/tests/test_stockman_promise_sovereignty.py` afirma presença ou ausência de strings: `'Decimal("999999")' not in ...` e `"decision = decision_from_availability(" in ...`. O teste ficaria verde com `Decimal(999999)` ou com a cópia em outro arquivo, como em A2-1.
- **Correção:** um teste de comportamento que compare `availability.check` com `decision_from_availability` numa matriz (rastreado, não rastreado, `demand_ok`, pausado, kg).

**A2-3 · P2 · O vocabulário de recusa não está fechado no caminho de reserva.**

- `services/availability.py` devolve:
  - `error_code` igual a `error_code or "hold_failed"` (linha ~1097), que repassa o código cru do hold (`INSUFFICIENT_AVAILABLE`);
  - `"product_not_found"` (`adapters/stock.py:116`);
  - `e.code if hasattr(e, "code") else "hold_failed"` (`adapters/stock.py:199`).
- `not_in_listing` sai com `is_paused=True` em `_reserve_listing_gate_error` e com `is_paused=False` em `_listing_gate_decision`. É o mesmo portão, escrito duas vezes com saídas diferentes.
- `_reserve_across_quants` tem três defeitos:
  - devolve `int(qty)` e trunca kg;
  - divide por `// 2`, o que zera fração;
  - mantém `hold_id` "for compatibility".
- O teste A5 só proíbe a grafia `insufficient_stock`; não prova vocabulário fechado.
- **Correção:** enum de recusa do orquestrador compondo o `PromiseReasonCode`; um portão de vitrine só; quantidade em `Decimal`.

**A2-4 · P2 · Leitores do formato antigo de `hold_ids` e fallback de tracking.**

- `shopman/shop/management/commands/diagnose_remote_order.py:105-116` trata `hold_ids` como lista de ids (`Hold.objects.filter(id__in=hold_ids)`). O formato canônico é lista de `dict` `{sku, hold_id:"hold:N", qty, is_tracked}`, então o diagnóstico não funciona com dado atual.
- `projections/order_tracking.py:897` filtra `isinstance(entry, dict)`, o que tolera o formato velho em silêncio.
- `packages/stockman/.../availability.py:315` lê `info.get("is_tracked", bool(info.get("positions")))`, um fallback para `dict` sem `is_tracked`, coisa que o Stockman não produz mais.
- **Correção:** ler só o formato canônico e falhar gritando.

**O que não consegui derrubar:**

- `promise_decision_from_availability` e `999999` sumiram do runtime.
- O `check()` delega para `decision_from_availability` (`services/availability.py:589`).
- `PromiseDecision` separa `available_qty` e `orderable_ceiling`.
- O marcador de não rastreado tem uma forma só, e o leitor recusa as formas históricas.

### WP-3 · Preço

**A3-1 · P1 · A revisão do PDV é uma segunda implementação do "maior desconto ganha", e trava venda.**

- **As duas contas:**
  - `shopman/shop/services/pos.py:3794-3847` (`_payload_line_discounts_q`) declara "A MESMA CONTA do kernel (`DiscountModifier._calc_manual`)", mas faz `int(round(list_price_q * value / 100))`. O `round` do Python arredonda meio centavo para o par.
  - O kernel (`modifiers.py:1352`) faz `monetary_div(...)`, com `ROUND_HALF_UP`.
- **Encadeamento:** o fechamento sela `expected_total_q` = total da revisão (`pos.py:862-873`, `CommitAuthority.OPERATOR_REVIEWED`). O Orderman confere esse total contra o motor (#1856).
- **Prova 1 (paridade pura):** sonda `csadv/pos_discount_parity.py`, comparando as duas funções reais. Preços de 1 a 5000 centavos e 5%/10%/15%/25%/50%.
  ```
  casos: 25000 divergentes: 2375
  ```
- **Prova 2 (ponta a ponta):** sonda `csadv/test_csadv_pos_rounding.py`, com caixa aberto e cortesia de 10%.
  ```
  REVIEW 1205 1085
  CLOSE_REFUSED 1205 PosIntentError total_changed O total mudou de R$ 10,85 para R$ 10,84. ...
  REVIEW 1300 1170
  CLOSE_OK 1300 1170
  ```
  Um item de R$ 12,05 com 10% de cortesia **não fecha nunca**: cada nova revisão volta a dizer R$ 10,85. Antes do #1856, a mesma diferença virava 1 centavo de troco errado, calado (a classe do incidente PDV-260826-V03). O selo transformou isso em recusa permanente.
- **Por que o verde não pegou:** `test_pos_line_discount_matches_kernel.py` usa só valores com
  divisão exata (510×10% = 51) e nunca chama `_calc_manual`.
- **Correção:**
  - A revisão usa o total do motor. O `_stamp_engine_prices` já roda a sonda de pricing do kernel.
  - Apagar `_payload_line_discounts_q` como conta própria.
  - Paliativo mínimo: chamar `DiscountModifier._calc_manual`.
  - Teste de paridade por varredura.

**A3-2 · P1 · O PDV anuncia promoção de aniversário sem o filtro canônico.**

- `shopman/backstage/projections/pos.py:1036-1044` filtra `Promotion.objects.filter(is_active=True, birthday_only=True, valid_*)` sem canal e sem excluir as promoções de cupom.
- O canônico, `services/promotions.py:20-41` (`get_active_promotions`), exclui cupom e aplica `applies_to_channel`. O rótulo pode prometer uma promoção que o reprice não aplica.
- **Correção:** usar `get_active_promotions(now, channel_ref=...)`.

**A3-3 · P2 · Alias legado no ingresso do PDV.**

- `shopman/shop/services/pos_intent.py:359` lê `item.get("unit_price_q", item.get("price_q", 0))`. A superfície só manda `unit_price_q` (`surfaces/pos-nuxt/app/utils/posIntent.ts:145`).
- **Correção:** apagar o fallback.

**O que não consegui derrubar:**

- `services/pricing.py::resolve` não existe mais, e há teste que garante isso.
- `ContextualPrice.adjustments[]` sobrevive no contrato do catálogo e da PDP.
- O selo de revisão e total (`CommitSeal`) vale para todas as autoridades.
- Não há segundo algoritmo de faixa (`min_qty`) fora do Offerman nos consumidores nomeados.

### WP-7 · Orquestrador

**A7-1 · P1 · O critério "nenhuma constante de instância" não foi cumprido, e o teste congela a dívida.**

- `docs/architecture/orchestrator-instance-debt.json` tem 8 itens, todos `pending`, com alvo no WP-6 ou no WP-11 (já mergeados):
  - `adapters/_sms.py:20` (`DEFAULT_CODE_MESSAGE` com "Nelson Boulangerie");
  - `courier_machine.py:46` (`USER_AGENT` com o domínio);
  - `watchman_infrastructure.py:116,129`;
  - `setup_commercial_groups.py` ("Aliança Francesa");
  - `brand_tokens.py`;
  - `rules/suggestion.py` (`DEFAULT_*_PARAMS`).
- `scripts/tests/test_check_orchestrator_units.py:44` exige `pending > 0`, ou seja, falha se a dívida zerar.
- O validador só aceita `status == "pending"` (`check_orchestrator_units.py:1240`).
- **Correção:** mover os itens para descritor, settings ou `Shop`. Inverter a asserção para `== 0`.

**A7-2 · P1 · A constante que o plano cita pelo nome continua no código, e o detector não a vê.**

- `shopman/shop/modifiers.py:47-49` define `DEFAULT_TIME_WINDOW_DISCOUNT_PERCENT = 25`, `DEFAULT_TIME_WINDOW_START = "17:30"` e `DEFAULT_TIME_WINDOW_END = "18:00"`. São o Happy Hour do Nelson, usados como fallback silencioso em `modifiers.py:155-160`.
- O plano §2.3 cita `DEFAULT_TIME_WINDOW_START` pelo nome. O detector só procura nomes próprios (`check_orchestrator_units.py:1230,1253-1258`).
- **Correção:** `RuleConfig.params` obrigatório, falhando sem ele. O detector passa a pegar `DEFAULT_*` com literal numérico ou de hora.

**A7-3 · P1 · As regras (a) "não reimplementar decisão" e (c) "um entrypoint" são verificadas só por nome.**

- Testei mutantes contra uma cópia do repositório, com `gate.validate(root=cópia)`.
- **Pego:** importar `shopman.stockman` sem declarar, reportado como `domain-drift`. A regra (b) é real.
- **Passa:** `DiscountModifier._reaches_floor` com uma segunda comparação de `min_order_q`.
- **Passa:** `coupon_minimum_eligible` em `services/cart.py`, declarado na unidade existente. É política nova nascendo fora de `policies/`.
- A regra (c) é unicidade das strings `question`/`public_entrypoint` (linhas 1438-1441).
- Há 189 unidades `policy:true` e só 1 em `policies/`.
- **Correção:** `policies/` obrigatório para unidade de política nova (as existentes ficam numa lista congelada) e detecção de comparação sobre campo possuído por política fora do entrypoint dela.

**A7-4 · P1 · A elegibilidade de promoção continua com três implementações.**

- As três:
  - `modifiers.py:1237-1246` (`DiscountModifier._matches`);
  - `services/cart.py:447-487` (`customer_eligible_for_promotion`, que se diz espelho do `_matches`);
  - `services/fomo.py:199-206`, que refaz aniversário, segmento, fulfillment, mínimo, SKU e coleção.
- O piloto extraiu só a comparação de mínimo. O gate também só olha `shopman/shop`; storefront e backstage ficam fora dele.
- **Correção:** `promotion_matches(promo, ctx)` em `policies/promotion.py` e as três chamam.

**A7-5 · P2 · Nada impede `modifiers.py` de crescer.**

- 1491 linhas e 7 classes em `35d95104d`; 1893 linhas e 9 classes agora.
- Nenhuma classe nova entrou depois do WP-7, mas não há trava.

**A7-6 · P2 · A métrica do piloto ("3→2") é declarada à mão.**

- O número só existe em `docs/architecture/PROMOTION-PILOT.md`. Nenhum script o calcula.
- Parte da queda veio da troca da borda do teste (ver 2.2).

**O que não consegui derrubar:**

- O teste puro do piloto não depende de Django: 104 passed com `-p no:django`, e `policies/promotion.py` não tem imports.
- O piloto não é fachada: todo `min_order_q` em `modifiers.py` e `adapters/pricing.py` delega.
- Não existe `mixed`: as 442 unidades têm uma responsabilidade cada.
- `scripts/check_orchestrator_units.py` passa (487 fontes, 442 unidades).

### WP-6 · Instância

**A6-1 · P1 · `seed --flush` sobre banco que já teve loja cria duas `Shop` (regressão do WP-6).**

- `_materialize_instance` roda antes de `_seed_shop` (`config/management/commands/seed.py:1134`). O `_flush` apaga `Shop` sem reiniciar a sequência (`seed.py:2022`), então o apply cria a loja com pk=2. O `_seed_shop` faz `update_or_create(pk=1)` (`seed.py:1511`).
- **Prova:** sonda `csadv/wp6_shop_probe_test.py`.
  ```
  after _seed_shop shops: [(1, '', 'Nelson Boulangerie'), (2, 'Nelson Boulangerie', '')]
  channel pdv shop_id: 2 Shop.load pk: 1
  ```
- Os canais apontam para uma loja e o `Shop.load()` devolve outra, com nome vazio. Os testes passam porque partem de banco virgem.
- **Vira P0 se o go-live passar por reseed do alpha.**
- **Correção:** o seed atualiza a loja que o apply criou. Teste de `--flush` sobre banco usado.

**A6-2 · P1 · O apply corrige drift sem relatar e apaga estado operacional.**

- `config/instance_descriptors.py:216-236` sobrescreve `Channel.config` inteiro e `is_active`. O retorno conta só os registros criados.
- **Prova:** canal desligado pelo operador, com `activation` gravada e `safety_margin` 5. Depois do apply: `channels_created: 0`, `is_active: True`, `activation: None`, `safety_margin: 0`.
- `RuleConfig` mostra o mesmo: `discount_percent` 99 voltou a 25, com `rules_created: 0`.
- O apply não registra versão, hash nem trilha.
- **Correção:** diff antes, relato por mudança, recusa sem flag explícita, e `activation`/`paused_skus` fora do que o apply possui.

**A6-3 · P1 · O dump exporta estado operacional, e o filtro de segredo é uma denylist.**

- `project_from_database` copia `Channel.config`, `RuleConfig.params` e `task.config` inteiros (linhas 103-129). O registro `activation` (`by`, `approved_by`, `reason`, `at`) sai no dump.
- `assert_export_safe` usa uma regex de nome. Passaram: `pix_key`, `chave_pix`, `webhook_hmac`, `authorization` (JWT de exemplo), `signing` (valor `whsec_` de exemplo), `senha` e `certificado_a1`.
- **Correção:** allowlist pelos campos do dataclass `ChannelConfig`, recusando chave desconhecida.

**A6-4 · P1 · RBAC com duas fontes.**

- `setup_groups` roda em todo deploy (`.do/app.subdomains.yaml:1163`, `.do/app.alpha-subdomains.yaml:1451`) e faz `.set()` dos 13 grupos do Nelson. O `nelson.json` declara os mesmos grupos.
- Na counter-minimal, depois do release, sobram 14 grupos.
- **Correção:** o release aplica as personas do descritor da Instância configurada.

**A6-5 · P1 · Segunda definição do canal WhatsApp.**

- `shopman/shop/management/commands/bootstrap_whatsapp_channel.py:36-45` tem um `CHANNEL_CONFIG` próprio, divergente do `nelson.json`: sem `fallback_chain`, `safety_margin` nem `waitlist`. Ele roda no release do alpha.

**A6-6 · P1 · A suíte inteira roda com o fallback que o #1868 tirou da produção.**

- `shopman/conftest.py` tem a fixture autouse `_legacy_unit_channel_config`. Ela captura `InstanceConfigurationError` e devolve defaults em todo teste sem a marca `instance_runtime_strict`.
- Só 5 arquivos usam a marca. Os outros ~4.000 testes não detectam um caminho que hoje dá 500 por falta de canal.
- **Correção:** estrito por default.

**A6-7 · P1 · Silêncios e políticas do Nelson ainda no código.**

- `config.py:670-676` (`_safe_init`) descarta chave desconhecida: `safty_margin: 9` foi aceita e virou default.
- O prazo do Pix tem duas fontes (`payment_efi.py:340-344`).
- O limiar de aprovação do PDV mora só em settings (`pos.py:4144`).
- `receipt_escpos.py:73` imprime "NELSON BOULANGERIE" fixo.
- O kernel `doorman/conf.py:112` tem `PASSKEY_RP_NAME="Nelson Boulangerie"`.
- Há cerca de 30 defaults `"pdv"` e 55 `"web"`, inclusive no kernel cashman (`terminal.py:16`).

**P2 do WP-6:**

- A suíte de soberania cobre 3 de 12 kernels e não carrega models, migrations nem suíte.
- A suíte de evolução não simula upgrade de pacote nem migration.
- A composição não faz request: na counter-minimal, `/health/` responde 200, mas `/api/v1/storefront/catalog/` levanta `InstanceConfigurationError`.
- `pipelines`, `pricing_policies`, `units` e `fiscal_profiles` ficaram fora. `NotificationTemplate`, `PriceTier` e `Promotion` do Nelson seguem como literais no `seed.py`.

**O que não consegui derrubar:**

- O runtime não lê o descritor, e há trava AST para isso.
- As 19 remoções do #1868 viraram exceção, não outro default.
- O rollback é real (atomic sobre banco, falhando depois de gravar).
- O apply é idempotente.
- O `diff` sai com código 1 quando há drift.
- Nenhuma asserção de negócio foi removida sem substituto.

### WP-8 · Fronteira de entrega

**A8-1 · P1 · Leitura (GET) com efeito continua aceita como dívida.**

- `shopman/shop/tests/test_import_boundaries.py:106-113` (`LEGACY_GET_WRITE_DEBT`) lista 7 chamadas de escrita em GET:
  - `tracking.py`: `ensure_payment_intent`, `reconcile_payment_with_gateway_if_due`, `consume_just_placed`;
  - `notifications.py`: `reconcile_user_notifications` ×2;
  - `print_jobs.py`: `reconcile_job_state`;
  - `surface.py`: `ensure_active_collection`.
- Um GET de acompanhamento que **cria** intenção de pagamento ou concilia com o gateway é efeito externo em leitura.
- O detector só olha métodos chamados `get` e chamadas com prefixo de mutação. Uma projeção que chame um service de escrita sem esse prefixo passa.
- **Correção:** zerar a lista antes do go-live, movendo as 7 chamadas para POST/worker. Estender o detector a projeções que importam serviços de comando.

### Fronteira de kernel (critério 4)

**AK-1 · P2 · Os gates de import não veem acoplamento por `apps.get_model` em código de domínio.**

- `packages/orderman/shopman/orderman/services/commit.py:694` e `services/modify.py:62` consultam `guestman.Customer` por ORM com os campos `phone` e `contact_points__value_normalized`.
- `orderman/integrations.py:18` usa `get_model("shop","Channel")`.
- `craftsman/models/recipe.py:404` usa `get_model("offerman","Product")`.
- Todos são anteriores à missão (set/2026), mas o critério "kernel→kernel proibido" se declara cumprido. `test_domain_kernels_do_not_import_each_other_outside_bridges` só olha `import`.
- **Correção:** porto de identidade ou bridge em `adapters/`. O gate passa a pegar `get_model("<outro kernel>"`.

### WP-10, WP-11, WP-12

- **A12-1 · P1 · Gates que não rodam na CI.** `.github/workflows/runtime-gate.yml:94-97` não roda `check_docs_governance.py`, `test_check_docs_governance.py`, `test_promotion_minimum_policy.py` nem `check_instance_descriptors.py`; eles existem só no Makefile. **Correção:** acrescentá-los ao job de qualidade.
- **A12-2 · P2 · O teto histórico de links conta por tipo, não por link.** `docs/governance/docs-link-debt.json` = `{missing_target: 394, outside_repo: 37}`: consertar um link velho "paga" um quebrado novo. O gate só varre `docs/**`; fora dele, `tools/pos-counter-agent/README.md:18` aponta para um plano inexistente.
- **A10-1 · P2 · Não há ADR de topologia (app único, shell ou federado).** O kitchensink saiu de produção corretamente: `kind: internal`, sem tile e sem ingress.
- **A11-1 · P2 · Classificação declarativa sem cruzamento.** `docs/reference/admin-surface-boundary.json` diz `shop.promotion` = `rare`, enquanto o workflow `marketing-offer-crud` diz `daily`. Nenhuma tarefa diária só no Admin foi encontrada.

---

## 4. Perguntas ao dono (responda com 1 ou 2)

1. **Troca de telefone ou e-mail (P0, A4-1).**
   1. A troca passa a apagar também o identificador antigo, e todo login exige o contato atual. **(recomendado)**
   2. O login deixa de ler o identificador e volta a olhar só o contato.

   A 1 conserta na origem e mantém o login por handle secundário que o WP-4 pediu.

2. **Revisão do PDV (A3-1).**
   1. A revisão mostra o total que o motor calcula, e a conta paralela do PDV é apagada. **(recomendado)**
   2. Manter a conta do PDV, corrigindo só o arredondamento.

   Com a 2, a próxima regra de desconto volta a divergir.

3. **SKU vendável sem estoque controlado, no checkout da loja (A2-1).**
   1. Vale a regra do canal (`allow_untracked`), como o Stockman já decide. **(recomendado)**
   2. A loja recusa sempre o SKU sem ledger.

   Hoje o carrinho aceita e o checkout recusa.
