# Verificação WP-07 — B.I.

Verificado contra a worktree `coordenar-sessoes-deploys-b9cdac`, descendente de `main`
(`9469c92a2`, 29/08/2026). Toda linha citada foi aberta e lida inteira. Onde a linha mudou
de lugar em relação ao WP do G ou do D, registro a **linha atual**.

## A. Superfície real (o que existe hoje)

### Backend — fundação de dados (`shopman/backstage/bi/`)
| Arquivo | O que é |
|---|---|
| `bi/canonical.py` | Camada canônica: `CanonicalSale`/`CanonicalSaleLine`/`CanonicalShift`/`CanonicalCashEvent` + a regra "o dia nativo vence" e os `source_conflicts`. |
| `bi/sources/orderman.py` | Pedido nativo → venda canônica. Exclui `CANCELLED`/`RETURNED` e devolve a contagem à parte. |
| `bi/sources/historical.py` | Export do Yooga → venda canônica. |
| `bi/sources/cashman.py` | Livro-caixa → `CanonicalShift`/`CanonicalCashEvent`. |
| `bi/ingest/yooga.py` | Ingestão do export histórico (`ImportBatch`). |
| `bi/mapping.py` | Sugestão de de-paras (produto/categoria/forma de pagamento). |
| `bi/daily_series.py` | Materialização da série diária (`DailySalesFact`) + `materialized()`. |
| `bi/alerts.py` | Cinco alarmes (`import_silence`, `daily_revenue_vs_baseline`, `native_overrides_history`, `cash_variance_by_drawer`, `curation_pending`) → `OperatorAlert` + `BIAlertEvent`. |
| `bi/scenarios.py` | Cenários com IA: `gather_inputs` → `build_prompt` → `copy_assist.suggest` → `BIScenarioReport`. |

### Backend — projections (`shopman/backstage/projections/`)
`bi_sales.py`, `bi_production.py`, `bi_cash.py`, `bi_customers.py`, `bi_explore.py` (24 métricas
em 9 famílias), `bi_forecast.py`, `bi_change.py`, `bi_profiles.py`, `bi_payments.py`,
`bi_scenarios.py`, e `sales_series.py` (dono único da série diária — **não é `bi_*` mas é o
coração do B.I.; nenhum dos dois WPs o mencionou**).

### Backend — API (`shopman/backstage/api/bi.py`, montado em `api/urls.py:265-280`)
11 rotas: `bi/production/`, `bi/sales/`, `bi/cash/`, `bi/customers/`, `bi/explore/`,
`bi/consumption-profiles/`, `bi/forecast/`, `bi/change/`, `bi/views/`, `bi/views/<pk>/`,
`bi/scenarios/`. Gate comum `backstage.view_bi`; `bi/cash/` soma `cashman.audit_shift`.
**Não há SSE, não há export CSV/XLSX** (confirmado por varredura em `surfaces/bi-nuxt/`).

### Admin (não mencionado por G; mencionado só de passagem por D)
- `shopman/backstage/admin/bi_alerts.py` — `BIAlertRuleAdmin`, `BIAlertEventAdmin`, `BIScenarioReportAdmin`.
- `shopman/backstage/admin/imports.py`, `aliases.py`, `curation.py` — lotes, de-paras, curadoria.
- `shopman/backstage/admin/navigation.py:195` — item "Alarmes" no menu.
- **Não há tela `admin_console/` de B.I.** (o `admin_console/` só tem caixa/copy/badge/agente/settings).

### Comandos
`shopman/backstage/management/commands/evaluate_bi_alerts.py` (rodado pelo
`maintenance_worker.py:64`), `refresh_bi_daily_series`, `export_bi_schema`;
`config/management/commands/setup_bi_reference.py` e o bloco de `BIAlertRule` do `seed.py:8253-8315`.

### Superfície (`surfaces/bi-nuxt/`)
8 páginas (`index`=produção, `sales`, `cash`, `customers`, `profiles`, `explore`, `forecast`,
`scenarios`), 7 composables, `presentation/bi.ts` (puro), `generated/biContract.ts` (gerado por
`export_bi_schema`, com teste de drift).

---

## B. Evidências dos WPs, veredito uma a uma

| # | Afirmação (de quem) | Arquivo:linha ATUAL | Veredito | Nota |
|---|---|---|---|---|
| 1 | Gate comum `view_bi` (G `bi.py:38`; D `:38-42`) | `shopman/backstage/api/bi.py:38-42` | CONFIRMADO | `_BIBase.required_permission = "backstage.view_bi"`. |
| 2 | Caixa exige permissão adicional (G `:94`,`:99`; D `:94-99`, tupla=AND) | `api/bi.py:94-99` + `api/permissions.py:129-133` | CONFIRMADO | `_required_codes` + `all(...)`: é AND mesmo. |
| 3 | API poda métricas audit-only (G `:157`; D `:157-161`) e 403 no pedido direto (D `:142-146`) | `api/bi.py:139-146` e `:157-161` | CONFIRMADO | `replace(report, metrics=...)` filtra por `metric_family`. |
| 4 | `cash_difference` é audit-only (G `bi_explore.py:222`; D `:224`) | `projections/bi_explore.py:224` | CONFIRMADO (D exato, G off-by-2) | `AUDIT_ONLY_FAMILIES = frozenset({"cash"})`; a métrica está em `:73`. |
| 5 | Exemplo estático de quebra de caixa (G+D `bi.ts:246`) | `surfaces/bi-nuxt/app/presentation/bi.ts:246` | CONFIRMADO | `{metric:"cash_difference", by:"operator"}`. |
| 6 | `availableExamples` filtra dimensão, não métrica (G `:184`; D `:184-196`) | `presentation/bi.ts:184-196` | CONFIRMADO | Só testa `supported.has(by/by2)`. E `operator` continua "suportado" via as métricas de produção, então o chip **nunca** some. |
| 7 | Save de cenário não checa auditoria (D `bi.py:254-272`) | `api/bi.py:254-272` (+ list em `:291-295`) | CONFIRMADO | `_validated_view_config` chama só `validate_config` (gramática). O `GET /bi/views/` devolve config bruta. |
| 8 | Clientes mistura janela e global (G `:48,75,90`; D `:48,75,90,93` — "4 de 5") | `projections/bi_customers.py:48` (janela), `:55-72` (segments), `:90-93` | CONFIRMADO, e **pior** | São **5** campos globais, não 4: `segments` (`:69-72`) também é global. Só `new_by_week` (`:74-80`) respeita a janela. |
| 9 | `average_ticket_q` de Clientes = média de médias com divisão inteira (D) | `bi_customers.py:93` | CONFIRMADO | `sum(tickets)//len(tickets)`, não ponderado por `total_orders`. Menor. |
| 10 | Cenários IA não enviam janela (G `useBiScenarios.ts:17`; D `:17-20`) | `composables/useBiScenarios.ts:17-20` | CONFIRMADO | `body: { focus }`, nada mais. |
| 11 | A proposta do G ("enviar `useBiWindow().range`") não funciona: a API lê `request.GET` num POST (D `bi.py:376-377`) | `api/bi.py:376-377` | CONFIRMADO | `_query_date(request, ...)` lê `request.GET`. Body seria ignorado. D está certo e G está errado. |
| 12 | Backend grava a janela bruta, não a efetiva (D `scenarios.py:236-237`) | `bi/scenarios.py:236-237` vs `:99-101` | CONFIRMADO, impacto ~nulo hoje | `date_from/date_to` já vêm defaultados em `:229-230`; a normalização só difere se `from>to` ou janela > 1830 dias — inalcançável pela UI, que não manda janela nenhuma. É dívida de contrato, não bug vivo. |
| 13 | Cenário salvo não exibe a janela na UI (D) | `pages/scenarios.vue` — zero ocorrência de `window`/`janela` | CONFIRMADO | O contrato TEM `window_from`/`window_to` (`projections/bi_scenarios.py:26-27,57-58`); a tela não os usa. |
| 14 | `cash_variance_by_drawer` já está mitigado (D `alerts.py:115-130`) | `bi/alerts.py:115-118` e `:121-142` | CONFIRMADO | `_fire` troca a mensagem por `_CASH_AUDIT_PUBLIC_MESSAGE` quando `rule.metric in AUDIT_ONLY_METRICS` (`models/bi_alerts.py:56`). Há teste (`test_bi_alerts.py:258`, `:343`). |
| 15 | O vazamento real é `daily_revenue_vs_baseline` com `_brl` (D `alerts.py:216-218`) | `bi/alerts.py:216-218` (+ `_fire` `:126-130` não redige) | CONFIRMADO | A mensagem pública sai com `R$ medido` e `R$ baseline`. |
| 16 | O bus de alertas é mais largo que `view_bi` (D `permissions.py:120-129`) | `shopman/backstage/permissions.py:120-129` + `api/alerts.py:45-59` | CONFIRMADO | `is_staff AND (manage_orders \| production \| operate_pos \| operate_kds \| operate_production \| operate_purchase)`. O grupo "Caixa" (`setup_groups.py:102-105`) tem `operate_pos` e `manage_orders`. |
| 17 | A regra de faturamento está ativa e roda | `config/.../seed.py:8256-8265` (`is_active: True`) + `shop/.../maintenance_worker.py:64` | CONFIRMADO (novo — nenhum dos dois provou que dispara) | O vazamento não é hipotético: a regra nasce ligada no seed e o worker a avalia todo ciclo. |
| 18 | Datas inválidas viram default silencioso (G+D) | `api/bi.py:45-52` (`return None`) + `projections/bi_production.py:178-186` | CONFIRMADO | `date.fromisoformat` falha → `None` → `_normalize_window` inventa a janela. |
| 19 | "Reverte decisão documentada DUAS vezes" (D) | `api/bi.py:52` (comentário) ; `bi_production.py:178-186` (**sem** docstring/comentário) | PARCIAL | Documentado **uma** vez, no `_query_date`. O `_normalize_window` não declara nada — nem o clamp de 1830 dias. D superestimou o lastro. |
| 20 | Célula mínima: as projections não expõem `n` por bucket (D) | `bi_explore.py:385-420` (`_sales_rows`), `:616+` (`_payment_rows`) | CONFIRMADO | `BIExploreRow` só tem `value`; `orders` existe dentro de `_sales_rows` mas não sai no contrato. Custo real. |
| 21 | Egress de agregados financeiros para o provedor de IA (D `scenarios.py:94-128`) | `bi/scenarios.py:94-156` (o bloco é maior do que D citou) | CONFIRMADO no fato, **REFUTADO como achado** | Ver §E.1. É decisão documentada e correta, com fronteira explícita. |
| 22 | Aba "Caixa" sem gate client-side (D `BiTopBar.vue:30`) | `components/BiTopBar.vue:30` | CONFIRMADO | Tab estática; nenhum payload do B.I. expõe capacidade de auditoria, então a UI não tem como esconder. |
| 23 | SSE `/events/<kind>/` não é achado (descarte de D) | — | CONFIRMADO | Não há **nenhum** canal SSE de B.I.: `grep -rni "sse\|eventStream"` em `surfaces/bi-nuxt/` não retorna nada. O descarte é correto, e por um motivo ainda mais forte do que D deu. |
| 24 | "Alertas BI podem vazar valores financeiros" — formulação vaga do G | — | PARCIAL | O G acertou o cheiro e errou o alvo: apontou para "o bus é amplo" sem nomear a regra. Só a versão do D é acionável. |
| 25 | Superfície é `surfaces/bi-nuxt` + `api/v1/backstage/bi/*` (G+D, cabeçalho) | `surfaces/bi-nuxt/`, `api/urls.py:265-280` | CONFIRMADO, incompleto | Ambos omitem o **Admin** (3 ModelAdmins de B.I.), o `evaluate_bi_alerts` no `maintenance_worker`, e o `sales_series.py`. |

---

## C. Achados confirmados, com gravidade recalibrada

### C1 — P0: `cash_difference × operador` derruba o explorador com 500 (regressão viva em `main`)

**Não foi achado por nenhum dos dois.** É o achado mais grave deste WP.

**Mecanismo, do clique ao efeito.** O commit `d76a66c70` (21/08, "a custódia é da GAVETA")
removeu `CanonicalShift.operator_key` e o substituiu por `operator_keys: tuple` +
`sole_operator_key`. A docstring da dataclass diz isso em voz alta
(`shopman/backstage/bi/canonical.py:216`: *"Não há `operator_key`"*). O commit atualizou
`bi/alerts.py` e `projections/bi_cash.py`, mas **não** atualizou `bi_explore.py`. Hoje:

```
shopman/backstage/projections/bi_explore.py:859
    parts.append((shift.operator_key, shift.operator_key))
```

`CanonicalShift` é `@dataclass(frozen=True, slots=True)` — provado em runtime:

```
slots: ('key','terminal_key','opened_by_key','operator_keys','opened_at','closed_at','difference_q')
ATTRIBUTE_ERROR: 'CanonicalShift' object has no attribute 'operator_key'
```

O gestor-auditor abre **Explorar**, escolhe o chip de exemplo **"Quebra de caixa por operador"**
(`presentation/bi.ts:246` → `metric=cash_difference&by=operator`). A view valida a gramática,
chama `_cash_rows`, o laço `for shift in cashman.read_closed_shifts(...)` roda no primeiro turno
fechado da janela e levanta `AttributeError`. Isso **não** é `ExploreError`, então o `except` de
`api/bi.py:155` não pega; `shopman/shop/api_errors.py:54-56` devolve `None` para exceções não-DRF;
resulta 500 sem `detail`. Na tela, `explore.vue:233` só renderiza `errorDetail` (que vem de
`data.detail`) — como não há `detail`, e `report` é `null`, o painel fica **em branco, sem
mensagem nenhuma**. Pior que stacktrace: silêncio.

O único corte de `cash_difference` que funciona é `by=time, by2=""` — que é justamente o que o
dropdown escolhe sozinho (`useBiExplore.ts:42` cai em `dimensions[0]`). Por isso passou:
**o único teste que toca o caminho (`test_bi_business.py:113`) assere 200 num banco sem nenhum
`Shift` fechado** — o laço não executa. Smoke de banco vazio escondendo bug de linha.

**Fix mínimo.** Duas decisões, e a segunda é a certa:
- (a) uma linha, restaura o comportamento: `parts.append((shift.sole_operator_key or "—", shift.sole_operator_key or "compartilhado"))`.
- (b) **preferível**, e coerente com `d76a66c70` e com `bi_cash.py`: a dimensão de `cash_difference`
  vira `terminal` (gaveta), não `operator` — `MetricSpec("cash_difference", …, ("time","terminal"), "cash")`
  em `bi_explore.py:73`, `DIMENSION_LABELS["terminal"]="Gaveta"`, e o chip de `bi.ts:246` vira
  "Quebra de caixa por gaveta". Hoje o explorador atribui quebra a **pessoa** exatamente onde o
  resto do sistema decidiu, por escrito, que não se pode.

**Teste que fecha:** um `Shift` fechado com `Entry(kind=COUNT)` na janela + GET
`bi/explore/?metric=cash_difference&by=operator` como auditor → 200 (hoje 500).

---

### C2 — P1: alerta de faturamento entrega R$ ao balconista

`bi/alerts.py:216-218` monta *"14/08 (sexta) faturou R$ 3.412,00, 48% do esperado
(R$ 7.100,00 na média de 4 sextas)"*. `_fire` (`:126-130`) só redige quando
`rule.metric in AUDIT_ONLY_METRICS`, e esse conjunto é `{"cash_variance_by_drawer"}`
(`models/bi_alerts.py:56`). A mensagem íntegra vira `OperatorAlert`, servido por
`api/alerts.py:45-59` sob `CanViewOperatorAlerts` → `permissions.py:120-129`: qualquer staff com
`operate_pos`, `operate_kds`, `manage_orders`, `operate_production` ou `operate_purchase`.
O grupo **"Caixa"** (`setup_groups.py:102-105`) tem dois deles.

Isso contraria uma decisão escrita no próprio `setup_groups.py:129-132`: *"Dinheiro fica de fora,
e não é esquecimento… quem vê dinheiro é quem audita."* E a regra **está ligada**
(`seed.py:8260 is_active: True`) e é avaliada todo ciclo do `maintenance_worker` (`:64`).

**Fix mínimo** (mesmo padrão que o caixa já usa): acrescentar `daily_revenue_vs_baseline` a
`AUDIT_ONLY_METRICS`? Não — aí o gerente perde o aviso. O correto é uma mensagem pública própria:

```python
_REVENUE_PUBLIC_MESSAGE = "faturamento de {day} ficou em {share}% do esperado. Detalhe no B.I. › Vendas."
```
e em `_fire` trocar o `if` por um mapa `metric → mensagem pública`, mantendo `reading.message`
íntegro no `BIAlertEvent` (que já é gateado). Duas linhas de `alerts.py` + um guardrail de teste:
nenhum `OperatorAlert.message` de regra de B.I. contém `"R$"`.

---

### C3 — P1: números que enganam — a série longa soma o que não se soma

**Não foi achado por nenhum dos dois**, e é exatamente o objetivo declarado do WP.

`presentation/bi.ts:354-377` (`bucketRows`) agrupa por semana acima de 120 pontos e por mês acima
de 740, e a docstring é honesta: *"Devolve os dias de cada balde para a página somar **do jeito da
métrica dela**"*. A página não faz isso — `explore.vue:96-103`:

```js
value: bucket.rows.reduce((sum, r) => sum + r.value, 0)
```

soma incondicionalmente. Seis métricas com dimensão `time` **não são aditivas**
(`bi_explore.py:59, 69, 88, 110, 116, 118`): `average_ticket` (q), `yield_percent` (%),
`unavailable_share` (%), `room_peak_groups` (pico), `room_revenue_per_spot_hour` (q),
`room_turns` (giro). O gestor escolhe **1A** ou **6M** + **Ticket médio** + **Tempo** e a barra da
semana mostra ~7× o ticket real, formatada como reais, com `formatExploreValue(unit="q")` dando
um "R$ 178,50" perfeitamente convincente. Rendimento passa de 100%.

**Fix mínimo.** O contrato já tem `unit`. Duas linhas em `explore.vue`: um conjunto
`const MEAN_UNITS = new Set(["percent"])` mais uma lista explícita de métricas de média/pico, e
`value: isAdditive ? soma : soma / bucket.rows.length` — média do balde para média, e para
`room_peak_groups` o `Math.max`. Alternativa mais limpa e um pouco maior: o servidor declara
`aggregation: "sum" | "mean" | "max"` no `MetricSpec` e a UI obedece. Prefiro esta: hoje a regra
mora em duas cabeças e nenhuma no contrato.

---

### C4 — P1: exemplo e cenário salvo de métrica proibida (mantido de G+D, com o agravante de D)

Confirmado como descrito em B#5, B#6, B#7. Recalibro para P1 (não P0) porque a API **fecha**:
`bi.py:139-146` devolve 403. O dano é confiança, não vazamento — e, com C1 no ar, o dano é pior:
o chip nem 403 dá, dá tela branca.

**Fix mínimo:** três pontos, todos pequenos.
1. `availableExamples(supportedDimensions, allowedMetrics)` — filtrar também por
   `report.metrics.map(m => m.key)` (`presentation/bi.ts:184-196`).
2. `_validated_view_config` recebe o `request` e rejeita família audit-only para não-auditor
   (`api/bi.py:254-272` + `:304`).
3. `BIViewListView.get` (`:291-295`) filtra contra a permissão **corrente** — quem perdeu
   `audit_shift` para de ver as próprias views de caixa.

---

### C5 — P1: "Clientes" mostra base global sob rótulo de período

Confirmado e agravado (B#8): **cinco** dos seis blocos são globais — `segments`
(`bi_customers.py:69-72`), `customers_total` (`:90`), `with_insight` (`:91`), `at_risk` (`:92`),
`average_ticket_q` (`:93`). Só `new_by_week` (`:74-80`) usa a janela, que é calculada em `:48` e
devolvida no contrato (`:83-84`) como se governasse tudo. O gestor troca de "28D" para "1A", vê
`date_from/date_to` mudarem no cabeçalho e os quatro KPIs **não** mudarem — e conclui que a base
está estagnada.

**Fix mínimo:** `scope: "global" | "window"` por campo no contrato e dois títulos na página
("Base atual" × "No período"). **Não** recalcular RFM por janela — `CustomerInsight` é agregado do
guestman e o B.I. declara que só lê (`bi_customers.py:1-6`). D está certo nesse limite.

---

### C6 — P2: janela inválida e clamp silenciosos (recalibrado do G pelo D)

`api/bi.py:45-52` engole `date_from=bad`; `bi_production.py:178-186` inverte `from>to` e clampa
1830 dias, sem dizer. A proposta do G (400 seco) reverte a decisão documentada em `bi.py:52`; a do
D (`normalized_window_reason` no contrato) é a certa. Acrescento: o clamp de `MAX_WINDOW_DAYS` não
tem comentário nenhum (B#19), então documentá-lo faz parte do fix.

**Fix mínimo:** `_normalize_window` devolve `(from, to, reason)` com `reason ∈ {"", "invertida",
"clampada"}`; os relatórios publicam `normalized_window_reason`; a UI mostra "período ajustado
para o máximo de 5 anos". Sem 400 em endpoint de leitura.

---

### C7 — P2: sem célula mínima em famílias financeiras

Mantido de G+D, com o custo que D declarou e eu confirmo: `BIExploreRow` não carrega `n`
(`bi_explore.py`, dataclass do `BIExploreRow`), e `_sales_rows` só mantém `orders` internamente
(`:386, :407`). Escopar às famílias `sales`, `payment` e `cash`, e só nas dimensões finas
(`hour`, `payment_method`, `channel`). P2 porque a padaria é uma só e o público do B.I. é o
gestor — o risco de reidentificação é baixo, o custo é médio. **É o candidato natural a sair do
WP se o escopo apertar.**

---

## D. Achados NOVOS (que G e D perderam)

*(C1, C2 no ponto da regra ativa, e C3 acima já são novos; repito aqui só os que ainda não
apareceram.)*

### D1 — P2: o alarme de faturamento trata ausência como zero e grita

`bi/alerts.py:209`:

```python
measured = float(series[target].revenue_q) if target in series else 0.0
```

`daily_sales` **não devolve o dia quando não há venda registrada** — e diz isso em letra grande
(`projections/sales_series.py:40-44`: *"Ausência não é zero… não pode entrar numa média como um
dia de faturamento zero"*, e `bi/canonical.py:19`). O alarme viola o contrato do módulo que ele
consome: `measured=0.0` → `share=0` → `0 < threshold(70)` → **dispara** *"ontem faturou R$ 0,00,
0% do esperado"*.

Quando isso acontece na prática: dia sem `DayContext` carimbado em que `is_open_on` diz "aberto"
mas a casa não abriu (feriado não cadastrado); ou dia cuja fonte é o histórico e o lote ainda não
entrou. Note que `day_similarity._was_open` (`:305-307`) ainda **falha para "aberto"** quando o
calendário lança. Todas as outras ausências do módulo abstêm-se corretamente (`:194`, `:204`) —
esta é a única que inventa um número.

**Fix de uma linha**, no dialeto que o resto do arquivo já fala:

```python
if target not in series:
    return Reading(value=None, baseline=None, fired=False,
                   message=f"{target:%d/%m} não tem venda registrada: sem leitura")
```

### D2 — P2: `BIAlertRuleAdmin._request_user` é atributo de classe — corrida de autorização

`shopman/backstage/admin/bi_alerts.py:53-57`: `_request_user = None` na classe, e
`changelist_view` faz `self._request_user = request.user`. `ModelAdmin` é **singleton** no
registro do Django, e o deploy roda **daphne** (`Dockerfile:74`, `.do/app.alpha-subdomains.yaml:432`)
— ASGI, requisições concorrentes no mesmo processo, views sync num threadpool. Duas aberturas
simultâneas de `/admin/backstage/bialertrule/` — uma do Dono (auditor), outra da Gerente — podem
render a coluna "última leitura" da Gerente usando a identidade do Dono, e aí `reading_display`
(`:48`) entrega a mensagem completa da quebra de caixa (com nome de operador, quando
`sole_operator_key` resolveu). O `get_fieldsets` (`:61`) faz certo, com `request.user`.

**Fix de uma linha:** trocar `reading_display` por um `@display` que leia o usuário do request via
`get_list_display`/`get_queryset` anotando na queryset, ou — mais simples e igualmente correto —
mover a redação para `get_queryset` (como `BIAlertEventAdmin` já faz em `:80-85`), que recebe
`request`. Apagar `_request_user` e `changelist_view` inteiros.

### D3 — P2: `resolveWindowRange` usa data UTC — a janela pula um dia à noite

`presentation/bi.ts:303-304`: `const iso = (d) => d.toISOString().slice(0,10)` e
`const to = iso(today)`. `toISOString` é **UTC**. Em BRT (UTC-3), a partir das 21h locais a data
UTC já é a de amanhã. Consequências, todas silenciosas:
- preset **"Dia"** (`:308-310`) manda `date_from=date_to=amanhã` → "Nada no período".
- presets móveis (`:325-327`) deslocam a janela inteira um dia para a frente, incluindo um dia que
  não existe e descartando o dia mais antigo real.
- o servidor **não clampa `date_to` a hoje** (`bi_production.py:178-186`), então nada corrige.

Colide com a convenção da casa (`feedback_localdate_not_now_date`).
**Fix de uma linha:** `const iso = (d) => \`${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,"0")}-${String(d.getDate()).padStart(2,"0")}\`;`
(a mesma função já é usada em `:369-370` para a segunda-feira do balde, com o mesmo defeito).

### D4 — P3 (cosmético, mas é regra da casa): resíduo de rename no seed

`config/management/commands/seed.py:8293`: `"label": "Quebra de caixa acumulada por operador"`
para a métrica `CASH_VARIANCE_BY_DRAWER`. O `d76a66c70` renomeou a métrica e migrou os dados
(`backstage/migrations/0034_cash_variance_by_drawer.py`) mas deixou o rótulo, que é o texto que o
gestor lê no Admin. Zero residuals. Uma linha.

### D5 — P3: `BIViewListView.post` sobrescreve cenário homônimo sem avisar

`api/bi.py:307-309`: `update_or_create(owner, name, defaults={"config": config})`, e a UI responde
"Cenário salvo." (`useBiViews.ts:23`). Salvar com um nome já usado apaga o corte anterior em
silêncio. Baixo dano, fix barato: devolver `created` no payload e a UI dizer "Cenário atualizado."

### D6 — não é achado, é um alívio verificado
`bi/sources/orderman.py:18-21, 31-40, 84` exclui `CANCELLED`/`RETURNED` das vendas **e** das
linhas, e conta os cancelados à parte (`bi_sales.py:150`), com teste
(`test_bi_business.py:129-138`). A hipótese "agregação soma pedidos cancelados" está **refutada**.
Idem "PII de cliente nas projections de B.I.": `bi_customers.py` devolve **só contagens** — nenhum
nome, telefone, CPF ou id de cliente sai por ali. E não existe export CSV em `bi-nuxt`.

---

## E. Achados a DESCARTAR (de G ou D)

### E.1 — "Egress de agregados financeiros para o provedor de IA" (D, P1) → **descartar como achado; virar pergunta ao dono**

Verifiquei com rigor, porque era a acusação mais pesada. O que sai, para onde, e sob que condição:

- **O que sai** (`bi/scenarios.py:94-156`, foco `sales`): totais e período anterior
  (pedidos, faturamento, ticket, cancelados), série por dia, faturamento por canal, **top 10 SKUs
  com nome e SKU**, pedidos por hora e por dia da semana, e a projeção da semana. Foco
  `production` (`:159-195`): lotes, forno por receita, esgotado/sobra/indisponibilidade por SKU.
- **Para onde**: `copy_assist.suggest` → `anthropic.Anthropic(api_key=...)`
  (`shopman/shop/services/copy_assist.py:87-100`). `AI_ASSIST_PROVIDER` só aceita `"anthropic"`
  (`:88-89`).
- **Sob que condição**: apenas se `AI_ASSIST_API_KEY` estiver definida
  (`config/settings.py:893`; declarada como `SECRET` em `.do/app.alpha-subdomains.yaml:390` — **não
  consegui confirmar se tem valor no alpha**). Sem chave, `is_configured()` é falso, o GET diz
  `configured=false`, o POST responde 409 e a tela nem oferece o botão.
- **Quem dispara**: `POST bi/scenarios/` sob `backstage.view_bi` — Gerente e Dono
  (`setup_groups.py:161`). Síncrono, sob demanda, sem agendamento.
- **O que NÃO sai**: nenhum `Order`, nenhum nome/telefone/CPF de cliente, nenhuma apuração de
  caixa, nenhum nome de operador.

**Isso é decisão documentada, e documentada três vezes**: a docstring do módulo
(`scenarios.py:5-8`: *"Nenhum `Order`, nenhum nome de cliente, nenhuma apuração de caixa"*), a da
função (`:84`: *"Tudo com unidade no nome; nada pessoal"*), e o plano
(`docs/plans/BI-DATA-FOUNDATION-PLAN.md:556-566`, *"caixa fora, é auditoria"*). A fronteira foi
desenhada de propósito e o código a respeita — conferi campo a campo.

**Veredito:** não é vazamento, não é bug, não é P1. É uma **decisão de negócio** que o código
implementa corretamente. A proposta do D ("remover nomes de SKU, reduzir dia→semana") *degradaria*
o recurso para resolver um problema que ninguém decidiu que existe: sem nome de produto e sem
granularidade diária, o cenário vira genérico e o botão perde a razão de ser. Se o dono não
aceitar o envio, a resposta certa é **não configurar a chave** — o desligamento já está construído.
Vai para §H como pergunta, não para o WP como tarefa.

### E.2 — "Cenários IA: `useBiScenarios.generate()` envia `useBiWindow().range`" (G) → **descartar a proposta**

Refutada pelo código: `api/bi.py:376-377` lê `request.GET` num POST; o body seria ignorado.
D pegou isso e está certo. A **necessidade** (o cenário deve refletir a janela visível) fica; a
**proposta do G** sai.

### E.3 — "400 para data inválida" (G, P2) → **descartar a forma, manter o fundo**

Reverte a decisão de `api/bi.py:52` sem argumento. Fica a versão do D (C6).

### E.4 — "Persistir a janela efetiva" (D) como item próprio → **rebaixar a nota de rodapé de C6**

Verificado (B#12): hoje é inalcançável — `date_from/date_to` já vêm defaultados antes do
`gather_inputs`, e a UI nunca manda janela. Vira uma linha dentro do fix do contrato de cenários,
não um item.

### E.5 — Célula mínima (C7) → **candidato a corte**, pelo motivo em C7.

### E.6 — SSE (descarte do D) → **confirmado o descarte**, e por motivo mais forte: o B.I. não tem SSE nenhum.

---

## F. Aceites verificáveis

| # | Critério | Como se prova |
|---|---|---|
| F1 | `cash_difference × operator` responde 200 com dado real | Teste `django_db` que cria `Terminal` + `Shift` fechado + `Entry(kind=COUNT, amount_q=-500)` e faz `GET bi/explore/?metric=cash_difference&by=operator` como auditor. **Hoje falha com `AttributeError` — provado em runtime nesta verificação.** |
| F2 | Nenhum `OperatorAlert` de regra de B.I. contém `"R$"` | Teste que dispara as 5 regras (já há fixtures em `test_bi_alerts.py:120-143`) e assere `"R$" not in alert.message` para todo `alert.type.startswith("bi_")`. Hoje `bi_below_baseline` falha. |
| F3 | Balde semanal de métrica de média não é soma | Teste vitest sobre `explore.vue`/helper: 140 dias de `average_ticket` com valor 1000 em todos → todo balde vale 1000, nunca 7000. |
| F4 | Explorador não oferece exemplo de métrica podada | Teste vitest: `availableExamples(dims, ["revenue","orders"])` não contém "Quebra de caixa por operador". |
| F5 | Save e list de view audit-only respeitam a permissão corrente | Teste API: usuário com `audit_shift` salva view `cash_difference`; a permissão é removida; `GET bi/views/` não a lista e `POST` de nova é 403. |
| F6 | Aba Caixa some para não-auditor | Payload de `bi/explore/` (ou de um endpoint de sessão) traz `can_audit_cash`; teste vitest de `BiTopBar` com a flag falsa não renderiza o tab `/cash`. |
| F7 | Clientes rotula escopo | Contrato de `bi/customers/` traz `scope` por bloco; teste que muda a janela e assere que os campos `global` não mudam e que a UI os agrupa fora de "No período". |
| F8 | Janela normalizada declara o motivo | `GET bi/sales/?date_from=bad` → 200 com `normalized_window_reason` não vazio; `?date_from=2020-01-01&date_to=2019-01-01` → `"invertida"`. |
| F9 | Alarme sem venda no dia se abstém | Teste: nenhuma venda em `ontem`, baseline com 4 amostras → `Reading.fired is False` e `value is None`. |
| F10 | Admin de alarmes não guarda usuário na classe | `grep -c "_request_user" shopman/backstage/admin/bi_alerts.py` → 0. |
| F11 | Janela do cliente não usa UTC | Teste vitest de `resolveWindowRange` com `new Date("2026-08-29T23:30:00-03:00")` → `date_to === "2026-08-29"`. |
| F12 | Paridade do contrato TS | `python manage.py export_bi_schema` + teste de drift já existente (`test_bi_schema_export.py`) continua verde após as mudanças de contrato (F7, F8). |

Todos checáveis com a suíte e o repositório de hoje. Nenhum depende de infra inexistente.

---

## G. Fronteiras e colisões

### Arquivos que este WP precisa tocar

**Backend (exclusivos deste WP, salvo nota):**
- `shopman/backstage/projections/bi_explore.py` — C1 (`:73`, `:859`), C7.
- `shopman/backstage/projections/bi_customers.py` — C5.
- `shopman/backstage/projections/bi_production.py` — C6 (`_normalize_window`, `:178-186`).
  ⚠️ **colisão**: `_normalize_window` é importado por `bi_sales.py:24`, `bi_customers.py:46`,
  `bi_explore.py:25`, `bi_profiles.py`, `bi_change.py`. Mudar a assinatura mexe em cinco arquivos.
  Ou muda todos de uma vez, ou adiciona `normalize_window_with_reason` ao lado.
- `shopman/backstage/projections/bi_sales.py`, `bi_profiles.py`, `bi_change.py`, `bi_forecast.py` — só se C6 mudar a assinatura.
- `shopman/backstage/api/bi.py` — C4 (`:254-272`, `:291-295`), C6, flag `can_audit_cash`, contrato de janela do POST de cenários (`:365-381`).
- `shopman/backstage/bi/alerts.py` — C2 (`:121-142`, `:216-218`), D1 (`:209`).
- `shopman/backstage/admin/bi_alerts.py` — D2 (`:42-57`).
- `config/management/commands/seed.py` — D4, linha 8293 **apenas**. ⚠️ **arquivo de altíssima
  colisão**: o `seed.py` é tocado por quase toda frente. Um `git add` de arquivo nomeado e uma
  linha só.

**Superfície (exclusiva):**
- `surfaces/bi-nuxt/app/presentation/bi.ts` — C3 (agregação), C4 (`:184-196`), D3 (`:303`, `:369`), `:246`.
- `surfaces/bi-nuxt/app/pages/explore.vue` — C3 (`:96-103`), C4.
- `surfaces/bi-nuxt/app/pages/customers.vue` — C5.
- `surfaces/bi-nuxt/app/pages/scenarios.vue` — exibir `window_from/to`.
- `surfaces/bi-nuxt/app/components/BiTopBar.vue` — gate da aba Caixa.
- `surfaces/bi-nuxt/app/composables/useBiScenarios.ts`, `useBiExplore.ts`, `useBiViews.ts`.
- `surfaces/bi-nuxt/app/generated/biContract.ts` — **gerado**, não editar à mão: rodar
  `python manage.py export_bi_schema` (o teste `test_bi_schema_export.py` falha se divergir).

**Testes:** `shopman/backstage/tests/test_bi_business.py`, `test_bi_alerts.py`,
`test_bi_explore.py`, `test_bi_scenarios.py`, e vitest em `surfaces/bi-nuxt/`.

### Permissões novas e impacto em `setup_groups.py`

**Nenhuma permissão nova.** `backstage.view_bi` (`models/closing.py:37`, concedida em
`setup_groups.py:161` ao grupo Gerente) e `cashman.audit_shift` (concedida em `:228` ao grupo Dono)
já existem e já são administradas. `can_audit_cash` vira **flag derivada** no payload, não
permissão. **`setup_groups.py` não precisa mudar por causa deste WP** — e é bom que não mude:
o arquivo é `permissions.set(...)`, fonte-da-verdade, e uma edição concorrente de outro WP
revoga em silêncio o que este acrescentar.

Uma observação de leitura, não uma proposta: `setup_groups.py:142` dá `*_ver("backstage")` inteiro
à Gerente, o que já cobre `view_bialertevent`/`view_biscenarioreport` re-listados em `:168-170`.
Redundância inofensiva (o `BIAlertEventAdmin.get_queryset` filtra o audit-only), mas quem mexer ali
precisa saber que a lista explícita não é o gate real.

### O que pertence a outro app/dono

| Item | Dono |
|---|---|
| Segmentação RFM por janela | **guestman** (`CustomerInsight`). Este WP só rotula escopo; não recalcula. |
| Consumo dos `OperatorAlert` de B.I. nas telas | **orders-nuxt / production-nuxt / hub-nuxt** — coordenação de superfície. O fix de C2 é no emissor (`bi/alerts.py`), não nos consumidores. |
| `can_view_operator_alerts` (`permissions.py:120-129`) | Predicado **compartilhado** por todo o backstage. C2 se resolve **sem tocá-lo** — redigindo a mensagem, não estreitando o gate. Estreitar o gate seria WP de alertas, e quebraria outras superfícies. |
| `day_similarity._was_open` falha-aberto (`:305-307`) | **backstage/services**, fora do B.I. Só anotado; não entra neste WP. |
| Dimensão `terminal` no explorador (fix (b) de C1) | Toca `bi/sources/cashman.py`? **Não** — `CanonicalShift.terminal_key` já existe. Fica dentro deste WP. |

---

## H. Pergunta aberta para o dono do produto

1. **Quebra de caixa por PESSOA ou por GAVETA no explorador?** O commit de 21/08 decidiu, por
   escrito, que a custódia é da gaveta e que atribuir quebra a uma pessoa "inventaria um culpado" —
   e `bi/alerts.py` e `bi_cash.py` obedecem. O explorador ainda oferece `by=operator` (e hoje
   quebra com 500). Trocar a dimensão para `terminal` alinha tudo; manter `operator` exige decidir
   se vale a atribuição só quando `sole_operator_key` resolve. **Muda o fix de C1 e o rótulo do
   chip.**

2. **Sales aggregates podem sair para a Anthropic?** Hoje o botão "gerar cenários" manda
   faturamento por dia e por canal, e os 10 produtos mais vendidos **com nome**, para a API da
   Anthropic — quando `AI_ASSIST_API_KEY` está definida. Não há PII e não há caixa; é decisão
   documentada e o código a respeita. Só o dono decide se o dado de venda da casa pode trafegar.
   Se a resposta for não, a ação é **não configurar a chave** (o recurso já se desliga sozinho) —
   não mutilar o prompt. **Preciso saber também se a chave está setada no alpha hoje; não consigo
   ler o valor do segredo.**

3. **A Gerente deve ver o alarme "faturamento abaixo do esperado" com o valor em R$?**
   `setup_groups.py:129-132` diz que dinheiro é do Dono; o alarme hoje entrega R$ a qualquer
   operador com `operate_pos`. A mensagem sem valor ("48% do esperado") resolve o vazamento e
   preserva o sinal para todo mundo — mas se o dono quiser o valor visível para a Gerente, o fix
   muda de "redigir a mensagem" para "dois níveis de alerta".
