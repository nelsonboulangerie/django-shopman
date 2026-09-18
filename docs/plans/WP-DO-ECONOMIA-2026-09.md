# WP-DO-ECONOMIA-2026-09 — a conta da DigitalOcean, medida, e onde ela encolhe

> Aberto em 2026-09-17, a pedido do dono: *"Já passou de 100 dólares por mês!"*.
> Documento de **plano**, feito só com leitura: nenhum `apps update`, nenhum resize,
> nenhum garbage collection e nenhuma escrita no banco foram executados.
> Irmão: [WP-PERFORMANCE-2026-09](WP-PERFORMANCE-2026-09.md). Onde cortar custo mexe
> em performance, as duas frentes apontam uma para a outra.

## O problema em uma frase

A conta passou de US$ 100/mês com **tráfego de alpha** (≈ 2 pedidos/dia em setembro),
e ~70% dela é um desenho de **um container por superfície**: 10 services, 3 workers,
e um Postgres e um Valkey que usam 2% e 1% do que pagam.

## Regra que vale para todo este WP

⛔ **Nada de componente novo na DO sem esgotar os existentes** (regra do Pablo, 17/09).
A etapa de entrega do Marketing roda **dentro do `maintenance-worker`**; não há worker
novo para ela, e nenhuma proposta abaixo cria um.

## 1. Como foi medido

| Fonte | Comando (somente leitura) | Resultado |
|---|---|---|
| Apps e specs | `doctl --context shopman-spec-update apps list -o json` | 3 apps; componentes, slugs, contagens, região |
| Preço dos slugs de app | `doctl apps tier instance-size list` | tabela de preços **da própria API**, 17/09/2026 |
| Bancos | `doctl databases list/get/pool list/replica list/backups/configuration get` | 2 clusters, 1 pool, 0 réplicas |
| Registry | `doctl registry get -o json`, `registry repository list-v2`, `list-tags`, `list-manifests`, `garbage-collection list` | 12,43 GB, 1 repositório, 752 tags, nenhum GC já rodado |
| Postgres | `psql` pelo pool, `BEGIN READ ONLY` | tamanho, `pg_stat_*`, contagens |
| Valkey | cliente Python, `INFO` e `SCAN` (sem ler valores) | memória, chaves, conexões |
| Deploys | `doctl apps list-deployments` (1.170) e `gh run list --workflow deploy-images.yml` (300) | frequência e fan-out |
| Faturamento | `doctl balance get`, `invoice list`, `billing-history list` | **403 nos dois contextos** — sem acesso |
| Outros recursos | `compute droplet/volume/load-balancer/snapshot/reserved-ip/firewall list`, `vpcs`, `kubernetes`, `projects`, `domain` | **403 nos dois contextos** — não dá para afirmar que não existem |

Preços de banco e registry: páginas públicas da DigitalOcean consultadas em 17/09/2026
([managed databases](https://www.digitalocean.com/pricing/managed-databases),
[container registry](https://docs.digitalocean.com/products/container-registry/details/pricing/),
[App Platform](https://docs.digitalocean.com/products/app-platform/details/pricing/)).
Valores em US$ de lista, **sem impostos**.

## 2. Inventário medido com custo mensal

### App `shopman-nelson` (região `nyc`, 1 instância por componente, sem autoscaling)

| Componente | Tipo | Slug | Qtde | US$/mês |
|---|---|---|---:|---:|
| `web` (daphne, API + Admin + SSE) | service | `apps-s-1vcpu-1gb` | 1 | 12,00 |
| `storefront-nuxt` | service | `apps-s-1vcpu-1gb` | 1 | 12,00 |
| `pos-nuxt`, `kds-nuxt`, `orders-nuxt`, `production-nuxt`, `hub-nuxt`, `marketing-nuxt`, `bi-nuxt`, `purchase-nuxt` | service | `apps-s-1vcpu-0.5gb` | 8 | 40,00 |
| `directive-worker` (`process_directives --watch`) | worker | `apps-s-1vcpu-0.5gb` | 1 | 5,00 |
| `maintenance-worker` (ciclo de 300 s, ~30 comandos) | worker | `apps-s-1vcpu-0.5gb` | 1 | 5,00 |
| `ifood-poll-worker` (`ifood_poll --watch --interval 30`) | worker | `apps-s-1vcpu-0.5gb` | 1 | 5,00 |
| `release` (PRE_DEPLOY: check, migrate, setup_groups, bootstrap) | job | `apps-s-1vcpu-0.5gb` | por segundo | ≤ 0,50 (estimado) |
| **Subtotal app** | | | | **≈ 79,50** |

O job `release` é cobrado só enquanto roda (US$ 0,0000021/s). Com 391 deployments em 7
dias e ~2 min cada, fica abaixo de US$ 0,50/mês. O custo dele é de estabilidade, não de
dinheiro (ver [WP-PERFORMANCE P5](WP-PERFORMANCE-2026-09.md#p5--um-deployment-por-run-e-não-dez)).

### Bancos gerenciados (`nyc3`, 1 nó cada, sem standby, sem réplica)

| Cluster | Engine | Slug | Uso medido | US$/mês |
|---|---|---|---|---:|
| `shopman-staging-postgres` | PG 16 | `db-s-1vcpu-1gb`, 10 GiB | banco `shopman` = **194 MB** (2% do disco); backups diários de 0,24 GB; cache hit 100%; `max_connections` 25; pool `transaction` de 5 | 15,15 |
| `shopman-staging-cache` | Valkey 8 | `db-s-1vcpu-1gb` | **4,95 MB** usados de 418 MB (pico 10,9 MB); **8 chaves**; ~5 ops/s; 0 evicções | 15,00 |
| **Subtotal bancos** | | | | **30,15** |

Os dois já estão no **menor slug que a DO vende**. Não há o que reduzir por tamanho.

### Container registry `nelsonboulangerie` (`nyc3`)

| Item | Medido |
|---|---|
| Uso | **12.433.007.616 bytes = 11,58 GiB** |
| Repositórios | 1 (`shopman`) |
| Tags | 752 (web 255, storefront 99, pos 73, production 60, marketing 53, orders 51, purchase 51, kds 37, bi 37, hub 35) |
| Manifests | 761, dos quais 20 sem tag (0,66 GB) |
| Imagem atual | web 183 MB comprimida; cada Nuxt 59–73 MB |
| Garbage collection | **nunca rodou** (`garbage-collection list` vazio) |
| Plano | **não visível para os tokens**; o Starter é recusado pela API por `OverStorageLimit` |

A causa das 752 tags está no `deploy-images.yml`: cada build publica a tag móvel e uma
tag imutável `<componente>-<sha>`, e nada apaga as antigas.

| Se o plano for | Conta | US$/mês |
|---|---|---:|
| Basic (US$ 5, 5 GiB) | 5,00 + 6,58 GiB × 0,02 | **5,13** |
| Professional (US$ 20, 100 GiB) | 20,00 | **20,00** |

### Apps fora do shopman

| App | Componentes | Custo | Decisão vigente |
|---|---|---:|---|
| `nb-catalog-app` (`cardapio.nelsonboulangerie.com.br`) | 1 static site | 0,00 | **Fica de pé até o go-live**, palavra do Pablo em 01/09. Não se propõe desligar. |
| `nb-site` (apex e `www` de `nelsonboulangerie.com.br`, `boulangerie.com.br`) | 2 static sites no mesmo app | 0,00 | Nada a fazer. |

A DO cobra zero por até **três apps só com static sites**. São dois hoje, então aposentar
os dois economizaria **US$ 0**. Criar um quarto custaria US$ 3.

### Total

| Bloco | US$/mês (Basic) | US$/mês (Professional) |
|---|---:|---:|
| App `shopman-nelson` | 79,50 | 79,50 |
| Postgres + Valkey | 30,15 | 30,15 |
| Registry | 5,13 | 20,00 |
| Static sites | 0,00 | 0,00 |
| **Total estimado** | **≈ 114,78** | **≈ 129,65** |

Bate com o *"já passou de 100"*. A diferença entre as duas colunas depende do plano do
registry, que só o painel mostra (ver pré-requisito da E4).

### Fatura real (lida no painel com o Pablo, 17/09/2026)

O painel *Billing* (atualizado 17/09 02:41 BRT, 384 h = 16 dias de setembro) confirma a
estimativa e fecha as lacunas da seção 5. **O plano do registry é Basic.**

| Item da fatura | 1–17/09 (US$) | Projeção 30 dias (US$) |
|---|---:|---:|
| Apps — `shopman-staging` (é o nome de faturamento do `shopman-nelson`, plano professional) | 45,18 | ≈ 84,70 |
| Apps — `nb-catalog-app`, `nb-static-landing-page` (starter) | 0,00 | 0,00 |
| Apps — `shopman-ip-probe-20260915-a` (ensaio de 15/09) | 0,01 | — |
| Container Registry Basic + excedente 1,46 GiB | 2,89 | ≈ 5,40 |
| Droplet snapshots de 2019 (nyc1 4,38 GB; sfo2 5,03 GB) | 0,32 | ≈ 0,60 |
| Postgres `shopman-staging-postgres` | 8,66 | ≈ 16,20 |
| Valkey `shopman-staging-cache` | 8,57 | ≈ 16,10 |
| Postgres `shopman-restore-test` (ensaio de restore) | 0,03 | — |
| **Total** | **65,69** | **≈ 123** |

Consequências para as propostas:
- **E4 (registry):** não há descida de plano possível — já é o Basic. A economia real da
  retenção é só o excedente (centavos) e impedir que ele cresça; a E4 continua útil como
  higiene, não como corte.
- **Achado novo:** dois snapshots de droplet de 2019, sem relação com o Shopman, cobram
  ≈ US$ 0,60/mês. Apagar é irreversível e pede a palavra do Pablo.
- Os recursos de ensaio (`shopman-ip-probe-…`, `shopman-restore-test`) aparecem com
  centavos: conferir no painel se ainda existem e remover ao fim do ensaio.

**O que este total não inclui:** transferência de saída acima da franquia (não medível
pelos tokens), impostos, e recursos da conta fora de apps, bancos e registry (droplets,
volumes, Spaces, snapshots, load balancers), que devolveram 403.

## 3. Propostas, ordenadas por economia × risco

| # | Proposta | Economia US$/mês | Risco | Fase |
|---|---|---:|---|---|
| E1 | `web` e `storefront-nuxt` em `apps-s-1vcpu-1gb-fixed` | 4 | baixo | 1 |
| E4 | Retenção de tags + garbage collection do registry | 0,13 a 15 | baixo | 1 |
| E3 | `ifood-poll-worker` dentro de um worker existente | 5 | baixo a médio | 2 |
| E2 | Os 8 Nuxt de operador em um único service | 15 a 30 | médio | 3 |
| E5 | Aposentar o Valkey | 15 | alto | ⛔ não agora |
| E6 | Reduzir o Postgres | 0 | — | não se aplica |
| E7 | Aposentar `nb-catalog-app`/`nb-site` | 0 | — | ⛔ decidido: fica até o go-live |

**Onde isso chega:** a fase 1 tira de US$ 4 a 19. A fase 2 tira mais 5. A fase 3 tira de
15 a 30. Com as três, a conta vai de ≈ 114,78 para **≈ 70–90/mês** (Basic), ou de
≈ 129,65 para **≈ 70–105/mês** (Professional).

---

### E1 · `web` e `storefront-nuxt` em `apps-s-1vcpu-1gb-fixed`

- **O que muda:** o slug dos dois services passa de `apps-s-1vcpu-1gb` (US$ 12) para
  `apps-s-1vcpu-1gb-fixed` (US$ 10). A CPU e a RAM são as mesmas (1 vCPU compartilhada,
  1 GiB). A única diferença é que o *fixed* não escala para mais de uma instância.
- **Economia:** US$ 4/mês.
- **Risco:** baixo. Hoje os dois rodam com `instance_count: 1` e sem autoscaling
  (medido). O risco aparece só se o go-live pedir escalar horizontalmente.
- **Como reverter:** voltar o slug no spec e aplicar. A DO recria o container e não há
  migração nem dado envolvido.
- **Pré-requisitos:** mudar em `.do/app.alpha-subdomains.yaml`; `make deploy-spec-drift`
  limpo antes; `doctl apps propose --spec` para ver o custo que a DO calcula (é uma
  validação, não altera o app); janela fora do expediente.
- **Prova:** deployment `ACTIVE`, Alpha Smoke verde e a linha de custo nova no painel
  *Billing → App Platform*.

### E4 · Retenção de tags e garbage collection do registry

- **O que muda:**
  1. Um workflow semanal apaga as tags imutáveis `<componente>-<sha>` além das **10 mais
     recentes por componente** e nunca toca as tags móveis (`web`, `pos`...).
     - ⚠️ **Invariante nova, desde o job `drift` do `deploy-images.yml`:** a tag imutável
       que a tag MÓVEL aponta não pode ser apagada nunca. É ela que permite dizer qual
       commit está no ar — sem ela o confronto pós-deploy passa a responder "impossível
       provar" para todo componente, e o guardrail vira ruído. Com N=10 isso é grátis (a
       irmã da móvel é sempre o build mais recente); se N cair para 1, ou se a regra
       passar a ser por DATA, confira isto antes de ligar.
  2. Depois dele roda `registry garbage-collection start --include-untagged-manifests`.
  3. O `deploy-images.yml` ganha uma nota apontando a retenção.
- **Economia:**
  - Se o plano for **Professional**, sair de 11,58 GiB para menos de 5 GiB permite descer
    para o Basic: **US$ 15/mês**. Estimativa de 10 tags por componente: web ≈ 1,8 GB e
    surfaces ≈ 9 × 10 × 60 MB ≈ 5,4 GB antes de camadas compartilhadas. O `node:22-alpine`
    e as dependências se repetem, então o número real tende a ficar abaixo, mas **só o GC
    prova**. Se passar de 5 GiB, reduzir para 5 tags.
  - Se o plano já for **Basic**, a economia é o excedente: **US$ 0,13/mês**. O ganho real
    é operacional, com menos coisa para listar e para o GC varrer.
- **Risco:** baixo. Enquanto roda, o GC deixa o registry **só leitura**, e um push do
  `deploy-images` nesse intervalo falha. O workflow de GC tem de usar o mesmo
  `concurrency: deploy-images` e rodar de madrugada. Rollback continua possível para os
  últimos 10 builds de cada componente.
- **Como reverter:** tag apagada não volta. O que se reverte é a política: basta subir o
  número N. Uma imagem antiga necessária se reconstrói do commit com
  `workflow_dispatch` + `git checkout <sha>`.
- **Pré-requisitos:** **o Pablo confere no painel qual é o plano do registry.** A API não
  mostra para os tokens atuais. Também é preciso um token com escopo de escrita no
  registry, que nenhum dos dois contextos tem hoje.
- **Prova:** `doctl registry get -o json` → `storage_usage_bytes` antes e depois;
  `registry repository list-v2` com a contagem de tags; e, se houver troca de plano, a
  linha nova na fatura.

### E3 · `ifood-poll-worker` para dentro de um worker existente

- **O que muda:** o laço de 30 s do iFood deixa de ter container próprio. A opção
  preferida é o `directive-worker` ganhar um tique periódico, porque o laço dele já roda a
  cada 1–2 s e só executa o `ifood_poll` a cada 30 s. A alternativa é rodar os dois
  processos no mesmo container com um supervisor mínimo. O `maintenance-worker` **não** é
  candidato: o ciclo dele é de 300 s, e o iFood exige polling a cada 30 s.
- **Economia:** US$ 5/mês.
- **Risco:** baixo a médio.
  - O `directive-worker` passa a carregar duas responsabilidades, e um travamento do
    iFood atrasaria as directives. O tique precisa de timeout próprio e de try/except
    que não derrube o laço, o mesmo padrão que o `process_directives` já usa.
  - O alerta `RESTART_COUNT` do `ifood-poll-worker` passa a valer para o worker que o
    hospedar.
- **Como reverter:** recolocar o bloco do worker no spec. A imagem é a mesma (`web`).
- **Pré-requisitos:**
  1. **O Pablo decide se o iFood está operando.** O banco tem 4 pedidos `ifood` na
     história (2 em agosto, 2 em setembro), a homologação está em curso
     (`docs/reports/IFOOD-*`) e há `IFOOD_WEBHOOK_TOKEN` no spec. Se o iFood não opera
     antes do go-live, a alternativa mais barata é **desligar o polling** até lá, com a
     mesma economia e risco zero de mistura.
  2. Medir o RSS dos três processos (`doctl apps console` → `ps -o rss`) antes de juntar:
     com 512 MB, dois processos Django precisam caber com folga.
- **Prova:** o iFood segue recebendo e confirmando pedido de teste; o `check_directive_health`
  não acusa atraso; e a latência das directives (`started_at - available_at`) não piora
  em 7 dias.

**Sobre o Marketing (decisão de 17/09):** a entrega fica no `maintenance-worker`, com
custo **zero**. O limite a vigiar é o log `maintenance_worker: ciclo levou Xs, mais que o
intervalo`: se o ciclo passar de 300 s, a resposta é **tirar trabalho inútil do ciclo**,
não criar worker. O primeiro candidato é o scan de 380 mil linhas do B.I. a cada 5 min,
medido em [WP-PERFORMANCE P2](WP-PERFORMANCE-2026-09.md#p2--o-bi-e-o-pedido-sem-índice-de-data).
O gate local do MKT-043 mediu pico de 82,6 MiB para 100 mil elegíveis
(`docs/reports/execution/marketing-capacity-mkt043-20260909.json`), e isso cabe no
worker de 512 MB se o resto do ciclo não estiver perto do teto. **Medir o RSS antes de
ligar a entrega.**

### E2 · Os 8 Nuxt de operador em um único service

- **O que muda:** `pos`, `kds`, `orders`, `production`, `hub`, `marketing`, `bi` e
  `purchase` passam a morar num único service `operator-nuxt`, e o App Platform roteia os
  8 hostnames para ele. Há duas formas de construir:
  - **(a) Um processo Node** que monta os 8 handlers Nitro (preset `node-listener`) e
    escolhe o app pelo `Host`. Usa menos memória, mas exige mudar o build de cada app.
  - **(b) Oito processos Node no mesmo container**, com um proxy mínimo por `Host`. O
    build fica igual e a memória é somada.

  O `storefront-nuxt` **fica fora**: é a superfície do cliente, com CSP e harness próprios.
- **Economia:**

  | Destino | US$/mês | Economia |
  |---|---:|---:|
  | 1 × `apps-s-1vcpu-1gb-fixed` | 10 | **30** |
  | 1 × `apps-s-1vcpu-2gb` | 25 | **15** |
  | Fase parcial: só `hub`+`marketing`+`bi`+`purchase` (uso do gestor, esporádico) em 1 × 0,5 GB | 5 | **15** |

- **Risco:** médio.
  - **Raio de explosão:** um crash derruba o PDV e o KDS juntos. Por isso a fase parcial
    agrupa primeiro os apps do gestor e deixa balcão e cozinha para depois, com evidência.
  - **Deploy:** hoje mudar o PDV reconstrói só o PDV. Com um service, **toda mudança em
    qualquer app de operador reinicia os 8** e derruba as conexões SSE do KDS e do PDV.
  - **Envelope de segurança (ADR-026):** a CSP com nonce é opt-in por app. Juntar não
    pode enfraquecer o Marketing (piloto) nem ativar o envelope nos apps não migrados.
  - **CPU:** uma vCPU compartilhada para os 8 event loops, incluindo SSE e SSR.
- **Efeito em performance:** o custo de deploy piora para os apps de operador, e o do
  registry melhora (1 imagem em vez de 8). Ver
  [WP-PERFORMANCE P9](WP-PERFORMANCE-2026-09.md#p9--consolidação-dos-nuxt-o-que-medir-antes).
- **Como reverter:** os 8 blocos de service ficam no histórico do spec, e as imagens
  por app continuam sendo construídas até a consolidação provar 14 dias. Voltar é
  reaplicar o spec anterior.
- **Medição real (painel Insights, 17/09 ~10h BRT, com o Pablo; `apps-s-1vcpu-0.5gb` = 512 MB):**

  | App | Memória | CPU (fração da vCPU) |
  |---|---|---|
  | PDV (7 dias) | 15–22% ≈ 77–113 MB | 2–6% |
  | KDS | 10–21% ≈ 51–108 MB | 2–4% |
  | Pedidos | 14–18% ≈ 72–94 MB | 3–6% |
  | Produção | 14–19% ≈ 72–97 MB | 4–8% |
  | Central | 10–13% ≈ 51–67 MB | 2–4% |
  | Marketing | 13–16% ≈ 67–82 MB | — |
  | B.I. | 10–14% ≈ 51–72 MB | — |
  | Compras | 8–10% ≈ 41–51 MB | — |

  Somas nos picos: chão (PDV, KDS, Pedidos, Produção, Central) ≈ 480 MB → cabe em 1 GB com
  folga ~2×; gestão (Marketing, B.I., Compras) ≈ 205 MB → cabe em 0,5 GB com folga ~2,5×.
  CPU ociosa de 2–8% por app numa manhã de pouco uso sugere custo fixo (health check em `/`,
  ver P1) — somada no chão fica em 15–25% de uma vCPU. Amostra de 1 hora (PDV: 7 dias);
  repetir no pico do balcão antes de juntar o chão.
- **Pré-requisitos:**
  1. Medir o **RSS de cada `.output/server/index.mjs` ocioso e com SSE aberto**, local e
     em `doctl apps console`. Sem esse número não se escolhe entre 0,5, 1 e 2 GB.
  2. ADR curta registrando a troca de isolamento por custo.
  3. Rotas de health baratas por app (já existe `marketing-nuxt/server/routes/health/live.get.ts`).
  4. Testes do `operator-kit` e de cada consumer verdes.
- **Prova:** 14 dias sem `RESTART_COUNT` no service novo; SSE do KDS e do PDV
  reconectando depois do deploy; TTFB das shells ≤ o baseline de
  [WP-PERFORMANCE §2](WP-PERFORMANCE-2026-09.md#2-baseline-medido); e a fatura com 7
  services a menos.

### E5 · Aposentar o Valkey — ⛔ não agora

- **O que mediu:** 4,95 MB, 8 chaves e 5 ops/s. É o recurso mais ocioso da conta, a US$ 15.
- **Por que não agora:** ele é a ponte do SSE entre processos (`EVENTSTREAM_REDIS`). Um
  `send_event` do `directive-worker` só acorda o listener do `web` por ele. Ele também
  carrega o heartbeat dos workers que o `/ready/` confere e o cache compartilhado.
  Tirá-lo exige LISTEN/NOTIFY do Postgres no lugar do pub/sub, cache em banco e uma ADR,
  o que é trabalho de código em caminho de tempo real (ADR-016).
- **Quando reabrir:** depois do go-live, se a conta ainda doer. Antes disso, o melhor
  uso dos 400 MB livres é **cache de leitura pública** (ver
  [WP-PERFORMANCE P6](WP-PERFORMANCE-2026-09.md#p6--cache-da-leitura-pública-do-cardápio)),
  que transforma custo ocioso em ganho de performance.

### E6 · Postgres — nada a cortar

`db-s-1vcpu-1gb` é o menor slug. O banco usa 194 MB de 10 GiB e o cache hit é de 100%.
**Não aumentar** antes de tirar os scans e o spill em disco medidos em
[WP-PERFORMANCE P2](WP-PERFORMANCE-2026-09.md#p2--o-bi-e-o-pedido-sem-índice-de-data):
cerca de 40 GB de arquivos temporários em 13 dias, com `work_mem` de 2 MB, é consulta mal
feita, não falta de máquina. Manutenção pendente nos dois clusters: Postgres sexta
03:44 UTC, Valkey quinta 15:16 UTC. **Quinta 15:16 UTC é 12:16 em Brasília, horário de
loja aberta.** Mover essa janela é leitura de agenda, sem custo, e fica recomendado.

### E7 · Apps fora do shopman — ⛔ decidido

O `nb-catalog-app` fica de pé até o go-live (Pablo, 01/09), e o `nb-site` é o apex. Os
dois custam US$ 0 no plano de static sites. Nenhuma ação.

## 4. Decisão que o go-live precisa tomar (não é corte, é para não dobrar a conta)

Existe `.do/app.subdomains.yaml` como template de produção. O app vivo `shopman-nelson`
já responde nos domínios reais (`api.`, `admin.`, `pdv.`, `gestor.`...), embora rode com
`SHOPMAN_ENVIRONMENT=staging` e os clusters se chamem `shopman-staging-*`. **Se o go-live
criar um segundo app a partir do template, a conta dobra para ≈ US$ 230/mês.** A virada
precisa ser decidida explicitamente como *in-place* (trocar envs e renomear clusters por
fork, se necessário) ou *app novo com desligamento do antigo no mesmo dia*. Nunca as duas
pilhas lado a lado.

## 5. O que não foi possível medir, e por quê

| Item | Por quê | Como obter |
|---|---|---|
| Fatura, saldo e histórico | 403 pelos tokens — **resolvido 17/09 pelo painel** (ver "Fatura real" na seção 2) | histórico de meses anteriores: painel *Billing → History* |
| Plano do registry | a API não expõe o tier — **resolvido 17/09: Basic** | — |
| Droplets, volumes, Spaces, snapshots, LB, IPs, domínios, projetos | 403 | painel *Resources*, ou token com `read` nesses escopos |
| CPU e memória por componente | sem escopo `monitoring:read`, e `doctl apps` não expõe métricas | painel *Insights* do app, ou token com `monitoring:read` |
| Transferência de saída | não exposta | fatura |
| RSS dos processos Node e Django | exigiria `apps console` interativo | pré-requisito de E2 e E3 |
| Custo do GitHub Actions (cache de 12,28 GB, acima dos 10 GB padrão) | fora da DO; billing do GitHub não consultado | `gh api /orgs/<org>/settings/billing/actions` com permissão de admin |
