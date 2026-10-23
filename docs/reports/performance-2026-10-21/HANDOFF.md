# Handoff — Avaliação completa de desempenho e capacidade do Shopman

Data: 21/10/2026, ~13h UTC (10h BRT).
Origem: sessão DSH (DeepSeek Harness), que fez a medição externa e o profile local.
Destino: Codex/Claude com acesso ao painel da DigitalOcean.
Objetivo: executar a avaliação de desempenho completa, com os dados que só o painel tem, e fechar a decisão de capacidade e custo sem mudar a stack.

## 0. Papel e postura

Você assume a avaliação. O trabalho já feito está na seção 3 e não precisa ser refeito, exceto para confirmar com uma amostra pequena. O que falta é o que exige painel, logs, banco e métricas: CPU, memória, tráfego, cache hit ratio, consultas lentas, restarts e o experimento controlado de tamanho.

Regra de ouro: **não comece comprando CPU**. Primeiro leia CPU/RAM/tráfego. Se a CPU no pico estiver abaixo de 60%, o problema é I/O, cache ou código, e comprar CPU não resolve. Se estiver em 100% com fila, aí sim.

## 1. Regras invioláveis

- **Somente leitura primeiro.** Fase A não altera nada. Fase B só muda tamanho de serviço, com aprovação explícita do dono.
- **Não rodar teste de carga em horário de funcionamento.** A loja abre 9h; use a janela de 06h30 a 08h BRT ou depois do fechamento. Concórdia máxima 4, no máximo 8 requisições por nível, com aborto em 5xx ou p95 acima de 8 s.
- **Uma variável por vez.** Nunca mudar código e tamanho no mesmo teste.
- **Spec vivo, nunca o blueprint do repo.** O arquivo .do/app.alpha-subdomains.yaml é referência e pode estar velho. Capture o spec real com doctl apps spec get, edite, valide com doctl apps propose, aplique com doctl apps update. Preserve SECRET e EV[...].
- **Sem segredos no relatório, no chat ou em log.** Não imprimir variáveis de ambiente sensíveis.
- **Sem escrita no banco.** Use BEGIN READ ONLY. pg_dump, se precisar, só pela conexão direta (porta 25060, banco shopman), nunca pelo pool (25061).
- **Sem mudar a stack.** Python/Django, Nuxt/Nitro, SSR, SSE, Postgres e Valkey ficam. O que se avalia é capacidade, cache, consultas e configuração.
- **Código só em worktree.** O checkout principal é compartilhado. Se for implementar correção, git worktree primeiro, um branch por frente, PR.
- **Fato com evidência.** Cada número no relatório precisa de comando, arquivo:linha ou captura do painel. O que não foi medido deve ser dito como não medido.

## 2. Ambiente e topologia

Produção única: app **shopman-nelson**, região **nyc**. Alpha e staging estão mortos desde 01/09/2026. O App ID aparece no header x-do-app-origin como 4d1da99e-d41a-44b0-ad32-d354ec200758; confirme com doctl apps list.

Roteamento por host:

| Host | Serviço | Plano atual | US$/mês |
|---|---|---|---:|
| www.nelsonboulangerie.com.br | storefront-nuxt | apps-s-1vcpu-1gb-fixed | 10 |
| api.boulangerie.com.br /api/v1/backstage | web-operator | apps-d-1vcpu-2gb | 39 |
| api.boulangerie.com.br /api/v1 (storefront) | web-storefront | apps-s-1vcpu-1gb | 12 |
| api.boulangerie.com.br / (resto) | web-operator | apps-d-1vcpu-2gb | 39 |
| admin.boulangerie.com.br | web-operator | apps-d-1vcpu-2gb | 39 |
| central, pdv, kds, gestor, prod | operator-floor | apps-s-1vcpu-0.5gb | 5 |
| mkt, bi, compras | operator-office | apps-s-1vcpu-0.5gb | 5 |
| status.boulangerie.com.br | status-nuxt (externo) | n/a | 0 |
| img.nelsonboulangerie.com.br | storefront-nuxt, rewrite /img/ | igual www | 0 |

Workers: directive-worker, maintenance-worker e ifood-poll-worker, cada um apps-s-1vcpu-0.5gb (5 cada, 15 no total). O job de release só roda no deploy.

Total dos serviços de aplicação: **~US$ 86/mês**. Banco gerenciado e Valkey ficam fora dessa conta.

Fatos de rede já medidos: Cloudflare em GRU, origem em nyc, piso de rede de ~0,25 s (api./health/live). O health check do Nuxt bate em /health/live, não renderiza a home. O /ready/ completo não é mais o probe de plataforma.

## 3. O que já foi medido (21/10/2026)

Método: curl com 5 amostras por endpoint, p50; Server-Timing do Django; Chrome 156 headless via Playwright (390x844 na loja, 1280x800 no operador); profile local com sqlite e seed real (131 produtos, 4.099 pedidos). Tudo GET, nenhuma escrita.

### 3.1 TTFB por superfície

| Endpoint | p50 quente | p50 após 30 s (borda fria) |
|---|---:|---:|
| www./ (home) | 0,63 s | 1,26 s |
| www./menu | 0,44 s | 0,78 s |
| www./produto/FENDU | 1,67 s | 3,52 s (primeira carga) |
| www./sacola | 0,35 s | 0,62 s |
| www./busca | 0,39 s | 0,79 s |
| api./storefront/home/ | 0,84 s | 0,81 s |
| api./storefront/menu/ | 1,17 s | 1,10 s |
| api./storefront/catalog/ | 0,92 s | 0,92 s |
| api./storefront/products/FENDU/ | 1,55 s | 1,55 s |
| central. | 0,44 s | 0,40 a 0,70 s |
| pdv. | 0,42 s | idem |
| kds. | 0,35 s | idem |
| gestor. | 0,43 s | idem |
| prod. | 0,41 s | idem |
| mkt. | 0,38 s | idem |
| bi. | 0,43 s | idem |
| compras. | 0,25 s | idem |
| status. | 0,15 s | 0,16 s |
| admin./admin/login/ | 0,34 s | 3,98 s (primeira rota) |

### 3.2 Server-Timing (mediana, ms)

| Endpoint | projection | availability | db | cache | Leitura |
|---|---:|---:|---:|---:|---|
| home/ | 630 a 740 | 71 | 86 a 118 | 55 a 84 | 85% fora do SQL |
| menu/ | 850 a 1.100 | 210 a 284 | 150 a 175 | 28 a 43 | 82% fora do SQL |
| catalog/ | 700 a 877 | 180 a 293 | 145 a 315 | 23 a 37 | 79% fora do SQL |
| products/FENDU/ | 1.295 a 1.507 | 70 a 142 | 260 a 378 | 60 a 90 | 78% fora do SQL |
| shell/ | 113 a 124 | 0 | 6 a 9 | 39 a 43 | barato |
| cart/ | 27 a 35 | 0 | 0 | 25 a 33 | barato |
| checkout/ | 64 a 158 | 0 | 2 a 3 | 34 a 65 | barato |
| site/ | 168 a 250 | 0 | 6 a 11 | 95 a 149 | Redis domina |
| 404 de produto | 80 a 120 | 0 | 3 a 12 | 42 a 80 | piso alto |

Observação: os estágios são aninhados. projection inclui availability; db é a soma do SQL do request; cache é o custo do Redis.

### 3.3 O achado principal: mesmo código, 2x mais rápido no serviço dedicado

O host admin. cai no web-operator, que roda a mesma imagem Django e o mesmo banco, mas em apps-d-1vcpu-2gb. O host api. (storefront) cai no web-storefront, apps-s-1vcpu-1gb.

| Endpoint | api. shared 1 GB | admin. dedicado 2 GB | Ganho |
|---|---:|---:|---:|
| catalog/ | 734 ms | 364 ms | 2,0x |
| menu/ | 864 ms | 424 ms | 2,0x |
| products/FENDU/ | 1.391 ms | 692 ms | 2,0x |

O db foi parecido ou maior no dedicado. A diferença é CPU/processo. Ressalva: o A/B mudou CPU e RAM ao mesmo tempo. O teste de tamanho precisa isolar.

### 3.4 Capacidade medida (catalog/, rota privada, sem cache de borda)

| Serviço | Concorrência | p50 | Throughput |
|---|---:|---:|---:|
| web-storefront shared | 1 | 1,05 s | 0,84 req/s |
| web-storefront shared | 4 | 3,97 s | 1,03 req/s |
| web-operator dedicado | 1 | 0,66 s | 1,30 req/s |
| web-operator dedicado | 4 | 1,87 s | 1,97 req/s |

O SSR da loja (www./menu) foi de 0,49 s com 1 concorrente para 1,03 s com 4.

### 3.5 Profile local

| Caminho | Tempo local | Consultas |
|---|---:|---:|
| build_catalog | 21 ms | 38 |
| build_product_detail | 27 ms | 96 |
| projection_data | 0,3 ms | 0 |

O código é rápido. O ambiente de produção amplifica. Não reescrever a projeção antes de cortar idas, cachear e escolher o core certo.

### 3.6 Front

| Rota | Peso 1ª visita | JS | LCP 2ª carga |
|---|---:|---:|---:|
| www./ | 1.518 KB | 342 KB | 1,14 s |
| www./menu | 709 KB | 353 KB | 0,58 s |
| www./produto/FENDU | 528 KB | 353 KB | 1,87 s |
| www./sacola | 518 KB | 343 KB | 0,61 s |
| www./busca | 524 KB | 349 KB | 0,68 s |

Operador: 323 a 579 KB de JS; FCP de 0,5 a 0,8 s na segunda carga e 1,5 a 3,0 s na primeira. CLS episódico de 0,75 no /menu em 1 de 3 execuções, causado por DIV.shop-stack-section inserido por volta de 4 s.

Imagens: /img/home/*.webp somam ~1.001 KB na home e saem com cache-control private e cf-cache-status BYPASS. /img/products/* sai public, immutable e HIT. A regra de routeRules cobre só /img/products/**. Há 4 srcset no HTML, mas o hero mobile baixa o arquivo grande (312 KB).

### 3.7 Achados de código já confirmados no HEAD

- A PDP não tem gêmea pública: toda visita a produto passa pelo Django e constrói a projeção. home, shell e catalog já têm gêmea (shopman/storefront/api/public_cache.py e surfaces/storefront-nuxt/server/utils/djangoProxy.ts).
- TTL das gêmeas: public, max-age=0, s-maxage=30, stale-while-revalidate=30, stale-if-error=120.
- PDP: ~96 consultas no profile local, ~60 no orçamento de 18/10; o db no ar é 260 a 380 ms.
- Cache Redis: 10 a 50 ms por chamada, 2 a 4 chamadas por request. O backend já é SharedPoolRedisCache; o custo parece ser RTT/TLS, não handshake por request.
- KDS: build_kds_board ainda resolve a fonte por ticket no board (shopman/backstage/projections/kds.py:384), 5 + N consultas; a versão em lote existe em :625.
- Produção: build_production_board chama _production_suggestions (shopman/backstage/projections/production.py:1366), 2 consultas por ficha.
- OrderItem.sku continua db_index=False (packages/orderman/shopman/orderman/models/order.py:381); a demanda filtra por ele.
- KDSTicket não tem índice em status/completed_at (Meta em shopman/backstage/models/kds.py:175).
- Continuum: SHOPMAN_CONTINUUM_CATALOG_SNAPSHOT_ENABLED=true e NUXT_PUBLIC_CONTINUUM_CATALOG_ENABLED=true; shadow=false. O /menu nasce do snapshot e converge no canônico.
- O que já foi corrigido e não deve ser mexido: AP-1/AP-2/AP-3, check_alerts em 2 consultas, dashboard em 2, POS com orçamento de 45, build_order_queue e two_zone_queue constantes, health checks baratos.

## 4. Perguntas que a avaliação precisa responder

1. Qual é o pico real de CPU e memória de web-storefront, storefront-nuxt, operator-floor e operator-office em 7 dias, e em que horário?
2. Qual é o pico de requests/min de origem e a taxa de HIT da Cloudflare por host?
3. Qual é o p95/p99 real por endpoint, não só o p50 de madrugada?
4. A CPU do web-storefront fica em 100% no pico? A memória passa de 85%? Há restarts/OOM?
5. O db está saudável: consultas lentas, seq scans, conexões, pool, estatísticas do planner?
6. O Redis é RTT ou conexão? Qual o custo por request?
7. O ganho de 2x do dedicado se confirma no serviço certo, e qual é o tamanho mínimo que entrega?
8. Qual é o conjunto mais barato de mudanças para bater o alvo de p95, e qual o custo mensal?
9. O que é risco de pico e o que é risco de latência por request?
10. O que não vale a pena comprar ou otimizar?

## 5. Fases de execução

### Fase A — somente leitura (1 dia)

A1. Inventário: doctl apps list, doctl apps get, doctl apps spec get. Confirmar serviços, tamanhos, instance_count, região, alerts e envs não sensíveis. Comparar com a tabela da seção 2.

A2. Painel/Insights: CPU e memória de 7 dias para web-storefront, web-operator, storefront-nuxt, operator-floor, operator-office, com pico e média. Restart count, OOM, deploy frequency. Exportar os gráficos ou os números.

A3. Logs de runtime: coletar 1 hora de pico do logger shopman.storefront.continuum (storefront_catalog_observation) com query_count, projection_ms, availability_ms, personalization_ms, db_ms, cache_ms, cache_calls, response_bytes, status. Calcular p50/p95 por path. Procurar erros 5xx e timeouts.

A4. Cloudflare: requests por host, cache hit ratio por path, p95 TTFB, status codes, top paths. Separar anônimo de logado se possível.

A5. Banco: com psql em BEGIN READ ONLY, consultar pg_stat_database, pg_stat_user_tables, pg_stat_user_indexes, pg_stat_activity, pg_settings (work_mem, max_connections), e pg_stat_statements se existir. Verificar n_live_tup e last_analyze das tabelas quentes. Confirmar índices de OrderItem.sku e KDSTicket.

A6. Valkey: INFO, commandstats, clients, latency, memória, conexões recebidas. Comparar com o custo de cache do Server-Timing.

A7. Repetir o A/B api. contra admin. em 3 horários (manhã, almoço, noite), 3 amostras por endpoint, para confirmar o 2x e separar efeito de horário.

A8. Rampa leve (se autorizado e fora do horário): catalog/ e products/FENDU/ com concorrência 1 e 4, 6 requisições por nível, p50/p95, aborto em 5xx ou p95 acima de 8 s.

A9. Relatório da Fase A com os fatos, sem recomendação de compra ainda.

### Fase B — experimento de capacidade (com aprovação do dono)

B1. Teste de RAM: web-storefront de apps-s-1vcpu-1gb (12) para apps-s-1vcpu-2gb (25), +13/mês. Uma hora no mesmo horário, mesma rampa. Se o p50 cair ~2x, era RAM; manter o plano mais barato.

B2. Se B1 não mudar: web-storefront para apps-d-1vcpu-2gb (39), +27/mês. Repetir a medição. O A/B já indica 2x; aqui se confirma no serviço certo.

B3. Se a CPU ainda saturar no pico: avaliar réplica. Antes, verificar se a aplicação é stateless para sessão (Redis), se o SSE faz fanout por Redis e se o pool do banco aguenta (max_connections 25, pool 5 por instância). Só então +1 instância.

B4. operator-floor: se memória acima de 85% ou restarts, subir de 0.5 GB para 1 GB (+7/mês). Isso também habilita scaling manual, que o plano de 0.5 GB não permite.

B5. storefront-nuxt: só mexer se o SSR saturar no pico. O plano atual é fixed e não escala; para réplica, subir para apps-s-1vcpu-1gb (12) e então +1 réplica (+12).

B6. Relatório de decisão: cenário recomendado, delta mensal, ganho medido, risco e rollback.

### Fase C — código, só se aprovado

C1. Gêmea pública da PDP: StorefrontPublicProductView(PublicEdgeCacheMixin, StorefrontProductView), s-maxage 30 a 60, e a mesma recusa de cookie/query string. O BFF manda para a gêmea só GET sem sessionid. O cliente sobrepõe favoritos e quantidade na sacola. É o maior ganho isolado: tira a PDP da origem para a maioria das visitas.

C2. Alternativa de menor risco: cachear build_product_detail por (sku, canal) por 30 a 60 s no servidor e aplicar favoritos/sacola por cima. Corta CPU, não a ida à borda.

C3. TTL das gêmeas de home/catalog/shell de 30 para 180 ou 300 s, com stale-while-revalidate. Manter disponibilidade em endpoint curto. Medir hit ratio antes e depois.

C4. PDP: bater as ~96 consultas para ~15, em lote. Economia estimada de 250 a 400 ms.

C5. Cache local por processo, TTL 10 a 30 s, para Shop.load e ChannelConfig, que hoje pagam 2 a 3 idas ao Redis por request. Economia de 50 a 100 ms.

C6. Imagens: /img/** com public e max-age (ou nomes versionados + immutable) e variantes responsivas 480/960/1440. Primeira visita cai ~650 KB.

C7. KDS e Produção: usar a versão em lote de _resolve_ticket_sources no board e lotear _production_suggestions. Índices em OrderItem.sku e KDSTicket(status, completed_at). Só depois de medir o pico do operador.

C8. Toda mudança com teste de orçamento de consulta, sem mudar semântica, em worktree e PR.

## 6. Protocolo de medição (comandos)

Server-Timing de um endpoint:

~~~bash
curl -sS -o /dev/null -D - \
  "https://api.boulangerie.com.br/api/v1/storefront/catalog/" \
  | grep -i server-timing
~~~

A/B shared contra dedicado (mesmo código, mesmo banco):

~~~bash
for host in api admin; do
  curl -sS -o /dev/null -D - \
    "https://$host.boulangerie.com.br/api/v1/storefront/products/FENDU/" \
    | grep -i server-timing
done
~~~

Rampa mínima (somente fora do horário, concorrência 4, 6 requisições):

~~~bash
mkdir -p /tmp/ramp
seq 1 6 | xargs -P 4 -I{} sh -c '
  curl -sS -o /dev/null --max-time 30 \
    -w "%{http_code} %{time_starttransfer} %{time_total}\n" \
    "https://api.boulangerie.com.br/api/v1/storefront/catalog/"
' | sort
~~~

Spec vivo e experimento de tamanho:

~~~bash
doctl apps list
doctl apps spec get "$APP_ID" > /tmp/spec-live-before.yaml
# editar apenas instance_size_slug do serviço web-storefront
doctl apps propose --spec /tmp/spec-live-before.yaml --app "$APP_ID"
doctl apps update "$APP_ID" --spec /tmp/spec-live-before.yaml
# medir 1 hora, no mesmo horário e com a mesma rampa
# rollback: reaplicar /tmp/spec-live-before.yaml
~~~

Critérios de sucesso do experimento:

- PDP p50 abaixo de 0,85 s e p95 abaixo de 1,5 s.
- catalog p50 abaixo de 0,45 s e p95 abaixo de 0,8 s.
- Nenhum 5xx, nenhum restart, memória abaixo de 85%.
- CPU abaixo de 70% com concorrência 4.
- Se não bater, rollback e manter o plano anterior.

Custo do experimento: a App Platform cobra por segundo. Uma hora de apps-d-1vcpu-2gb custa cerca de US$ 0,05; um dia, cerca de US$ 1,30. O risco financeiro do teste é irrelevante.

## 7. Custos e cenários

Preços atuais da tabela oficial da App Platform (docs.digitalocean.com/products/app-platform/details/pricing, atualizada em 13/07/2026):

| Plano | vCPU | RAM | US$/mês |
|---|---|---:|---:|
| apps-s-1vcpu-0.5gb | 1 shared | 0.5 GB | 5 |
| apps-s-1vcpu-1gb | 1 shared | 1 GB | 12 |
| apps-s-1vcpu-1gb-fixed | 1 shared | 1 GB | 10 |
| apps-s-1vcpu-2gb | 1 shared | 2 GB | 25 |
| apps-s-2vcpu-4gb | 2 shared | 4 GB | 50 |
| apps-d-1vcpu-1gb | 1 dedicated | 1 GB | 34 |
| apps-d-1vcpu-2gb | 1 dedicated | 2 GB | 39 |
| apps-d-2vcpu-4gb | 2 dedicated | 4 GB | 78 |

Cenários:

| Cenário | Mudança | Delta/mês | Efeito esperado |
|---|---|---:|---|
| A | só grátis (PDP, TTL, lote, imagens, Redis) | 0 | -30 a -60% de CPU de origem; PDP anônima em 0,3 a 0,4 s |
| B | web-storefront 2 GB shared | +13 | isola RAM; pode entregar parte do 2x |
| C | web-storefront dedicado 2 GB | +27 | 2x medido no A/B |
| D | C + operator-floor 1 GB | +34 | estabilidade do operador |
| E | D + 1 réplica dedicada | +73 | pico acima de 2 req/s |
| F | E + réplica do storefront-nuxt | +87 | SSR no pico |

Recomendação de sequência: A, depois B, depois C, depois D. E e F só com o pico medido. Teto sugerido: +34/mês (US$ 120 de serviços) antes de qualquer réplica.

Árvore de decisão:

~~~text
Pico de CPU do web-storefront > 80%?
├── não: o gargalo é I/O/cache. Não comprar CPU. Aplicar A.
└── sim: RAM > 85% ou restarts?
          ├── sim: B (+13). Medir.
          └── não: C (+27). Medir.
                    Ainda satura no pico? → réplica (+39) ou 2 vCPU.
~~~

## 8. Entregáveis

1. Relatório de avaliação em docs/reports/performance-2026-10-21/ (ou diretório equivalente no seu worktree), com:
   - métodologia e evidências;
   - tabela por superfície: TTFB p50/p95, FCP/LCP, peso, CPU, memória, erros;
   - breakdown do servidor: projection, availability, db, cache, consultas;
   - curva de capacidade e gargalo nomeado;
   - comparação shared contra dedicado;
   - custo por cenário e recomendação;
   - riscos, rollback e próximos passos.
2. Memo de uma página para o dono: comprar ou não, quanto, e por quê.
3. Spec diff proposto (sem aplicar) e o comando de rollback.
4. Scripts de medição reproduzíveis.
5. Se houver código: PR em worktree, com testes de orçamento de consulta e sem mudança de semântica.

## 9. Critérios de aceite

- Responde com número: está razoável? onde está o gargalo? qual o conjunto mais barato para bater o alvo? quanto custa? qual o risco?
- Todo número tem evidência: comando, arquivo:linha ou captura.
- Nenhuma mudança sem aprovação; nenhum segredo exposto.
- O relatório distingue fato, inferência e não medido.
- O experimento de tamanho tem antes/depois, mesmo horário, uma variável por vez, rollback pronto.
- O relatório final cabe em uma página para o dono e tem anexos técnicos.

## 10. Perguntas ao dono (antes da Fase B)

1. Qual é o pico real: visitas/min, pedidos/hora, usuários concorrentes?
2. Qual é o teto de custo mensal aceitável para capacidade?
3. Autoriza o teste B (+13/mês) e, se necessário, C (+27/mês), com rollback?
4. Quer que a Fase C (código) entre agora ou só depois do relatório?

## 11. Referências

- docs/plans/WP-PERFORMANCE-2026-09.md (baseline de 17/09, topologia e banco).
- docs/reports/go-live-acceleration-20260929/01-perf-storefront.md.
- docs/reports/go-live-acceleration-20260929/02-perf-operador.md.
- docs/reports/go-live-acceleration-20260929/16-medicao-pos-p3-p8-p4.md.
- docs/plans/PERFORMANCE-CORE-AUDIT.md.
- docs/reports/core-sovereignty-adversarial-2026-10-18.md (AP-1/AP-2/AP-3).
- docs/guides/operations.md (Server-Timing, observabilidade).
- shopman/storefront/api/public_cache.py, surfaces/storefront-nuxt/server/utils/djangoProxy.ts.
- surfaces/storefront-nuxt/nuxt.config.ts, surfaces/storefront-nuxt/public/img/home.
- .do/app.alpha-subdomains.yaml (referência de topologia; não usar para update do vivo).
- shopman/shop/tests/load/locustfile.py (alvo P95 < 500 ms).

## 12. Resumo para quem assume

O código é rápido localmente (21 a 27 ms). No ar, a PDP custa 1,4 s na shared e 0,7 s no dedicado; o catálogo, 0,73 s e 0,36 s. A diferença de 2x é CPU. A shared satura em ~1 req/s e quadruplica a latência com 4 concorrentes; a dedicada entrega ~2 req/s. O maior ganho grátis é a gêmea pública da PDP; o segundo é TTL de borda; o terceiro é o lote de consultas. O primeiro teste de capacidade custa +13/mês (2 GB shared) e o segundo +27/mês (dedicado 2 GB). Não compre 2 vCPU nem réplicas antes de ler CPU, RAM e tráfego no painel. Sem esses três números, qualquer compra é chute.
