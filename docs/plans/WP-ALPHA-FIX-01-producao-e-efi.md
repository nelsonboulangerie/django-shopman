# WP-ALPHA-FIX-01 — o silêncio da produção e o token do Efí

**Origem:** [ALPHA-READINESS-CODE-AUDIT-2026-08](ALPHA-READINESS-CODE-AUDIT-2026-08.md),
revisado por dois verificadores independentes que rodaram os cenários em
PostgreSQL real. Este WP é o plano de execução do que sobrou de lá.

**Estado:** aberto (2026-08-17). Branch de origem da auditoria:
`claude/shopman-alpha-readiness-v2mwlg` (fix de pricing já commitado lá).

> **Leia a §0 antes de codar.** Ela corrige duas conclusões erradas da primeira
> auditoria e lista três armadilhas que fazem a "correção óbvia" não corrigir
> nada — ou piorar.

---

## 0. O que já foi verificado (não redescubra)

### O mecanismo, confirmado

`CraftExecution.finish()` abre `transaction.atomic()` em
`packages/craftsman/shopman/craftsman/services/execution.py:76` e fecha em `:319`.
O `production_changed.send(...)` está em **`:324`, fora** do bloco. O mesmo
formato em `void()` (atomic `:341-365`, send `:369`). Nenhuma transação externa
resgata: não há `ATOMIC_REQUESTS`, nenhum caller abre `atomic()` em volta
(`shop/services/production.py:195` e `:350`, `backstage/services/production.py:406-413`
são todos nus), e não há `transaction.on_commit` nesse caminho.

A escrita de estoque (MAKE) mora em
`packages/craftsman/shopman/craftsman/contrib/stockman/handlers.py`. A perna de
**output** engole tudo: `try` em `:498` → `except Exception` em `:560-565` com
`logger.warning("... (non-fatal)")`. Resultado empírico (probe com
`StockPlanning.realize` levantando): **`finish()` retorna com sucesso**, a WO fica
`finished`, os insumos foram consumidos e a vitrine fica **zero**. Retry →
`CraftError: TERMINAL_STATUS`. Irrecuperável pela mesma API.

### Duas conclusões da 1ª auditoria que estavam ERRADAS

1. **"Um receiver anterior estourando aborta a escrita de estoque."** ❌ Falso.
   O escritor de estoque é o receiver **#0**: o app
   `shopman.craftsman.contrib.stockman` está em `config/settings.py:204`, antes de
   `shopman.shop` (`:227`) e `shopman.storefront` (`:229`). Nada o preempta.
   (`Signal.send` de fato aborta os seguintes na primeira exceção — mas isso não
   alcança o estoque, e sim os 7 receivers *posteriores*.)
2. **"Toda perna engole a exceção."** ❌ Metade. `_consume_materials(work_order)`
   é chamado em `:483`, **antes** do `try` de `:498` — uma falha dura ali
   **propaga** para fora do `finish()`. Só o `StockMovements.issue` individual é
   protegido (`:402-406`), e o *shortfall* de insumo (`:408-412`) é
   **decisão deliberada e documentada** (docstring em `:370-372`, insumo ainda
   não é first-class pré-go-live). **Não "conserte" o shortfall neste WP.**

### Severidade real: P3 latente, não P1

Todos os gatilhos de operação normal já estão fechados: over-yield (corrigido, com
regressão em `shopman/shop/tests/test_production_yield_ledger.py`), under-yield
(`_write_off_yield_shortfall`, `handlers.py:415-466`), insumo insuficiente
(barrado em `backstage/services/production.py:397-399` **antes** do `finish`),
quant planejado ausente (não é caminho de drift — `planning.py:133-135` credita
`min(actual, max(planned_balance,0))`). Drift precisa de falha genuína: queda de
DB/deploy no meio do handler, ou bug novo no realize.

### Por que ninguém nunca viu (o achado que importa)

Quando o realize falha, as unidades **ficam no quant `started`**. A
disponibilidade classifica esse bucket como `in_production`
(`packages/stockman/shopman/stockman/services/availability.py:249-251`) e
`_policy_promisable_qty` devolve `expected + planned` para **toda** política
exceto `stock_only` (`:23-33`). O catálogo Nelson é semeado `PLANNED_OK`
(`config/management/commands/seed.py:1433`, `:2797`). **A loja continua vendendo
normal.** O pão está na prateleira, o dinheiro entra. O que fica errado é o
bucket/posição e o insumo que não baixou.

E o fechamento do dia **mascara**: `produced_by_sku` sai de `WorkOrder.finished`
(`backstage/services/closing.py:263-266`) e `available = counted + produced`
(`:296-298`), então `sold > available` nunca dispara; o SKU simplesmente
**desaparece** da tela de contagem.

Observabilidade hoje: **nenhuma**. Sentry só captura `ERROR` (o `init` em
`config/settings.py:1343-1348` não passa `LoggingIntegration`), os engolimentos
logam `WARNING`. Nenhum `OperatorAlert`, nenhum sweep, nenhuma seção de produção
no `diagnose_operational.py`. O tipo de alerta `stock_discrepancy` existe em
`shopman/backstage/models/alerts.py:17` e **nunca é emitido em lugar nenhum**.

### ⚠️ Três armadilhas

1. **`transaction.on_commit` NÃO corrige.** O callback roda *depois* do commit —
   a WO já está `FINISHED` quando o handler falha. Move o problema, não resolve.
2. **`_handle_finished` NÃO é idempotente.** Re-rodar credita a vitrine **em
   dobro** (o `realize` credita o `actual` cheio, independente do saldo
   planejado). Portanto o **marcador** tem que ser o guarda do sweeper — nunca
   confie em idempotência do handler.
3. **Hazard inverso, já vivo.** Um receiver *posterior* estourando faz uma fornada
   **100% commitada** devolver `400 "Falha ao concluir produção"` ao operador
   (`backstage/services/production.py:404-410` → `_looks_like_stock_error` False),
   e o retry morre em `TERMINAL_STATUS`. O `idempotency_key` existe no Core
   (`execution.py:78-92`) e o backstage **nunca passa**. É o item 6.

---

## 1. Tarefas

Ordem recomendada. Cada uma é independente; commit separado por tarefa.

### T1 — Parar de engolir a perna de output (o silêncio é o bug)
**Onde:** `packages/craftsman/shopman/craftsman/contrib/stockman/handlers.py:560-565`.

O caso "insumo consumido e nada realizado" não pode ser uma linha de log. Subir
para `logger.exception` e **re-levantar** depois de logar, alinhando com a perna
de insumos (que já propaga). A camada externa **já está pronta** para receber:
`backstage/services/production.py:414-418` captura, chama `_create_stock_short_alert`
quando parece de estoque, e mostra o erro ao operador — hoje isso é código morto
para esta falha.

⚠️ Core é sagrado: leia os outros `except Exception` do arquivo antes
(`:154, :172, :199, :221, :238, :281, :355, :403`) e **não** mude o
comportamento do *shortfall* de insumo (`:408-412`) nem os engolimentos de
`planned`/`adjust`/`void` — só a perna `finished`/realize. Se a decisão for
"não propagar", então **obrigatoriamente** emitir `OperatorAlert`
(`stock_discrepancy`, que já existe e está órfão) — o requisito é **deixar de ser
silencioso**, propagar é o meio mais simples.

**Teste:** forçar `StockPlanning.realize` a levantar e provar que
(a) o operador vê erro/alerta, (b) a divergência não passa calada. O harness do
probe: criar recipe+batch, `craft.plan/start/finish` reais, Postgres.

### T2 — Quick-finish sem partição passa a honrar o guardrail de insumos
**Onde:** `shopman/backstage/services/production.py:113-148`.

`apply_quick_finish` com `partition=None` chama `production_core.quick_finish(...)`
direto (`:129-135`), então **nunca** passa por `apply_finish` → `check_finish_materials`
(`:627-664`) não roda: sem `ProductionStockShortError`, sem alerta `stock_short`.
Só o caminho *com* partição passa por `apply_finish` (`:137-148`). A "fornada
avulsa" é o único finish sem guardrail de insumo.

Rotear o caminho sem partição pelo mesmo `apply_finish` (via `quick_plan` +
`apply_finish`, como o partitioned já faz), preservando a assinatura de retorno
(`output_sku, wo_ref, total`) e o `force`.

**Teste:** quick-finish sem partição com insumo insuficiente → erro/alerta de
estoque (hoje passa calado).

### T3 — Marcador durável + sweeper (espelhar o lifecycle de pedido)
**Onde:** Core `craftsman` (marcador) + `shopman/shop/management/commands/` (sweeper)
+ `maintenance_worker.py:37-64` (registro).

O lifecycle de pedido resolve exatamente isso e é o modelo a copiar:
`order_changed` é emitido **dentro** do `@transaction.atomic _do_commit`
(`packages/orderman/.../services/commit.py:185`, `:397-402`), o receiver roda
`secure_stock` **sincronamente, pré-commit** (`shopman/shop/lifecycle.py:163-202`),
e há marcador durável (`DURABLE_PHASES` / `phase_complete`, `:205-238`) com
re-dispatch por `sweep_stuck_orders`. Produção não tem nenhum dos dois.

1. Carimbar algo como `WorkOrder.meta["stock_realized"] = true` **depois** das duas
   pernas terem sucesso.
2. Novo comando (ex. `sweep_unrealized_production`) que acha WO `FINISHED` além de
   um limiar **sem** o marcador e re-realiza.
3. Registrar em `MAINTENANCE_COMMANDS`.

⚠️ **O marcador é o guarda** (armadilha 2: re-rodar sem guarda credita em dobro).
⚠️ Não use `on_commit` como "a correção" (armadilha 1).
✅ `WorkOrder.meta` **já existe** (`packages/craftsman/shopman/craftsman/models/work_order.py:125`,
`JSONField`) — **sem migração**, é o padrão do projeto para dado contextual
(CLAUDE.md §Core é Sagrado, regras 1–3).

### T4 — Efí: token só por header + fechar o fail-open de valor
**Onde:** `shopman/shop/webhooks/efi.py:188-190`,
`shopman/shop/services/pix_confirmation.py:188-191`.

(a) `_check_auth` cai para `request.query_params.get("token")` em `:190`. Em query
string o segredo vaza nos access logs do provedor e **vai para o Sentry** em
qualquer erro (o sentry-sdk captura a query string; `send_default_pii=False` não
remove). Como **não há proxy mTLS no deploy** (nada de nginx/traefik no repo; DO
App Platform direto, então `X-SSL-Client-Verify` nunca chega), o token estático é
a autenticação **única**. Aceitar só por header — ou, se a Efí exigir query,
manter e **documentar** o requisito de não logar query string + rotação.

(b) `_captured_payment_is_sufficient`: no ramo `intent_backed=False`,
`paid_q is None → return True` (`:188-191`). Webhook autenticado **sem `valor`**
dispara `on_paid` sem conferir valor. Fechar (tratar ausência de valor como
insuficiente/indeterminado, não como suficiente), preservando o caminho com intent
(que usa `has_sufficient_captured_payment`).

**Teste:** `shopman/shop/tests/test_payment_webhooks.py` já cobre Efí — estender:
token em query rejeitado (se (a) for header-only) e webhook sem `valor` não paga.

### T5 — Tirar o auto-confirm mock do template de produção
**Onde:** `.do/app.subdomains.yaml:160-163`.

`SHOPMAN_MOCK_PIX_AUTO_CONFIRM=true` está no template de **produção**. Inerte hoje
(o check `SHOPMAN_E003` barra `payment_mock` em prod), mas fica **pré-armado**: no
dia que alguém ligar `SHOPMAN_ALLOW_MOCK_PAYMENT_ADAPTERS=true` para destravar um
deploy, todo PIX se autoconfirma de graça. Default `false`.

### T6 — Backstage passa `idempotency_key` no finish (mata o dead-end do retry)
**Onde:** `shopman/backstage/services/production.py` (chamada de `finish`) +
`shopman/backstage/api/operations.py` (`WorkOrderFinishView`).

O Core aceita `idempotency_key` e devolve a WO existente no replay
(`execution.py:78-92`); o backstage nunca passa, então o retry do operador após o
hazard inverso (armadilha 3) morre em `TERMINAL_STATUS`. Passar uma chave estável
(derivada de WO+quantidade+ação) para o retry ser idempotente de verdade.

---

## 2. Definição de pronto

- [ ] `make test` verde (~6.500). ⚠️ `test_maintenance_worker.py` falha com
      `OperationalError: the connection is closed` em Postgres efêmero mal
      provisionado — é artefato de ambiente, não regressão (passa em SQLite e no
      CI). Se falhar só isso, não é você.
- [ ] `make test-runtime` verde (141) — exige PostgreSQL + Redis reais.
- [ ] `make lint` e `make admin` verdes.
- [ ] Teste novo por tarefa, e **cada um provado como guarda**: falha no código
      antigo, passa no corrigido (foi assim que o fix de pricing entrou).
- [ ] Nada de alias de compat / resíduo de rename (CLAUDE.md).
- [ ] Se T3 mexer em `docs/reference/data-schemas.md` (chave nova em
      `WorkOrder.meta`), documentar lá **antes** de usar.

## 3. Fora de escopo (decidido, não esquecido)

- **Shortfall de insumo não-fatal** (`handlers.py:408-412`): decisão deliberada
  pré-go-live. Não mexer neste WP.
- **Antifraude de coordenada** (`shop/rules/validation.py:250-253`): a cidade
  curto-circuita o CEP; numa operação de cidade única o CEP nunca é alcançado.
  A correção ingênua (CEP estrito) **bloqueia cliente legítimo** cujo pin cai num
  prefixo vizinho — troca fraude de ~R$ 7 por pedido perdido. A correção certa
  compara a **faixa de distância** do pin com a do CEP alegado (bloqueia só spoof
  que muda a taxa) e precisa de decisão de produto sobre tolerância. WP próprio.
- **Hardening P2/P3 restante** (SSE por permissão fina, throttle de PIN,
  `/health` sem throttle, Sentry sem corpo, stock-alert anônimo): ver §Hardening
  da auditoria. WP próprio.
