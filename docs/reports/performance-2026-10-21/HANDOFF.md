# Desempenho: Fase A, evidências e pendências

Atualização: **29/10/2026**. Esta revisão substitui a proposta inicial de 21/10.
A avaliação desta frente foi somente leitura no ambiente vivo. Não houve aumento de
plano, mudança de configuração, instalação de extensão, limpeza de dados ou teste
concorrente. A documentação pode ser publicada; o aceite integral da Fase A ainda
está **parcial**: recursos e causa do 403 estão fechados; atribuição histórica da
cauda HTTP e hit ratio real não podem ser certificados com a cobertura recuperada
(seção 7). Não declarar essas lacunas como resolvidas.

## 1. Decisão para o dono

**Não há base suficiente para comprar capacidade agora.** As faixas amostradas de
CPU/RAM não mostram saturação sustentada nos quatro serviços, mas a cauda do
ingresso chega a 9–10 s em intervalos da semana. A correlação recuperada descarta deploy como explicação universal, mas não
identifica a rota de todos os picos. O histórico por requisição não está arquivado
no App Platform; ver seção 6.1 antes de escolher uma intervenção.
Baixa CPU agregada não prova que CPU deixou de participar do atraso.

Os gargalos de código comprovados em 21/10 já tiveram correções publicadas:
recomendações no caminho principal da PDP, releitura de produtos/tags e varredura
repetida do histórico do BI. Não abrir outras frentes para refazer esses trabalhos.
O #1985 corrigiu depois o adiamento real do rail e adicionou sua gêmea pública.
Hoje a borda respondeu HIT nessa rota. Isso comprova funcionamento do cache, não
um hit ratio representativo do tráfego real.

A Fase B permanece uma proposta, **sem autorização de execução nesta avaliação**.
Os deltas +US$ 13/mês e +US$ 27/mês eram cenários do handoff de 21/10, não cotação
renovada nem recomendação de compra. Não aplicar spec, escalar, reiniciar serviços,
reconfigurar banco/cache ou ampliar permissões com base neste relatório.

## 2. Ambiente conferido em 29/10

App `shopman-nelson`, ID `40b86e35-bafe-4a1a-a1b0-e124d3d9fd0f`, região `nyc`.
O valor de `x-do-app-origin` do handoff antigo não era o App ID da API de gestão.
Spec resumido e deployment ACTIVE estão em
[evidence/do-readonly-2026-10-29.json](evidence/do-readonly-2026-10-29.json).
Nenhum env ou spec completo foi salvo.

| Serviço | Plano no spec vivo | Instâncias configuradas |
| --- | --- | ---: |
| web-storefront | apps-s-1vcpu-1gb | 1 |
| storefront-nuxt | apps-s-1vcpu-1gb | 1 |
| operator-floor | apps-s-1vcpu-1gb-fixed | 1 |
| operator-office | apps-s-1vcpu-0.5gb | 1 |
| web-operator | apps-d-1vcpu-2gb | 1 |

Isso corrige a tabela antiga, que indicava `operator-floor` com 0,5 GB e Nuxt fixed.
Múltiplas séries no gráfico não significam múltiplas instâncias configuradas.
Esta frente não mudou nenhum desses planos.

## 3. Painel: janela de sete dias

Fonte: Insights, Select Period **Last 7 days**, componentes individuais. Janela
exibida de 22 a 29/10. As descrições acessíveis e uma segunda leitura do storefront
foram transcritas em
[evidence/panel-7d-2026-10-29.json](evidence/panel-7d-2026-10-29.json).
A DigitalOcean define duração P95 em milissegundos e taxa em requests/s na
[documentação de Insights](https://docs.digitalocean.com/products/app-platform/how-to/view-insights/).

| Serviço | CPU: máximo na primeira faixa exibida | RAM: máximo na primeira faixa exibida | Faixa do P95 de ingresso por intervalo |
| --- | ---: | ---: | ---: |
| web-storefront | 26,45% | 32,73% | 96,25–10.000 ms |
| storefront-nuxt | 16,35% | 12,57% | 23,75–9.000 ms |
| operator-floor | 24,43% | 39,17% | 23,75–10.000 ms |
| operator-office | 9,43% | 44,70% | 23,75–2.425 ms |

Esses são extremos de **faixas amostradas/agregadas do painel**, não máximos
instantâneos garantidos. Uma segunda janela deslocada alguns minutos mostrou
web-storefront com CPU máxima 13,64% e RAM 32,82%; alinhamento/resolução afetam os
extremos. As duas leituras foram preservadas, sem atribuir a diferença a uma ação.
O gráfico de restart count exibiu 0–1 nos quatro serviços. Não é uma contagem
cumulativa de falhas nem prova de ausência de OOM; requer correlação com eventos.

O maior valor de um P95 por intervalo **não é o P95 global da semana**. Não se
calcula P50/P95 global ou média de CPU a partir dos limites de um gráfico. A
exportação inicialmente retornou **403** porque o token `shopman-do-app-admin`
não tem `monitoring:read`. A tela View Scopes mostrou seus oito escopos; nenhum
é Monitoring. O erro da API foi `Forbidden: You are not authorized to perform
this operation`. **Causa fechada**, sem relação demonstrada com carga, CORS ou
checkout. [Evidência](evidence/export-403-diagnosis-2026-10-29.json).

A exportação foi concluída usando `DIGITALOCEAN_READ_TOKEN`, já configurado no
Watchman, dentro da CI. Nenhum segredo saiu da CI e nenhuma permissão foi ampliada.
As 12 consultas foram bem-sucedidas no
[run 40922403473](https://github.com/nelsonboulangerie/django-shopman/actions/runs/40922403473).
O job temporário foi retirado da revisão final da PR; nenhum workflow novo será
implantado. [Séries exportadas](evidence/monitoring-7d-2026-10-29.json) e
[resumo por série](evidence/monitoring-summary-2026-10-29.json).

Janela exportada: **22/10 17:36:59 a 29/10 17:36:59 UTC**. A API retornou 401
pontos da série `*-0` por métrica, espaçados por 1.512 s (25,2 min). Mediana e P95
nearest-rank desses pontos, em **percentual de recurso**, abaixo. Não são percentis
de latência, nem amostragem de todas as requisições, nem garantia sobre picos entre
pontos. As séries `*-1`, com 30–48 pontos em CPU/RAM, permanecem separadas no JSON;
não foram somadas nem confundidas com duas instâncias permanentes.

| App, série *-0 | CPU P50 | CPU P95 | RAM P50 | RAM P95 |
| --- | ---: | ---: | ---: | ---: |
| web-storefront | 3,57% | 4,78% | 25,67% | 32,45% |
| storefront-nuxt | 3,11% | 4,30% | 9,42% | 11,84% |
| operator-floor | 3,11% | 5,84% | 31,20% | 37,14% |
| operator-office | 2,95% | 3,41% | 34,29% | 44,38% |

Restart count foi zero nos 401 pontos exportados de cada série `*-0`; o painel
mais detalhado mostrou faixa 0–1. Resoluções diferentes não permitem declarar
que nenhum restart transitório ocorreu. A exportação remove o bloqueio do 403,
mas não fornece o histograma histórico de latência ou os contadores do CDN.

## 4. Amostra HTTP atual e cache

[Coleta bruta](evidence/http-2026-10-29.json): três GETs anônimos por URL,
sequenciais, intervalo de 1 s, sem cookies, timeout de 15 s e aborto em 5xx.
Todas as 21 respostas foram 200. Mede **resposta HTTP completa**, não TTFB, LCP,
capacidade concorrente ou o comportamento de um operador autenticado.

| Leitura | Mediana de 3 | Máximo observado |
| --- | ---: | ---: |
| Página /produto/FENDU | 1.409,40 ms | 2.520,17 ms |
| API principal products/FENDU/ | 1.401,96 ms | 1.544,99 ms |
| Recomendações privadas | 1.156,72 ms | 1.166,25 ms |
| Recomendações públicas | 133,36 ms | 1.334,46 ms |
| Catálogo público | 148,64 ms | 1.988,36 ms |
| Central, operator-floor | 572,38 ms | 672,48 ms |
| Marketing, operator-office | 448,78 ms | 2.631,71 ms |

Recomendações públicas: **MISS → HIT → HIT**, TTL 60 s, Age 1 e 2 nas duas HIT.
Catálogo público: **MISS → HIT → HIT**, TTL 30 s. A repetição foi intencional para
conferir a borda. Os 2/3 HIT de cada sequência **não são o hit ratio de produção**.
`Server-Timing` em HIT foi reapresentado pelo cache junto do corpo; não representa
nova execução do Django. As rotas privadas permaneceram BYPASS.

O painel App expõe throughput de CDN por cache status, mas não foi exportada uma
série completa para somar HIT/total com cobertura conhecida e separar host,
rota e sessão. Essa lacuna permanece. Não procurar zonas na conta Cloudflare
pessoal como se ela necessariamente administrasse o CDN integrado da plataforma.

## 5. Postgres, Valkey e arquivos temporários

[Agregados do console](evidence/database-cache-2026-10-29.json), em 29/10 às
17:12 UTC. Postgres em transação READ ONLY, timeout local de 5 s e rollback;
Valkey somente INFO e cinco PING. Não houve dump, escrita, reset de estatística,
consulta de dados pessoais, instalação de extensão ou exclusão de arquivo.

- Postgres: `work_mem=2048 kB`, `max_connections=25`, isolamento read committed;
  três conexões no banco consultado, zero deadlocks acumulados. A leitura inclui
  a conexão da própria sonda. Buffer hit calculado dos contadores: aproximadamente
  99,9945%. Não comprova ausência de consultas lentas ou filas.
- `pg_stat_statements` não está instalado. Não existe aqui um ranking histórico
  completo de queries/p95 do banco, e não se propõe instalar sem decisão específica.
- `temp_files=3306`, `temp_bytes=18174813932`, `stats_reset=null`: os **18,17 GB são
  bytes temporários acumulados**, não ocupação atual comprovada de disco nem um
  conjunto de arquivos para apagar. O período desde o reset não é conhecido.
- Valkey: 5.317.576 bytes usados de `maxmemory=438304768`, 11 clientes, zero
  bloqueados e zero evicções. Hit ratio cumulativo das chaves: aproximadamente
  98,49%; não é hit ratio de Cloudflare, nem somente desta semana.
- GET no servidor Valkey: 9,95 µs/chamada cumulativos. Cinco PING pela aplicação:
  6,154 / 6,949 / 3,259 / 4,033 / 5,657 ms. Tempo no servidor e ida/volta não são
  a mesma métrica; não se atribui todo `cache_ms` apenas ao processamento do Valkey.

Leituras SQL reproduzíveis, na mesma transação/conexão:

```sql
BEGIN READ ONLY;
SET LOCAL statement_timeout = '5s';
SELECT temp_files, temp_bytes, blks_hit, blks_read, deadlocks, numbackends, stats_reset
FROM pg_stat_database WHERE datname = current_database();
SELECT name, setting, unit FROM pg_settings
WHERE name IN ('work_mem', 'max_connections', 'default_transaction_isolation');
SELECT state, count(*) FROM pg_stat_activity GROUP BY state;
SELECT extname FROM pg_extension WHERE extname = 'pg_stat_statements';
ROLLBACK;
```

## 6. Logs e correções já entregues

A captura de até 2.000 linhas disponíveis do serviço, filtrada antes de salvar,
trouxe **duas observações** `storefront_catalog_observation`. O JSON de evidência
preserva somente campos agregados autorizados pelo logger. Não cobre uma hora de
pico nem sete dias. Os valores de construção foram 1.047,71 e 1.011,66 ms, com
36/34 queries, SQL 216,67/182,25 ms e cache 63,05/30,46 ms. Esses estágios se
sobrepõem; não devem ser somados como partes independentes. Duas observações não
fecham a análise histórica de P50/P95 por endpoint.

| Entrega | Evidência e limite da conclusão |
| --- | --- |
| [#1974](https://github.com/nelsonboulangerie/django-shopman/pull/1974) | Separou rail da PDP e agrupou tags. Na amostra de 21/10, API principal 1.716,11 → 962,93 ms. O adiamento no mobile ainda precisou da correção posterior #1985. |
| [#1975](https://github.com/nelsonboulangerie/django-shopman/pull/1975) | Removeu mapa/rotas/modelo legado da PDP; não remover aliases e de-para do BI. |
| [#1976](https://github.com/nelsonboulangerie/django-shopman/pull/1976) | Agrupou/cacheou distribuição histórica do BI. EXPLAIN original: 380.199 linhas e 1.343 blocos temporários; agrupado: 229 grupos, zero blocos. Alarme aquecido 1.994,86 → 21,71 ms na amostra publicada. Não rodar outra varredura para redescobrir isso. |
| [#1977](https://github.com/nelsonboulangerie/django-shopman/pull/1977) | Reutilizou produtos/tags e montou quatro cards, mantendo seleção. Construção controlada 254,53 → 225,36 ms, 31 → 28 queries. HTTP de 21/10: mediana 718,57 ms; não tratar como latência garantida ou atual de 29/10. |
| [#1985](https://github.com/nelsonboulangerie/django-shopman/pull/1985) | Adiamento com rootMargin 0, reserva estável de altura e gêmea pública 60 s do rail. Testes locais de CLS e adiamento estão na PR; HIT real foi confirmado na coleta de hoje. CLS vivo ainda não foi revalidado nesta frente. |

Gargalos comprovados historicamente: varredura/materialização repetida do histórico
BI com spill e trabalho repetido no catálogo/recomendações. Leitura atual: a
construção canônica de catálogo/PDP ainda custa aproximadamente 1 s na amostra,
e a cauda de ingresso precisa de atribuição por rota. O tempo fora de `db_ms`
inclui cache, Python, serialização e espera; não é prova isolada de CPU.

## 6.1. Investigação dos picos de 10 s

[Evidência de correlação](evidence/peak-correlation-2026-10-29.json),
[deployments](evidence/deployments-2026-10-29.json),
[access logs saneados](evidence/access-coverage-2026-10-29.json) e
[resumo da amostra](evidence/access-summary-2026-10-29.json).

No gráfico de sete dias do `web-storefront`, a linha renderizada tem 1.009 pontos,
espaçados por dez minutos, e três pontos no valor de 10.000 ms. Horários abaixo
são derivados da posição no SVG e dos extremos do eixo, em UTC, **aproximados**;
não são timestamps de requests ou tooltips. A largura real da agregação não foi
exposta. Não é possível inferir rota ou timeout individual a partir dessa linha.

| Ponto aproximado UTC | Relação com deploy mais próximo | Recurso mais próximo na exportação |
| --- | --- | --- |
| 23/10 16:11 | 12 min 26 s antes do início do próximo deploy | CPU 2,98%, RAM 28,02%, amostra 6 min 41 s depois |
| 27/10 01:01 | 16 h 35 min antes do próximo deploy | CPU 4,61%, RAM 31,11%, amostra 4 min 55 s antes |
| 29/10 17:41 | 34 min 56 s após o fim do último deploy | CPU 4,05%, RAM 24,10%, amostra 4 min 07 s antes |

**Deploy não explica todos os picos.** A granularidade dos recursos não exclui
picos breves, fila, contenção ou espera de rede. Tampouco comprova falta de CPU ou
RAM. Os timeouts canônicos de fetch normal nos BFFs são **25 s**, não 10 s
(`surfaces/storefront-nuxt/server/utils/djangoProxy.ts:30` e
`surfaces/operator-kit/server/utils/djangoProxy.ts:61`). Não há prova de que o teto
de 10 s seja um timeout ou bucket interno do provedor; essas hipóteses ficam sem
confirmação, não viram diagnóstico.

Dos logs disponíveis do deployment atual, recuperaram-se 53 access events entre
17:05:44 e 17:36:01 UTC em 29/10: 52 não streaming, P50 **421 ms**, P95 nearest-rank
**1.024 ms**, máximo **1.134 ms**, nenhuma duração ≥10 s. São logs do Django, com
sondas incluídas, não latência externa ou amostra representativa da semana. Houve
51 respostas 200, um 403 de checkout (evento distinto do 403 de exportação) e um
404 da primeira sonda desta investigação, que usou prefixo incorreto e foi corrigida.
Não há 5xx nessa amostra; isso não prova ausência de 5xx na semana.

Uma única sonda pública de SSE entregou cabeçalhos em **678,59 ms** e primeiro byte
em **678,69 ms**, mantendo conexão por **12.681,78 ms** até encerramento voluntário.
No Django, o mesmo tipo de request apareceu como `streaming=true`, abertura **4 ms**.
[Evidência SSE](evidence/sse-readonly-2026-10-29.json). Esse experimento demonstra
que duração de conexão e abertura/primeiro byte medem coisas diferentes. O ponto
mais recente de 10 s está na vizinhança temporal da sonda, portanto está também
contaminado por investigação. **Não prova que os picos históricos eram SSE**, e
não deve ser usado como incidente espontâneo nem como ganho de desempenho.

A tentativa de ler o deployment anterior retornou **400: cannot get running logs
from deployment in phase final_cleanup**. O spec não tem `log_destinations` no app
nem nos componentes. Há Sentry de erros configurado, mas não há taxa de tracing
no spec e o default do código é zero; não é arquivo completo de access logs.
[Evidência de retenção](evidence/log-retention-2026-10-29.json).
A [documentação de logs da DigitalOcean](https://docs.digitalocean.com/products/app-platform/how-to/view-logs/)
orienta forwarding para retenção de runtime logs. Nenhum forwarding, tracing,
permissão ou configuração foi ativado nesta investigação.

**Conclusão de atribuição:** o responsável individual pelos picos antigos de 10 s
permanece indeterminado. A evidência permite rejeitar a atribuição automática a
RAM, a deploy ou a SSE. Não há registro recuperado com rota/status/duração para
fechar causalidade retrospectiva. Mais exportações de CPU não recompõem logs que
não foram arquivados. O gargalo atual comprovado continua sendo **construção da
projection canônica do catálogo/PDP (~1 s nas observações)**, com custo também fora
do SQL, e o custo de origem no MISS. Isso sustenta perfil de código, não aumento
de plano. Não atribuir os 10 s a essa projection sem correlação.

## 7. Pendências reais antes de encerrar o aceite da Fase A

1. **P50/P95 histórico por endpoint e por app**, em janela com cobertura conhecida,
   incluindo hora de pico, 5xx e timeouts. O painel fornece P95 por intervalo;
   53 eventos recentes e duas observações de catálogo não recompõem a semana.
   Não há como certificar esse histórico com o material recuperado.
2. **Exportação de CPU/RAM/restarts e causa do 403 concluídas.** Correlação temporal
   realizada no storefront; atribuição por rota/fila permanece sem histórico
   recuperável nesta coleta. Não ampliar escopo ou ativar coleta no ambiente vivo.
3. Hit ratio real da borda por host/rota, com denominador e janela definidos.
   Funcionamento de HIT foi provado; taxa representativa não foi medida.
4. Revalidar CLS vivo com conteúdo abaixo do rail. Não refazer os testes locais
   já publicados no #1985 como se fossem medições do ambiente vivo.
5. Determinar tráfego/pico esperado e SLO de go-live. A/B entre serviços diferentes
   e SQLite local não isolam RAM, CPU ou efeito de cache.

Trabalho de código ainda potencialmente útil, **a avaliar em frente própria**:
perfil da construção atual e separação da sacola antes de qualquer gêmea pública
da PDP inteira. A resposta principal contém `cart`; não colocá-la em cache público
por simples herança de mixin. Não executar isso como parte desta Fase A documental.

## 8. Fase B condicionada e rollback

Somente após decisão específica do dono, com custo e janela atualizados:

- Comparar baseline com 2 GB shared e, se necessário, dedicado 2 GB, sem mudar
  código simultaneamente. A mudança de tamanho pode alterar mais que RAM; não
  concluir “era RAM” só porque o P50 caiu.
- Capturar spec vigente com cuidado de segredos, guardar original **imutável** e
  preparar um arquivo candidato separado. Comparar somente o serviço autorizado.
  Nunca editar o mesmo arquivo que será usado como rollback.
- Definir previamente SLO, tráfego comparável, duração, aborto por erro/latência
  e monitoramento de banco/SSE. Não há rampa concorrente autorizada por este texto.
- Rollback é reaplicar o original validado; não remover cache, executar seed,
  apagar dados ou alterar credenciais para realizar o experimento.

## 9. Como reproduzir a parte segura

Na worktree, sem cookies e sem credenciais nos comandos HTTP:

```bash
python3 docs/reports/performance-2026-10-21/capture_http_readonly.py \
  --samples 3 --output /tmp/shopman-performance-http.json
python3 docs/reports/performance-2026-10-21/capture_do_readonly.py \
  --context shopman-do-app-admin --output /tmp/shopman-performance-do.json
```

O segundo script usa o contexto já existente do `doctl`, lê app/logs, não troca
contexto nem imprime credenciais. Spec completo e linhas arbitrárias de log não
são salvos. Não usar `--trace`, publicar envs ou token, nem alterar autenticação
para repetir a tentativa sem o escopo necessário. A alternativa que funcionou foi
a execução isolada em CI com a credencial de leitura já existente, sem extraí-la.
O coletor `export_monitoring_readonly.py` usa apenas GETs documentados e calcula
percentis por série; o JSON do run está preservado nesta PR. A coleta HTTP é curta, sequencial e aborta em 5xx; não é um
teste de carga. A proposta original permanece recuperável no histórico Git da PR
#1973, commit `03ac2b80986afdda9c406765a38dc6250be05645`.
