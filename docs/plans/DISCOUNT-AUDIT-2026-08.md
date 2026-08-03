# DISCOUNT-AUDIT-2026-08 — auditoria adversarial do sistema de descontos

**Motivação:** um cliente na staging viu, ao confirmar, "O total do pedido mudou
para R$ 36,00 (preço ou cupom atualizado)" — enquanto a tela mostrava R$ 28,00
(item Shokupan, "Lista de espera / previsto para hoje"). Mandato: auditar TODOS
os descontos, interações e empilhamento — **nenhum furo**.

**Método:** 4 análises paralelas do código (pipeline/empilhamento, divergência
revisão↔confirmação, preços por tempo/disponibilidade, gating de cupom/promo) +
reprodução por teste da cadeia real de modifiers. Furos marcados **✅ REPRO** têm
teste que reproduz (`shopman/shop/tests/test_discount_stacking_audit.py`); **✅ CÓDIGO**
foram confirmados por leitura direta file:line; **⚠️ VERIFICAR** carecem de repro
antes de corrigir.

---

## Causa-raiz (a estrutura que gera a classe inteira de bugs)

**Existem DOIS motores de preço que precisam concordar, e nada garante que
concordem:**

1. **Menu** — [`StorefrontPricingBackend.get_price`](../../shopman/shop/adapters/pricing.py) — aplica **só promoções**.
2. **Sacola/checkout** — [`ItemPricingModifier`](../../shopman/shop/handlers/pricing.py) (order 10) → [`DiscountModifier`](../../shopman/shop/modifiers.py) (20) → D-1 (15), funcionário (60), happy hour (65), etc.

A loja usa `pricing.policy = "internal"` (default; só iFood é "external"). Consequência:

- A **sacola IGNORA o preço do menu**. A cada recálculo, o `ItemPricingModifier`
  **limpa `modifiers_applied` e reescreve `unit_price_q` para o preço de lista**;
  os descontos re-aplicam do zero.
- O **confirm dispara um recálculo fresco** ([checkout.py:81-88](../../shopman/shop/services/checkout.py)) porque manda os `set_data` de cliente/entrega/pagamento como ops. O **commit sela** o que esse recálculo produziu (não reprecifica).
- As telas de **revisão NÃO reprecificam** — exibem o `line_total_q` persistido no último mutation. Então o preço exibido é um **snapshot** que pode estar velho.

**Explicação do 28→36 do cliente (D-1 REFUTADO):** o item era "previsto para hoje"
= planejado fresco, **não** é D-1 (D-1 exige `d1>0 and ready==0 and in_prod==0`).
O R$8 (~22%) era uma **promoção/cupom** que, entre o último recálculo e o confirm,
**expirou ou deixou de casar** — `now = timezone.now()` é relido a cada passagem e
`Promotion.valid_until` tem precisão de minuto. O `ItemPricingModifier` já tinha
zerado a linha pro preço de lista (36) e o desconto não foi re-conquistado → 36. O
guardião pegou. Mas o guardião é **opcional** (ver H3).

---

## Progresso das correções (branch `fix/discount-safety`)

| Fix | Bloco | Status |
|---|---|---|
| **H5** resíduo do desconto manual (cobrado = registrado) | PDV | ✅ CORRIGIDO + teste |
| **H3** guardião estruturado (new/old total) + mapeamento p/ o modal | Cliente | ✅ CORRIGIDO + teste |
| **Modal** reprecifica no `total_changed` (mostra o novo total) | Cliente | ✅ CORRIGIDO (finalizar.vue) |
| **D0** menu não mostra promo fixa por card (= sacola) | Cliente | ✅ CORRIGIDO + teste |
| **H1/H2** empilhamento composto → "maior desconto ganha" | PDV | ✅ CORRIGIDO + testes (árbitro por-linha via `meta`) |
| **C1** cupom expirado/esgotado no commit | Cliente | ✅ JÁ CONFORME — re-validado no reprice do confirm (`get_coupon_promotion`) + guardião; teste de regressão trava |
| **R1** `unit×qty ≠ line_total` na NFC-e (fiscal) | Fiscal | ✅ CORRIGIDO — vUnCom derivado de vProd/qCom (alta precisão) quando há resto; teste |
| **S2** `pricing["total_q"]` defasado | — | ✅ CORRIGIDO — recalcula no fim da cadeia (order 90); teste |
| **D1** base do `min_order` menu×sacola | Cliente | ✅ CORRIGIDO — `session_pricing_hints` exclui taxa de entrega (base = mercadoria, como o carrinho) |
| **D4** gate de coleção frágil (try/except mudo) | Cliente | ✅ CORRIGIDO — carrinho usa o helper canônico `collection_refs_by_sku` (mesma fonte do menu); fail-closed + WARNING |
| **D2** birthday só na sacola | Cliente | ✅ ACEITO — surpresa de aniversário intencional (menu SUBestima; cliente só ganha no checkout). Sem overcharge. |
| **D3** segmento menu(request)×sacola(session) | Cliente | ✅ ACEITO/COBERTO — dormente no seed (promo de segmento é CUPOM, excluído do menu). Para uma promo AUTO por segmento, o guardião pega o overcharge no confirm. Fix pleno = vincular cliente à sessão (registrado). |
| **S1** `meta.is_d1` congelado no add | — | ✅ ACEITO — a favor do cliente (honra o preço "de ontem" cotado ao adicionar); re-derivar subiria preço no meio do carrinho (pior UX). |
| **edge** promo fixa order-level + staff | PDV | ✅ ACEITO — cobrança correta; só a transparência pode superestimar. Raro (fixo é cupom no seed, excluído). |

O **bloco cliente** (o incidente 28→36) está fechado e verde. O **bloco PDV**
(H1/H2) e a robustez residual seguem no próximo passo — H1/H2 exige um árbitro
único de desconto (funde D-1/promo/funcionário/happy hour sob "maior ganha") com
transparência reconstruída a partir de `modifiers_applied`, e migração dos testes
que hoje codificam o empilhamento. É refatoração de preço com raio grande; merece
PR próprio e bateria de invariância, não fim de sessão longa.

## Nota de implementação para H1/H2 (descoberta ao começar o fix)

Verificado empiricamente: **`modifiers_applied` NÃO sobrevive a `update_items`** —
`Session._normalize_items` só mantém `meta`/`unit_price_q`/`line_total_q` (packages/
orderman/.../session.py:200). Consequências:

- O guard do happy hour "pula linha de funcionário" (`any(... employee_discount ...
  in item.modifiers_applied)`) lê uma lista **sempre vazia** → é **código morto**;
  happy hour compõe sobre funcionário também.
- Entre modifiers, o único estado durável é `unit_price_q` (reduzido) + `meta` +
  as chaves de `session.pricing`. `modifiers_applied` é rascunho LOCAL de um
  modifier, perdido no `update_items`.

**Design do fix (árbitro "maior desconto ganha"):**
1. `ItemPricingModifier` (10) carimba `meta["_list_q"]` (preço de lista pré-desconto)
   e zera `meta["_disc"]` a cada run.
2. Cada desconto por-linha (D-1, promo/cupom, funcionário, happy hour) aplica sobre
   `_list_q` e só vence se seu valor > `meta["_disc"].amount_q` atual; ao vencer,
   grava `meta["_disc"] = {type, amount_q, label}` e `unit_price = _list_q - amount`.
   Isso mata a composição (sempre sobre a lista, nunca sobre preço já reduzido) e
   deixa UM desconto por linha.
3. Um passo de reconciliação reconstrói as chaves de transparência
   (`pricing["d1_discount"/"discount"/"employee_discount"/"happy_hour"]`) a partir de
   `meta["_disc"]` — fonte única, elimina a duplicação. Corrige de brinde o S2
   (`pricing["total_q"]` calculado cedo demais).
4. Migrar os testes que hoje afirmam o empilhamento/chaves por-modifier
   (`test_persona_3_employee`, `test_discount_transparency`, `test_pos_line_discount`,
   `test_d1_persisted_pipeline`, e os xfail de `test_discount_stacking_audit`).

É refatoração de preço com raio grande (4 modifiers + reconcile + migração de
testes). PR próprio, test-driven, com bateria de invariância — não emendar no fim de
sessão longa.

## `modifiers_applied` — diagnóstico e MORTE (2026-08-03)

Pergunta do Pablo: se `modifiers_applied` é código morto, **ressuscitar ou matar?**

**Diagnóstico:** era uma **lista por linha** de todos os descontos aplicados —
abstração do modelo de **EMPILHAMENTO**. O projeto adotou "maior desconto ganha"
(UM desconto por linha), então a forma certa é o **vencedor único** (`meta["_disc"]`),
não uma lista. Além disso ele não persistia (`_normalize_items` só mantém
`meta`/`unit_price_q`/…), e alguns guards cross-modifier o liam → ficavam CEGOS.

**Achado grave (P1) que a cegueira escondia:** o guard `is_d1_line` do
`DiscountModifier` lia `modifiers_applied` (sempre `[]`) → **D-1 nunca era pulado →
promoção/cupom automáticos COMPUNHAM sobre o preço de D-1** (1000→500→350 com promo
30%; →300 com cupom 40%). Customer-facing (um pão "de ontem" também em "Semana do
Pão"). O próprio repo já documentara isto (`test_d1_stacking_bug_actual_numbers`,
xfail "BUG P1").

**Veredito: MATAR** (não ressuscitar). Ressuscitar reviveria a semântica SKIP (≠
best-wins) e criaria uma 3ª fonte de verdade. Feito:
- Guard `is_d1_line` passa a ler a fonte durável (`meta.is_d1` via `_line_is_d1`) →
  P1 corrigido (D-1 + promo/cupom = só o D-1, best-wins).
- Removidos TODOS os `modifiers_applied` (appends + reads): o total do D-1 acumula
  em variável local; a elegibilidade do fixo order-level usa `meta["_disc"]` (que
  também exclui corretamente linhas D-1 de um fixo de pedido).
- Duas fontes de verdade limpas: **`meta["_disc"]`** (vencedor por linha, decisões) +
  **`session.pricing`** (agregado por tipo, exibição — o que build_cart/PDV já usam).
- Testes migrados: os 3 D-1 que o repo deixou como xfail/bug viraram asserções
  normais; marcadores checam `meta["_disc"]`.

## Quadro de furos

> **Correção (2026-08-02):** o empilhamento H1/H2 é **do POS/balcão, não da loja**.
> Verificado contra a boundary do e2e `test_persona_3_employee.py`: a loja **não
> escreve `session.data.customer.group="staff"`** (staff paga cheio na loja) e o
> happy hour é escopado p/ fora da `web` no seed. Na loja, cada linha já tem **no
> máximo um** desconto automático (D-1 XOR promo/cupom — o `DiscountModifier` pula
> linhas D-1). Exceção estreita: se um cliente staff tiver o grupo vinculado à
> sessão (via cupom por segmento), o desconto de funcionário passa a compor — mas o
> caminho comum da loja não vincula. **O bug do cliente (28→36) NÃO é H1/H2** — é a
> divergência (D0/D1) + expiração de promo no reprice + guardião opcional (H3).

| # | Furo | Onde dispara | Severidade | Status |
|---|------|--------------|-----------|--------|
| **H1** | Happy hour **empilha** sobre D-1/promoção (só pula linha de funcionário) | **POS/balcão** (happy hour escopada p/ fora da `web`) | 🔴 ALTA (POS) | ✅ REPRO |
| **H2** | Desconto de **funcionário empilha** sobre promoção/D-1 (sem guarda) | **POS/balcão** (loja não seta staff, salvo edge de cupom+grupo) | 🔴 ALTA (POS) | ✅ REPRO |
| **H3** | Guardião anti-surpresa é **opcional** (`expected_total_q` nullable) → total surpresa comete em silêncio | Loja | 🔴 ALTA | ✅ CÓDIGO |
| **D0** | Promoção de **VALOR FIXO**: menu mostra "−R$X por card" (por unidade), sacola aplica **uma vez** no pedido | Loja (qualquer promo fixa ativa) | 🔴 ALTA | ✅ CÓDIGO |
| **H5** | Resíduo do **desconto manual** cai no índice errado (última posição, não última linha elegível) → cobrado ≠ registrado | POS | 🟠 MÉDIA | ✅ REPRO |
| **C1** | Cupom **não é revalidado no commit** (expiração/min_order); só no apply | Loja | 🟠 MÉDIA | ⚠️ VERIFICAR |
| **D1** | `min_order_q`: menu usa base (todas as linhas + entrega, persistida); sacola usa base (só mercadoria, bruta) → promo aparece/some | Loja | 🟠 MÉDIA | ⚠️ VERIFICAR |
| **D2** | `birthday_only`: sacola aplica, **menu nunca** (ctx do menu não seta `is_birthday`) | Loja | 🟡 BAIXA | ⚠️ VERIFICAR |
| **D3** | `customer_segments`: menu lê `request.customer`; sacola lê `session.data["customer"]` → fontes divergentes | Loja | 🟡 BAIXA | ⚠️ VERIFICAR |
| **D4** | Gate de coleção na sacola é `try/except`-silenciado → se a query falha, promo por coleção some na sacola mas fica no menu | Loja | 🟡 BAIXA | ⚠️ VERIFICAR |
| **R1** | `unit_price_q × qty ≠ line_total_q` após modifier distribuidor (floor no per-unit) → deriva em consumidores por-linha (NFC-e/recibo) | Todos | 🟡 BAIXA | ⚠️ VERIFICAR |
| **UX** | Modal não faz `refresh()` no erro `total_changed` → mostra R$28 velho ao lado do aviso "R$36" | Loja | 🟠 MÉDIA (confiança) | ✅ CÓDIGO |
| **S1** | `meta.is_d1` congelado no add, nunca re-derivado → preço velho após restock (a favor do cliente) | Todos | 🟡 BAIXA | ✅ CÓDIGO |
| **S2** | `pricing["total_q"]` é calculado no order 50, mas employee/HH/entrega/loyalty/manual mutam depois → fica stale | Superfícies que confiam nele | 🟡 BAIXA | ✅ CÓDIGO |

---

## Detalhe dos furos ALTA + os reproduzidos

### H1 — Happy hour empilha sobre D-1/promoção 🔴 ✅ REPRO
[`TimeWindowDiscountModifier.apply`](../../shopman/shop/modifiers.py) pula **só**
linhas com `employee_discount` (não pula `d1`, `promotion`, `coupon`), e lê o
`unit_price_q` **já reduzido** → tira % de novo. Viola a política "maior desconto
ganha, um por item".
**Repro:** item R$10 → D-1 50% → R$5 → happy hour −25% → **R$3,75** (correto R$5,00).
**Onde:** happy hour é escopada p/ fora da `web` no seed, então dispara no **POS**
(staff comprando item D-1 na Hora da Xepa pega D-1 + HH + funcionário compostos).

### H2 — Funcionário empilha sobre promoção/D-1 🔴 ✅ REPRO
[`EmployeeDiscountModifier.apply`](../../shopman/shop/modifiers.py) não tem
NENHUMA guarda de `modifiers_applied`; roda no order 60 (depois de D-1/promo) e
tira 20% do que estiver na linha.
**Repro:** R$10 → promo 30% → R$7 → funcionário −20% → **R$5,60** (correto R$7,00).
**Onde:** `employee_discount` **não** é escopado no seed → roda em **todo canal,
inclusive a loja** (cliente com grupo `staff`).

### H3 — Guardião anti-surpresa é opcional 🔴 ✅ CÓDIGO
`expected_total_q` é `required=False, allow_null=True`
([serializers.py:34](../../shopman/storefront/api/serializers.py)); o guardião só roda
`if expected_total_q is not None` ([checkout.py:93](../../shopman/shop/services/checkout.py)).
Cliente que omitir o campo **comete o total recalculado (maior) em silêncio** — vira
cobrança surpresa em vez de erro. Além disso o guardião **rejeita** mesmo quando o
preço CAIU a favor do cliente (bloqueia pedido mais barato).

### D0 — Promoção de valor fixo diverge menu×sacola 🔴 ✅ CÓDIGO
O menu ([pricing.py](../../shopman/shop/adapters/pricing.py)) **não filtra por tipo**:
chama `_calc_discount(promo, list_unit_price_q)` p/ toda promo, e p/ fixo isso é
`max(0, min(value, price))` — desconto **por unidade**, com badge `-R$X`. A sacola
([modifiers.py](../../shopman/shop/modifiers.py)) **pula fixo no loop por-linha** e
aplica **uma vez no pedido** (distribuído). Uma promo fixa de R$5 num carrinho de 6
itens: **menu anuncia R$30 off, sacola entrega R$5.** É o 28×36 amplificado.

### H5 — Resíduo do desconto manual no índice errado 🟠 ✅ REPRO
[`ManualDiscountModifier`](../../shopman/shop/modifiers.py) põe o resíduo em
`is_last = i == len(items) - 1` (último **índice**), não na última linha **elegível**.
Se a última linha é `__DELIVERY_FEE__` (pulada), a correção do resíduo nunca aplica.
[`LoyaltyRedeemModifier`](../../shopman/shop/modifiers.py) já corrige isso com
`last_eligible`; o manual não recebeu o fix.
**Repro:** 2 linhas + taxa; desconto R$9,99 → cobrado caiu **R$10,00** mas registrado
R$9,99 (cobrança ≠ registro).

---

## Plano de correção (priorizado)

**Fase 1 — parar o sangramento (dinheiro + surpresa), pequeno e cirúrgico:**
1. **H3:** tornar `expected_total_q` obrigatório no confirm da loja; e no
   `_ensure_total_matches`, quando o total mudou, retornar o **novo total** pro
   cliente reconfirmar (não bloquear cego). Fonte única do total.
2. **UX modal:** no `catch` de `total_changed` em `finalizar.vue`, dar `refresh()`
   e reprecificar antes de exibir, para a tela mostrar o número fresco (36) e o
   próximo `expected_total_q` casar.
3. **H2:** `EmployeeDiscountModifier` deve pular linhas que já têm desconto
   (`modifiers_applied`) ou competir sob "maior ganha" — nunca empilhar.
4. **H1:** `TimeWindowDiscountModifier` idem — pular linhas já descontadas.
5. **H5:** resíduo do manual → última linha **elegível** (copiar o padrão do loyalty).

**Fase 2 — matar a divergência na raiz (fonte única de preço):**
6. **D0 + a classe menu×sacola:** unificar a avaliação de promoção numa função
   compartilhada consumida pelos dois motores (menu e `DiscountModifier`), com o
   MESMO tratamento de fixo (order-level) e o MESMO ctx (fulfillment, min_order,
   segmento, birthday, coleção). Um "dono" só do preço ([[feedback_one_question_one_owner]]).
7. **C1:** revalidar cupom (expiração, min_order, uso) no commit, não só no apply.

**Fase 3 — robustez:**
8. **R1:** reconciliar `unit_price_q × qty` com `line_total_q` (ou documentar que a
   fonte de verdade é `line_total_q` e blindar os consumidores por-linha).
9. **S1/S2:** re-derivar `meta.is_d1` no reprice (ou documentar como snapshot
   intencional); recalcular `pricing["total_q"]` no fim da cadeia.

**Guarda geral:** uma bateria de testes de invariante de preço (a de
`test_discount_stacking_audit.py` é a semente) que afirma, para cada par de
descontos e cada superfície: "no máximo um desconto por linha; total exibido ==
total cobrado; menu == sacola para o mesmo SKU/condições".
