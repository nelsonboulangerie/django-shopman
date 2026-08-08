# ADR-020 - Campanha anuncia, nao vende

**Status:** Proposto
**Data:** 2026-08-08
**Escopo:** `shopman/shop` (models/services/handlers de broadcast, `audience.py`, `directives.py`),
`shopman/backstage` (API + projections), `surfaces/broadcast-nuxt`, `guestman` (nenhuma mudanca de
model)
**Depende de:** ADR-018 (canal `display`), ADR-019 (`Promotion.ref` e `Promotion.channels`)
**Refina:** `docs/plans/FOMO-BROADCAST-SPECS.md` §2, §3, §4, §7 e §9
**Nao reabre:** o veto a B.I. (ADR-017 §8) nem o "nao e um Hootsuite"
(`docs/plans/FOMO-BROADCAST-SPECS.md:37-38`)

---

## Contexto

O dono quer liberdade para criar disparo pontual para clientes escolhidos, promocao relampago em faixa
de horario, e uma oferta acionavel de menor friccao possivel. Cinco fatos do codigo delimitam a
resposta.

**Primeiro: `broadcast` nomeia o transporte, e descreve mal metade do que o app faz.** Uma onda de
WhatsApp e broadcast; um `localPost` de Google Business e colocacao; um banner na TV e sinalizacao. E o
mesmo registro dirige os tres (`shopman/shop/services/broadcast.py:466-491`,
`shopman/shop/handlers/broadcast.py:219-256`), o que forca a superficie a chamar de "post" um SMS. O
rotulo visivel ja discorda do identificador: o Hub mostra **"Marketing"**
(`shopman/backstage/projections/hub.py:82`).

**Segundo: o opt-in de marketing e uma fechadura sem chave, e o consentimento tem dois donos.**
`audience.py` declara opt-in como lei (`shopman/shop/services/audience.py:9-13`) e derruba quem nao
tiver `CustomerPreference(category="marketing", key="broadcast_optin")` (`:340-353`), com uma unica
porta lateral para assinante de alerta de SKU (`:348-350`). Mas **`broadcast_optin` nao tem escritor**:
a chave aparece so na constante e na docstring (`:34-35`, `:10`); nao esta no seed, em nenhuma API nem
em nenhum service. Somente o proprio teste a cria, na fixture (`shopman/shop/tests/test_audience.py:32`).

Enquanto isso, o toggle que **o cliente usa** escreve outro model:
`toggle_notification_consent` (`shopman/shop/services/account.py:199-219`) chama
`ConsentService.grant_consent(..., source="storefront_settings", legal_basis="consent", ip_address=...)`,
persistindo `CommunicationConsent`
(`packages/guestman/shopman/guestman/contrib/consent/models.py:33`) — o model LGPD de verdade, com
canal (`:58`), status (`:64`), base legal (`:72`), IP (`:87`), `consented_at` (`:95`), `revoked_at`
(`:101`) e unique por (cliente, canal) (`:115-119`). O guestman ate entrega
`get_marketable_customers(channel)`, cuja docstring diz que serve para montar audiencia de campanha
(`contrib/consent/service.py:144-162`).

Consequencias: em producao **so assinante de alerta de estoque recebe**; favoritos e recompra resolvem
destinatarios e sao zerados. E um cliente que revoga WhatsApp na tela de conta **continua recebendo**,
porque a audiencia nunca le `CommunicationConsent`. Dois donos para um fato — o erro que a ADR-011
nomeou.

**Terceiro: o agendamento existe pela metade e mira o relogio errado.** `Trigger.SCHEDULED`
(`shopman/shop/models/broadcast.py:29`) **nao tem produtor**: os unicos chamadores de `evaluate()` sao
os tres receivers de signal (`handlers/broadcast.py:53`, `:71`, `:105`). E `schedule`
(`models/broadcast.py:123`) so sabe **adiar** post nascido de evento — `next_publish_at` devolve `None`
ou o inicio da proxima janela (`services/broadcast_schedule.py:34-57`); o `help_text` do campo promete
`{"type": "cron"}` (`:125`) que o parser nao implementa.

Pior, o disparo do que ja esta agendado anda na vassoura: `dispatch_scheduled_broadcasts` e o setimo de
onze comandos do `maintenance_worker` (`management/commands/maintenance_worker.py:48`), cujo `handle()`
roda o ciclo e **depois** dorme `interval` (`:74-80`, default 300s em `:62`). O periodo real e 300s
**mais** a duracao do ciclo — que inclui `reconcile_payments` falando com gateway. O docstring promete
"a cada 5 minutos" (`:4`) e o codigo garante "pelo menos 5 minutos de intervalo". Um `publish_at` de
17h30 sai depois disso.

Existe outro relogio, muito mais preciso e ja no ar: `process_directives --watch` roda com intervalo
default de **2 segundos** (`packages/orderman/shopman/orderman/management/commands/process_directives.py:89`,
piso 0.5s em `:130`) e esta no spec de deploy (`.do/app.staging-subdomains.yaml:627`).

**Quarto: recusa e vencimento sao indistinguiveis.** `discard()` grava `status = EXPIRED`
(`services/broadcast.py:380-387`). Nao existe `rejected_by`, nem motivo, nem estado proprio: post
recusado pelo gestor e igual a post que caducou no relogio.

**Quinto: ha flags que ninguem le.** `PostTemplate.use_ai_generation` e `ai_prompt`
(`models/broadcast.py:74-78`) sao gravados, exibidos no Admin e na projection, e **nunca lidos**:
`resolve_content` faz substituicao de `{{var}}` e nada mais (`services/broadcast.py:161-171`). Existe IA
real, em outro app: `ai_assist_field` (`shopman/backstage/services/catalog.py:752`). E
`get_adapter("posting", ...)` devolve sempre `None`, porque `"posting"` nao esta no mapa de settings
(`shopman/shop/adapters/__init__.py:26-36`), de modo que todo post externo fica `pending_manual`
(`handlers/broadcast.py:201-205`).

---

## Decisao

### 1. `Campaign`, `Announcement`, `AnnouncementTemplate`

| Hoje | Proposto | `verbose_name` |
|---|---|---|
| `BroadcastRule` | `Campaign` | "campanha" / "campanhas" |
| `BroadcastPost` | `Announcement` | "anuncio" / "anuncios" |
| `PostTemplate` | `AnnouncementTemplate` | "modelo de anuncio" |
| `PostStatus` | `AnnouncementStatus` | — |
| `shop.manage_broadcast` | `shop.manage_campaigns` | "Pode revisar e publicar campanhas" |
| `NotificationCategory.BROADCAST` | `CAMPAIGN` | "campanha" |
| `surfaces/broadcast-nuxt` | `surfaces/campaign-nuxt` | — |
| `SHOPMAN_BROADCAST_*` | `SHOPMAN_CAMPAIGN_*` | — |

`Campaign` nomeia o compromisso — *a loja se compromete a levar esta oferta a este publico nesta
janela* — e cobre igualmente o disparo unico, a recorrente e a regra permanente. `Announcement` nomeia
o fato, e nao e cosmetico: "post" e palavra do Instagram, e o mesmo registro dirige onda de WhatsApp e
banner de TV.

**Nome de app e nome de entidade sao niveis diferentes, e isso nao e conflito.** A secao visivel
continua "Marketing" (`projections/hub.py:82`) e o host publico passa a `mkt.`, exatamente como a secao
"Pedidos" contem `Order` e "Catalogo" contem `Product`. O operador dira "campanha" ao falar de uma
linha dentro do Marketing, que e o `verbose_name`. O nome da secao nao pode ser o nome de nenhuma das
tres entidades que ela abriga.

**Cinco strings persistidas que uma busca-e-substitui nao pega**, alem da permissao e do content type
que a ADR-011 §Negativas ja alertou (`adr-011:70`):

- prefixos de dedupe `f"broadcast:{pk}:{platform}"` e `f"broadcast:{pk}:wa:{...}"`
  (`services/broadcast.py:418`, `:455`) — linhas vivas sob unique parcial em `Directive.dedupe_key`
  (`packages/orderman/shopman/orderman/models/directive.py:52-60`)
- `action_url = f"/broadcast/posts/{pk}/"` (`services/broadcast.py:523`) — ja enviado a celulares;
  quem o captura e `surfaces/broadcast-nuxt/nuxt.config.ts:22-24`
- a chave `action_data["broadcast_post_id"]` (`services/broadcast.py:524`, lida em
  `shopman/backstage/api/notifications.py:136`)
- a chave do mapa de templates do ManyChat `"broadcast.post"`
  (`shopman/shop/adapters/notification_manychat.py:92`)
- a chave `broadcast_optin` (`services/audience.py:35`) — que **morre** pela decisao 3, e nao ha rename;
  renomea-la em vez de mata-la optaria todo mundo out em silencio

Nenhum *valor* de TextChoices contem "broadcast" exceto `NotificationCategory`: `Trigger` e `PostStatus`
sao palavras de dominio (`models/broadcast.py:25-29`, `:35-41`). E como a UI ja diz "Marketing", o
rename e **invisivel ao operador**.

### 2. Os topics de Directive nomeiam o fato, nao a intencao

`broadcast.post` -> **`announcement.publish`**; `broadcast.notify` -> **`announcement.notify`**
(`shopman/shop/directives.py:82-83`).

O payload e `{"post_id": ...}` (`services/broadcast.py:414-420`, `:447-461`) — pk de `Announcement`,
nao de `Campaign`. A constituicao §7.1 pede payload em linguagem de dominio; nomear o topic pela
intencao quando ele age sobre o fato desalinharia os dois.

### 3. Consentimento tem um dono: `CommunicationConsent`, por canal

`broadcast_optin` e **apagado** (`audience.py:34-35`), e a audiencia passa a consultar
`CommunicationConsent` pelo canal de entrega, via `ConsentService` — a exportacao de nivel de pacote que
`account.py:194` ja usa, e nao `contrib.consent.models`, para nao depender de interno de kernel.

Isso e mais que consertar um dono duplicado. Ganha-se: o toggle que o cliente ja usa na conta passa a
valer de fato; consentir WhatsApp deixa de ser o mesmo que consentir SMS (`ConsentChannel`,
`contrib/consent/models.py:7-13`); e vem base legal, IP e trilha de revogacao de graca — que e o que
LGPD pede e que `CustomerPreference` nao tem.

**A porta lateral do alerta de SKU permanece**, e por um motivo defensavel: `StockAlertSubscription`
para um SKU **e** consentimento explicito para aquele produto (`audience.py:348-350`). Ela nao vira
consentimento de marketing geral.

**Escolher a pessoa na tela nao dispensa consentimento.** `customer_refs` (decisao 7) passa pelo mesmo
filtro. O gestor escolhe *entre quem consentiu*, nunca *apesar de*.

Este e o passo que faz a campanha manual valer: sem ele, um disparo para clientes escolhidos a dedo
seria filtrado a zero.

### 4. `Campaign.promotion_ref` — ponteiro, nao JSON

```python
promotion_ref = models.CharField(max_length=64, blank=True, db_index=True)
```

A oferta e entidade e tem dono (ADR-019). A campanha **aponta**; nao reencoda. Ponteiro textual
indexado no formato da ADR-004, apontando para `Promotion.ref`.

Com isso o carrinho pre-montado sai de graca: os SKUs do prefill sao os `skus`/`collections` da propria
promocao (`shopman/shop/models/promotions.py` pos-ADR-019). A campanha nao repete a lista, nao repete o
desconto e nao repete a janela.

**Vazio e o caso mais comum**, nao a excecao: anuncio sem oferta ("saiu pao quente") e o que a fornada
dispara hoje. `promotion_ref` vazio le exatamente como e — anuncio sem promocao.

**Nao existe `Campaign.channel_ref`.** Canal e da oferta (`Promotion.channels`, ADR-019 §4). A campanha
tem `platforms` (onde anunciar) e `promotion_ref` (o que anunciar); a promocao apontada sabe em que
canais vale. Um dono por pergunta.

### 5. `Announcement.occurrence_key` — a unica coluna que se paga

```python
occurrence_key = models.CharField(max_length=128, blank=True, db_index=True)
# unique parcial quando != ""
```

Passa o criterio de query indexada e de idempotencia, no mesmo papel e na mesma forma de constraint
parcial de `Directive.dedupe_key` (`packages/orderman/.../models/directive.py:52-60`). Sem ela, armar
duas vezes a mesma ocorrencia gera dois anuncios da promocao das 17h30.

**Nao existe `Campaign.next_run_at`.** Seria cache de `schedule` + relogio — valor derivado com risco de
drift — justificado por um argumento de query indexada que nao se aplica nesta cardinalidade: uma
padaria tem dezenas de campanhas, nao milhoes. O comando de varredura filtra
`is_active=True, trigger=SCHEDULE` e avalia as janelas em Python com o codigo que ja existe
(`services/broadcast_schedule.py:34-57`), e "proxima vez 17h30" e calculado na projection — sempre
certo, sem coluna e sem segundo escritor.

### 6. A vassoura arma, a fila dispara

O vocabulario de `schedule` passa a distinguir adiar de disparar, sem overload:

```json
{"type": "immediate"}
{"type": "preferred_hours", "windows": [["07:00","11:00"]], "weekdays": [0,1,2,3,4,5]}
{"type": "once",      "at": "2026-08-15T07:00:00-03:00"}
{"type": "recurring", "windows": [["17:30","18:30"]], "weekdays": [4,5],
                      "starts_on": "2026-08-10", "ends_on": "2026-09-30"}
```

`immediate` e `preferred_hours` **adiam** (semantica atual, intocada). `once` e `recurring`
**disparam**, e sao validos so com `trigger=schedule`. `starts_on`/`ends_on` cobrem "periodo
especifico" sem terceiro tipo. As janelas continuam validadas por `_windows`
(`services/broadcast_schedule.py:111-125`), inclusive a recusa de janela que vira o dia.

**E o disparo nunca acontece na vassoura.** O comando de varredura apenas **arma**: cria uma `Directive`
com `available_at` no instante exato do inicio da janela. Quem dispara e
`process_directives --watch`, que roda a cada ~2 segundos. Latencia de armar e irrelevante (acontece na
hora anterior); latencia de disparar e de segundos.

Isso resolve a granularidade sem broker, sem tocar nenhum threshold da ADR-003, e usando o padrao que a
propria feature ja usa para o atraso da onda VIP (`create_deduped(..., available_at=...)`,
`services/broadcast.py:456-461`) e que o `PREORDER_ACTIVATE` estabeleceu (`directives.py:55`).

**Dois consertos vem no mesmo passo.** `dispatch_scheduled_broadcasts` sai da vassoura e passa a armar
Directive, e o `publish_at` para de mentir. E `handle()` do `maintenance_worker` passa a dormir
`interval - elapsed` (`maintenance_worker.py:74-80`), para "a cada 5 minutos" deixar de ser falso para
**todos** os crons.

### 7. `Trigger.MANUAL`, e o vocabulario de publico cresce sem motor novo

`Trigger.SCHEDULED` (`models/broadcast.py:29`), hoje escolha morta, e substituido por `MANUAL` e
`SCHEDULE`, ambos com produtor real: uma Action na superficie e o comando que arma.

`audience.resolve(sku, rules)` (`services/audience.py:151`) muda de assinatura, porque campanha manual
nao tem evento nem SKU:

```python
def resolve(rules: dict | None = None, *, sku: str = "") -> AudienceResult: ...
```

E `audience_rules` ganha chaves (identificadores em ingles, `help_text` em portugues):

| Chave | Fonte | Pergunta |
|---|---|---|
| `customer_refs` | `Customer.ref` | "estes clientes" — o gestor escolhe na tela |
| `groups` | `CustomerGroup.ref` | "so o grupo corporativo" |
| `rfm_segments` | `CustomerInsight.rfm_segment` | "champions e loyal" |
| `churn_risk_min` | `CustomerInsight.churn_risk` | win-back |
| `bought_skus` / `bought_collections` + `bought_within_days` | `CustomerInsight.favorite_products` | **"interesse genuino de consumo especifico"** |
| `birthday_today` | `Customer.birthday` | espelha `Promotion.birthday_only` |

Nada disso e model novo: sao irmaos de `_favorites`/`_pending_alerts`/`_recompra` no mesmo arquivo,
todos devolvendo `Recipient` (`:43-52`) e passando pelo mesmo `_merge` (`:454-479`) e pelo mesmo filtro
de consentimento (`:340-353`). **`CustomerInsight` ja e o motor de segmentacao**; construir um segundo
seria criar o terceiro dono de um fato que ja tem dois.

#### 7.1. O vocabulario `bought_*` mata o portugues que sobrou no codigo

A regra do projeto e clara: identificador, chave de JSON e valor de TextChoices em ingles; rotulo e
mensagem em portugues. Cinco pontos violam isso hoje, e um deles e **valor de string que viaja em
dado**:

| Hoje | Passa a ser |
|---|---|
| `_recompra()` (`services/audience.py:289`) | absorvido pelo resolvedor `bought_*` |
| chave `recompra_days` (`:177`, `models/broadcast.py:120`, migration `0023:45`) | `bought_within_days` |
| chave `recompra_count` (`:180`) | `bought_count` |
| `reason="recompra"` (`:181`), que entra em `Recipient.reasons` (`:48`) | `"bought"` |
| log `audience.recompra_failed` (`:303`) | `audience.bought_failed` |

**Nao e traducao, e a generalizacao que a §7 ja decidiu** — `recompra_days` estava preso ao SKU do
evento, e `bought_within_days` acompanha `bought_skus`/`bought_collections`. O predicado em ingles ja
existe no arquivo: `_bought_recently` (`:326`).

**E ha uma camada em Core.** `CustomerInsight.favorite_products` e documentado como
`{sku, nome, qtd, ultimo_pedido}`
(`packages/guestman/shopman/guestman/contrib/insights/models.py:66`), e o orquestrador le
`entry.get("ultimo_pedido")` (`services/audience.py:330`): **chaves JSON em portugues dentro de um
pacote core**. Viram `name`, `quantity` e `last_ordered_at`.

Essa e a **unica** mudanca em Core de todo este plano, e ela e barata por um motivo verificavel:
`favorite_products` e **derivado**, recomputado de pedidos por `_calculate_favorite_products`
(`contrib/insights/service.py:128`). Logo **nao ha data migration** — troca-se o escritor, o unico
leitor no orquestrador, e recomputa-se. A consulta existente `favorite_products__contains=[{"sku":
sku}]` (`service.py:195`) sobrevive intacta, porque `sku` ja estava em ingles. Depois do go-live a
ADR-015 transformaria isso em expand-contract com janela de alias.

Copy voltada ao cliente **nao muda**: `shopman/storefront/api/surface.py:207` e `:369` dizem
"recompra" em portugues para o cliente ler, e e isso que a regra manda.

**`audience_rules` e vocabulario fechado e plano.** Sem AND/OR aninhado, sem construtor de segmento
arbitrario. No dia em que alguem precisar de arvore booleana, o que esta sendo construido e um CDP, e a
resposta e nao.

### 8. Quem cria publica; recusa vira estado de verdade

`requires_approval` (`models/broadcast.py:127`) continua valendo para o que a operacao gerou sozinha —
fornada, estoque baixo, produto novo. Campanha que o gestor escreveu **publica direto**: nao ha segundo
par de olhos quando o autor e o revisor.

E `discard()` para de colapsar em `EXPIRED` (`services/broadcast.py:380-387`).
`AnnouncementStatus.REJECTED` nasce como estado proprio, com `rejected_by` e `rejected_reason`. Recusa e
fato observavel distinto de vencimento no relogio (constituicao §2.4), e sem isso o Admin nao consegue
responder "quantos anuncios o gestor recusou, e por que".

### 9. A oferta e anunciada, nao construida: `Action` com link nao autenticado

**A campanha emite uma `Action`. Ela nao cria carrinho.** A ADR-012 lista o contrario em "nao
aceitamos" (`adr-012:111`, `:115`): *"Criar `RemoteOrder`, status remoto ou lifecycle paralelo"* e
*"Duplicar pricing, stock, payment gate, timers, availability"*.

Tres razoes concretas. `Session` e estado de sessao, chaveada por `session_key` + `channel_ref`, nao de
pessoa — montar 40 carrinhos cria 40 sessoes orfas que `cleanup_stale_sessions` depois varre.
`cart.add_item` chama `_reserve_or_raise` (`shopman/shop/services/cart.py:377`), que **toma hold no
Stockman**: marketing segurando pao para quem nunca clicou promete a um e nega a outro. E o preco
envelheceria entre o envio e o clique.

O precedente certo ja existe e e o **reorder**: uma `Action` no contrato da ADR-012
(`ref`/`kind`/`label`/`href`/`method`/`payload_schema`/`idempotency`, `adr-012:73`, `:78-79`), como em
`shopman/storefront/presentation/home.py:346-360`, cujo clique executa `add_reorder_items`
(`shopman/shop/services/customer_orders.py:530-568`) — que **re-resolve o preco no momento do clique**
(`:549`), **pula o que nao e vendavel** (`:545-548`) e **pula o que o Stockman recusa** (`:558-560`),
devolvendo os descartados para a superficie explicar.

**O `href` e um deep link NAO autenticado.** Nao se usa `build_access_url`
(`shopman/shop/services/access_urls.py:30-67`): `AccessLink` expira em **5 minutos** por default
(`packages/doorman/shopman/doorman/conf.py:6`, `:24`) e e single-use
(`packages/doorman/shopman/doorman/models/access_link.py:149`, `:153`). Mensagem de marketing dorme
horas no WhatsApp — o link morreria antes do clique. Os usos atuais sao transacionais (acompanhamento,
pagamento), clicados em minutos.

E a correcao **nao** e aumentar o TTL para campanha: isso espalharia N links de concessao de sessao, de
vida longa, em historicos de conversa que sao encaminhados e printados. Troca ruim para uma promo. O
link carrega a promocao; a autenticacao acontece onde ja acontece, no checkout. Ninguem precisa estar
logado para encher uma sacola.

### 10. `platforms` fica, sem `tv`; o adapter de posting e registrado

`platforms` (`models/broadcast.py:114-117`) **nao e renomeado**. Com a ADR-018 eliminando
`CatalogSyncState.platform` e o `?platform=`, ele passa a ser o unico uso da palavra, e a lista que ele
carrega — `instagram`, `facebook`, `google_business`, `whatsapp` — sao mesmo plataformas.

**`tv` sai da lista.** A TV mostra a promocao porque a promocao **vale naquele canal**
(`Promotion.channels` incluindo o menuboard, ADR-018 + ADR-019), nao porque um anuncio a escolheu como
destino. Isso explica por que o canal SSE `broadcast-tv` (`services/broadcast.py:482-483`) tem **zero
consumidores** em todo o repo: estava resolvendo um problema que o modelo de canal resolve. `_push_tv`
(`:466-491`) e o canal orfao saem, e a lista fica homogenea — so envio externo.

O conserto real nao e de nome: `POSTING_PLATFORMS` como tupla hardcoded (`services/broadcast.py:42`)
com tres ramos de despacho vira o registro da costura `posting` que **ja existe** e so nao esta no mapa
(`shopman/shop/adapters/__init__.py:26-36`), de modo que `get_adapter("posting", method=...)`
(`handlers/broadcast.py:280`) pare de devolver `None`. Sem taxonomia nova.

### 11. Copy com IA e adapter, e a voz da marca sai do codigo

`use_ai_generation` e `ai_prompt` (`models/broadcast.py:74-78`) ganham leitor ou saem. Ganham.

**Nao e superficie.** O texto que o cliente le e **dado**: entra em `Announcement.content["body"]`, e
aprovado, e despachado, e auditavel. Superficie que gerasse copy inventaria conteudo de marca, contra a
ADR-012.

**Nao e core.** Nenhum pacote de `packages/` pode nascer dependendo de provedor de LLM (ADR-001 §4;
constituicao §10).

**E adapter no orquestrador**, e agora ha razao concreta no sentido da ADR-001 §3: uma implementacao
real, um estado desligado real e **dois chamadores**. O que existe em
`shopman/backstage/services/catalog.py:636-798` e extraido para
`shopman/shop/adapters/copy_assist.py` com assinatura minima
`suggest(prompt, *, system, max_tokens) -> str`, e catalogo e campanha passam a consumir. Nao e backend
"para o futuro"; e o backend que ja existe ganhando o segundo cliente. O registro por campo
(`_AI_ASSIST_FIELDS`, `:653-700`) e a forma certa e se mantem — o contexto e que precisa deixar de ser
acoplado a `Product` (`_ai_assist_context`, `:705-730`).

**A voz da marca vira dado.** `_AI_ASSIST_VOICE` (`:644-650`) codifica "Nelson Boulangerie", "padaria
artesanal brasileira", "primeira pessoa do plural" — default de instancia com aparencia de verdade do
produto, que a constituicao §2.6 e §10 recusam. Vira campo em `Shop`, ao lado de `tagline` e
`description` (`shopman/shop/models/shop.py:134-137`):

```python
brand_voice = models.TextField(_("voz da marca"), blank=True)
```

Um dono, dois consumidores, editavel no Admin.

**A geracao roda no momento da revisao, nunca dentro de `evaluate()`.** `evaluate` executa em
`transaction.on_commit` do finish da fornada (`handlers/broadcast.py:119-120`) e o handler jura nao
derrubar quem disparou. Uma chamada de rede de segundos ali penaliza o operador que esta com o pao na
mao. Se algum dia houver auto-post com IA, o caminho e uma Directive, nao chamada inline.

**Arte gerada por IA fica fora.** Foto de produto e ativo real; imagem sintetica de um pao que nao e
aquele pao e o sistema mentindo sobre o mundo (§2.3) e contradiz o que a spec ja decidiu
(`FOMO-BROADCAST-SPECS.md:667`: *"FOMO falso destroi confianca"*). Cabe **selecao** e **recorte** de
foto existente, nunca sintese.

### 12. Nenhum numero vira B.I.

Reafirmando o veto (ADR-017 §8): os quatro numeros do painel
(`shopman/backstage/projections/broadcast.py:85-92`) sao **contagens operacionais** — quantas decisoes
esperam, quantas sairam, quantas falharam. Ficam exatamente esses quatro. Impressoes, curtidas,
alcance, CTR e funil de UTM: nao. O parametro UTM no deep link continua permitido **como parametro**; um
relatorio construido sobre ele e o B.I. vetado.

Sem A/B test e sem otimizacao de horario alem do `preferred_hour` que ja existe
(`services/audience.py:217-238`): otimizar horario sem medir conversao e supersticao, e medir conversao
e B.I.

**Sem lista de destinatarios persistida.** A regra atual (`models/broadcast.py:180-183`, *"So contagens
— a lista de destinatarios nunca e persistida aqui"*) vale para as fontes novas tambem; a lista e
recalculada no despacho (`handlers/broadcast.py:229-248`).

---

## Consequencias

### Positivas

- O nome para de mentir antes de existir consumidor externo, e o rename e invisivel ao operador.
- Consentimento passa a ter um dono, com base legal e trilha de revogacao — e o toggle do cliente
  passa a valer.
- A campanha manual funciona de verdade, em vez de disparar para zero pessoa.
- Relampago das 17h30 sai em segundos, sem broker e sem tocar a ADR-003.
- Zero tabela nova. Duas colunas: `Campaign.promotion_ref` e `Announcement.occurrence_key` — ambas
  ponteiro/chave.
- Somem: `Trigger.SCHEDULED` sem produtor, `broadcast_optin` sem escritor, `_push_tv` sem consumidor,
  o canal SSE `broadcast-tv`, a tupla `POSTING_PLATFORMS`, e o `help_text` que prometia cron.
- O catalogo herda voz de marca editavel ao ganhar o adapter de copy.
- `publish_at` para de mentir para todo mundo, nao so para campanha.

### Negativas

- Rename amplo: ~380 pontos de codigo de producao e ~230 de teste, mais cinco data migrations de string
  persistida e uma de permissao/content type.
- Trocar o dono do consentimento significa que quem tinha `broadcast_optin` criado a mao no Admin
  precisa de migracao para `CommunicationConsent`, senao sai da audiencia.
- `audience.resolve()` muda de assinatura; todo chamador e teste acompanha.
- Extrair o adapter de copy mexe numa tela de catalogo que funciona.
- O resolvedor de recompra carrega todos os `CustomerInsight` e filtra em Python
  (`services/audience.py:298-309`), e com `bought_collections` a conta cresce. **Medido em 2026-08-08:
  13 clientes, 6 insights.** Nesta escala — e em qualquer escala plausivel para uma padaria — a
  varredura em Python custa milissegundos, algumas vezes por dia. **Nao se cria indice para isso**
  (ver Alternativas descartadas), e jamais uma tabela desnormalizada de cliente x sku, que seria
  warehouse.

### Mitigacoes

- A janela e agora: `go-live-v1` nao existe (a tag mais avancada e `v0.1.0-alpha`), logo a ADR-015 nao
  vigora e o rename e barato. Depois do alpha, exige janela de alias e dois deploys.
- A migracao de consentimento e verificavel: contagem de destinatarios elegiveis por canal antes e
  depois.
- O rename e mecanico e concentrado: cinco arquivos respondem por metade das ocorrencias
  (`tests/test_broadcast.py`, `backstage/api/broadcast.py`, `services/broadcast.py`,
  `handlers/broadcast.py`, `backstage/projections/broadcast.py`).
- `promotion_ref` vazio preserva exatamente o comportamento atual de anuncio de fornada.

---

## Invariantes

- Campanha nunca escreve preco, nunca segura estoque, nunca cria pedido, nunca cria carrinho.
- A campanha aponta para a promocao (`promotion_ref`); nunca reencoda oferta, desconto ou janela.
- Nao existe `Campaign.channel_ref`. Canal e da promocao.
- Nao existe `Campaign.next_run_at`. A proxima ocorrencia e calculada, nunca armazenada.
- Uma ocorrencia, um anuncio: `Announcement.occurrence_key` sob unique parcial.
- Consentimento de marketing tem um dono: `CommunicationConsent`, por canal, lido via `ConsentService`.
- Escolher a pessoa na tela nao dispensa consentimento. A unica porta lateral e
  `StockAlertSubscription`, e vale so para o SKU assinado.
- Lista de destinatarios nunca e persistida. So contagens.
- Um destinatario por telefone.
- Disparo agendado nunca acontece na vassoura: a vassoura arma uma Directive, a fila dispara.
- `audience_rules` e vocabulario fechado e plano. Sem AND/OR aninhado.
- Geracao de copy nunca roda dentro de `evaluate()`.
- Voz da marca vive em `Shop`, nunca em constante de codigo.
- Nao ha sintese de imagem: so selecao e recorte de foto real.
- Recusa e vencimento sao estados distintos.
- Nao existe tabela de agregacao, snapshot, warehouse ou grafico. As contagens do painel sao quatro.

---

## Migracao

Ordem obrigatoria; cada passo entrega valor sozinho e passa `make test`.

1. **Consentimento.** `audience.py` passa a ler `CommunicationConsent` via `ConsentService`;
   `broadcast_optin` e apagado, com data migration convertendo qualquer linha existente. **Vem
   primeiro**, porque sem ele todo o resto dispara para ninguem.
2. **Rename.** Models, permissao, content type, topics de Directive, categoria de notificacao,
   diretorio da superficie, settings, e as cinco strings persistidas do item 1 da Decisao. Zero
   mudanca de comportamento.
3. **Disparo manual.** `Trigger.MANUAL`; `audience.resolve()` muda de assinatura; `audience_rules`
   ganha as seis chaves novas; Action "Criar campanha" na superficie. Sem IA, sem oferta.
4. **Agendamento.** `once`/`recurring` em `schedule`; `Announcement.occurrence_key` com unique
   parcial; o comando de varredura passa a **armar** Directive; `dispatch_scheduled_broadcasts` sai da
   vassoura; `handle()` do worker passa a `sleep(interval - elapsed)`.
5. **Recusa.** `AnnouncementStatus.REJECTED`, `rejected_by`, `rejected_reason`; campanha criada pelo
   gestor pula aprovacao.
6. **Oferta acionavel.** `Campaign.promotion_ref`; `Action` em `Announcement.content["actions"]`;
   endpoint no idioma do reorder; deep link nao autenticado. Depende da ADR-019.
7. **Copy com IA.** `shopman/shop/adapters/copy_assist.py` extraido; `Shop.brand_voice`;
   `use_ai_generation`/`ai_prompt` ganham leitor no momento da revisao; catalogo passa a consumir o
   adapter.
8. **Posting externo.** Registrar `"posting"` no mapa de adapters e implementar
   `posting_meta`/`posting_google`, gated por credencial. Escopo ja definido em
   `FOMO-BROADCAST-SPECS.md` §5 e §7.

---

## Criterios de aceite

- `make test` e `make admin` verdes; `make test-migrations` verde do zero.
- `grep -ri "broadcast" shopman/ surfaces/ config/` retorna vazio, com duas ressalvas legítimas: as
  **migrations do próprio rename**, que precisam citar o nome antigo para renomeá-lo, e o nome do
  documento histórico `FOMO-BROADCAST-SPECS.md`, que não muda (é registro, não código).
- `grep -rn "broadcast_optin\|Trigger.SCHEDULED\|POSTING_PLATFORMS\|_push_tv\|broadcast-tv"` retorna
  vazio.
- Cliente que revoga WhatsApp na tela de conta deixa de receber campanha no disparo seguinte.
- Cliente sem `CommunicationConsent` de WhatsApp nao recebe, mesmo escolhido a dedo em
  `customer_refs`.
- Cliente com `StockAlertSubscription` de um SKU recebe o anuncio daquele SKU sem consentimento geral,
  e **nao** recebe campanha de outro SKU.
- Campanha `recurring` com janela 17h30-18h30: o anuncio e criado com `published_at` a menos de 10
  segundos de 17h30.
- Rodar o comando de varredura duas vezes na mesma janela produz **um** anuncio.
- Campanha criada pelo gestor publica sem passar por `pending_review`; regra de fornada continua
  passando.
- `discard` produz `REJECTED` com autor e motivo; anuncio caducado produz `EXPIRED`. Os dois sao
  distinguiveis em query.
- Clique na Action monta carrinho com preco resolvido no clique, pula item nao vendavel e devolve os
  descartados — sem nenhum hold criado antes do clique.
- Nenhum `AccessLink` e criado no despacho de campanha.
- `Announcement.audience` contem apenas contagens; nenhum telefone persistido.
- Alterar `Shop.brand_voice` muda a sugestao de copy do catalogo e da campanha.

---

## Alternativas descartadas

**Manter `broadcast`.** O nome descreve o transporte de metade dos casos e nomeia o empurrao esquecendo
o retorno — o oposto da `Action` da ADR-012. E o custo cresce monotonicamente a partir da tag.

**`marketing` como identificador.** E departamento, nao compromisso: inbox, DM, comunidade e analytics
cabem todos em "Marketing", e e essa deriva que a spec proibe
(`FOMO-BROADCAST-SPECS.md:37-38`). Serve como rotulo da secao, jamais como nome de entidade.

**`announcement` como nome do app.** Nomeia o artefato, nao a intencao — e a intencao e o que o gestor
cria. Como rotulo PT, "anuncio" colide com midia paga na cabeca do operador. Fica como o nome do
**fato**, onde e preciso.

**Uma tabela `FlashPromotion`.** Duplicaria `Promotion`, que ja tem janela, SKU, colecao, segmento e
minimo. Seria o `FormulaPlan` da ADR-011 outra vez. Promocao relampago e **uma `Promotion` (o
desconto) + uma `Campaign` (o anuncio)**.

**Uma tabela `CampaignOccurrence`.** Falha na cardinalidade: existe exatamente *uma* proxima ocorrencia
por campanha, e a query indexada e satisfeita por nada — a varredura avalia dezenas de linhas.

**Uma tabela `CampaignAudience` com destinatarios materializados.** Contraindicada: persistir telefone e
PII que o codigo hoje evita de proposito (`models/broadcast.py:180-183`).

**`Campaign.next_run_at` como coluna.** Cache de um valor derivado, com segundo escritor a policiar e
drift a debugar, para resolver um problema de escala que uma padaria nao tem.

**Criar carrinho no envio.** Recusado pela ADR-012 em tantas palavras, e tomaria hold no Stockman para
quem nunca clicou.

**`build_access_url` na Action da campanha.** Morreria pelo TTL de 5 minutos, e aumentar o TTL
espalharia links de concessao de sessao, de vida longa, em historico de WhatsApp encaminhavel.

**Renomear `platforms` para `destinations`, com `DestinationKind`.** O `kind` nao e dado: Instagram e
sempre `post`, WhatsApp e sempre `message`. E registry, nao campo de model. E depois da ADR-018 a
palavra "platform" para de colidir, entao o rename ficaria apoiado so em estetica. O que precisava
mudar era o despacho — tupla hardcoded virando a costura `posting` que ja existe.

**Manter `tv` como plataforma de anuncio.** Recria a colisao que a ADR-018 acabou de matar: ref de canal
dentro de um campo de plataformas. E era dead code — zero consumidores do canal SSE.

**Gerar copy dentro de `evaluate()`.** Poria uma chamada de rede de segundos no `on_commit` do finish
da fornada, penalizando o operador que esta com o pao na mao.

---

## Referencias

- [Constituicao Semantica](../constitution.md) — §2.2, §2.3, §2.4, §2.6, §3.1, §5, §7.1, §8.3, §10
- [ADR-001 - Protocol/Adapter e fronteiras de core](adr-001-protocol-adapter.md)
- [ADR-003 - Directives sem Celery](adr-003-directives-sem-celery.md)
- [ADR-004 - String refs para identificadores cross-domain](adr-004-string-refs.md)
- [ADR-009 - WhatsApp via ManyChat](adr-009-whatsapp-via-manychat.md)
- [ADR-011 - Formula sem FormulaPlan](adr-011-formula-and-cashshift.md)
- [ADR-012 - Contrato headless de superficie](adr-012-headless-surface-contract.md)
- [ADR-014 - Corte dado/apresentacao](adr-014-surface-data-presentation-cut.md)
- [ADR-015 - Backward-compat pos-producao](adr-015-backward-compat-policy-post-prod.md)
- [ADR-016 - Tempo real por SSE](adr-016-sse-first-realtime.md)
- [ADR-017 - Qualidade e o resultado da producao](adr-017-quality-as-production-outcome.md)
- [ADR-018 - Superficie e canal, com politica comercial](adr-018-surface-is-channel-with-commerce-policy.md)
- [ADR-019 - A promocao tem um dono](adr-019-promotion-belongs-to-the-orchestrator.md)
- [FOMO-BROADCAST-SPECS](../plans/FOMO-BROADCAST-SPECS.md)
