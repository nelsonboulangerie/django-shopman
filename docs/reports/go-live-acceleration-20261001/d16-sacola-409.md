# D16 — Sacola: o 409 de ajustar a quantidade (PR #1323)

- `verificado_em`: 2026-10-01T08:56Z
- `arvore`: `origin/main` = `beb9bf9737da0bc343cc64f86e423a7d26a81f17` (2026-10-01T07:46:39+00:00, o **merge do próprio #1323**). Todo o código lido veio de `git show origin/main:<caminho>`; o checkout local está em outro branch e não foi usado como evidência.
- `objeto`: **PR #1323** — `night/hold-compensatorio`, head `be6ae85fafdeecb2d4ce14efaa21293bab19b5d3`, 3 commits (`1d6ca0efc`, `e2b05ab0b`, `be6ae85fa`), `merged_at` 2026-10-01T08:10:48Z, merge `beb9bf973`. Leitura via API pública: `curl -sS https://api.github.com/repos/nelsonboulangerie/django-shopman/pulls/1323`.
- `vizinhança`: **PR #1324 ABERTO** (`night/hold-margem-devolucao`, head `167aeb660`) mexe no mesmo `return_hold_remainder`; o próprio corpo dele diz que é achado de uma **2ª** revisão independente e que **não é regressão do #1323**.
- `revisão independente`: o registro está **no corpo do PR #1323**, seção "Rodada 2 (revisão independente)" (3 achados: ALTO, MÉDIO, BAIXO), e na mensagem do commit `be6ae85fa` ("Revisão do #1323: 1) … 2) …"). Não há comentários nem reviews na API do GitHub: `issues/1323/comments` → `[]`, `pulls/1323/reviews` → `[]`, `pulls/1323/comments` → `[]`.
- `regra`: só FATO com `caminho:linha` ou comando+saída. Nada foi inventado; o que é dedução está marcado `[INFERÊNCIA]`.

---

## Resposta direta ao dono (2 minutos)

**1. O defeito original, em uma frase.** Com a fila de espera ligada, a sacola ancora a reserva no **dia da fornada**, mas todo ajuste de quantidade criava o hold **para HOJE**: aumentar era recusado com 409 "disponível 0", e **reduzir soltava a reserva da fila e não conseguia recriá-la — a linha mostrava 1 e a sacola ficava com ZERO reservado** (`session now under-reserved`), sem nenhum aviso ao cliente. [FATO: corpo do #1323, tabela "Reprodução" e causa; mensagem de `1d6ca0efc`; docstring do teste `shopman/storefront/tests/web/test_cart_adjustment_keeps_reservation.py:1-17`]

**2. As duas regressões do conserto (rodada 1 → revisão → rodada 2).** (a) **ALTO** — a sobra de uma reserva da fila era recriada sempre sem a margem da vitrine, herdando `planned` e "sem prazo"; como o Stockman escolhe quant **por validade, não por origem**, a sobra caía no **pão pronto que chegou** e ficava presa ali como fila sem relógio, fora do alcance do balcão e da materialização da fornada. (b) **MÉDIO** — **reduzir podia ser recusado**: com o quant encolhido (perda/ajuste), o troco não voltava, a rodada 1 desfazia a soltura e respondia **409 `INSUFFICIENT_AVAILABLE`** ("Usar 3.000 unidades") a um pedido de redução. [FATO: corpo do #1323, "Rodada 2"; mensagem de `be6ae85fa`]

**3. O que o 409 de AJUSTE mostra hoje.** Mostra o que sobra **ALÉM** do que a sacola já reservou (2), não o teto da linha (4) — e o botão aplica esse número como quantidade **absoluta** da linha. Virou pergunta de produto porque rótulo e ação discordam: na cena "sacola 2, fornada 4, pediu 6", o botão **não muda nada**; e na cena "linha 4, pediu 5", **encolhe a sacola para 2**. [FATO para os números e o rótulo: corpo do #1323 + `shopman/storefront/api/surface.py:122-138` + `surfaces/storefront-nuxt/app/composables/useCartState.ts:403-408`. `[INFERÊNCIA]` para o caso "linha 4 → pediu 5": os caminhos são `useCartState.ts:345-349` (409 vira `cartIssue`) + `SubstituteSheet.vue:52-59` (rótulo) + `acceptAvailableQty` (`useCartState.ts:403-408`), que faz `setSkuQty(meta, available_qty)` absoluto.]

**4. As opções de regra em jogo.** (i) **que número o 409 de ajuste mostra** (delta livre 2 vs. teto da linha 4) e **o que o botão faz** com ele (absoluto, como hoje, ou relativo); (ii) **uma linha pode juntar hoje + fornada?** Hoje **não** — uma linha, uma data, travado por teste; (iii) **o que acontece com a sobra** na redução (três degraus, abaixo); (iv) a **margem da vitrine** pode comer a unidade que a sacola já segurava (PR #1324, aberto).

**5. Minha recomendação.** (i) **mostrar o teto da linha (4) e o botão levar a linha até ele** — o cliente pensa "quantos eu posso ter", e "2" com um botão que não muda nada (ou encolhe a sacola) é mentira; manter o delta só no `add`, onde os dois números coincidem. (ii) **não** deixar a linha juntar hoje + fornada agora — é promessa nova (dois dias numa linha, atinge checkout/agenda/fila) e a recusa atual erra para o lado seguro. (iii) **fechar o #1324 antes do go-live**; o achado BAIXO da revisão (linha da fila que cresce pode consumir pão pronto de hoje) fica **aceito e documentado**.

---

## 1. O defeito original

**Caminho do usuário (fila de espera ligada, nada pronto hoje, 4 planejados para amanhã):**

1. O cliente põe **2** pães na sacola. `reserve()` resolve a data pela fila (`shopman/shop/services/availability.py:702-706` → `waitlist.reserve_target_date`), então o hold nasce ancorado em **amanhã**, com `planned` e **sem TTL** (`shopman/shop/adapters/stock.py:177-185`). A sacola mostra o selo "Lista de espera" + "Previsto para amanhã" (`surfaces/storefront-nuxt/app/pages/sacola.vue:234-244`).
2. Ele **toca no "−" para ficar com 1**. O ajuste passa por `reconcile()` → `_reconcile_simple`, que soltava o hold **inteiro** (o Stockman não parte hold) e recriava a sobra com `target_date=None`, **isto é, para hoje**, onde não há nada. A recriação falhava; o código **só logava** (`compensating hold failed … session now under-reserved`) e devolvia `ok=True`. **A tela diz 1, a sacola tem 0 reservado, e o cliente perdeu a vaga na fila.**
3. Se ele **toca no "+"** para 4, o delta pedia **hoje** → **409** com `available_qty` 0.
   [FATO: corpo do #1323 (tabela "Reprodução" e "Causa"); mensagem de `1d6ca0efc`; docstring do teste, `shopman/storefront/tests/web/test_cart_adjustment_keeps_reservation.py:9-12`]

**Onde o 409 nasce.** [FATO]
- `shopman/storefront/api/surface.py:1093-1109` — `CartSkuQtyView.put` chama `set_qty_by_sku`; `except CartMutationUnavailable` → `Response(_stock_error_payload(...), status=409)` (linha **1108**: `status.HTTP_409_CONFLICT`).
- `shopman/storefront/services/cart_mutations.py:115-116` — `CartUnavailableError` do Core vira `CartMutationUnavailable`.
- O código por baixo é `INSUFFICIENT_AVAILABLE` do Stockman (`docs/reference/errors.md:276`).

**O que a tela mostra.** O `SubstituteSheet` (bottom-sheet global, sobe em qualquer superfície). [FATO]
- `useCartState.ts:345-349`: qualquer **409** vira `cartIssue` — **não navega e não dispara toast**, a folha sobe.
- `SubstituteSheet.vue:36-55`: título e descrição. Se `is_planned`, o título é `planned_offer_title` (**"Já vem quentinho"**, `surface.py:177-179`) e a descrição é `planned_offer_message` (**"Sai fresquinho no próximo lote. Quer garantir o seu?"**, `surface.py:180-183`). Com saldo, o título é **"Ajuste a quantidade"** e a descrição **"Agora temos N unidades de X."**
- Botão primário (`SubstituteSheet.vue:52-55`): **"Pré-reservar N unidades"** se `is_planned`, senão **"Levar N unidades"**.
- O `detail` do backend para linha de fila é "Disponível por encomenda, com limite para esta data." (`surface.py:95-96`), mas a folha **não o renderiza** — ela reescreve título/descrição.
- [FATO] Depois do conserto a recusa de fila carrega `is_planned: true` (teste, `test_cart_adjustment_keeps_reservation.py:126-127`), o que é o que faz a folha enquadrar a recusa como "próximo lote" em vez de "acabou".

---

## 2. As duas regressões que a revisão independente achou no conserto

A rodada 1 do conserto (`1d6ca0efc` + `e2b05ab0b`) fechou o defeito original mas introduziu duas regressões, ambas medidas contra o código da rodada 1 e corrigidas em `be6ae85fa`.

### Regressão A — ALTO: a sobra da fila virava pão pronto preso sem relógio

**Cenário concreto.** Fila ligada; a sacola tem 3 pães **da fornada de amanhã**; chega **pão pronto hoje** (quant físico, sem data, como a produção grava). O cliente **reduz para 2**. A sobra de 1 era recriada com a data da fornada e **sem a margem da vitrine**, herdando `planned`; o Stockman escolhe o quant **por validade (FEFO), não pela origem da reserva**, então a sobra caía **no pão pronto** — carimbada como **fila** e **sem prazo** (`is_cart_hold=False`, `is_waitlist_hold=True`). Pão que está na prateleira ficava **preso sem relógio**, fora do alcance do balcão e da materialização da fornada.
[FATO: corpo do #1323 "Rodada 2 · ALTO"; mensagem de `be6ae85fa` item 1; teste `test_queue_remainder_landing_on_ready_bread_is_a_regular_cart_hold`, `test_cart_adjustment_keeps_reservation.py:155-191`; código da rodada 1: `git show e2b05ab0b:shopman/shop/adapters/stock.py` linha 447 `_recreate_remainder` ("`sem a margem da vitrine`")]

**Correção (degrau 2).** `return_hold_remainder` só devolve "a mesma reserva" (prazo e carimbos do original, sem margem) quando a sobra cai no **MESMO quant** (`shopman/shop/adapters/stock.py:502-525`); em **outro quant** ela é solta e refeita como **reserva comum de sacola** — carimbos de tipo e prazo saem do quant onde ela cai (`create_hold`), com a margem valendo (`stock.py:527-538`). [FATO]

### Regressão B — MÉDIO: reduzir podia virar 409

**Cenário concreto.** Sacola com 3 pães prontos de hoje; uma **perda/ajuste** deixa o quant com **1**; o cliente **reduz de 3 para 2**. O troco não cabe em lugar nenhum, a rodada 1 desfazia a soltura e **respondia 409 `INSUFFICIENT_AVAILABLE` com "Usar 3.000 unidades"** — ou seja, **reduzir**, que não deveria falhar nunca, era recusado.
[FATO: corpo do #1323 "Rodada 2 · MÉDIO"; teste `test_shrink_after_the_quant_shrank_keeps_what_exists`, `test_cart_adjustment_keeps_reservation.py:195-213` (docstring: "antes: 409 `INSUFFICIENT_AVAILABLE` com 'Usar 3.000 unidades'"); código da rodada 1: `git show e2b05ab0b:shopman/shop/services/availability.py:1301-1329` — `_ShrinkAborted` → `ok=False`]

**Correção (degrau 3).** `create_holds_up_to` devolve **o que couber**: a linha fica com o que o cliente pediu, a reserva com o que existe, e a revalidação da sacola mostra a falta (`shopman/shop/adapters/stock.py:540-554`; `shopman/shop/services/availability.py:1285-1329`; aviso na tela: `shopman/storefront/presentation/cart.py:325-331`, "Apenas N unidades disponíveis"). [FATO]

### (Não é uma das duas) o terceiro achado, já fora do #1323

A revisão também registrou um **BAIXO, sem mudança**: uma linha da fila de amanhã **que cresce** pode consumir pão pronto de hoje — o delta ancora na data da fornada e o Stockman, por validade, pode escolher o quant pronto. É o mesmo comportamento do `reserve()` no `main`, não herança da sobra. [FATO: corpo do #1323, "Rodada 2 · BAIXO (registrado, sem mudança)"]

---

## 3. O que exatamente o 409 de AJUSTE mostra hoje — e por que virou pergunta de produto

**Dois números com o mesmo nome.** [FATO de código]
- No **409**, `available_qty` é o que sobra **além do que a sacola já reservou**: a recusa vem de `check(sku, delta, …)` (`shopman/shop/services/availability.py:1214`) e o corpo publica `status["available_qty"]` (`availability.py:1228-1237`; `surface.py:165`). Na reprodução: fornada de 4, sacola com 2 → o 409 mostra **2**. [FATO: corpo do #1323, tabela "Reprodução", linha `{qty: 6}`]
- Na **linha da sacola**, o `available_qty` é o **teto que a linha pode alcançar**: `max_orderable = total_promisable + own_hold` (`shopman/shop/projections/cart.py:591-605`), devolvido como `available_qty` da linha (`cart.py:478, 503`). Na mesma cena, a linha mostra **4**. [FATO de código]

**O que o cliente vê e o que o botão faz.** [FATO + `[INFERÊNCIA]` marcada]
- Rótulo do botão primário: `"Levar {N} unidades"` / `"Pré-reservar {N} unidades"` (`SubstituteSheet.vue:52-55`), com N = o `available_qty` do 409.
- A ação envia **qty absoluta**: `acceptAvailableQty()` → `setSkuQty(meta, availableQty)` (`useCartState.ts:403-408`). O backend também publica a ação `set_available_qty` com `qty: {const: available_qty}` (`surface.py:122-138`), coerente com o plano antigo — "faz POST com `qty=available_qty` (**qty absoluta**, idempotente)" (`docs/plans/STOCK-UX-PLAN.md:107`). [FATO]
- **Caso "sacola 2, pediu 6"**: o botão oferece **2**, que é exatamente a quantidade que a linha já tem → **tocar não muda nada**, quando **4 caberiam**. [FATO: corpo do #1323, "Ambiguidades de regra" §1]
- [INFERÊNCIA] **Caso "linha 4, pediu 5"**: o 409 volta com `available_qty` 2; `cartIssue` é preenchido (`useCartState.ts:345-349`) e o botão primário diz "Levar 2 unidades"; tocando, `acceptAvailableQty` faz `setSkuQty(meta, 2)` — **encolhe a sacola de 4 para 2**. Os caminhos são os citados; não executei o app para confirmar a cena ponta a ponta.
- [FATO] O `actions[]` que o backend manda com `set_available_qty` **não é consumido** pela folha: `SubstituteSheet.vue` monta o próprio botão a partir de `available_qty` (`SubstituteSheet.vue:21-22, 52-59`); no `storefront-nuxt` o array existe só na tipagem e na leitura (`useCartState.ts:23, 173`).
- [FATO] No caminho acessório da sacola, "Usar N" usa o `available_qty` **da linha** (o teto): `sacola.vue:262-269` + `adjustToAvailable()` em `sacola.vue:78-82`. Ou seja, **a mesma tela usa os dois números diferentes** dependendo de onde o cliente está.

**Por que virou pergunta de produto.** A recusa carrega um número cujo significado mudou entre o `add` e o `ajuste` (no `add` os dois coincidem; no ajuste, não), e o rótulo herda a promessa do outro caminho. Erra para menos — não promete o que não existe — mas **rótulo e ação discordam**: o cliente ou toca num botão que não faz nada, ou perde unidades que tinha. [FATO: corpo do #1323, "Ambiguidades de regra" §1]

---

## 4. As opções de regra em jogo

### (i) Que número o 409 de um AJUSTE mostra — e o que o botão faz com ele

| Opção | O que o cliente vê | Consequência |
|---|---|---|
| **A. Delta livre (hoje)** — mostrar 2, botão absoluto | "Levar 2 unidades" | No ajuste o botão não muda nada (sacola já em 2) ou **encolhe** a linha (estava em 4) |
| **B. Teto da linha** — mostrar 4 (`promisable + own_hold`), botão absoluto | "Levar 4 unidades" | Botão sempre avança até o que cabe; exige o backend publicar um campo novo (o `available_qty` do 409 não é o teto) |
| **C. Delta livre, botão relativo** — "Adicionar 2" | "Adicionar 2 unidades" | Correto no ajuste, mas o `add` teria de continuar absoluto: **dois contratos** para a mesma folha |

[FATO de base: corpo do #1323 §1; `surface.py:122-138`; `useCartState.ts:403-408`; `projections/cart.py:591-605`]

### (ii) Uma linha pode juntar hoje + fornada?

- **Hoje: não.** "Uma linha, uma data" é invariante travado por teste: linha de pronta-entrega que cresce **só cresce dentro de hoje**, e pedir mais continua dando **409** (igual ao `main`) — `test_growing_a_ready_line_never_splits_it_across_days`, `test_cart_adjustment_keeps_reservation.py:241-259`. O crescimento usa a data do hold vivo da própria linha (`availability.py:1165-1175` + `adapters/stock.py:791` `hold_target_date`). [FATO]
- **A alternativa em jogo:** "**2 hoje + 2 amanhã** na mesma linha". O próprio PR diz que é **promessa nova** e que o teste trava só o invariante, **sem consagrar o 409**. [FATO: corpo do #1323, "Ambiguidades de regra" §2]
- [FATO] Com fila **desligada**, o comportamento de hoje é cobrado pelo teste parametrizado `test_refusal_keeps_reservation_and_next_fitting_request_passes[False|True]` (`...:216-238`): 409 não toca na reserva e o pedido seguinte que cabe dá 200.

### (iii) O que acontece com a sobra (a redução)

Três degraus, em `shopman/shop/adapters/stock.py:453-554` (`return_hold_remainder`), chamados de `availability.py:1306-1319` dentro de um `transaction.atomic()` (soltar + devolver vivem no mesmo savepoint): [FATO]
1. **A mesma reserva** se a sobra volta ao **MESMO quant** do hold original — mesma data, mesmo prazo (inclusive o "sem prazo" da fila), mesmos carimbos, **sem a margem da vitrine** (`stock.py:502-523`).
2. **Reserva comum de sacola** se ela cairia em **outro quant** — carimbos e prazo saem de `create_hold` (o quant decide), **com** a margem valendo (`stock.py:527-538`).
3. **O que couber** (`create_holds_up_to`) se o quant encolheu — **reduzir nunca falha**; a linha fica com o que o cliente pediu, a reserva com o que existe, e a sacola mostra a falta ("Apenas N unidades disponíveis", `presentation/cart.py:325-331`). Se a sobra não voltar, o log registra `shrink kept less than the line` (`availability.py:1314-1319`). [FATO]
- O caminho do **balcão** que cede reservas (`_return_remainder_to_cart`) foi deixado **idêntico ao do `main`** (`adapters/stock.py:557`). [FATO: corpo do #1323]

### (iv) A margem da vitrine pode comer a unidade que a sacola já segurava — **PR #1324, aberto**

Canal com `safety_margin=2` (**o valor do alpha**), 5 prontos, sacola com 3; uma perda deixa o quant em 1 e o cliente reduz para 2 → **200, linha 2, reserva 0**, embora 1 pão exista. Causa: o **degrau 3** reaplicava a margem da vitrine, e um quant com livre ≤ margem não devolvia nada. O `main` antes do #1323 **já tinha** esse defeito — **não é regressão do #1323**. O #1324 corrige o degrau 3 (tenta o **quant original**, sem margem, só até o livre dele) e passa o degrau 1 a usar o mesmo ajudante. Limite assumido: se a FEFO puser a reserva sem margem em outro quant, ela é desfeita. [FATO: corpo do PR #1324 (`curl .../pulls/1324`), estado `open`, head `167aeb660`]

---

## 5. Minha recomendação, opção por opção

| # | Decisão | Recomendação | Motivo |
|---|---|---|---|
| i | Número do 409 de ajuste + ação do botão | **(B) mostrar o teto da linha e o botão levar a linha até o teto**; manter o delta atual só no `add`, onde os dois números coincidem | O cliente pensa "quantos eu posso ter", não "quanto sobrou". Hoje o botão ou é no-op (sacola 2, pediu 6) ou **tira** unidades do cliente (linha 4, pediu 5). É o único caso em que a ação do 409 pode **piorar** a sacola. Exige um campo novo no payload (ex.: `line_ceiling_qty`) — o `available_qty` do 409 não é o teto (`projections/cart.py:591-605` vs. `availability.py:1214`) |
| i-b | Alternativa mais barata, se não houver janela | **(C) "Adicionar N"** no ajuste (relativo) e absoluto só no `add` | Custa uma string por caminho, não mexe no backend; mas cria dois contratos para a mesma folha |
| ii | Linha com hoje + fornada | **Não fazer agora.** Manter "uma linha, uma data" e o 409 como está | É promessa nova (dois dias numa linha) e atravessa checkout, agenda de retirada/entrega, materialização da fornada e preço. A recusa atual erra para o lado seguro: nunca promete o que não existe. Reavaliar depois do go-live, com dados de quantas vezes a recusa acontece |
| iii | Sobra da redução | **Manter os três degraus** | É a régua certa: "reduzir nunca falha" e "a sobra é do tipo do quant onde cai" resolvem as duas regressões sem tocar em `packages/` |
| iv | Margem da vitrine vs. unidade da sacola (#1324) | **Fechar o #1324 antes do go-live** | O valor configurado no alpha é `safety_margin=2`; é exatamente nele que o cenário deixa a sacola com **0 reservado** tendo pão no balcão. É o mesmo modo de falha do defeito original (linha > reserva), agora sem nem precisar de fila |
| v | Achado BAIXO (linha da fila que cresce pode consumir pão pronto de hoje) | **Aceitar e documentar**; não travar o go-live | É o comportamento do `reserve()` no `main`, não regressão; o efeito é a fornada de amanhã perder um pão para o pronto de hoje, e o cliente recebe o que pediu |

**O que o dono precisa decidir em uma linha:** *"Quando o cliente pede mais do que cabe e a sacola já tem reserva, o 409 oferece o que **sobra** (hoje) ou o que **cabe na linha** (recomendado)?"* — e, separado: *"A linha pode misturar hoje e a fornada de amanhã?"* (recomendado: não, por ora).

---

## Anexos — comandos usados

```
git fetch origin
git log origin/main --oneline -30
git show origin/main:shopman/storefront/api/surface.py | nl -ba | sed -n '30,180p;1070,1140p'
git show origin/main:shopman/shop/services/availability.py | nl -ba | sed -n '474,535p;1130,1330p'
git show origin/main:shopman/shop/adapters/stock.py | nl -ba | sed -n '120,216p;453,560p'
git show origin/main:shopman/shop/projections/cart.py | nl -ba | sed -n '570,640p'
git show origin/main:surfaces/storefront-nuxt/app/components/SubstituteSheet.vue | nl -ba
git show origin/main:surfaces/storefront-nuxt/app/composables/useCartState.ts | nl -ba | sed -n '320,435p'
git show origin/main:surfaces/storefront-nuxt/app/pages/sacola.vue | nl -ba | sed -n '60,145p;210,290p'
git show origin/main:shopman/storefront/tests/web/test_cart_adjustment_keeps_reservation.py | nl -ba
curl -sS https://api.github.com/repos/nelsonboulangerie/django-shopman/pulls/1323      # corpo do PR + "Rodada 2 (revisão independente)"
curl -sS https://api.github.com/repos/nelsonboulangerie/django-shopman/pulls/1324      # seguimento aberto
curl -sS 'https://api.github.com/repos/nelsonboulangerie/django-shopman/issues/1323/comments'   # [] (sem review no GitHub)
```

---

## O que NÃO verifiquei

- **Nada foi executado**: não rodei os testes nem subi o app. Toda evidência é leitura de código em `origin/main` + o corpo do PR (a reprodução do PR é medida pelo autor, e eu a cito como FATO *do PR*, não como medida minha).
- **A folha do 409 no app vivo** (título/descrição/botão renderizados) é leitura de código, não observação de tela.
- **O caso "linha 4 → pediu 5 → botão encolhe para 2"** é `[INFERÊNCIA]` a partir dos caminhos citados; não foi reproduzido.
- **Onde vive o texto da "revisão independente"**: procurei em `docs/`, em `.dsh-worktrees/` e nos comentários/reviews da API do GitHub e não achei artefato próprio — o registro é o corpo do PR #1323 e a mensagem de `be6ae85fa`. [NÃO VERIFICADO se existe um relatório de revisão em outro lugar]
- **`safety_margin=2` "é o valor do alpha"**: [FATO do corpo do #1324], não conferi o `RuleConfig`/seed de produção.
