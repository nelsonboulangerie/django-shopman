# Verificação WP-02 — POS / Caixa

Base verificada: worktree `coordenar-sessoes-deploys-b9cdac`, HEAD `9469c92a2` (descendente do main de 29/08/2026).
Método: leitura de função inteira em cada citação + **duas provas executadas** contra a suíte real
(`DJANGO_SETTINGS_MODULE=config.settings_test`, `.venv` da raiz). Onde digo CONFIRMADO com prova, o
resultado do runner está transcrito.

---

## A. Superfície real (o que existe hoje)

### Backend — endpoints (todos em `shopman/backstage/api/urls.py`, montados em `/api/v1/backstage/`)

| Caminho | View (`shopman/backstage/api/operations.py`) | Permissão | Uma linha |
|---|---|---|---|
| `GET pos/` | `POSView` :297 | `cashman.operate_pos` | Projection inteira do terminal (produtos, ações, cash_runtime, comandas) |
| `POST pos/sale/review/` | `POSReviewSaleView` :2655 | `operate_pos` | Revisão não-commitada da venda (totais, troco, warnings) |
| `POST pos/sale/close/` | `POSCloseSaleView` :2683 | `operate_pos` | Fecha a venda (idempotente por `client_request_id`) |
| `POST pos/sale/recent/cancel/` | `POSCancelRecentSaleView` :2719 | `operate_pos` + PIN gerente | Cancela/reabre venda recente |
| `POST pos/cash/open/` | `POSCashOpenView` :1850 | `operate_pos` | Abre turno da gaveta |
| `POST pos/cash/close/` | `POSCashCloseView` :1895 | `operate_pos` + `perform_closing` interno | Fechamento cego |
| `POST pos/cash/movement/` | `POSMovementView` :1932 | `operate_pos` (+PIN na sangria) | Sangria / suprimento |
| `GET/POST pos/cash/entry/<id>/receipt/` | `POSCashReceiptView` :1972 | `operate_pos` | Bytes ESC/POS do comprovante + resultado da impressão |
| `POST pos/cash/drawer-open/` | `POSCashDrawerOpenView` :2023 | `operate_pos` | Abertura de gaveta sem venda (só motivo, sem PIN) |
| `POST pos/cash/drawer-unlock/` | `POSCashDrawerUnlockView` :2054 | `operate_pos` + PIN | Libera a próxima venda com gaveta aberta |
| `POST pos/cash/change-request/` | `POSChangeRequestView` :2091 | `operate_pos` | Pede troco (net zero) |
| `POST .../<ref>/serve/` `.../<ref>/cancel/` | :2128 / :2164 | `operate_pos` (+PIN no serve) | Atende / cancela pedido de troco |
| `POST pos/cash/refund/<order_ref>/` | `POSCashRefundView` :2192 | `operate_pos` + PIN | Devolve dinheiro de venda cancelada |
| `GET pos/cash/report/` | `POSCashReportView` :2280 | **`cashman.audit_shift`** | Leitura X/Z — gate separado por decisão do dono |
| `GET pos/accounts/`, `POST pos/accounts/<ref>/settle/` | :2225 / :2244 | `operate_pos` | Conta na casa: saldos e acerto |
| `pos/tabs/*` (create/open/save/rename/move-lines/fire/unfire/clear) | :2344–2568 | `operate_pos` | Comandas |
| `pos/customer/*` (lookup/search/resolve/profile) | :2569–2654, :1378 | `operate_pos` | Cliente no balcão |
| `GET pos/payment/<ref>/status/` | `POSPaymentStatusView` :319 | `operate_pos` | Polling do PIX |
| `GET pos/sale/<ref>/receipt|danfe/` | :1335 / :1272 | `operate_pos` | Recibo e DANFE ESC/POS |
| `GET/POST closing/` | `DayClosingView` :952 | `backstage.perform_closing` | Fechamento do dia |
| `/events/cash/`, `/events/tabs/` (SSE) | `_sse_emitters.py` | canal gateado por `operate_pos` | Push de turno/troco/devolução |

### Backend — camadas

- `shopman/backstage/projections/pos.py` — `build_pos()` :440 e `_pos_actions()` :940 (manifest de 24 ações).
- `shopman/backstage/services/pos.py` — mutações de caixa sobre o `cashman`; `_terminal()` :497, `current_shift()` :479, `_open_shift_or_raise()` :638.
- `shopman/shop/services/pos.py` (3423 linhas) — `close_sale` :241, `review_sale` :530, `fire_pos_tab` :1097, `build_session_ops` :1375, `validate_manager_approval` :1661, `validate_manager_override` :1698, `_payload_tenders` :2281.
- `shopman/shop/services/pos_intent.py` — parser estrito do intent (allow-list de chaves :18-50, enums :51-53).
- `packages/cashman/.../services/shifts.py` — único escritor da custódia; `models/terminal.py:43` `Terminal.default()`.
- `shopman/backstage/services/closing.py` — fechamento do dia.

### Frontend (`surfaces/pos-nuxt/app/`)

`utils/posIntent.ts` (resolvePayment/actionHref/buildPosSaleIntent), `composables/usePosSale.ts` (1700 linhas),
`usePosCashSession.ts`, `useDrawerLock.ts`, `useCounterAgent.ts`, `useCashReport.ts`, `usePosEvents.ts`,
`presentation/payment.ts` (gate de cobertura), `generated/posContract.ts` (gerado de `pos_intent.py`).

### O que os dois WPs NÃO mencionaram e faz parte da superfície

- `POSCashReportView` com gate **próprio** (`cashman.audit_shift`) e o predicado documentado em
  `shopman/backstage/permissions.py:70-86` — a apuração já está separada da operação.
- `pos/accounts/*settle*` — **entrada de dinheiro na gaveta sem PIN e sem idempotência**.
- `pos/cash/entry/<id>/receipt/` (GET+POST) — o único endpoint do PDV que já passa `terminal_ref` de propósito.
- SSE: `_publish_backstage` (`shop/handlers/_sse_emitters.py:467-480`) publica **sempre** em
  `backstage-cash-main` **e** no canal escopado; o payload é `{kind, ref}` — sem PII, sem valor.
- `shopman/backstage/services/closing.py:144` `_parse_qty` — o fechamento do dia.

---

## B. Evidências dos WPs, veredito uma a uma

| # | Afirmação (de quem) | Arquivo:linha ATUAL | Veredito | Nota |
|---|---|---|---|---|
| 1 | `build_pos` usa terminal default quando nenhum é passado (G :440,:454) | `backstage/projections/pos.py:440`, `:454-457` | **CONFIRMADO** | `if terminal is None: terminal = Terminal.default()`; linhas idênticas às citadas. |
| 2 | `POSView` chama `build_pos(operator=...)` sem terminal (G :297 / D :304) | `backstage/api/operations.py:304` | **CONFIRMADO** | D acertou a linha; G está 7 linhas atrás. |
| 3 | `_open_cash_shift_for_request()` usa `current_shift()` sem `terminal_ref` (G :226 / D :226-232) | `backstage/api/operations.py:229` (função :226-232) | **CONFIRMADO** | `return pos_service.current_shift()` — sem argumento. |
| 4 | `open_cash_shift()` transforma negativo em zero (G/D :65) | `backstage/services/pos.py:65` | **CONFIRMADO (provado)** | `float_q = max(0, parse_money_to_q(...))`. Probe: `-10` abriu turno com **zero lançamentos** (nem `FLOAT_IN`). |
| 5 | O guard do `cashman` nunca dispara (D, `shifts.py:57-58`) | `packages/cashman/.../services/shifts.py:57-58` | **CONFIRMADO** | `if float_q < 0: raise CashError(...)` é inalcançável pela superfície. |
| 6 | `resolvePayment()` omite tender explícito para uma linha (G :44 / D :44-63) | `surfaces/pos-nuxt/app/utils/posIntent.ts:50` | **CONFIRMADO, mas o dano é outro** | A linha 50 devolve `paymentTenders: []` e `tenderedQ: null`. Só que `isPaymentCovered` (`presentation/payment.ts:105-107`) desabilita "Finalizar" abaixo do total, e o total é o da **review** (`usePosSale.ts:343-345`). Ver §E. |
| 7 | `actionHref()` cai para fallback hardcoded (G :65) | `posIntent.ts:65-71` | **PARCIAL** | O fallback existe, mas **nenhum** dos 16 refs usados no front está ausente de `_pos_actions()`, e todos os hrefs batem com `api/urls.py:369-425`. Fallback hoje é código morto, não risco vivo. |
| 8 | `request_change` projetado diverge do payload real (G/D) | schema `projections/pos.py:1113`; endpoint `operations.py:2109-2111`; service `services/pos.py:318`; front `usePosCashSession.ts:247` | **CONFIRMADO** | Schema diz `required:["kind"], optional:["amount","note"]`. Não existe `kind`; `amount` é obrigatório (`services/pos.py:339`); `denominations` é validado (`:294-315`) e nem aparece no schema. |
| 9 | `fire_tab` promete `client_request_id` mas o service só loga (G/D) | ação `projections/pos.py:1223`; service `shop/services/pos.py:1159` | **CONFIRMADO** | `client_request_id` aparece uma única vez, no `logger.info`. |
| 10 | O fire **já é** idempotente por mecanismo mais forte (D) | `shop/services/kds.py:103-162` (`select_for_update` :144, dedupe por `line_id` :156-160) | **CONFIRMADO** | A recalibração de D está certa: implementar dedupe por request quebraria o fire progressivo por curso. |
| 11 | Aprovação gerencial inconsistente: dois validadores (G/D) | `shop/services/pos.py:1661-1695` (só username+PIN) vs `:1698-1754` (badge OU username+PIN) | **CONFIRMADO — e pior** | O parser do intent **descarta `badge`** antes de chegar ao validador (`pos_intent.py:392-399` só copia `username`/`pin`). O crachá não vale na venda nem que se queira. |
| 12 | O desconto persiste `approved_by` do username cru (D, "valida A persiste B") | `shop/services/pos.py:1378-1379`, `:1401-1406`, `:1556-1558` | **CONFIRMADO no fato, ERRADO no diagnóstico** | Quando a aprovação **é** exigida, `validate_manager_approval` já verificou aquele username — A e B são o mesmo. O buraco real é o inverso e mais grave: ver §D-1. |
| 13 | "Dois resolvers de terminal divergentes" (D, achado principal) | `projections/pos.py:454-457` (`Terminal.default()`) vs `backstage/services/pos.py:506-507` (primeiro ativo por `ref`) | **CONFIRMADO (provado) — exemplo de D invertido** | D citou `totem-01 < pdv-main`; alfabeticamente `pdv-main < totem-01`, então esse caso **não** quebra. Quebra com qualquer ref antes de `pdv-main` (`balcao`, `atendimento`, `caixa-02`). Probe abaixo. |
| 14 | `review_sale` e `close_sale` não compartilham validação (D) | review `shop/services/pos.py:598-633`; close `:2203-2223` + `:2327-2334` | **PARCIAL** | É verdade que review avisa e close recusa. Mas **todo** caso que o close recusa a review já sinaliza no mesmo `code` — é escalada preview→commit, não divergência cega. Ver §E. |
| 15 | Micro-drift: `cash_movement` declara `reason` required (D) | schema `projections/pos.py:1063` vs `services/pos.py:122-124` | **CONFIRMADO, inofensivo** | O contrato é mais estrito que o servidor. O cliente manda sempre (`usePosCashSession.ts:117-121`). Documentação, não bug. |
| 16 | "RBAC: nenhuma permissão nova" (D) | `shop/management/commands/setup_groups.py:102-105`, `:148`, `:154-157`, `:227-228` | **CONFIRMADO** | `Caixa` = `operate_pos` + `manage_orders`. `Gerente` tem `adjust_shift` e **não** `audit_shift` (comentário :224-226). `Dono` tem `audit_shift`. Nada a mudar. |
| 17 | "Permissão única gateando riscos diferentes" (G, implícito) | `permissions.py:57-86`; views acima | **REFUTADO** | O gate único é a **porta**; o risco é regateado por dentro: PIN de gerente (`adjust_shift`) na sangria/destrave/refund/serve/cancel, `perform_closing` no fechar caixa, `audit_shift` no X/Z. |
| 18 | "Vazamento de PII no SSE" (implícito na pauta) | `_sse_emitters.py:361-375`; `backstage/handlers.py:86-118` | **REFUTADO** | Corpo é `{kind, ref}`. Sem nome, telefone, CPF ou valor. |
| 19 | `close_sale` sem idempotência real (implícito em G §P2) | `shop/services/pos.py:287-301` | **JÁ CORRIGIDO** | `_claim_sale_request` trava `IdempotencyKey(scope,key)` no banco; a segunda request devolve a mesma venda. O comentário :272-286 descreve o defeito que isso consertou. |

### Prova executada (probe descartável, fora do repo)

```
projection_terminal=pdv-main | shift_terminal=pdv-main | projection_ve_turno_aberto=True
| drawer_open=RECUSADO(Caixa não aberto.)
| close=RECUSADO(...)  | current_shift_sem_ref=None
```
(cenário: `Terminal.objects.create(ref="balcao")` + `Terminal.default()`; abertura pelo fluxo real da UI,
que manda `terminal_ref = pos.terminal_ref` — `usePosCashSession.ts:94`.)

E, abrindo **sem** ref (como faz qualquer chamada direta):
```
mutation=balcao  projection=pdv-main  open=False
```

---

## C. Achados confirmados, com gravidade recalibrada

### C-1 · P0 — Dois resolvers de terminal: um segundo terminal cadastrado no Admin **paralisa o PDV**

**Risco × esforço:** risco máximo (o balcão para de vender e a mensagem mente sobre o motivo), gatilho de
um clique de gestor, correção de poucas linhas. É o achado mais grave do WP.

**Mecanismo, do clique até o efeito:**
1. A gerente tem `add_terminal`/`change_terminal` (`setup_groups.py:148`) e cadastra o segundo aparelho em
   Equipamentos com ref `balcao-2` (ou `atendimento`, `caixa-02` — qualquer coisa antes de `pdv-main`).
2. `POSView.get` → `build_pos(operator=…)` (`operations.py:304`) → sem terminal → `Terminal.default()`
   (`projections/pos.py:454-457`) → **`pdv-main`**. A tela diz `pdv-main`.
3. O operador aperta "Abrir caixa". A tela manda `terminal_ref = pos.terminal_ref` (`usePosCashSession.ts:94`)
   → turno abre em `pdv-main`. A projection recarrega e mostra **caixa aberto**. Tudo parece bem.
4. A partir daqui, **toda** mutação que não carrega ref resolve por `_terminal("")` =
   `Terminal.objects.filter(is_active=True).order_by("ref").first()` (`backstage/services/pos.py:506-507`)
   → **`balcao-2`**, que não tem turno:
   - `_open_shift_or_raise` (`:638-642`) → `POSError("Caixa não aberto.")` em sangria, suprimento,
     abertura de gaveta, destrave, pedido de troco, atender/cancelar troco e devolução em dinheiro;
   - `_pos_payload_with_runtime` → `_open_cash_shift_for_request` (`operations.py:226-232`) devolve `None`
     → **`POSReviewSaleView` e `POSCloseSaleView` retornam 409 `cash_shift_required`** (`:2661`, `:2689`):
     **não se vende mais nada**;
   - `closeCashShift` não manda ref (`usePosCashSession.ts:99-105`) → `current_shift("")` = `None` →
     "Caixa não aberto": o turno aberto **não pode ser fechado pela tela**.
5. O operador lê "Abra o caixa antes de finalizar" numa tela que mostra o caixa aberto. Não há saída pela UI.

**Por que passou:** todo teste do caixa roda com **um** terminal — `test_pos_cash_service.py:83` chega a
afirmar `shift.terminal == Terminal.default()`, o que só é verdade no mundo de uma gaveta. O comentário em
`current_shift` (`:487-490`) já previu isso ("quem chama precisa passar o ref"), e o único chamador que
obedeceu foi o comprovante (`usePosCashSession.ts:157-162`).

**Fix mínimo (uma linha + promoção do helper):** um resolver só. Em `backstage/services/pos.py`, renomear
`_terminal` para `resolve_terminal` (público) e, em `projections/pos.py:454-457`, trocar
`terminal = Terminal.default()` por:

```python
        terminal = resolve_terminal("")
```

Isso já fecha o P0 (projection e mutação passam a concordar sempre). O endurecimento de D — falhar fechado
com 409 quando há 2+ terminais ativos e nenhuma estação vinculada — é a **segunda** fase, correta e
separável; a decisão de produto de `Terminal.default()` (`terminal.py:44-50`) continua válida para loja de
uma gaveta.

---

### C-2 · P1 — "Abrir caixa" com valor negativo abre com R$ 0 em silêncio

**Risco × esforço:** risco médio-alto (fundo de troco errado envenena o esperado do fechamento cego do dia
inteiro), esforço de uma linha. A assimetria é gritante: `close_cash_shift` **recusa** negativo
(`test_pos_cash_service.py:126-130`), e `parse_money_to_q` (`:24-42`) tem docstring dizendo que zero
silencioso num fechamento cego é inaceitável — a abertura faz exatamente isso.

**Mecanismo:** operador digita `-10` (ou cola com sinal). `parse_money_to_q` devolve `-1000`;
`max(0, …)` (`backstage/services/pos.py:65`) devolve `0`; `cash.open_shift(float_q=0)` não lança
`FLOAT_IN` nenhum (`shifts.py:76`); o guard `float_q < 0` (`shifts.py:57-58`) nunca vê o sinal. Probe:
turno criado, `ENTRIES = []`. O operador acha que declarou fundo; o livro começa vazio; a contagem cega no
fim do dia acusa a sobra do fundo real como diferença sem explicação.

**Fix mínimo (uma linha), em `backstage/services/pos.py:65`:**
```python
    float_q = parse_money_to_q(opening_amount_raw)
```
O `CashError("INVALID_AMOUNT")` do pacote já vira `POSError` no `except` logo abaixo (`:73`) e a view devolve
400 com `field: opening_amount` (`operations.py:1871`). Vazio continua valendo `0` (`parse_money_to_q:35-36`).

---

### C-3 · P2 — Contrato de ações: `request_change` descreve um payload que não existe

**Risco × esforço:** risco baixo hoje (nada consome `payload_schema` em runtime no POS — o teste de contrato
`test_pos_headless_surface_contract.py:156-164` só confere que os **refs** existem), esforço trivial.
Mas é a única fonte que uma segunda superfície leria, e ela está errada nos três campos.

**Mecanismo:** `projections/pos.py:1113` declara `{"required": ["kind"], "optional": ["amount","note"]}`.
O endpoint lê `amount`/`denominations`/`note` (`operations.py:2109-2111`); o service exige `amount > 0`
(`services/pos.py:339`) e valida `denominations` contra `CHANGE_DENOMINATION_VALUES` (`:294-315`); `kind`
não existe em lugar nenhum — é resíduo do tipo "aproximado/moedas/notas" que o próprio docstring
(`:335-338`) conta que foi removido.

**Fix mínimo, uma linha em `projections/pos.py:1113`:**
```python
            payload_schema={"required": ["amount"], "optional": ["denominations", "note"]},
```
Junto (2 linhas): `close_cash_shift` (`:1052`) não declara `terminal_ref`, que o endpoint lê
(`operations.py:1909`); e `fire_tab` (`:1223`) deve declarar `idempotency="ledger"` — ver C-4.

---

### C-4 · P2 — `fire_tab` promete dedupe por `client_request_id` que não existe (a proteção real é outra)

**Risco × esforço:** risco baixo (o comportamento é seguro), esforço de uma linha. Vale corrigir porque a
promessa errada convida alguém a confiar nela no futuro.

**Mecanismo:** `projections/pos.py:1223` declara `idempotency="client_request_id"`; `fire_pos_tab`
(`shop/services/pos.py:1097-1161`) usa a chave só no `logger.info` (`:1159`). A idempotência verdadeira é do
ledger KDS: `fire_lines` toma `select_for_update` na Session (`shop/services/kds.py:144`) e descarta linha já
disparada por `line_id` (`:156-160`). Dedupe por request quebraria o fire progressivo por curso.

**Fix mínimo, uma linha:** `idempotency="ledger"` em `projections/pos.py:1223`, com nota apontando o
`line_id`. A recalibração de D está certa e deve prevalecer sobre a proposta original de G.

---

### C-5 · P2 — Aprovação gerencial: dois parsers, e o crachá é descartado antes de chegar ao validador

**Risco × esforço:** risco operacional (atrito no balcão, que é o que faz o time deixar de chamar gerente),
esforço médio — mexe no `shop`, dono declarado.

**Mecanismo:** `validate_manager_override` (`shop/services/pos.py:1698-1754`) aceita **crachá OU
username+PIN**, recusa autoassinatura nas duas portas e devolve o `User` verificado — está certo e
documentado. `validate_manager_approval` (`:1661-1695`), usado só pelo desconto/override de preço da venda,
aceita **apenas** username+PIN e não devolve nada. E o parser do intent
(`shop/services/pos_intent.py:392-399`) copia só `username` e `pin`: mesmo que a tela mandasse `badge`, ele
morreria na porta. Resultado: o gerente com crachá no pescoço autoriza sangria encostando o crachá, mas tem
de digitar username+PIN para liberar um desconto.

**Fix mínimo:** `validate_manager_approval` passa a delegar em `validate_manager_override(payload.get("manager_approval"), operator_username=…, action="sale_discount")` quando há `reasons`, e `_manager_approval` (`pos_intent.py:392-399`) passa a preservar `badge`. Duas mudanças pequenas, um parser só.

---

### C-6 · P2 — Fechamento do dia: quantidade ilegível vira 0 em silêncio

**Risco × esforço:** risco médio (a sobra do dia deixa de ser baixada e a conciliação do fechamento passa a
mentir), esforço de uma linha. É o mesmo defeito que `parse_money_to_q` foi escrito para **não** cometer.

**Mecanismo:** o operador digita `1O` (letra O) ou `2,5` na sobra de um SKU. `_parse_qty`
(`backstage/services/closing.py:144-148`) devolve `0`; `perform_day_closing:44-48` toma o caminho
"nada sobrou": nenhum write-off de vencido/não-conforme acontece, e o snapshot grava zero. A divergência
aparece depois em `_reconciliation_errors` (`:335`) como venda fantasma, sem ninguém saber de onde veio.

**Fix mínimo:** `_parse_qty` levanta `ValueError("Quantidade inválida em <sku>.")` em vez de devolver 0; a
view já traduz `ValueError` para 400 (`operations.py:979-980`).

---

## D. Achados NOVOS (que G e D perderam)

### D-1 · P2 — `approved_by` de desconto é gravado **sem verificação nenhuma** quando a aprovação não era exigida

**Risco × esforço:** risco de integridade da trilha antifraude (não de dinheiro direto), esforço de uma linha.
É o inverso do que D descreveu, e é o caso que realmente existe.

**Mecanismo:** `validate_manager_approval` (`shop/services/pos.py:1666-1667`) **retorna cedo** quando não há
`reasons` — desconto abaixo do teto, sem override de preço: nada é verificado. Mas `build_session_ops`
(`:1378-1379`) lê `manager_approval.username` do payload **incondicionalmente** e carimba:
`meta["price_approved_by"]` (`:1402`), `line_discount["approved_by"]` (`:1406`) e
`manual_discount.approved_by` (`:1556-1558`). O parser do intent aceita `{"username": "joyce", "pin": ""}`
(`pos_intent.py:397-399` só exige que um dos dois exista). Um payload montado à mão — ou uma tela com o campo
de gerente preenchido e o PIN limpo — grava no pedido que a Joyce aprovou um desconto que ela nunca viu.
Quando a aprovação **é** exigida, o nome persistido coincide com o verificado, então o defeito é invisível
nos testes atuais.

**Fix mínimo, uma linha em `shop/services/pos.py`, dentro de `validate_manager_approval` no ramo `if not reasons:`:**
```python
        payload["manager_approval"] = None
```
(assinatura só existe quando houve desafio). O fix estrutural é `validate_manager_approval` devolver o `User`
verificado e `build_session_ops` receber esse nome em vez de ler o payload — o mesmo remédio que
`POSCancelRecentSaleView:2741` já aplicou e que o docstring de `validate_manager_override:1705-1710`
descreve como a lição aprendida.

### D-2 · P2 — Movimento de caixa não tem idempotência: uma resposta perdida vira sangria em dobro

**Risco × esforço:** risco de dinheiro real e silencioso, esforço médio (reusar o `IdempotencyKey` que a
venda já usa). É o maior P2 desta lista.

**Mecanismo:** `POSMovementView` (`operations.py:1936-1957`) não aceita nem consome `client_request_id`, e a
ação declara honestamente `idempotency="none"` (`projections/pos.py:1064`). O front tem só uma trava de
reentrância local (`usePosCashSession.ts:71`) e **não** faz retry automático (`usePosAction.ts:18-47`). Numa
resposta perdida (wifi da padaria, proxy, tablet dormindo), o `$fetch` estoura, o `catch` mostra
"Falha ao registrar movimento." (`:84`) e o operador aperta de novo com o mesmo corpo — inclusive o mesmo
`manager_approval`, que revalida e passa. Duas linhas `cash_out` de R$ 100 no livro; o esperado cai R$ 200
por R$ 100 que saíram; a contagem cega fecha com sobra de R$ 100 e ninguém consegue explicar. Vale igual para
`pos/accounts/<ref>/settle/` (`operations.py:2244`), que é **entrada** de dinheiro sem PIN e sem chave.

**Fix mínimo:** aceitar `client_request_id` em `POSMovementView` e `POSAccountSettleView` e reusar o
`_claim_sale_request`/`IdempotencyKey` de `shop/services/pos.py:384-468`, com escopo `cash-movement:<shift_id>`;
declarar `idempotency="client_request_id"` nas duas ações. Alternativa mais barata e ainda correta: o front
manda a chave e o servidor recusa uma segunda `Entry` com a mesma chave no mesmo turno.

### D-3 · P3 — `serveChangeRequest` é a única mutação do PDV com URL 100% hardcoded

`usePosCashSession.ts:266-269` monta o path na mão, sem passar por `actionHref`/`concreteActionHref`, apesar
de a ação `serve_change_request` existir na projection (`projections/pos.py:1116-1125`). Não quebra hoje (o
path bate), mas é o ponto que a fase 3 do WP precisa varrer junto com o fallback.

### D-4 — o que eu **procurei e não achei**

Registro pelo valor do negativo: (a) **sem** vazamento de PII no SSE do caixa — corpo é `{kind, ref}`
(`_sse_emitters.py:361-375`); (b) **sem** possibilidade de o browser escolher o turno da venda — a view 409a
antes e `_pos_payload_with_runtime` sobrescreve `cash_shift_id`/`pos_terminal_ref`
(`operations.py:214-223`, `shop/services/pos.py:2733-2750`); (c) **sem** parsing frouxo no intent da venda —
`_ALLOWED_TOP_LEVEL_KEYS` recusa chave desconhecida (`pos_intent.py:120-129`) e método/coleção/canal são
enums estritos (`:406-417`); o `_normalize_payment_method` permissivo de `shop/services/pos.py:2375-2379`
está **atrás** desse gate e não é alcançável pela API; (d) **sem** duplicação de venda por duplo clique — o
`IdempotencyKey` de `close_sale` (`:287-301`) resolve.

---

## E. Achados a DESCARTAR (de G ou D)

1. **G §P1 "pagamento digitado pode desaparecer" na formulação atual.** O mecanismo citado existe
   (`posIntent.ts:50`), mas o dano descrito não se materializa: o botão Finalizar só habilita com o total
   coberto (`presentation/payment.ts:105-107`) contra o total **da review** (`usePosSale.ts:343-345`), e o
   excedente não-dinheiro já é avisado nos dois lados (`payment.ts:99-102` e `shop/services/pos.py:589-597`).
   O que sobra é: numa linha única não-dinheiro, o valor digitado a mais é descartado e o servidor cobra o
   total exato — que é o comportamento **correto** (cartão não dá troco). Manter só como item de teste
   (fuzz de tender), não como P1 de implementação.
2. **G §P2 "idempotência prometida mas não aplicada" na versão "implementar dedupe por `client_request_id`".**
   Refutado pelo código: o dedupe por comanda quebraria o fire por curso (`kds.py:120-121`). Fica a opção B
   do próprio G, que é o que D propõe (C-4).
3. **D §P2 "sem estação vinculada, POS não abre estado mutável" como aceite do P0.** Contradiz
   `Terminal.default()` (`terminal.py:44-50`), decisão de produto explícita. D já reformulou; a versão
   reformulada é a que vale, e ela é **fase 2**, não pré-requisito do conserto do P0.
4. **D "review e close divergem" como P1 próprio.** Descartar como achado; manter como **teste de paridade**.
   Toda recusa do close tem aviso correspondente na review, com o mesmo `code`
   (`cash_tendered_amount_too_low` :606 ↔ :2218; `payment_tenders_total_mismatch` :630 ↔ :2329;
   `payment_tenders_required` :624 ↔ :2341). É escalada preview→commit, e o `code` estável é justamente o que
   permite a tela bloquear antes. O que falta é o teste que trava isso, não uma refatoração.
5. **D "o desconto valida A e persiste B".** Descartar a formulação; substituir por D-1, que é o defeito real.
6. **"Permissão única gateando coisas de risco diferente"** (pauta de auditoria). Refutado — ver B-17.
7. **G §P2 "manifest de actions gerado" como bloco grande.** O custo (gerador + consumo em 3 WPs) é
   desproporcional ao risco medido: nada valida `payload_schema` em runtime e todos os hrefs conferem hoje.
   Reduzir ao que paga: corrigir os 3 schemas errados (C-3/C-4) e **um teste** que percorre
   `_pos_actions()` e resolve cada `href` contra a URLconf. Isso pega a próxima divergência sem construir
   infraestrutura nova.

---

## F. Aceites verificáveis

Todos checáveis contra o código/suíte de hoje — nada depende de infra inexistente.

| # | Critério | Como se prova |
|---|---|---|
| F1 | Com dois terminais ativos (`balcao-2` e `pdv-main`), `build_pos().terminal_ref` == `current_shift().terminal.ref` | Teste de backend novo em `test_pos_cash_service.py`: cria os dois terminais, abre turno pelo fluxo da UI, assert de paridade projection↔mutation |
| F2 | Com dois terminais ativos, sangria/suprimento/gaveta/troco/refund **não** retornam "Caixa não aberto." com turno aberto | Teste de backend, um assert por mutação |
| F3 | Com dois terminais ativos, `POST pos/sale/close/` **não** retorna 409 `cash_shift_required` | Teste de API (`APIClient`), assert-negativo do código de erro |
| F4 | Turno aberto por um terminal pode ser fechado pela mesma tela sem passar `terminal_ref` | Teste de API em `POSCashCloseView` |
| F5 | `opening_amount="-10"` retorna 400 com `error.field == "opening_amount"` e **nenhum** `Shift` é criado | Teste de API; espelha `test_close_cash_shift_rejects_negative_count` (`test_pos_cash_service.py:126`) |
| F6 | `opening_amount=""` continua abrindo com `float_q == 0` (fluxo preservado) | Teste de backend (regressão) |
| F7 | Cada `href` de `_pos_actions()` resolve contra a URLconf, e cada chave de `payload_schema["required"]` é lida pela view correspondente | Teste de contrato em `test_pos_headless_surface_contract.py`, varrendo as 24 ações |
| F8 | `request_change` declara `required:["amount"]` e `optional` inclui `denominations` | Assert direto na projection |
| F9 | `fire_tab` **não** declara `idempotency="client_request_id"`; duplo fire do mesmo curso continua não duplicando ticket | Assert na projection + o teste existente de `test_pos_fire.py` |
| F10 | Venda com `manual_discount` abaixo do teto e `manager_approval={"username":"joyce","pin":""}` fecha **sem** gravar `approved_by` em `order.data`/`session.data` | Assert-negativo de payload em teste de backend |
| F11 | Todo `code` de erro do `close_sale` tem `code` de warning correspondente na `review_sale` para o mesmo payload | Teste de paridade parametrizado (matriz cash/pix/card/mixed/conta/parcial/excedente) |
| F12 | Duplo `POST pos/cash/movement/` com o mesmo `client_request_id` cria **uma** `Entry` | Teste de API |
| F13 | Quantidade ilegível no fechamento do dia retorna 400 e **não** grava `DayClosing` | Teste de API em `DayClosingView` |
| F14 | O canal SSE `cash` continua sem PII: payload só tem `kind` e `ref` | Assert-negativo em `test_pos_sse_cash_channel.py` (já existe a fixture) |

---

## G. Fronteiras e colisões

### Arquivos que este WP precisa tocar (lista exata)

**Backend — obrigatórios**
- `shopman/backstage/services/pos.py` — C-1 (`_terminal` → `resolve_terminal`), C-2 (`:65`), D-2
- `shopman/backstage/projections/pos.py` — C-1 (`:454-457`), C-3 (`:1052`, `:1113`), C-4 (`:1223`)
- `shopman/backstage/api/operations.py` — C-1 (`:229` passa a receber ref), D-2 (`POSMovementView:1936`, `POSAccountSettleView:2250`)
- `shopman/shop/services/pos.py` — C-5 (`:1661-1695`), D-1 (`:1666-1667` e/ou `:1378-1379`,`:1556-1558`)
- `shopman/shop/services/pos_intent.py` — C-5 (`_manager_approval` `:392-399` preserva `badge`)
- `shopman/backstage/services/closing.py` — C-6 (`_parse_qty` `:144-148`)

**Frontend — obrigatórios**
- `surfaces/pos-nuxt/app/composables/usePosCashSession.ts` — `closeCashShift` passa `terminal_ref` (`:99-105`), D-2 (`client_request_id`), D-3 (`:266-269` via `concreteActionHref`)
- `surfaces/pos-nuxt/app/utils/posIntent.ts` — só se a fase 3 remover o fallback do caminho de mutação (`:65-71`)

**Testes**
- `shopman/backstage/tests/test_pos_cash_service.py` (F1, F2, F5, F6, F12)
- `shopman/backstage/tests/test_pos_headless_surface_contract.py` (F7, F8, F9)
- `shopman/backstage/tests/test_pos_stress_guards.py` (F10, F11)
- `shopman/backstage/tests/test_day_closing_blind_count.py` (F13)

**Fora do escopo deste WP:** `packages/cashman/**` não precisa mudar — o guard de `float_q < 0`
(`shifts.py:57-58`) já está certo, só precisa parar de ser contornado.

### Matriz de colisão

| Arquivo | Risco | Quem mais mexe |
|---|---|---|
| `shopman/backstage/api/operations.py` (2761 linhas) | **ALTO** | Views de produção (`:712-922`), pedidos (`:995-1604`) e fechamento (`:952`) moram no mesmo arquivo — WPs 03/04/05. Este WP toca só `:214-232`, `:1850-2350`, `:2244-2260`. Coordenar por faixa de linha. |
| `shopman/shop/services/pos.py` (3423 linhas) | **ALTO** | Dono declarado é o orquestrador; qualquer WP que mexa em desconto, fiscal ou entrega colide. Faixas deste WP: `:1375-1420`, `:1550-1560`, `:1661-1695`. |
| `shopman/backstage/projections/pos.py` | MÉDIO | WP de catálogo/vitrine mexe em `_load_products`/`_product_projection`. Faixas deste WP: `:440-460`, `:940-1235`. |
| `shopman/backstage/services/closing.py` | MÉDIO | Provavelmente é do WP de fechamento do dia — C-6 pode migrar para lá (uma linha, sem dependência). |
| `surfaces/pos-nuxt/app/composables/usePosCashSession.ts` | BAIXO | Exclusivo do PDV. |

### Permissões novas e impacto em `setup_groups.py`

**Nenhuma.** Li `shopman/shop/management/commands/setup_groups.py` inteiro: o `Caixa` continua com
`cashman.operate_pos` + `shop.manage_orders` (`:102-105`); o PIN de gerente reusa `cashman.adjust_shift`,
que o `Gerente` já tem (`:155`); o fechar-caixa reusa `backstage.perform_closing` (`:157`); o X/Z reusa
`cashman.audit_shift`, que só o `Dono` tem (`:227-228`) — e o comentário `:224-226` explica por que o
`Gerente` **não** entra ali. Nada neste WP muda esse arquivo. Confirmo a seção RBAC de D.

### O que pertence a outro app/dono

- **Contrato único de `manager_approval` (C-5) e o `approved_by` verificado (D-1)** moram no orquestrador
  (`shopman/shop/services/pos.py` + `pos_intent.py`). O backstage consome. Precisa da palavra do dono do
  `shop`, como D já apontou.
- **C-6 (fechamento do dia)** é do app de fechamento, não do PDV. Incluí aqui porque G o listou na seção de
  testes; se houver WP de fechamento, migre para lá.
- **Cadastro de Terminal** (Admin/Unfold, `shopman/backstage/admin/terminal.py`) é do WP de Admin — mas é
  a porta que dispara o C-1, então a correção do C-1 é pré-requisito de qualquer trabalho de multi-terminal.

---

## H. Perguntas abertas para o dono do produto

1. **O alpha (`alpha.nelsonboulangerie.com.br`) tem mais de um `Terminal` ativo hoje?** O `seed` só cria
   `pdv-main` (`config/management/commands/seed.py:7282`), mas a gerente pode cadastrar outro pelo Admin. Se
   já houver um segundo com ref antes de `pdv-main` em ordem alfabética, o PDV **já está** quebrado em
   produção e o C-1 vira hotfix, não WP. É uma consulta de um comando ao banco do alpha.
2. **Quando houver balcão + totem, o terminal deve vir da estação confiável (`IsTrustedStation` /
   `station_trust`) ou de uma escolha explícita do operador na antessala?** A fase 2 do C-1 (falhar fechado
   com 2+ terminais) muda de desenho conforme a resposta: se é a estação, o ref vem do provisionamento; se é
   escolha, a antessala ganha um seletor e o PDV grava a preferência no dispositivo.
3. **Fundo de troco negativo deve ser 400 (recusa) ou 0 com aviso na tela?** Proponho 400, para espelhar o
   fechamento, que já recusa. Mas se o balcão usa "-" como atalho de alguma coisa hoje, quero saber antes de
   trocar um zero silencioso por uma parede na abertura do dia.
