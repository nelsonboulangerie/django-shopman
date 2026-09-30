# 11 — Observabilidade e medição: o que dá para medir hoje, e o que falta para provar melhoria

**Árvore:** `.dsh-worktrees/go-live-acceleration` (origin/main = `f0ffd02fd`, 2026-09-29).
**Escopo:** capacidade de MEDIR o sistema vivo — Server-Timing, logs estruturados, telemetria de erro
no front, observabilidade de worker, harness de carga, baselines, `pg_stat_statements`.
**Método:** leitura estática (`read`/`grep`/`glob`, `git log` read-only), **leitura** do app vivo via
`doctl apps spec get` / `doctl apps logs` (read-only), e `curl` externo sem credencial.
**Nada foi editado além deste arquivo.**
**Legenda:** [FATO] verificado com path:linha ou saída de comando · [INFERÊNCIA] dedução minha ·
[NÃO VERIFICADO] não confirmei · [BLOQUEADO] exigiria acesso que esta máquina não tem.

> **Irmãos:** `01-perf-storefront.md` (por que a loja é lenta), `02-perf-operador.md`,
> `03-continuum-impacto.md`. Aqui o assunto não é *onde o tempo vai* — é **com que instrumento
> alguém descobre isso, e se o instrumento sobrevive à próxima mudança.**

---

## 1. Resumo executivo

- **O quadro mudou desde o WP-PERFORMANCE de 17/09, e mudou para melhor.** Das lacunas que
  aquele documento registrou em §7, **quatro já têm instrumento no ar**: `Server-Timing` com
  estágios no cardápio, log estruturado allowlisted por request, telemetria de capacidade do
  contêiner (CPU/memória via cgroup) e um **avaliador de percentis que lê os logs**. [FATO]
- **O que NÃO mudou:** `pg_stat_statements` continua sem instalar, `log_min_duration_statement`
  continua desligado, e `monitoring:read` continua ausente. **E não é falta de vontade — é falta de
  credencial:** `doctl databases list` e a API de monitoring respondem **403** com o token desta
  máquina. [FATO, reproduzido abaixo]
- **A infraestrutura de medição mais valiosa que existe hoje é a que já está no repo e ninguém
  usa:** `scripts/evaluate_continuum_shadow.py` (141 linhas) lê `doctl apps logs`, calcula
  p50/p75/p95, conta divergências e **falha fechado** contra thresholds. Ela é específica de um
  caminho; **generalizá-la para (path, mode) é a menor infraestrutura que responde à pergunta desta
  tarefa**, e é um script de ~150 linhas, não um fornecedor. [FATO no arquivo; INFERÊNCIA no esforço]
- **Medi o sistema vivo agora, de fora e sem credencial, e o cardápio está ~2× mais lento que o
  baseline do WP:** `/api/v1/storefront/menu/` deu TTFB **2,57–2,83 s** contra **0,93–1,39 s**
  medidos em 17/09 — com o mesmo piso de rede (`/health/live/` hoje 0,27–0,56 s contra 0,35–0,48 s
  então). O `Server-Timing` da mesma resposta diz onde: `projection;dur=2219`, de que
  `availability;dur=1277`. **Nenhum alerta existe para isso, e nada no repositório teria detectado
  a regressão.** [FATO — números e comandos abaixo]
- **A maior lacuna de instrumentação é assimétrica e conhecida:** `Server-Timing` cobre `menu/`,
  `catalog/` e `continuum/…` — e **não** cobre `home/`, `shell/`, `site/`, `cart/`, `checkout/`,
  `tracking/`, `products/<sku>/` nem a Conta. Ou seja, o *endpoint mais lento* é o que não tem
  régua. [FATO — inventário completo por `curl` abaixo]
- **A página SSR não devolve `Server-Timing` nenhum.** O BFF anexa `bff;dur=` no proxy
  (`djangoProxy.ts:214-220`) e isso aparece quando eu chamo a **rota de API** pelo host da loja;
  quando eu chamo a **página HTML**, o header não vem. O tempo que o cliente sente — 3,50–3,93 s na
  home — não está instrumentado. [FATO medido; causa [INFERÊNCIA]]
- **Instrumentação morta em produção:** `shopman/storefront/perf.py` (`CartMutationPerf`) tem
  **zero chamadores** no repositório, e a variável que a liga está setada no app vivo
  (`SHOPMAN_CART_MUTATION_PERF_LOG_MS=250`). Esperava-se log de mutação de carrinho; nunca saiu um.
  [FATO]

---

## 2. Achados

### A1 — Server-Timing existe, emite estágios, e é legível de fora [FATO] [habilitador]

**Onde é produzido.** `shopman/storefront/observability.py:18-33` — a dataclass `CatalogTiming`
acumula `durations_ms` e serializa:

```python
# observability.py:26-33
def server_timing(self, *, include_bff: bool = False) -> str:
    names = ["projection", "availability", "personalization", "shadow", "db"]
    if include_bff:
        names.insert(0, "bff")
    return ", ".join(f"{name};dur={self.durations_ms.get(name, 0.0):.2f}" for name in names)
```

**Onde é anexado** — três sítios, e só:

| path:linha | view | rotas |
|---|---|---|
| `shopman/storefront/api/surface.py:492` | `StorefrontMenuView` / `StorefrontCatalogView` | `/storefront/menu/[/<collection>/]`, `/storefront/catalog/` |
| `shopman/storefront/api/continuum.py:110,129` | `CatalogStructureSnapshotView` | `/storefront/continuum/v0.2/catalog-structure/` |

**Estágios e como são medidos.** `catalog_stage(name)` (`:39-47`) é um context manager sobre um
`ContextVar`; `capture_catalog_timing()` (`:50-67`) instala um `connection.execute_wrapper` que conta
queries e soma `db`. Os estágios de negócio são aninhados em `surface.py:459-489` (`projection` →
`personalization`, `shadow`) e `presentation/catalog.py:241,256,457` (`personalization`,
`availability`). O estágio `bff` é do Nuxt, não do Django (`include_bff=True` **nunca é chamado no
Python** — grep = 0): `surfaces/storefront-nuxt/server/utils/djangoProxy.ts:214-220`.

**Como ler (sem credencial nenhuma):**

```bash
$ curl -s -o /dev/null -D- "https://api.boulangerie.com.br/api/v1/storefront/catalog/" | grep -i server-timing
server-timing: projection;dur=2097.08, availability;dur=1152.44, personalization;dur=18.98, shadow;dur=0.00, db;dur=405.87

$ curl -s -o /dev/null -D- "https://www.nelsonboulangerie.com.br/api/v1/storefront/menu/" | grep -i server-timing
server-timing: projection;dur=2583.03, availability;dur=1606.28, personalization;dur=30.59, shadow;dur=0.00, db;dur=470.50, bff;dur=2776.46
```

**O que isso já responde hoje:** qual estágio domina, e quanto o BFF acrescenta sobre o Django
(`bff;dur` 2776 ms contra `projection` 2583 ms ⇒ **~193 ms de overhead do proxy** nessa amostra). [FATO]

**Inventário de cobertura — medido agora, endpoint por endpoint:**

| endpoint | `Server-Timing` | status |
|---|---|---|
| `/storefront/home/` | **ausente** | 200 |
| `/storefront/shell/` | **ausente** | 200 |
| `/storefront/site/` | **ausente** | 200 |
| `/storefront/catalog/` | presente | 200 |
| `/storefront/cart/` | **ausente** | 200 |
| `/storefront/checkout/` | **ausente** | 200 |
| `/storefront/menu/` | presente | 200 |
| `/storefront/continuum/v0.2/catalog-structure/` | presente | 200 / 304 |

**Impacto:** é o único instrumento que separa "tempo de servidor" de "tempo de rede" sem APM e sem
credencial — e ele não cobre a rota de entrada da loja. [FATO]
**Confiança:** alta (código + header observado ao vivo).

---

### A2 — O sistema vivo está mais lento que o baseline do WP, e nada detecta [FATO] [ALTO]

**Medido agora** (2026-09-29 ~17:35–17:45 UTC, desta máquina, `curl -w`):

| endpoint | TTFB medido hoje | Baseline WP-PERFORMANCE §2.1 (17/09) |
|---|---:|---:|
| `api./health/live/` | 0,267 · 0,273 · 0,562 s | `api./health/` 0,35–0,48 s (piso de rede) |
| `api./health/ready/` | 0,386 · 0,408 · 0,754 s | 0,44–0,84 s |
| `api./api/v1/storefront/menu/` | **2,57 · 2,72 · 2,83 s** | **0,93–1,39 s** |
| `api./api/v1/storefront/home/` | **2,77 · 3,52 s** | 1,03–1,88 s |
| `www.` home (SSR) | **3,50 · 3,50 · 3,93 s** | 2,10–3,00 s (medido em `menu.`) |
| `www.` `/menu` (SSR) | 0,63 · 0,69 · 0,75 s | — |
| `api./continuum/…/catalog-structure/` | 2,69 s (miss) → **0,145 s ×2 (hit)** | não existia |

O piso de rede está o mesmo (health deu 0,27 s hoje contra 0,35 s de piso em 17/09), então a
diferença do cardápio **não é rede**: o `Server-Timing` da mesma resposta localiza o custo no
servidor (`projection;dur=2219`, `db;dur=435`). [FATO]

**Cruzando com o log do `web`, o mesmo número aparece em 12 amostras independentes:**

```
$ doctl apps logs 40b86e35-bafe-4a1a-a1b0-e124d3d9fd0f web --type run --no-prefix --tail 20000 | <percentis>
('storefront_menu', 'baseline')  n=12
   projection_ms     p50=2338  p95=2891  max=2891
   availability_ms   p50=1396  p95=1656
   db_ms             p50=501   p95=696
   query_count       p50=93    p95=94   max=94
   cache_status={'off': 12}
```

**Impacto:** o alvo declarado no WP §4 (`menu/` ≤ 0,6 s) está a **~4×** de distância, e não há nada
— nem alerta, nem gate, nem relatório — que tenha registrado a piora de 17/09 para cá. [FATO]
**Confiança:** alta nos números; [INFERÊNCIA] sobre a causa (o WP §5-P6, cache da leitura pública,
não foi implementado: `cache-control: private` e `cf-cache-status: BYPASS` continuam, medidos hoje).

---

### A3 — Logs estruturados: o que é logado, em que nível, e onde [FATO]

**Configuração** (`config/settings.py:2192-2236`):

```python
SHOPMAN_JSON_LOGS = os.environ.get("SHOPMAN_JSON_LOGS", "true" if not DEBUG else "false")...
LOGGING = {
  "formatters": {"verbose": {"()": "shopman.shop.logging.PrivacySafeFormatter", ...},
                 "json":    {"()": "shopman.shop.logging.JsonLogFormatter"}},
  "handlers":   {"console": {"class": "logging.StreamHandler", "formatter": _SHOPMAN_LOG_FORMATTER}},
  "root":       {"handlers": ["console"], "level": os.environ.get("DJANGO_LOG_LEVEL", "INFO")},
  "loggers":    {"django": {..., "level": DJANGO_LOG_LEVEL or INFO},
                 "shopman": {..., "level": "DEBUG" if DEBUG else "INFO"}},
}
```

- `SHOPMAN_JSON_LOGS=true` **no app vivo** (confirmei no spec: `envs: SHOPMAN_JSON_LOGS = true`). [FATO]
- `DJANGO_LOG_LEVEL` **não está setado** no app vivo ⇒ vale `INFO`. [FATO]
- Nível `shopman` em produção = `INFO` **hardcoded** (`settings.py:2232`), não segue `DJANGO_LOG_LEVEL`.
  A dívida dos `logger.debug` dentro de `except` está inventariada em `docs/reference/silencio-inventario.md`
  e no runbook `docs/runbooks/ativar-sentry.md:19-24`. [FATO]
- `JsonLogFormatter` (`shopman/shop/logging.py:40-67`) emite **todo `record.__dict__` não reservado**
  como campo de topo, passando cada valor pelo redator (`shopman.shop.telemetry_redaction`). Ou seja:
  `extra={...}` vira campo de topo e é **filtrável por `jq`**. [FATO]

**Não existe log de acesso/duração por request para a loja.** O que existe:

| sinal | onde | campos | nível |
|---|---|---|---|
| `storefront_catalog_observation` | `observability.py:70-99` ← `surface.py:495`, `continuum.py:131` | `query_count, response_bytes, projection_ms, availability_ms, personalization_ms, db_ms, cache_status, snapshot_*` | INFO |
| `operator.request.started/finished` | `backstage/api/telemetry.py:237-256` (mixin) | `request_id, operation, method, actor_id, resource_ref, response_status, outcome, replayed, view_elapsed_ms` | INFO |
| `operator_capacity.sample` | `backstage/api/operator_capacity.py:66-76` | `service, memory_percent, cpu_percent, capacity_level, recorded` | INFO se attention/critical, DEBUG se folga |
| `marketing.metric` | `shop/services/marketing_observability.py:122-144` | `metric_name, metric_kind, metric_value, metric_labels` | INFO |
| `capacity.probe` | `surfaces/operator-kit/server/utils/containerCapacity.ts:495-527` (stdout do Nitro) | quais caminhos de cgroup existem, qual régua valeu | — |

**O mixin de request do backstage cobre só 9 módulos** (`grep -rln OperationalObservationMixin`) —
`catalog.py`, `catalog_bindings.py`, `channel_health.py`, `customers.py`, `feeds.py`, `operations.py`
(4 views). **A API do storefront não tem equivalente nenhum** — nenhuma view de
`shopman/storefront/api/` herda o mixin. [FATO — grep = 0]

**Amostra real do log do `web` (1.466 linhas, ~12 min de janela):**

```
json lines 713 | access lines 812 | access com query string 80
loggers: django.request 355, django_eventstream.views 250, shopman.operational 75,
         shopman.shop.apps 10, shopman.storefront.continuum 10, ...
```

`operator.request.finished` **está vivo e medindo** — amostra real:

```json
{"event":"operator.request.finished","operation":"OrderQueueView","outcome":"read",
 "request_id":"3c4f0d8a789a47d1a64db90119dd65c2","response_status":200,"view_elapsed_ms":636.059,"actor_id":8}
```

**Duas ressalvas de privacidade, ambas medidas:** (a) **80 das 812 linhas de acesso trazem query
string** na request line do daphne — é o vetor de PII que o WP §7 usou como motivo para não ler log
de acesso; (b) o `storefront_catalog_observation` é allowlisted por construção
(`observability.py:72-93`, comentário explícito: "nunca payload, SKU, sessão ou pessoa"), então
**esse** é seguro de agregar. [FATO]

---

### A4 — Telemetria de erro no front: existe, é write-only, e o destino depende de um DSN [FATO]

**Cadeia completa, nas duas superfícies:**

| superfície | cliente | endpoint | destino |
|---|---|---|---|
| storefront | `surfaces/storefront-nuxt/app/plugins/errorReporter.client.ts:9,33-36` (`vue:error`, `window:error`, `unhandledrejection`; dedupe + teto de 20/sessão; inerte em dev) | `POST /api/v1/storefront/client-error/` (`shopman/storefront/api/telemetry.py:96-120`) | `logger.error(...)` com `extra={"client_report": …}` → console; **Sentry se `SENTRY_DSN`** |
| operador | `surfaces/operator-kit/app/utils/clientErrorReport.ts:19,50-56` + `app/plugins/errorReporter.client.ts:32-33` | `POST /api/v1/backstage/client-error/` (`shopman/backstage/api/telemetry.py:74-102`) | idem, logger `shopman.backstage.client` |

Ambos são `AllowAny` + rate-limit por IP (`30/m`), allowlist de campos, truncamento e redação
(`_EMAIL_RE`/`_PHONE_RE` no storefront, `telemetry_redaction` no backstage). **Não persistem em
banco** — são log. [FATO]

**A mudança que o runbook não sabe:** `docs/runbooks/ativar-sentry.md` foi escrito quando
`SENTRY_DSN` "nunca foi setado". **No app vivo ele está setado** (app-level, `type: SECRET`, valor
criptografado). [FATO — `doctl apps spec get`]. O `init` (`settings.py:2244-2300`) é cuidadoso:
`send_default_pii=False`, `max_request_body_size="never"`, `before_send` que tira a query string (o
webhook da Efí autentica por `?token=`). `SENTRY_TRACES_SAMPLE_RATE` **não está setado** ⇒ default
`0` ⇒ **performance tracing desligado**. [FATO]

**O que isso significa para esta tarefa:** o Sentry, ligado, captura **exceção que sobe** — não
captura latência (traces em 0) nem `logger.warning` (o `LoggingIntegration` default só manda
`ERROR`). Não é, e não substitui, um instrumento de performance. [INFERÊNCIA forte a partir do
código; NÃO VERIFICADO se o DSN colado é válido e se eventos chegam]

**Não há Web Vitals no storefront.** O único coletor de vitals é
`surfaces/marketing-nuxt/app/plugins/marketingVitals.client.ts:11-24` (+ endpoint autenticado
`MarketingVitalView`, `backstage/api/telemetry.py:206-235`, métrica `marketing_frontend_vital` com
`LCP/INP/CLS` e rotas fechadas). **O padrão existe e a loja não o usa.** [FATO — grep por
`PerformanceObserver`/`web-vitals` em `surfaces/`]

---

### A5 — Observabilidade de worker: heartbeat existe; duração de ciclo, não [FATO]

**Heartbeat.** `packages/orderman/shopman/orderman/worker_heartbeat.py:28-35` — `beat(name)` grava
`shopman:worker_heartbeat:{name}` no cache do Django, `last_beat(name)` lê. Batido por:
`shopman/shop/management/commands/maintenance_worker.py:291-299` e
`packages/orderman/.../management/commands/process_directives.py:119,150`. [FATO]

**Consumido por:**
- `/health/ready/` → `_check_required_workers` (`shop/views/health.py:146-165`) e `_check_queue`
  (`:168-206`) — heartbeat velho ou fila parada ⇒ `fail` ⇒ **503**. [FATO] **Cuidado de operação:**
  com cache **locmem** (dev/CI) `required=()` — a checagem se desliga sozinha (`:151-154`).
- `check_directive_health` (`shop/management/commands/check_directive_health.py:108-113`), que roda no
  ciclo do `maintenance_worker` (`maintenance_worker.py:167`) e vira `OperatorAlert`. [FATO]

**Duração do ciclo — a lacuna.** `maintenance_worker.py:266-288`:

```python
started = time.monotonic()
try: self._run_cycle()
except Exception: logger.exception("maintenance_worker: ciclo falhou (worker continua)")
if once: return
elapsed = time.monotonic() - started
remaining = interval - elapsed
if remaining > 0: time.sleep(remaining)
else:
    logger.warning("maintenance_worker: ciclo levou %.1fs, mais que o intervalo de %ds", elapsed, interval)
```

A duração **é medida** mas só é **emitida quando excede o intervalo** (`--interval` default `300` s).
O alvo do WP §4 ("ciclo ≤ 60 s, log por ciclo") **não é observável hoje** — no log do
`maintenance-worker` não há uma linha por ciclo, nem início, nem duração. [FATO: 86 linhas de
amostra, todas de boot/handlers]. A prova de ≤ 60 s hoje só sai por um truque: subir com
`--interval 60` e observar se o WARNING aparece.

---

### A6 — Capacidade do contêiner: CPU e memória AGORA são medidos (o P7 do WP tem resposta) [FATO]

O WP §7 registrava "CPU e memória por componente: sem `monitoring:read`". **Há um segundo caminho,
e ele está no ar:**

- `surfaces/operator-kit/server/utils/containerCapacity.ts:529-576` lê o **cgroup do próprio
  contêiner** (v2 → v1 → soma de `/proc`), com três réguas declaradas e recusa honesta:
  `available: false` quando nenhuma é legível (`:21-27`).
- Rota `GET /health/capacity` (`operator-kit/server/routes/health/capacity.get.ts` +
  `capacityRoute.ts:24-61`) — autenticada, o Nitro lê e reporta.
- `POST /api/v1/backstage/operator/capacity/` (`shopman/backstage/api/operator_capacity.py:43-84`)
  avalia contra os limiares do Admin, **loga** `operator_capacity.sample` e pode abrir `OperatorAlert`
  tipo `operator_capacity_critical` (`shop/services/operator_capacity.py:47`).
- Diagnóstico de primeira leitura: uma linha JSON `capacity.probe` no stdout do Nitro
  (`containerCapacity.ts:495-527`) dizendo **qual régua valeu** e quais caminhos existem.

**Ressalva medida:** a amostra de log que puxei do `operator-floor` (17 linhas) **não continha
`capacity.probe` nem `operator_capacity.sample`** — o que é esperado, porque o log grava `DEBUG` em
folga e a amostra é minúscula. Ou seja: **a capacidade só vira linha de log quando aperta**, e folga
não é observável em série histórica. [FATO na amostra; INFERÊNCIA na generalização] Isso responde
"quanto está agora" (com operador logado, na tela) mas **não** "como estava ontem às 19h".

**E o caminho da DO continua fechado — verificado:**

```bash
$ doctl apps list --format ID,Spec.Name
40b86e35-bafe-4a1a-a1b0-e124d3d9fd0f    shopman-nelson        ...      # leitura OK
$ doctl databases list
Error: GET https://api.digitalocean.com/v2/databases: 403 ... You are not authorized
$ curl -H "Authorization: Bearer $TOKEN" \
    "https://api.digitalocean.com/v2/monitoring/metrics/apps/cpu_percentage?app_id=40b8..."
403 {"id":"Forbidden","message":"You are not authorized to perform this operation"}
```
[FATO — reproduzido nesta sessão; o runbook `docs/runbooks/backup-e-restore.md:102,364` já
registrava que "os tokens desta máquina dão 403 em `doctl databases`"]

---

### A7 — `pg_stat_statements`: nada no repositório, e nada acessível daqui [FATO]

- `grep` por `pg_stat_statements`, `log_min_duration_statement` e `pgaudit` em `.py`/`.yaml`/`.sh`/
  `.toml` (excluindo `node_modules`): **as únicas ocorrências são dentro de
  `docs/plans/WP-PERFORMANCE-2026-09.md`**. Não há migração, `RunSQL`, setting nem script. [FATO]
- Não há `CREATE EXTENSION` em lugar nenhum do repo. [FATO — grep]
- **Não é verificável daqui se a extensão está disponível no cluster**: exigiria `doctl databases`
  (403) ou `DATABASE_URL` do alpha. [BLOQUEADO]
- **Consequência direta:** as provas antes/depois de P2 e P3 (deltas de `seq_scan`, `temp_bytes`,
  `EXPLAIN` das consultas, `n_live_tup`) **continuam inalcançáveis para um agente**. Elas dependem de
  uma ação de banco que só o dono pode autorizar/executar. [FATO]
- O runbook de sintoma (`docs/runbooks/postgres-lento.md:15-22`) manda rodar `make diagnose-runtime`/
  `diagnose-health` — que chamam `scripts/diagnose_operational.py` **contra o banco do ambiente
  local**, não contra o cluster vivo. **O runbook não tem uma linha sobre consulta lenta, `EXPLAIN`
  ou `pg_stat_statements`.** [FATO]

---

### A8 — Harness de carga: existe, e está desconectado da prova de melhoria [FATO]

| alvo | o que é | o que mede | onde |
|---|---|---|---|
| `make load-test` | Locust headless (`shopman/shop/tests/load/locustfile.py`, 317 linhas) | p95 alvo < 500 ms, 5 classes de usuário (browsing/checkout/payment/operator/KDS) | `Makefile:388-389` |
| `make storefront-e2e` | Playwright + seed + Django:8001 + Nuxt:3100 | **correção de fluxo**, não latência | `Makefile:391-395`, `scripts/run_storefront_e2e.sh` |
| `make marketing-capacity` | 200k candidatos / 20k targets, banco descartável, sem provider | escalabilidade do público de Marketing | `Makefile:276-281`, `shopman/shop/tests/test_marketing_capacity.py` |
| `make test-workflow-budgets` | teto do job vs espera declarada | **orçamento de CI**, não de runtime | `Makefile:351-353` |
| `test_operational_budget.py` | 24 mutações de carrinho, test client | p95 local, `budget_ms=1500` | `shopman/storefront/tests/test_operational_budget.py:12-40` |
| `test_catalog_nplus1_measure.py` | `CaptureQueriesContext` em fixture | `n <= 55` e `n_big - n_small <= 3` | `shopman/storefront/tests/web/test_catalog_nplus1_measure.py:234,297` |
| `performanceGuardrails.test.ts` | leitura de código-fonte | **estrutura**, não número | `surfaces/storefront-nuxt/tests/performanceGuardrails.test.ts` |
| Pre-go-live Smoke | 4 `curl` contra o ambiente vivo, pós-deploy + cron | **presença** (`/ready/` = 200, cardápio ≥ 30 SKUs, POST checkout = 403, home > 20 KB) | `.github/workflows/alpha-smoke.yml:212-254` |

**O smoke é o único guardrail que vê o ambiente vivo — e ele não olha tempo.** Ele captura
`-w '%{http_code}'` em toda parte (`alpha-smoke.yml:214,231,247`) e **`%{time_starttransfer}` em
lugar nenhum**. Um `curl -w` a mais, no passo que já baixa a home, daria a série de TTFB por deploy
de graça. [FATO — grep por `time_total`/`time_starttransfer` no repo: só aparece na documentação de
"como medir" dos relatórios, nunca em automação]

**`assertNumQueries` no repositório inteiro: ZERO ocorrências** (`grep -rln assertNumQueries
--include='*.py' shopman packages | wc -l` → `0`). A única trava de contagem de queries é a manual em
`test_catalog_nplus1_measure.py`. [FATO]

---

### A9 — Baseline: existe como documento e artefato, não como verificação [FATO]

| baseline | onde vive | formato | é comparado automaticamente? |
|---|---|---|---|
| Latência externa 17/09 (tabela §2.1) | `docs/plans/WP-PERFORMANCE-2026-09.md:35-43` | tabela markdown | **não** |
| Metas/SLO §4 | `WP-PERFORMANCE-2026-09.md:163-174` | tabela markdown | **não** |
| Orçamento local de mutação | `docs/reports/storefront-operational-20260910/continuation-postgres-budget.txt:553` (`p95_ms: 36.41`), `budget-after.txt:552` (`28.98`), `budget-before.txt:552` (`44.66`) | JSON em arquivo de log | só o teto `<= 1500` roda em `pytest`; **o valor medido não é comparado com o histórico** |
| Thresholds do shadow Continuum | `scripts/evaluate_continuum_shadow.py:122-129` (`--maximum-p95-shadow-ms 25.0`, `--minimum-samples 500`, `--minimum-window-seconds 86400`) | `argparse` defaults | **sim, mas só à mão** — nenhum workflow nem `make` invoca. [FATO: grep em `.github/`/`Makefile` = 0] |
| Sete thresholds normativos da spec 0.2 | `docs/specs/continuum-0.2.md:1845-1872` (`p95_latency_regression_ms`, `error_rate_regression`, …) | prosa normativa | **não** — a própria spec diz que o deployment precisa preencher owner/janela/thresholds, e isso não foi feito (`docs/reports/continuum-0.2-shopman-pilot-20260928.md:232-255`) |
| Perf artifacts de 09-10/09 | `docs/reports/storefront-operational-20260910/` (`budget-before/after`, `baseline-*`), `docs/reports/execution/orders-20260910/` (dezenas de `*-before`/`*-final`, `profile-before.txt`) | arquivos | **não** |

**Resposta curta:** hoje, provar que uma mudança melhorou performance é um **exercício manual de
`curl` + leitura de log**, reproduzível só porque o autor escreveu o comando no relatório. Não há um
número versionado que o CI ou um cron confira. [FATO]

---

### A10 — Instrumentação morta: `CartMutationPerf` [FATO] [BAIXO esforço, sinal imediato]

`shopman/storefront/perf.py` (79 linhas) define `CartMutationPerf` — fases, `sql_count`, `sql_ms`,
`maybe_log` que só emite acima de um limiar. Criado no commit `f1f77c366` ("perf: instrument cart
mutations and reuse stock availability").

```bash
$ grep -rn "CartMutationPerf\|maybe_log\|storefront import perf" --include='*.py' .
./shopman/storefront/perf.py:15:class CartMutationPerf:
./shopman/storefront/perf.py:60:    def maybe_log(self, **extra: Any) -> None:
$ grep -c "cart.set_qty.perf" /tmp/obs_web2.jsonl /tmp/obs_web_run.jsonl
0
0
```

**Zero chamadores; zero linhas no log de produção.** E a variável que a liga **está setada no app
vivo**: `SHOPMAN_CART_MUTATION_PERF_LOG_MS=250` (app-level, e também versionada em
`.do/app.alpha-subdomains.yaml:355-358`). Alguém esperava log de mutação de carrinho acima de 250 ms;
o instrumento nunca foi conectado. [FATO]

---

### A11 — Um sinal de instabilidade vivo no log, e nada olhando [FATO] [MÉDIO]

Na janela de ~12 min do log do `web`:

```
/api/v1/backstage/channels/attention/ : n=246  distinct_ip=2  status={'403': 233, '200': 13}
/api/v1/backstage/pos/               : n=24   distinct_ip=2  status={'403': 24}
/api/v1/backstage/operator/session/ : n=24   distinct_ip=1  status={'403': 24}
/api/v1/backstage/orders/            : n=39   distinct_ip=3  status={'200': 13, '403': 26}
```

São **2 IPs internos** (os contêineres Nitro de operador) batendo ~**21 req/min** e levando **403** em
quase todas — extrapolando, ~30 mil 403/dia. Cada uma dessas vem acompanhada de um `django.request`
WARNING. **Nenhum alerta existe para isso**, e o Sentry, mesmo ligado, **não recebe WARNING** por
default (`LoggingIntegration` só captura `ERROR`). [FATO nos dados; INFERÊNCIA sobre a causa — sessão
de operador expirada em superfície que continua fazendo poll]

Não é o assunto deste relatório, mas é **exatamente o tipo de sinal que este relatório existe para
tornar visível**: o dado está no log, é gratuito, e ninguém o lê. Vale conferir se o
`02-perf-operador.md`/`05-pwa-travado.md` já cobrem a causa — `grep "403"` nos dois: **0 ocorrências**.
[FATO]

---

## 3. O que já existe — inventário do que dá para medir HOJE sem trabalho novo

| # | Sinal | Como obter | Credencial | Latência por request? | Granularidade |
|---|---|---|---|---|---|
| 1 | `Server-Timing` (Django: `projection/availability/personalization/shadow/db`) | `curl -s -o /dev/null -D- <url> \| grep -i server-timing` | **nenhuma** | sim | `menu/`, `catalog/`, `continuum/…` |
| 2 | `Server-Timing` + estágio `bff` | idem, na rota de API pelo host da loja | **nenhuma** | sim | separa BFF de Django |
| 3 | `storefront_catalog_observation` | `doctl apps logs <id> web --type run --no-prefix \| jq 'select(.message=="storefront_catalog_observation")'` | `doctl apps logs` (OK) | sim (ms por estágio) | por request, allowlisted |
| 4 | `operator.request.finished` (`view_elapsed_ms`) | idem, `jq 'select(.message=="operator.request.finished")'` | `doctl apps logs` | sim | 9 módulos de API backstage |
| 5 | Log de acesso do daphne (path, método, status, bytes) | `doctl apps logs <id> web --type run` | `doctl apps logs` | não (sem duração) | por request — **80/812 linhas trazem query string** |
| 6 | Volume e mix de status por endpoint | agregação de (5) | `doctl apps logs` | não | por endpoint |
| 7 | TTFB e bytes de qualquer URL pública | `curl -w '%{time_starttransfer} %{size_download} %{http_code}'` | **nenhuma** | sim (ponta a ponta) | por URL; é o número do cliente |
| 8 | Cache/borda | `curl -D- … \| grep -iE 'cf-cache-status\|cache-control\|age\|vary'` | **nenhuma** | não | mostra `BYPASS`/`HIT`, `private`/`public` |
| 9 | Percentis (p50/p75/p95) de um log | `scripts/evaluate_continuum_shadow.py` (molde pronto) | `doctl apps logs` | sim | hoje só `storefront_menu`+`shadow` |
| 10 | Heartbeat de worker e lag de fila | `curl /health/ready/` → `checks.queue`; `make diagnose-worker` | **nenhuma** (o curl) / banco (o make) | não | binário por worker |
| 11 | CPU/memória do contêiner (cgroup) | `GET /health/capacity` com sessão de operador; `capacity.probe` no stdout do Nitro | sessão de operador | não | por serviço, sob demanda |
| 12 | Alertas de capacidade sustentada | `OperatorAlert operator_capacity_critical` | Admin | não | quando aperta |
| 13 | Erro de cliente do front (storefront e operador) | `doctl apps logs \| jq 'select(.message \| startswith("storefront_client_error"))'` | `doctl apps logs` | não | por erro, deduplicado no cliente |
| 14 | Erro não tratado do servidor | `OperatorAlert` severidade `error` + Sentry (DSN setado) | Admin / Sentry | não | exceção agrupada |
| 15 | Envelope de métrica vendor-neutral | `marketing.metric` no log (`marketing_observability.py:122-144`) | `doctl apps logs` | parcial | só Marketing |
| 16 | Carga local com p95 (Locust) | `make load-test` | local | sim | pré-merge, ambiente local |
| 17 | Contagem de queries em fixture | `pytest shopman/storefront/tests/web/test_catalog_nplus1_measure.py` | local | não | pré-merge |
| 18 | Orçamento local de mutação | `pytest shopman/storefront/tests/test_operational_budget.py -s` | local | sim | pré-merge |
| 19 | Presença do ambiente vivo pós-deploy | Pre-go-live Smoke | GitHub Actions | não | pós-deploy + cron |
| 20 | Deploy: duração, cancelados, erros, push→no ar | `doctl apps list-deployments`, `gh run list` | `doctl apps` + `gh` (OK) | não | por deploy |

**Sinais que NÃO estão ao alcance daqui, com a prova:**

| Quero | Preciso de | Estado |
|---|---|---|
| consulta lenta nomeada (`pg_stat_statements`) | `CREATE EXTENSION` + `databases:read/update` | `doctl databases list` → **403** |
| log de query lenta (`log_min_duration_statement`) | `doctl databases configuration update` | idem |
| CPU/memória da DO por componente | `monitoring:read` | API de monitoring → **403** |
| custo do hairpin BFF (medido de dentro) | `doctl apps console` interativo | não testado aqui; [NÃO VERIFICADO] |
| LCP/INP/CLS da loja no navegador real | Playwright instrumentado **ou** um coletor de vitals na loja | **não existe** na loja (existe no Marketing) |

---

## 4. Lacunas e riscos, ordenados

| # | Lacuna | Por que dói | Confiança |
|---|---|---|---|
| **L1** | **`Server-Timing` não cobre a rota de entrada** (`home/`, `shell/`, `site/`, `cart/`, `checkout/`, `tracking/`, `products/`, Conta) | o endpoint mais lento é o que não tem régua; qualquer ganho na home é **indemonstrável** | [FATO] |
| **L2** | **A página SSR não devolve `Server-Timing`** | o tempo que o cliente sente (3,5–3,9 s na home) não está instrumentado em lugar nenhum | [FATO medido] |
| **L3** | **Nenhum coletor automático lê os logs.** `evaluate_continuum_shadow.py` existe e é manual; nenhum `make`/workflow o chama | o sinal existe e expira: log do App Platform tem retenção curta, e a regressão de 17→29/09 só foi achada porque **eu** fui olhar | [FATO] |
| **L4** | **O smoke pós-deploy não mede tempo** | é o único guardrail do ambiente vivo, roda a cada deploy, e joga fora o TTFB que já tem na mão | [FATO] |
| **L5** | **Não existe baseline versionada comparável.** §2.1 do WP é prosa; os artefatos de 09-10/09 são arquivos soltos | "prove que melhorou" vira arqueologia de relatório | [FATO] |
| **L6** | **`pg_stat_statements` e log de query lenta seguem desligados**, e o token daqui não instala | P0 do WP continua sendo o bloqueio de P2/P3; nenhum agente consegue medir query sem o dono | [FATO] |
| **L7** | **Duração do ciclo do `maintenance_worker` só aparece quando estoura o intervalo** | o alvo "≤ 60 s, log por ciclo" é inobservável | [FATO] |
| **L8** | **Capacidade só loga quando aperta** (`DEBUG` em folga) | não há série histórica de CPU/memória; "como estava ontem às 19h" não tem resposta | [FATO na amostra / INFERÊNCIA na generalização] |
| **L9** | **`CartMutationPerf` é código morto com a flag ligada em produção** | a mutação mais sensível do funil (PUT do carrinho) não tem medição de fase, e alguém acha que tem | [FATO] |
| **L10** | **Zero `assertNumQueries` no repositório** | uma query nova em projeção quente entra sem trava nenhuma | [FATO] |
| **L11** | **O guard de N+1 mede fixture (≤ 55 queries), não produção (93–94 medidas)** | o teto do CI não representa a forma viva; verde no teste não significa verde no ar | [FATO nos dois números; INFERÊNCIA na conclusão] |
| **L12** | **Nada correlaciona requests.** `request_id` existe só no mixin do backstage e **não vai para o log de acesso** | não dá para seguir uma requisição lenta ponta a ponta | [FATO] |
| **L13** | **Access log traz query string em ~10% das linhas** | é o motivo declarado para "não ler log de acesso"; hoje é evitável com `jq` só no JSON allowlisted | [FATO] |
| **L14** | **WARNING não chega ao Sentry** (`LoggingIntegration` default = `ERROR`) e não há alerta para 403 em massa | os ~30 mil 403/dia de operador passam invisíveis | [FATO nos dados] |
| **L15** | **Web Vitals só existem no Marketing** | LCP/INP/CLS da loja — a métrica que o cliente sente — não existe; o padrão já está escrito no repo | [FATO] |

---

## 5. Recomendações: a MENOR infraestrutura de medição que prova antes/depois e pega regressão

> Princípio: **cada item abaixo usa o que já está no repo.** Nada aqui compra ferramenta, nada pede
> `monitoring:read`, nada depende de acesso que esta máquina não tem.

### R1 — Ligar `capture_catalog_timing()` nas views que faltam · *impacto alto × esforço XS*

Reusa `observability.py:50-67` — o `catalog_stage` sai cedo quando o `ContextVar` é vazio (`:40-47`),
custo ~zero. Anexar `response["Server-Timing"] = timing.server_timing()` e a chamada de
`log_catalog_observation` em `StorefrontHomeView`, `StorefrontShellView`, `StorefrontSiteView`,
`StorefrontCartView`, `StorefrontCheckoutView`, `StorefrontProductView`, `OrderTrackingView`.
**Prova:** `curl -s -D- …/storefront/shell/ | grep server-timing` passa a responder; e `db;dur` de
`home/` ≈ `db;dur` de `shell/` **+ catálogo** — que é exatamente a assinatura do achado A1 do
`01-perf-storefront.md`. **Fecha L1 e a maior parte de L2.**

### R2 — Generalizar o avaliador de logs para (path, mode) com thresholds versionados · *impacto alto × esforço S*

`scripts/evaluate_continuum_shadow.py` já faz 90%: lê stdin, extrai por `message`, calcula
`_percentile` (`:36-41`), devolve `status: pass|fail` e sai com código ≠ 0 (`:132-137`). O que falta é
o filtro sair de `path=="storefront_menu" and mode=="shadow"` (`:58`) para uma lista de alvos, e os
thresholds saírem de `argparse` para um JSON versionado.
**Forma mínima:** `scripts/evaluate_observation_window.py --targets docs/observability/targets.json`
com `{"storefront_menu": {"p50_projection_ms": 800, "p95_db_ms": 600, "p95_query_count": 60}}`.
**Prova:** `doctl apps logs <id> web --type run --no-prefix --tail 20000 | python3
scripts/evaluate_observation_window.py` sai `0` ou `1` com o JSON de percentis. **Fecha L3 e L5** — e
com os números de hoje já reprovaria, que é o ponto.

### R3 — Capturar TTFB no Pre-go-live Smoke e guardar como artefato · *impacto alto × esforço XS–S*

`.github/workflows/alpha-smoke.yml` já baixa a home (`:244-254`) e já usa `curl -w` (`:214,231,247`) —
só não pede tempo. Trocar por `-w '%{time_starttransfer} %{size_download} %{http_code}'`, publicar um
JSON (`upload-artifact`) e comparar contra um `docs/observability/ttfb-baseline.json` versionado, com
teto folgado (ex.: 1,5× o baseline). **É o único ponto do sistema que roda logo depois de cada deploy
no ambiente vivo.** Fecha parcialmente L4 e é o detector de regressão de produção mais barato que
existe aqui.

### R4 — Um alvo `make perf-window` que amarra R2 + R3 · *impacto médio-alto × esforço XS*

Encapsula o `doctl apps logs` + avaliador + smoke, para virar comando de uma linha no relatório de
cada PR. Sem ele, R2 e R3 ficam sendo scripts que ninguém lembra que existem — que é exatamente o
estado do `evaluate_continuum_shadow.py` hoje.

### R5 — `Server-Timing` na resposta HTML do SSR · *impacto médio × esforço S*

Hoje o BFF anexa `bff;dur` no `event` (`djangoProxy.ts:216-220`) e o header **não sobrevive até a
página** (medido). Enquanto isso não for resolvido, `curl` externo não consegue separar "SSR demorou"
de "Django demorou" — só o `bff;dur` da rota de API, que não é o que o cliente pede. Um hook
`render:response` no Nitro (o mesmo lugar onde `server/plugins/homeCompression.ts` já reescreve
headers da home, `:53-84`) resolve. **Fecha o resto de L2.**

### R6 — Conectar (ou apagar) `CartMutationPerf` · *impacto médio × esforço XS*

`shopman/storefront/perf.py` está escrito, testado por ninguém e sem chamador, e a flag
`SHOPMAN_CART_MUTATION_PERF_LOG_MS=250` já está ligada em produção. Duas saídas honestas: (a) envolver
`StorefrontCartSetQtyView` com `CartMutationPerf().capture()` e usar `step()` nas fases, ou (b) remover
o módulo e a env. **Deixar como está é o pior dos três.** Fecha L9.

### R7 — Vitals da loja, reusando o padrão do Marketing · *impacto médio × esforço S*

`surfaces/marketing-nuxt/app/plugins/marketingVitals.client.ts` é o molde (PerformanceObserver,
LCP/INP/CLS) e `MarketingVitalView` (`backstage/api/telemetry.py:206-235`) é o receptor allowlisted
que já existe. A loja precisa de um endpoint próprio com o mesmo saneamento. **Fecha L15** — e é a
única forma de medir o que o cliente sente, já que a home SSR é 3,5–3,9 s e a API só explica parte
disso.

### R8 — Log de duração por ciclo no `maintenance_worker` · *impacto baixo-médio × esforço XS*

`maintenance_worker.py:266-288` já calcula `elapsed`. Trocar o `logger.warning` condicional por um
`operational_event("maintenance_worker.cycle", elapsed_ms=…, over_interval=…)` no fim do `_run_cycle`
— INFO, agregável pelo R2. Fecha L7 e dá a série que o WP §4 pediu.

### R9 — `assertNumQueries` nas projeções do storefront · *impacto médio × esforço S–M*

O repositório tem **zero**. Um punhado de travas em `shopman/storefront/tests/api/` (home, shell,
cart, checkout, tracking) converte "achado de auditoria" em "teste vermelho no PR". Ataca L10 e L11
de uma vez, e é o único item desta lista que pega N+1 **antes** do merge.

### R10 — PII no access log e correlação · *impacto baixo × esforço XS–S*

Nada a fazer hoje: basta que qualquer agregador novo leia **só** o JSON allowlisted
(`storefront_catalog_observation`, `operator.request.finished`) e **nunca** a request line do daphne.
Vale registrar isso como regra no script do R2 — 80 de 812 linhas trazem query string. Fecha L13 por
construção.

### R11 — P0 do WP (`pg_stat_statements`, `log_min_duration_statement`) · *impacto alto × esforço… do dono*

Continua sendo o de maior impacto e **não é executável por agente**: `doctl databases` → 403
(reproduzido). Sem ele, "qual query", "quantas vezes", "quanto custa" continuam sendo inferência de
código. **Recomendação de encaminhamento:** é uma pergunta para o dono, com o comando pronto
(`WP-PERFORMANCE-2026-09.md:195-198`), não uma tarefa de agente.

### Quadro resumo

| Rec. | Fecha | Esforço | Depende de |
|---|---|---|---|
| R1 Server-Timing nas views que faltam | L1, L2 | XS | nada |
| R2 avaliador de janela de log | L3, L5 | S | nada |
| R3 TTFB no smoke + baseline | L4 | XS–S | nada |
| R4 `make perf-window` | L3 | XS | R2, R3 |
| R5 Server-Timing no SSR | L2 | S | nada |
| R6 `CartMutationPerf` | L9 | XS | decisão: ligar ou apagar |
| R7 Vitals da loja | L15 | S | endpoint novo |
| R8 log de ciclo do worker | L7 | XS | nada |
| R9 `assertNumQueries` | L10, L11 | S–M | nada |
| R10 regra de PII no agregador | L13 | XS | R2 |
| R11 `pg_stat_statements` | L6 | — | **credencial do dono** |

**Se for para fazer uma coisa só:** R2 + R3 + R4. Juntas são ~200 linhas de script, dois passos de
workflow e um JSON versionado, e transformam "eu fui olhar o log" em "o comando disse que passou" —
que é a definição de detectar regressão.

---

## 6. Perguntas abertas

1. **O `SENTRY_DSN` vivo é válido?** Ele está setado (app-level, `SECRET`, valor criptografado) e
   `SENTRY_TRACES_SAMPLE_RATE` está ausente ⇒ `0`. Não consigo verificar daqui se o DSN colado é
   bem-formado nem se eventos chegam ao projeto. O passo 3 do `docs/runbooks/ativar-sentry.md`
   (evento de fumaça) foi executado? O runbook precisa ser atualizado — hoje ele afirma que
   `SENTRY_DSN` "nunca foi setado", o que é falso. [NÃO VERIFICADO]

2. **Server-Timing na home: o ganho do achado A1 é mensurável sem deploy?** Não — depende de R1.
   Enquanto isso, alguém autoriza mudar código de observabilidade no meio de uma frente de go-live?

3. **A regressão de 17/09 → 29/09 no `menu/` (0,93–1,39 s → 2,57–2,83 s) é conhecida e explicada?**
   Achei 12 amostras consistentes no log e 7 `curl` independentes, e nenhum documento a registra. Se
   for efeito de carga/horário, precisa de uma segunda medição em outra janela para separar. **Este é
   o achado que mais pede resposta.**

4. **Onde mora a série de CPU/memória do `web`?** A telemetria de cgroup (`/health/capacity`) só loga
   quando aperta, e só com operador logado. O painel *Insights* da DO tem a série? Alguém com
   `monitoring:read` pode anexá-la? Sem isso, a decisão de processo do `daphne` (WP §7) continua no
   escuro — e a consolidação de 8 Nuxt em 2 serviços (`operator-floor`/`operator-office`, ADR-030) já
   aconteceu **sem** a medição que o próprio WP §5-P9 exigia como pré-requisito.

5. **A retenção do log do App Platform é suficiente para uma janela de 24 h?**
   `evaluate_continuum_shadow.py` exige `--minimum-window-seconds 86400` (`:125`), mas eu só consegui
   ~1.500 linhas (~12 min) com `--tail 20000`. O `doctl apps logs` trunca por tamanho/tempo? Se
   truncar, **a janela de 24 h do R2 não fecha** e o coletor tem que rodar em cadência e acumular.
   [NÃO VERIFICADO — não testei retenção longa]

6. **Quem é o dono do `SHOPMAN_CART_MUTATION_PERF_LOG_MS=250`?** O commit `f1f77c366` ligou o módulo
   e um commit posterior removeu os chamadores (ou nunca os teve). Foi desligamento deliberado ou
   regressão silenciosa?

7. **O `pg_stat_statements` está instalado no cluster hoje?** O WP dizia "disponível, não instalado"
   em 17/09. Não consigo verificar sem `doctl databases` (403). Alguém com o token de database pode
   responder com uma linha?

8. **O que é `SHOPMAN_ENVIRONMENT=staging` no app `shopman-nelson`?** O WP chamava esse ambiente de
   "alpha". Se ele é o ambiente que vai a produção, o `environment` do Sentry vai misturar os dois no
   painel — o comentário em `settings.py:2244` promete que não.
