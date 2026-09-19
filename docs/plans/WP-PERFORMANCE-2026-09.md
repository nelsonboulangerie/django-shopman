# WP-PERFORMANCE-2026-09 — onde o tempo vai, medido no ar

> Aberto em 2026-09-17, a pedido do dono, junto com a frente de custo. Documento de
> **plano**: tudo abaixo foi medido com leitura (curl GET público, `doctl` de leitura,
> `psql` com `BEGIN READ ONLY`). Nenhum código, índice ou configuração foi alterado.
> Irmão: [WP-DO-ECONOMIA-2026-09](WP-DO-ECONOMIA-2026-09.md). As propostas que mexem em
> custo apontam para lá, e vice-versa.

## O problema em uma frase

Com tráfego de alpha, a loja leva **2,1–3,0 s** para entregar o primeiro byte da home.
O servidor gasta ciclos com health check que renderiza a home, com scans completos a
cada 5 minutos e com uma cascata de 10 deployments por merge. **O gargalo não é a
máquina: é trabalho que não precisava existir.**

## 1. Como foi medido

- **Latência externa:** `curl -w` com 5 amostras por URL, espaçadas de 1 s, a partir do
  Brasil (Cloudflare `GRU`), em 17/09/2026 por volta de 11:30 UTC. Só GET de health e
  leitura pública.
- **Deploy:** `doctl apps list-deployments` (1.170 deployments desde 06/05) e
  `gh run list --workflow deploy-images.yml` (300 runs desde 29/08).
- **Banco:** `pg_stat_database`, `pg_stat_user_tables` e `pg_stat_user_indexes`. Os
  contadores valem desde o último restart, em **04/09 03:50 UTC (13,3 dias)**, e as
  taxas por dia abaixo dividem por esse intervalo.
- **Valkey:** `INFO` (uptime de 20 dias).
- **Código:** leitura dos pontos citados, com arquivo e linha no momento da leitura.
  Referência `arquivo:linha` envelhece em horas, então confira no ref.

## 2. Baseline medido

### 2.1 Latência externa (TTFB, s)

| Endpoint | min | máx | Corpo | Leitura |
|---|---:|---:|---:|---|
| `api./health/` | 0,35 | 0,48 | 45 B | **piso de rede** BR → Cloudflare → origem `nyc` |
| `api./ready/` | 0,44 | 0,84 | 96 B | +0,1 a +0,36 s sobre o piso |
| `menu.` `/` (SSR da home) | **2,10** | **3,00** | 133 KB (26,5 KB gzip) | `cf-cache-status: BYPASS` |
| `api./api/v1/storefront/home/` | 1,03 | 1,88 | 6,2 KB | `cache-control: private` |
| `api./api/v1/storefront/menu/` | 0,93 | 1,39 | 103 KB (7 KB gzip) | `vary: Accept, Cookie`; seta `csrftoken` em GET anônimo |
| `api./api/v1/catalog/products/` | 0,76 | 1,12 | 10,9 KB | |
| Shells de operador (`central.`, `gestor.`, `pdv.`, `mkt.`) | 0,33 | 0,67 | 7–20 KB | |
| `cardapio.` (static site) | 0,12 | 0,21 | 48 KB | servido da borda |

Tirando o piso de rede de ~0,35 s, o **tempo de servidor estimado** é de 0,6–1,5 s
para `home/`, 0,6–1,0 s para `menu/`, e 1,8–2,6 s para o SSR da home.

Referência local anterior: mutação de carrinho em PostgreSQL, p95 36 ms e máximo
457 ms (`docs/reports/storefront-operational-20260910/continuation-postgres-budget.txt`),
feita via test client, sem rede nem SSR. **A distância entre 36 ms local e ~1 s no ar
é o que este WP persegue.**

### 2.2 Deploy

| Métrica (janela) | Valor |
|---|---|
| Runs do `deploy-images` por dia (7 d / 14 d / 30 d) | 22,1 / 16,9 / 10,0 |
| Duração do run com sucesso (14 d, n=233) | p50 140 s · p90 279 s |
| Deployment DO criado → último passo (14 d, n=250) | p50 181 s · p90 235 s; passo `deploy` p50 139 s |
| **Push no `main` → deployment no ar** (14 d, n=193, aproximado) | **p50 329 s (5,5 min) · p90 606 s (10 min)** |
| Deployments em 7 dias | **391**: 167 superseded, **184 cancelados**, **39 em erro**, 1 ativo |
| Rajadas de deployment (≤ 120 s entre si) em 7 dias | 8 rajadas de 9, 8 de 10 e 3 de 11 deployments |
| Causa dos 39 erros | todos `release: DeployContainerExitNonZero`; 33 em 16/09 |
| Cache do GitHub Actions | **12,28 GB em 166 entradas**, acima do limite padrão de 10 GB por repositório |

A memória de 28/08 dizia "~6 min". A medição de hoje confirma o p50 de 5,5 min, mas a
cauda p90 é de 10 min.

### 2.3 Banco (`shopman`, 194 MB, 13,3 dias de contadores)

| Sinal | Medido | Por dia |
|---|---|---:|
| Cache hit | 100,00% | — |
| Arquivos temporários (spill em disco, `work_mem` = 2 MB) | **7.826 arquivos, 40 GB** | 588 arquivos · ~3 GB |
| `backstage_historicalsaleitem` (380.199 linhas): seq scans | 3.900 (1,48 bi de tuplas) | **293** ≈ 1 por ciclo do `maintenance-worker` (288/dia) |
| `backstage_historicalsale` (81.255): seq scans | 3.906 | 294 |
| `orderman_order` (6.196): seq scans | 203.642 (1,26 bi de tuplas) | **15.311** |
| `orderman_orderitem` (12.406): seq scans | 173.627 (2,15 bi de tuplas) | **13.055** |
| `django_migrations` (253): seq scans | 136.500 | **10.263** |
| `shop_channel` (6 linhas): seq scans | 1.342.956 | 100.974 |
| `offerman_product` (111): seq scans | 1.022.919 | 76.911 |
| Índices não-únicos nunca usados | 402 de 970 (23 MB de 81 MB) | — |
| `pg_stat_statements` | **disponível, não instalado** | — |
| `log_min_duration_statement` | `-1` (desligado) | — |
| Conexões | `max_connections` 25; pool `transaction` de 5; `CONN_MAX_AGE` 60 | — |

Estatística do planner: `orderman_orderitem` mostra `n_live_tup = 66` com 12.406
linhas reais, e nunca teve `autoanalyze`. As tabelas históricas mostram 0 com 380 mil
linhas. O planner está decidindo com números errados.

### 2.4 Valkey

| Sinal | Medido |
|---|---|
| Memória | 4,95 MB (pico 10,9 MB) de 418 MB |
| Chaves | 8 |
| Comandos | 11,9 mi em 20 dias (~5 ops/s) |
| **Conexões recebidas** | **563.533 em 20 dias ≈ 28 mil/dia ≈ 1 conexão TLS nova a cada 3 s** |
| Clientes conectados agora | 17 |

### 2.5 Topologia que pesa na latência

- **`web` é um único processo `daphne`** numa vCPU compartilhada, servindo API, Admin e
  as conexões SSE longas.
- **Os 9 BFFs Nuxt chamam o Django pela URL pública** (`NUXT_DJANGO_BASE_URL` aponta
  para `api.boulangerie.com.br`, conferido no spec sem ler valores sensíveis). Cada
  chamada de SSR sai do container, passa pela Cloudflare e volta ao mesmo app.
- **Health checks** (spec vivo):
  - `web` em `/ready/` a cada 10 s: 8.640/dia.
  - `storefront-nuxt` em `/` a cada 15 s, com timeout de 20 s: 5.760 renders de SSR/dia.
  - Os 8 Nuxt de operador em `/` a cada 10 s: 8.640/dia cada.
- Região `nyc`. A DO não tem região de App Platform na América do Sul, então o piso de
  rede de ~0,35 s não sai com troca de região; sai com borda (P6).

## 3. Gargalos, com evidência

1. **O health check da loja renderiza a home de verdade.** `app/pages/index.vue` faz
   `useFetch('/api/v1/storefront/home/')` no SSR, e a DO bate em `/` a cada 15 s. Por
   construção, são **5.760 chamadas/dia ao endpoint mais lento medido (1–1,9 s)**, no
   mesmo processo `daphne` que atende o cliente. *Prova pendente:* contar
   `/api/v1/storefront/home/` com user-agent da DO no log do `web`.
2. **O `/ready/` monta o grafo de migrations a cada 10 s.** `shopman/shop/views/health.py`
   `_check_migrations()` instancia `MigrationExecutor`, e o banco confirma: 10.263 seq
   scans/dia em `django_migrations`, perto das 8.640 sondas/dia. Ele também faz
   `cache.set/get/delete` a cada chamada, o que é compatível com as ~28 mil conexões/dia
   no Valkey.
3. **O B.I. varre 380 mil linhas a cada 5 minutos e derrama em disco.**
   - `refresh_bi_daily_series` roda em todo ciclo do `maintenance-worker` e recalcula 3
     dias (`DEFAULT_RECENT_DAYS = 3`).
   - `bi/sources/historical.py` filtra `HistoricalSaleItem` por
     `sale__occurred_at__range`.
   - O único índice de data (`backstage_hs_src_when_idx`) tem `source` na frente e
     nunca foi usado (0 scans).
   - A janela recente não tem histórico importado (o import é passado), e mesmo assim o
     scan acontece: 293/dia, batendo com 288 ciclos/dia.
   - Os ~588 arquivos temporários/dia são o hash join com `work_mem` de 2 MB.
4. **`orderman_order` não tem índice em `created_at`.** Os índices conferidos são `id`,
   `uuid`, `ref`, `channel_ref`, `session_key`, `external_ref` e `status`. Três leitores
   filtram por data:
   - `bi/sources/orderman.py` (`order__created_at__range`);
   - `craftsman/contrib/demand/backend.py` (`order__created_at__date__gte`);
   - `shop/services/fomo.py:sold_today` (`order__created_at__date=`, **por SKU**).

   Resultado: 15 mil seq scans/dia em pedidos e 13 mil em itens. Com 6 mil pedidos custa
   pouco; com o go-live, cresce linear. O `__date` também impede índice simples: precisa
   virar `__range` de datetimes.
5. **Cascata de deployments.** Cada tag publicada dispara `deploy_on_push`. Um run que
   publica 10 imagens cria 10 deployments, e 9 são cancelados (184 em 7 dias). O job
   `release` (check, migrate, setup_groups, bootstrap) roda em cada um que chega ao
   passo de deploy, e os 39 erros de 7 dias vieram todos dele.
6. **Leitura pública sem cache nenhum.** `menu/`, `home/` e `products/` saem com
   `cache-control: private` e `Vary: Cookie`, e o GET anônimo seta `csrftoken`. A
   Cloudflare dá BYPASS em tudo, e cada visitante recalcula o cardápio inteiro.
7. **Hairpin dos BFFs.** Toda chamada BFF → Django refaz TLS e passa pela borda. O custo
   exato não foi medido de fora; ver P4 para a prova.
8. **Laços curtos consultando o banco sem parar.** O `directive-worker` roda a cada 1–2 s
   e o `ifood_poll` a cada 30 s. Somado aos 100 mil scans/dia em `shop_channel` (6
   linhas), isso sugere lookup de canal sem cache em caminho quente. *Causa não
   identificada*: precisa de `pg_stat_statements` (P0).

## 4. Metas (SLO simples)

Medidas de fora (Brasil), 20 amostras, p95, fora do horário de deploy.

| Meta | Hoje | Alvo |
|---|---|---|
| `menu.` `/` TTFB | 2,10–3,00 s | **≤ 1,2 s** |
| `api./api/v1/storefront/home/` e `menu/` | 0,93–1,88 s | **≤ 0,6 s** |
| `api./ready/` − `api./health/` | +0,1 a +0,36 s | **≤ +0,1 s** |
| Push no `main` → no ar | p50 5,5 min · p90 10 min | **p50 ≤ 5 min · p90 ≤ 7 min** |
| Deployments por run do `deploy-images` | até 11 | **1** |
| Arquivos temporários do Postgres por dia | ~3 GB | **≤ 100 MB** |
| Seq scans/dia em tabela com > 5 mil linhas | 13–15 mil (`order`/`orderitem`), 293 × 380 mil (`historicalsaleitem`) | **≤ 100** |
| Ciclo do `maintenance-worker` | não medido | **≤ 60 s** (log por ciclo) |

## 5. Propostas, ordenadas por impacto × esforço

| # | Proposta | Impacto | Esforço | Custo DO |
|---|---|---|---|---|
| P0 | Ligar observabilidade de consulta | habilita tudo | XS | 0 |
| P1 | Health checks baratos | alto | S | 0 |
| P2 | B.I. e pedidos sem scan completo | alto | S–M (índice no Core) | 0 |
| P5 | Um deployment por run | médio (deploy e estabilidade) | S | 0 |
| P6 | Cache da leitura pública do cardápio | alto (loja) | M | 0 (usa o Valkey ocioso) |
| P4 | BFF → Django pela rede interna | médio | M | 0 |
| P3 | Estatística do planner em dia | baixo a médio | XS | 0 |
| P7 | Medir CPU e memória antes de mexer em processo | — | XS | 0 |
| P8 | Conexões do Valkey reaproveitadas | baixo | S | 0 |
| P9 | Consolidação dos Nuxt: o que medir antes | risco de piora | — | −15 a −30 |

Nenhuma proposta cria componente na DO.

### P0 · Observabilidade de consulta

- **O que:** `CREATE EXTENSION pg_stat_statements` no banco `shopman` e
  `log_min_duration_statement = 500` via `doctl databases configuration update`.
- **Por que primeiro:** hoje o gargalo 8 e a origem exata dos scans dos gargalos 3 e 4
  são inferência de código e contador. Com a extensão, viram consulta nomeada com tempo
  total.
- **Risco:** mínimo. O overhead documentado do `pg_stat_statements` é de poucos
  por cento; o log de consulta lenta pode expor parâmetros com PII, então manter o log
  só na DO e não exportar.
- **Prova:** `SELECT query, calls, total_exec_time FROM pg_stat_statements ORDER BY 3
  DESC LIMIT 20` após 24 h, anexado ao PR de P2.

### P1 · Health checks baratos

- **O que:**
  1. Nos 9 Nuxt, o `health_check.http_path` sai de `/` para uma rota Nitro que não chama
     o Django. O `marketing-nuxt` já tem `server/routes/health/live.get.ts`; levar para
     o `operator-kit` e criar a do storefront.
  2. No `web`, o health check da DO vai para `/health/` (liveness). O `/ready/` fica para
     o Alpha Smoke e o gate de deploy.
  3. No `/ready/`, a checagem de migrations passa a ser calculada **uma vez por
     processo**. As migrations só mudam com deploy, e o `release` roda `migrate` antes de
     o container subir.
- **Ganho esperado:** ~5.760 chamadas/dia a menos em `home/` e ~8.640 construções/dia a
  menos do grafo de migrations, no único processo do `web`. Menos conexões no Valkey.
- **Risco:** baixo. Um `web` com banco fora deixa de ser reiniciado pela DO, o que é o
  comportamento certo, porque reiniciar não cura banco. O alerta continua pelo smoke.
- **Prova antes/depois:**
  - `django_migrations.seq_scan/dia`: 10.263 → < 100.
  - Valkey `total_connections_received/dia`: ~28 mil → queda visível.
  - Contagem de `GET /api/v1/storefront/home/` com user-agent da DO no log: ~5.760/dia → 0.
  - TTFB da home (§4) antes e depois.

### P2 · O B.I. e o pedido sem índice de data

- **O que:**
  1. `refresh_bi_daily_series`: a fonte histórica **não é lida quando a janela está fora
     do intervalo importado** (min/max de `occurred_at` guardados no `ImportBatch`, ou um
     `EXISTS` barato). Quando for lida, o filtro usa um índice só em `occurred_at`, ou o
     índice composto ganha `source` fixado na consulta.
  2. `orderman_order` ganha índice em `created_at`. **É migração no Core** e segue a
     regra do CLAUDE.md: é índice, não campo, sem dado contextual, e há três consumidores
     reais citados no gargalo 4. Discutir no PR com esta evidência.
  3. `fomo.sold_today` e `demand/backend.py` trocam `__date=` por `__range` de datetimes
     no fuso da loja, porque sem isso o índice não serve.
  4. Avaliar `work_mem` de 8 MB para a sessão do B.I. (`SET LOCAL`), não global. Com 25
     conexões e 1 GB de RAM, subir o global é arriscado.
- **Ganho esperado:** fim dos ~3 GB/dia de arquivos temporários, ciclo do
  `maintenance-worker` mais curto e folga para a entrega do Marketing no mesmo worker.
  Isso sustenta a decisão de não criar worker novo
  ([WP-DO-ECONOMIA E3](WP-DO-ECONOMIA-2026-09.md#e3--ifood-poll-worker-para-dentro-de-um-worker-existente)).
- **Risco:** baixo a médio. Índice em tabela de 6 mil linhas cria em milissegundos, mas
  usar `CREATE INDEX CONCURRENTLY` (`AddIndexConcurrently`) já prepara para o volume do
  go-live. A troca de `__date` por range precisa de teste de borda de fuso (meia-noite
  em `America/Sao_Paulo`).
- **Prova antes/depois:**
  - Deltas de 24 h de `pg_stat_user_tables.seq_scan` em `orderman_order`,
    `orderman_orderitem` e `backstage_historicalsaleitem`.
  - `pg_stat_database.temp_bytes` em 24 h.
  - `EXPLAIN` das três consultas no PR.
  - Duração do ciclo no log do worker.

### P3 · Estatística do planner em dia

- **O que:** `ANALYZE` depois de import em massa. O comando de import do B.I. chama
  `ANALYZE` nas tabelas que escreveu, e o release pode rodar `ANALYZE` das tabelas com
  `n_mod_since_analyze` alto.
- **Por que:** `orderman_orderitem` com `n_live_tup` 66 contra 12.406 reais, e as
  históricas com 0 contra 380 mil. O planner escolhe plano para tabela vazia.
- **Prova:** `n_live_tup` ≈ `count(*)` e `EXPLAIN` com estimativas próximas do real.

### P4 · BFF → Django pela rede interna

- **O que:** `NUXT_DJANGO_BASE_URL` passa a usar `${web.PRIVATE_URL}` (HTTP interno do
  App Platform) em vez de `https://api.boulangerie.com.br`.
- **Riscos que precisam ser resolvidos antes (médio):**
  - `DJANGO_SECURE_SSL_REDIRECT` com HTTP interno gera loop de redirect se o BFF não
    enviar `X-Forwarded-Proto: https`.
  - `DJANGO_ALLOWED_HOSTS` e `CSRF_TRUSTED_ORIGINS` precisam do `Host` que o BFF envia.
    O proxy deve preservar o host público.
  - `DOORMAN_TRUSTED_PROXY_DEPTH`: rate limit e auditoria de login usam IP do cliente,
    e o número de saltos muda.
  - O cookie de sessão cross-subdomínio (`.boulangerie`) segue funcionando porque o
    navegador continua falando com o host público. Só o salto BFF → Django muda.
  - Fazer primeiro num app de operador de baixo risco (`bi-nuxt`), depois no storefront.
- **Prova antes/depois:** de dentro do container (`doctl apps console storefront-nuxt`),
  `curl -w` no `home/` pela URL pública e pela privada, 20 vezes cada. Depois, TTFB da
  home de fora (§4).

### P5 · Um deployment por run, e não dez

- **O que:** desligar `deploy_on_push` das tags e fazer o `deploy-images.yml`, no job
  `manifest`, disparar **um** deployment depois de todas as imagens publicadas. A forma
  preferida é `doctl apps update` com o spec apontando para `tag-<sha>`/digest imutável,
  que casa com a correlação por digest do #573 e torna o rollback um `apps update` para o
  sha anterior. A forma mínima é `doctl apps create-deployment`. Junto:
  - reduzir o cache do Actions (hoje 12,28 GB, acima dos 10 GB): `mode=min` nas surfaces,
    ou `scope` compartilhado para as 8 surfaces que dividem `node:22-alpine` e o
    `operator-kit`.
- **Ganho esperado:** rajadas de 9–11 deployments viram 1. O `release` roda uma vez por
  merge. A cauda p90 de 10 min cai, e há menos janelas de erro como as 33 de 16/09.
- **Risco:** baixo a médio. O token do Actions (`DIGITALOCEAN_ACCESS_TOKEN`) precisa de
  escopo `app:update`, e a memória registra dois tokens: o de deploy é mínimo. Também
  exige ajustar o Alpha Smoke, que hoje espera o deployment criado pelo push.
- **Prova antes/depois:** deployments por run = 1 em 7 dias (`list-deployments`
  agrupado); push → no ar p50/p90 recalculado com o mesmo script deste WP; contagem de
  `CANCELED` em 7 dias: 184 → ~0.

### P6 · Cache da leitura pública do cardápio

- **O que:** separar no `menu/` e no `products/` o que é **catálogo** (nome, foto, preço,
  coleção), que muda por ação do gestor, do que é **disponibilidade**, que muda por
  venda e estoque.
  - O catálogo vai para cache no Valkey, invalidado pelos signals de catálogo que já
    alimentam o SSE (`_sse_emitters`).
  - A disponibilidade continua por request, ou por SSE.
  - O GET anônimo deixa de setar `csrftoken`, que só é necessário em mutação.
- **Por que no Valkey:** ele tem 413 MB livres e custa US$ 15 de qualquer jeito. Dar a
  ele trabalho útil é também o argumento de mantê-lo, ver
  [WP-DO-ECONOMIA E5](WP-DO-ECONOMIA-2026-09.md).
- **Risco:** médio. Cache de disponibilidade seria promessa vencida ("o dado que falta
  fecha a promessa"), e por isso **só o catálogo** vai para cache.
- **Prova antes/depois:** TTFB p95 de `menu/`, `home/` e da home SSR (§4); contagem de
  queries por request no teste de budget do storefront.

### P7 · Medir CPU e memória antes de mexer em processo

- **O que:** obter as métricas que hoje não temos, com o painel *Insights* ou um token
  com `monitoring:read`, antes de qualquer decisão sobre o `daphne` de processo único
  (mais workers ASGI, `uvicorn` com 2 processos) ou sobre o tamanho do `web`.
- **Por que:** os alertas de CPU > 80% e memória > 85% existem só para o `web`, e nenhum
  disparo foi consultado. Mudar de processo às cegas é chute.
- **Prova:** série de 7 dias de CPU e memória por componente anexada a este WP.

### P8 · Conexões do Valkey reaproveitadas

- **O que:** depois de P1, medir de novo `total_connections_received`. Se continuar alto,
  configurar `CONNECTION_POOL_KWARGS` e conferir que os workers e o `django-eventstream`
  reutilizam conexão em vez de abrir uma por ciclo.
- **Prova:** conexões/dia (hoje ~28 mil) e latência do `_check_cache`.

### P9 · Consolidação dos Nuxt: o que medir antes

A proposta de custo
[E2](WP-DO-ECONOMIA-2026-09.md#e2--os-8-nuxt-de-operador-em-um-único-service) coloca 8
apps de operador numa vCPU. Antes de aprovar, este WP exige:

- RSS e CPU de cada Nitro ocioso e com SSE aberto (KDS e PDV mantêm conexão longa).
- TTFB das shells de operador depois da consolidação, sem piorar o baseline de
  0,33–0,67 s.
- Um teste de deploy mostrando quanto tempo KDS e PDV ficam sem SSE quando qualquer app
  de operador é publicado. Hoje a mudança num app não reinicia os outros.
- P1 aplicado antes: 8 health checks em `/` a cada 10 s num único processo seriam
  ~69 mil renders de SSR/dia.

## 6. Ordem de execução sugerida

1. **P0 + P1 + P3**, num PR pequeno cada. Nenhum toca regra de negócio.
2. **P2**, com a evidência do P0 anexada.
3. **P5**, junto com a fase 1 de custo (E1, E4), porque os dois mexem no pipeline e no spec.
4. **P6 e P4**, medindo a loja antes e depois.
5. **P7** em paralelo, quando houver acesso a métricas. **P9** só depois de P1 e P7.

## 7. O que não foi possível medir, e por quê

| Item | Por quê |
|---|---|
| CPU e memória por componente | sem `monitoring:read`; `doctl apps` não expõe métrica |
| Latência de servidor por endpoint | sem APM, `pg_stat_statements` não instalado, log de consulta lenta desligado |
| Volume real de requests por endpoint | exigiria ler logs de acesso, que carregam PII; não foi feito |
| Custo do hairpin BFF → Cloudflare → Django | só mensurável de dentro do container (`apps console`) |
| Latência vista do navegador (LCP, hidratação) | fora do escopo de curl; o harness Playwright do storefront pode medir |
| `make marketing-capacity` | não rodado nesta frente; citado o relatório de 09/09 (SQLite, pico 82,6 MiB) |
| p95 com 20 amostras | foram 5 amostras por URL, para não gerar carga; o SLO define 20 na prova |
