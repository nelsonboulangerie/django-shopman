# Plano de evolução do Broadcast — rename, ontologia e oferta acionável

> **SUPERADO em 2026-08-08.** As decisões foram tomadas nas
> [ADR-018](../decisions/adr-018-surface-is-channel-with-commerce-policy.md),
> [ADR-019](../decisions/adr-019-promotion-belongs-to-the-orchestrator.md) e
> [ADR-020](../decisions/adr-020-campaign-announces-it-does-not-sell.md), e a execução vive em
> [SURFACE-OFFER-CAMPAIGN-PLAN](SURFACE-OFFER-CAMPAIGN-PLAN.md). Este arquivo fica como registro do
> levantamento original. **Parte dele está factualmente errada** — em particular o §5.4 (frete grátis
> existe por zona e por distância, não só por limiar) e as citações de `config/settings.py` e
> `shopman/shop/modifiers.py`, deslocadas 76–95 linhas. O §0 do plano novo lista as correções.

**Status:** Superado (era: proposta de plano, sem implementação)
**Data:** 2026-08-07
**Escopo:** `shopman/shop` (models/services/handlers de broadcast), `shopman/backstage`
(API + projections), `surfaces/broadcast-nuxt`, e as fronteiras com `guestman`,
`offerman`, `orderman` e o motor de pricing.
**Refina:** [FOMO-BROADCAST-SPECS](FOMO-BROADCAST-SPECS.md) §2, §3, §4, §7 e §9.
**Não reabre:** o veto a B.I. (ADR-017 §8) nem o "não é um Hootsuite"
(FOMO-BROADCAST-SPECS:37-38).

---

## 0. O pedido do dono, traduzido

O dono pede quatro coisas que o sistema hoje não faz, e uma que ele faz sob outro nome:

| Pedido (palavras dele) | Estado real no código |
|---|---|
| "renomear logo, antes do alpha" | `go-live-v1` não existe (`git tag -l`: o mais avançado é `v0.1.0-alpha`). ADR-015 ainda não vigora. |
| "disparo específico, para clientes específicos, com filtros de skus/coleções/canais" | `Trigger.SCHEDULED` existe (`shopman/shop/models/broadcast.py:29`) mas **não tem produtor**: o único chamador de `evaluate()` é `shopman/shop/handlers/broadcast.py:127`, com `production_finished`, `low_stock`, `stock_back` e `product_created`. |
| "faixa de horário, única, recorrente ou período específico" | `BroadcastRule.schedule` (`shopman/shop/models/broadcast.py:123`) só entende `immediate` e `preferred_hours`, e `preferred_hours` **adia** um post nascido de evento — não dispara nada (`shopman/shop/services/broadcast_schedule.py:34-57`). |
| "arte + copy com IA, dados da empresa, voz da marca" | `PostTemplate.use_ai_generation` e `ai_prompt` existem (`shopman/shop/models/broadcast.py:74-78`) e **ninguém lê**: `resolve_content` só faz substituição de `{{var}}` (`shopman/shop/services/broadcast.py:161-171`). Existe IA real, mas em outro app: `ai_assist_field` (`shopman/backstage/services/catalog.py:753`). |
| "criar um carrinho com entrega grátis já definida, endereço sugerido" | Carrinho é `orderman.Session` (`packages/orderman/shopman/orderman/models/session.py:76`), criado por `shopman/shop/services/cart.py:68`. Entrega grátis existe **só** por limiar de subtotal (`shopman/shop/modifiers.py:1002-1015`). Endereço já é sugerido no checkout (`shopman/shop/services/checkout_defaults.py:47-63`). |

O que já existe e é bom não está em disputa: `matches_filter` (`shopman/shop/services/broadcast.py:114-140`),
o resolvedor de audiência com opt-in e ondas (`shopman/shop/services/audience.py:151-214`),
o despacho por Directive com dedupe (`shopman/shop/services/broadcast.py:414-463`), a
expiração do post pendente (`:595-602`) e a superfície de revisão (`surfaces/broadcast-nuxt`).

---

## 1. O rename

### 1.1. O que "broadcast" erra

`broadcast` é **transporte**, não compromisso. Descreve como bytes saem (um-para-muitos),
como `sync`, `bridge` e `integration_data` na lista de nomes a evitar da constituição §2.2
e §5.2. Três consequências concretas:

1. **Colide dentro e fora do repo.** `grep -ri broadcast` devolve `socketio`, `gevent`,
   `redis`, `twisted` e `psutil` no venv; dentro do repo, "broadcast" também é o verbo do
   SSE (`send_event` em `shopman/shop/services/broadcast.py:481`) e o nome da API do
   ManyChat (ADR-009:22). Um nome de domínio não deve disputar espaço com o nome do canal.
2. **Descreve mal metade do que o app já faz.** Uma onda de WhatsApp é broadcast. Um
   `localPost` de Google Business é *colocação*, não transmissão. Um banner na TV da loja
   (`_push_tv`, `shopman/shop/services/broadcast.py:466`) é sinalização. E o carrinho
   pré-montado que o dono quer não é broadcast de coisa nenhuma.
3. **Não carrega a ação.** O que o dono descreve termina num clique do cliente. "Broadcast"
   nomeia o empurrão e esquece o retorno — exatamente o oposto da `Action` da ADR-012.

O rótulo em português já discorda do identificador: o Hub mostra **"Marketing"**
(`shopman/backstage/projections/hub.py:82`). O código diz `broadcast`, a tela diz Marketing,
o README da superfície diz "gestor de marketing". Três palavras para uma coisa.

### 1.2. Candidatos

| # | Candidato | Julgamento (§2.2 nome de compromisso; §5 léxico) |
|---|---|---|
| 1 | `marketing` | **Rejeitado.** É departamento, não compromisso. Um nome de departamento não tem fronteira: inbox, DM, comunidade e analytics cabem todos em "Marketing", e é justamente essa deriva que FOMO-BROADCAST-SPECS:37-38 proíbe. Serve como *rótulo* PT no Hub, jamais como identificador. |
| 2 | `broadcast` (status quo) | **Rejeitado.** §1.1. |
| 3 | `campaign` | **Recomendado.** Nomeia o compromisso: *a loja se compromete a levar esta oferta a este público nesta janela*. É palavra de negócio, não de implementação — não pertence à família `helper`/`bridge`/`sync`. Cobre igualmente o disparo único, a promoção recorrente e a regra permanente ("always-on"). Risco real: puxa CRM, atribuição e A/B. Contido por invariantes explícitas (§7). |
| 4 | `announcement` | **Rejeitado como nome do app, adotado como nome da entidade de fato.** Nomeia o *artefato* ("o que foi anunciado"), não a intenção — e a intenção é o que o gestor cria. Como rótulo PT, "anúncio" colide com mídia paga (Google Ads) na cabeça do operador. Como model, é preciso e auditável. |
| 5 | `outreach` | **Rejeitado.** Jargão de CRM; nomeia *esforço*, não compromisso. E "reach out" sugere via de mão dupla — abre a porta do inbox que decidimos não ter. |
| 6 | `herald` | **Rejeitado.** Bonito e inútil: continua sendo o transporte (quem grita), sem cognato operacional em PT-BR e com descoberta pior que `broadcast`. |

### 1.3. Recomendação

**Nome do app/subsistema: `campaign`.** Pergunta canônica, no formato da constituição §4:

> Que oferta a operação quer levar a quem, em que momento, e com qual ação de menor fricção?

Mapa de rename (identificadores em inglês; rótulos em português):

| Hoje | Proposto | Rótulo PT (`verbose_name`) |
|---|---|---|
| `BroadcastRule` | `Campaign` | "campanha" / "campanhas" |
| `BroadcastPost` | `Announcement` | "anúncio" / "anúncios" |
| `PostTemplate` | `AnnouncementTemplate` | "modelo de anúncio" |
| `PostStatus` | `AnnouncementStatus` | — |
| perm. `shop.manage_broadcast` | `shop.manage_campaigns` | "Pode revisar e publicar campanhas" |
| topic `broadcast.post` | `campaign.publish` | — |
| topic `broadcast.notify` | `campaign.notify` | — |
| canal SSE `broadcast-tv` | `campaign-tv` | — |
| `surfaces/broadcast-nuxt` | `surfaces/campaign-nuxt` | tile do Hub segue "Marketing" |
| `NotificationCategory.BROADCAST` | `CAMPAIGN` | "campanha" |
| `SHOPMAN_BROADCAST_META`, `SHOPMAN_BROADCAST_BASE_URL` | `SHOPMAN_CAMPAIGN_*` | — |

`BroadcastPost` → `Announcement` não é cosmético: "post" é palavra do Instagram, e o mesmo
registro também dirige a onda de WhatsApp (`shopman/shop/handlers/broadcast.py:219-256`) e
o banner da TV (`shopman/shop/services/broadcast.py:466-491`), que não são posts. O nome
atual força a superfície a chamar de "post" um SMS.

### 1.4. Custo real

Contagem no branch `qa/alpha-08-validade` (exclui `.venv`):

| Alvo | Arquivos | Ocorrências |
|---|---|---|
| Python (fora de `migrations/`) | 41 | 613 |
| Migrations que citam broadcast | 3 (`0023_posttemplate_broadcastrule_broadcastpost_and_more.py`, `0024_broadcastpost_publish_at_and_more.py`, `0025_shop_realtime_cadence.py`) | — |
| `surfaces/broadcast-nuxt` (app/server/tests/config/README) | 18 | 125 |
| `docs/` | 13 | — |
| Outros | `.github/workflows/surfaces-gate.yml`, `CLAUDE.md`, `README.md` | — |

Concentração: 5 arquivos respondem por metade das ocorrências —
`shopman/shop/tests/test_broadcast.py` (111), `shopman/backstage/api/broadcast.py` (66),
`shopman/shop/services/broadcast.py` (64), `shopman/shop/handlers/broadcast.py` (28),
`shopman/backstage/projections/broadcast.py` (28).

**Pontos que não são busca-e-substitui:**

- **Content types e permissões.** ADR-011 §Negativas registra exatamente esta armadilha:
  *"Migracao de permissoes precisa cuidado porque permissoes Django dependem de content
  type."* `manage_broadcast` está em `BroadcastRule.Meta.permissions`
  (`shopman/shop/models/broadcast.py:150-152`), é lido em `shopman/backstage/permissions.py:83`,
  atribuído em `shopman/shop/management/commands/setup_groups.py:54` e consultado por
  `_reviewers` (`shopman/shop/services/broadcast.py:544-546`). Renomear o model muda o
  `content_type`; renomear o codename muda a linha de `auth_permission`. Grupos já criados
  perdem a permissão se a data migration não reatribuir.
- **`shop.manage_broadcast` como string literal** aparece em `required_permission`
  (`shopman/backstage/api/broadcast.py:51`) e nos testes de superfície — string, não símbolo.
- **`scripts/check_unfold_canonical.py:239-249`** referencia o caminho do arquivo de
  projection por path literal.
- **Deploy:** `SHOPMAN_SURFACE_URLS["broadcast"]` (`config/settings.py:1278`) e o host
  público `broadcast.` — o README da superfície já avisa que o host nunca é hardcoded
  (`surfaces/broadcast-nuxt/README.md`), então o host pode sobreviver ao rename do diretório
  se o cutover de DNS for indesejado agora.

**Por que agora é barato.** `go-live-v1` não existe. A ADR-015 só entra em vigor na tag
(ADR-015:3), e até lá valem as duas regras do `CLAUDE.md` que ela cita: *"migrações serão
resetadas"* e *"zero backward-compat aliases"*. Logo o caminho correto é **reset/squash das
3 migrations de broadcast + data migration de permissão**, não expand-contract. Depois do
alpha, o mesmo rename exige janela de alias e dois deploys (ADR-015 §2) — é o mesmo
argumento que a ADR-017 §Mitigações usou para justificar renomear os graus de qualidade agora.

Estimativa: uma passada mecânica + revisão de 5 arquivos densos + 1 data migration de
permissão + `make test`. É trabalho de horas, não de dias, e o custo cresce monotonicamente
a partir da tag.

---

## 2. A ontologia

### 2.1. O que `BroadcastRule` já é

`BroadcastRule` (`shopman/shop/models/broadcast.py:101-156`) já carrega seis eixos:

- **quando** — `trigger` (`:105`), enum fechado (`:22-29`)
- **se** — `trigger_filter` (`:106`): `collections`, `skus`, `quality_min`, `max_remaining`
  (`shopman/shop/services/broadcast.py:114-140`)
- **para quem** — `audience_rules` (`:118`): `favorites`, `alerts`, `recompra_days`,
  `vip_first_minutes`, `preferred_hour_window_hours` (`shopman/shop/services/audience.py:151-200`)
- **onde** — `platforms` (`:114`)
- **o quê** — FK `template` (`:110`)
- **governança** — `requires_approval` (`:127`), `expires_after_minutes` (`:131`),
  `notify_users` (`:136`), `is_active` (`:141`)

Ou seja: a entidade de intenção já existe e já é genérica. O que falta não é uma entidade —
são **valores** em três desses eixos.

### 2.2. Aplicando §8.3 a cada pedido

> *isto é core do domínio? plugin do domínio? conveniência de framework?*
> Se a resposta for "não sei", ainda não deve entrar.

| Pedido | É entidade nova? | Onde mora |
|---|---|---|
| **Disparo manual pontual** | Não. É `evaluate()` chamado por um operador em vez de por um signal. O slot já existe e está vazio (`Trigger.SCHEDULED` sem produtor). | `Trigger.MANUAL` + uma Action na superfície. |
| **Campanha única com data/hora** | Não. Uma ocorrência futura é *recalculável* da regra + relógio; só a ocorrência que aconteceu é fato — e ela já tem tabela (`BroadcastPost`). É o mesmo argumento da ADR-011 §2 contra `FormulaPlan`: *"Sugestoes recalculaveis nao sao dados operacionais ate o operador aceitar."* | `Campaign.schedule` (spec) + `Campaign.next_run_at` (uma coluna indexada). |
| **Promoção relâmpago recorrente** | Não, **e mais importante: o desconto não é dela.** O desconto já tem dono: `Promotion` (`shopman/storefront/models/promotions.py:8-64`), com `valid_from`/`valid_until`/`skus`/`collections`/`customer_segments`/`min_order_q`, aplicado por `PromotionRule` (`shopman/shop/rules/pricing.py:71`) e pelo `DiscountModifier` (`shopman/shop/modifiers.py:367`). Recorrência de horário já existe como `HappyHourRule` + `TimeWindowDiscountModifier` (`shopman/shop/rules/pricing.py:96`, `shopman/shop/modifiers.py:322`) parametrizados por `RuleConfig` com escopo de canal (`shopman/shop/models/rules.py:39`). Criar um `FlashPromotion` seria um **segundo source of truth de preço** — o erro exato que a ADR-011 nomeou. | Promoção relâmpago = **uma `Promotion`/`RuleConfig` (o desconto) + uma `Campaign` (o anúncio)**. A campanha *aponta* para o desconto; nunca o reimplementa. |
| **Oferta atrelada (carrinho + frete)** | Não. Ver §5. | `Campaign.offer` (JSON) + `Action` no `Announcement`. |
| **Clientes específicos** | Não. Ver §3. | Vocabulário novo em `audience_rules`. |

### 2.3. Teste dos quatro critérios

Os quatro critérios formulados na ADR-017 §2 (citando o ADR-006 arquivado) — **histórico,
auditoria, query indexada, cardinalidade > 1** — aplicados às tabelas que alguém sentiria
vontade de criar:

| Tabela tentadora | Histórico | Auditoria | Query indexada | Cardinalidade > 1 | Veredito |
|---|---|---|---|---|---|
| `CampaignOccurrence` (cada disparo futuro) | não (o passado é `Announcement`) | não | sim ("quais vencem agora") | **não** — existe exatamente *uma* próxima ocorrência por campanha | **Não criar.** A query indexada é satisfeita por uma coluna `next_run_at`. |
| `CampaignAudience` (destinatários materializados) | não | **contraindicado** — persistir telefone é PII que hoje é deliberadamente evitada (`shopman/shop/models/broadcast.py:180-183`: *"Só contagens — a lista de destinatários nunca é persistida aqui"*) | não | sim | **Não criar.** |
| `FlashPromotion` | — | — | — | — | **Não criar** (§2.2: duplica `Promotion`). |
| `CampaignOffer` | não | o snapshot já vai em `Announcement.trigger_context` (`:185`) | não | **não** — uma oferta por campanha | **Não criar.** Vira JSON em `Campaign.offer`. |

### 2.4. Veredito

**Uma entidade de intenção, uma de fato, um catálogo de conteúdo. Zero tabelas novas.**

```
Campaign  (era BroadcastRule)      — a intenção: quando, para quem, o quê, com qual oferta
Announcement (era BroadcastPost)   — o fato: o que foi dito, a quem, quando, com que resultado
AnnouncementTemplate (era PostTemplate) — o conteúdo reutilizável
```

`AnnouncementTemplate` sobrevive como tabela por **cardinalidade > 1** (um modelo serve N
campanhas, protegido por `on_delete=PROTECT`, `shopman/shop/models/broadcast.py:111`), não
por histórico.

**Colunas novas em `Campaign` (4):**

```python
next_run_at  = models.DateTimeField(null=True, blank=True, db_index=True)   # "próxima vez"
channel_ref  = models.CharField(max_length=64, blank=True, db_index=True)   # canal de venda da oferta
offer        = models.JSONField(default=dict, blank=True)                   # itens + cupom (§5)
# `schedule` e `audience_rules` já existem; só o vocabulário cresce.
```

`channel_ref` é `CharField`, não FK — ADR-004 §1: ponteiro textual indexado, e vale a
convenção `Listing.ref == Channel.ref`
(`packages/offerman/shopman/offerman/models/listing.py:20-22`). É necessário porque a oferta
precisa saber em que vitrine se precifica e para qual host o link aponta.

**Coluna nova em `Announcement` (1):**

```python
occurrence_key = models.CharField(max_length=128, blank=True, db_index=True)
# unique parcial quando != "" — garante uma ocorrência, um anúncio
```

Passa os quatro critérios pelo eixo *query indexada* + *idempotência*: é o mesmo papel de
`Directive.dedupe_key` (`packages/orderman/shopman/orderman/models/directive.py:52-60`), com
a mesma forma de constraint parcial. Sem ela, uma varredura repetida do worker gera dois
anúncios da mesma promoção das 17h30.

**O que é removido no mesmo passo (zero-residual):**

- `Trigger.SCHEDULED` (`:29`) — substituído por `Trigger.SCHEDULE` com produtor real, ou
  removido em favor de `MANUAL` + `SCHEDULE`. Hoje é escolha morta.
- `QUALITY_LEVELS` (`:45`) — a ADR-017 §Migração passo 3 e 6 já o condena; `quality_min`
  passa a comparar `QualityGrade.rank`.
- `use_ai_generation` / `ai_prompt` sem leitor (`:74-78`) — ou ganham leitor na Fase 5, ou
  saem. Flag que ninguém lê é mentira de admin (constituição §2.3 aplicada à UI).

---

## 3. Segmentação de público

### 3.1. O que `guestman` já entrega

| Fonte | Onde | O que serve |
|---|---|---|
| `Customer` | `packages/guestman/shopman/guestman/models/customer.py:31` | `ref`, `phone` (cache do contato primário, `:76`), `birthday` (`:72`), `group` FK (`:79`), `is_active` |
| `CustomerGroup` | `.../models/group.py:7` | `ref`, `priority`, `listing_ref` — o eixo de segmento que **já** governa preço |
| `CustomerInsight` | `.../contrib/insights/models.py:9` | `total_orders`, `total_spent_q`, `average_ticket_q`, `days_since_last_order`, `average_days_between_orders`, `preferred_weekday`, `preferred_hour`, `favorite_products` (`[{sku, nome, qtd, ultimo_pedido}]`), `preferred_channel`, `rfm_recency/frequency/monetary`, `rfm_segment`, `churn_risk`, `predicted_ltv_q`, `is_vip` (`:147`), `is_at_risk` (`:152`) |
| `LoyaltyAccount.tier` | `.../contrib/loyalty/models.py`, lido em `shopman/shop/services/audience.py:441-448` | gold/platinum |
| `CustomerPreference` | `.../contrib/preferences/models.py` | opt-in de marketing (`shopman/shop/services/audience.py:34-35`) e defaults de checkout (`shopman/shop/services/checkout_defaults.py:19`) |
| `CustomerFavorite` | `shopman/storefront/models/favorites.py:14` | favorito explícito por SKU |
| `StockAlertSubscription` | `shopman/storefront/models/stock_alerts.py:22` | "me avise" por SKU, dois gatilhos (`:29-31`) |

**`CustomerInsight` já é o motor de segmentação.** RFM, churn, LTV, hora preferida, produtos
favoritos com data do último pedido — tudo calculado e persistido. Construir um segundo
motor seria criar o terceiro dono de um fato que já tem dois (ADR-017 §1).

### 3.2. O que muda: vocabulário, não motor

Hoje `audience.resolve(sku, rules)` (`shopman/shop/services/audience.py:151`) recebe **um
SKU do evento**. Uma campanha manual não tem evento nem SKU. Mudança mínima:

```python
def resolve(rules: dict | None = None, *, sku: str = "") -> AudienceResult: ...
```

E o vocabulário de `audience_rules` cresce (chaves em inglês; `help_text` em português):

| Chave nova | Fonte | Pergunta que responde |
|---|---|---|
| `customer_refs: []` | `Customer.ref` | "clientes específicos" — o gestor escolhe na tela |
| `groups: []` | `CustomerGroup.ref` | "só o grupo corporativo" |
| `rfm_segments: []` | `CustomerInsight.rfm_segment` | "champions e loyal" |
| `churn_risk_min: 0.7` | `CustomerInsight.churn_risk` / `is_at_risk` | win-back |
| `bought_skus: []` / `bought_collections: []` + `bought_within_days` | `CustomerInsight.favorite_products` | **"interesse genuíno de consumo específico"** — generaliza o `recompra_days` de hoje, que está preso ao SKU do evento (`:289-323`) |
| `birthday_today: true` | `Customer.birthday` | espelha `Promotion.birthday_only` (`shopman/storefront/models/promotions.py:53`) |

Nada disso é model novo. É `_favorites`/`_pending_alerts`/`_recompra` ganhando irmãos no
mesmo arquivo, todos devolvendo `Recipient` (`:43-52`) e passando pelo mesmo `_merge`
(`:454-479`) e pelo mesmo `_filter_opted_in` (`:340-353`).

### 3.3. Invariantes que não se negociam

1. **Opt-in continua lei.** `shopman/shop/services/audience.py:9-13` e `:340-353`: sem
   `CustomerPreference(category="marketing", key="broadcast_optin")` ativo, ninguém recebe.
   **Escolher a pessoa na tela não é consentimento dela.** `customer_refs` passa pelo
   mesmo filtro que os outros. A única porta lateral continua sendo
   `StockAlertSubscription`, porque a assinatura *é* o consentimento daquele SKU (`:349`).
2. **Um destinatário por telefone** (`:14-15`), dedupe em `_merge`.
3. **Só contagens são persistidas** (`shopman/shop/models/broadcast.py:180-183`); a lista é
   recalculada no despacho (`shopman/shop/handlers/broadcast.py:229-248`).

### 3.4. Custo conhecido (não é motivo para tabela)

`_recompra` carrega **todos** os `CustomerInsight` e filtra em Python
(`shopman/shop/services/audience.py:298-309`). Para a Nelson isso é aceitável; para
`bought_collections` fica pior. A correção certa é a consulta no banco
(`favorite_products__contains` em Postgres), **não** uma tabela desnormalizada de
"cliente × sku" — isso seria warehouse, vetado.

---

## 4. Janela de tempo e recorrência

### 4.1. Separar dois significados que hoje se confundem

`schedule` hoje só sabe **adiar** um post nascido de evento: `next_publish_at` devolve `None`
(publica agora) ou o início da próxima janela (`shopman/shop/services/broadcast_schedule.py:34-57`).
Isso é *deferimento*, não agendamento. O vocabulário precisa distinguir, sem overload:

```json
{"type": "immediate"}
{"type": "preferred_hours", "windows": [["07:00","11:00"]], "weekdays": [0,1,2,3,4,5]}
{"type": "once",      "at": "2026-08-15T07:00:00-03:00"}
{"type": "recurring", "windows": [["17:30","18:30"]], "weekdays": [4,5],
                      "starts_on": "2026-08-10", "ends_on": "2026-09-30"}
```

- `immediate` / `preferred_hours` — **adiam** (semântica atual, intocada).
- `once` / `recurring` — **disparam** (semântica nova, só válida com `trigger=schedule`).
- `starts_on`/`ends_on` cobrem "período específico" sem terceiro tipo.

A janela `[início, fim]` continua sendo o par validado por `_windows` (`:111-125`), inclusive
a recusa de janela que vira o dia — regra que vale igual para a promo relâmpago.

### 4.2. Como dispara sem Celery

Dois caminhos, escolhidos pelo tipo — e ambos já têm precedente no repo (ADR-003):

**`once` → uma `Directive` com `available_at`.** É exatamente o padrão do
`PREORDER_ACTIVATE` (`shopman/shop/directives.py:55`: *"o despertador (available_at =
meia-noite da data)"*). Um instante conhecido, um alarme, sem varredura. `available_at` já é
indexado (`packages/orderman/shopman/orderman/models/directive.py:47`) e o
`create_deduped(..., available_at=...)` já é usado pelo próprio broadcast para o atraso das
ondas VIP (`shopman/shop/services/broadcast.py:456-460`).

**`recurring` → `next_run_at` + o ciclo de manutenção que já existe.** Uma recorrência não
tem conjunto finito de instantes; materializá-los seria a `CampaignOccurrence` que o §2.3
recusou. O `maintenance_worker` já roda a cada 300s
(`shopman/shop/management/commands/maintenance_worker.py:66-68`) e já contém dois comandos
de broadcast no ciclo (`:47-51`): `expire_broadcast_posts` e `dispatch_scheduled_broadcasts`.
Acrescenta-se um terceiro:

```
fire_due_campaigns  — Campaign.objects.filter(is_active=True, next_run_at__lte=now)
                      → evaluate(trigger="schedule", context={...})
                      → recalcula next_run_at a partir de `schedule`
```

Idempotência: cada disparo grava `Announcement.occurrence_key = f"{campaign.pk}:{iso}"` sob
unique parcial. At-least-once do worker + chave única = exactly-once lógico, a mesma
construção que a ADR-003 §Positivas atribui ao `dedupe_key`.

**Nada disso adiciona broker.** A tabela `Directive` continua sendo a fila; o worker de
manutenção continua sendo o cron. Nenhum threshold T1–T7 da ADR-003 é tocado por campanhas
de uma padaria.

### 4.3. Limite honesto

A granularidade é a do ciclo do worker: **~5 minutos** (default de `--interval`,
`maintenance_worker.py:66`). Uma "promoção relâmpago das 17h30" começa entre 17h30 e 17h35.
Se algum dia for preciso o minuto exato, isso é o gatilho T6 da ADR-003 ("SLA de notificação
crítica < 5s"), não um remendo. Ver pergunta aberta 4.

---

## 5. A oferta atrelada — carrinho × Action

### 5.1. A resposta

**A campanha emite uma `Action`. Ela não cria carrinho.**

### 5.2. Por que criar carrinho é proibido

1. **A ADR-012 lista isso literalmente em "Não aceitamos"**: *"Criar `RemoteOrder`, status
   remoto ou lifecycle paralelo"* e *"Duplicar pricing, stock, payment gate, timers,
   availability ou next_event em Nuxt, Ionic, ManyChat ou qualquer superfície"*
   (adr-012:111,115). Um carrinho montado pelo marketing precisaria reservar estoque,
   expirar, reprecificar e reconciliar — quatro responsabilidades que já têm dono.
2. **`Session` é estado de sessão, não de pessoa.** A chave é `session_key` + `channel_ref`
   (`packages/orderman/shopman/orderman/models/session.py:94-95`), ligada a um navegador ou
   a um terminal de PDV. Montar 40 carrinhos para 40 telefones cria 40 sessões órfãs, que o
   `cleanup_stale_sessions` (`maintenance_worker.py:41`) depois varre.
3. **E, pior, reserva estoque.** `cart.add_item` chama `_reserve_or_raise`
   (`shopman/shop/services/cart.py:377`), que toma hold no Stockman. Marketing segurando
   pão para gente que ainda não clicou viola a constituição §2.3 (*"stockman não pode
   liberar disponibilidade ilusória"*) do lado inverso: promete a um e nega a outro.
4. **O preço envelheceria.** O carrinho seria precificado na hora do envio; a pessoa clica
   20 minutos depois, quando a promoção, o D-1 e o happy hour já mudaram. A ADR-014
   identificou essa exata divergência ("preço-vitrine vs preço-carrinho") como sintoma do
   frankenstein.

### 5.3. O precedente já existe e está certo: **reorder**

```python
Action(
    ref="reorder", kind="mutation", label="Repetir pedido", priority="primary",
    href=f"/api/v1/orders/{last_order_ref}/reorder/", method="POST",
    payload_schema={...}, idempotency="required",
)
```
`shopman/storefront/presentation/home.py:346-360`

O clique executa `add_reorder_items` (`shopman/shop/services/customer_orders.py:530-568`),
que **re-resolve o preço no catálogo no momento do clique** (`:549`), **pula o que não é
vendável** (`:545-548`) e **pula o que o Stockman recusa** (`:558-560`), devolvendo a lista
de descartados para a superfície explicar. Um clique do lado do cliente, services canônicos
do nosso.

A oferta da campanha é a mesma forma com outro conteúdo:

```json
"offer": {
  "items": [{"sku": "CROISSANT", "qty": 2}],
  "coupon_code": "RELAMPAGO-CROISSANT",
  "channel_ref": "web"
}
```

→ vira, no `Announcement.content["actions"]`, uma `Action` no contrato da ADR-012
(`ref`/`kind`/`label`/`href`/`method`/`payload_schema`/`idempotency`), cujo `href` é um
endpoint no idioma do reorder e cujo destino final é o carrinho da loja
(`shopman/shop/services/storefront_links.py:41`), alcançado com sessão já autenticada via
`build_access_url` (`shopman/shop/services/access_urls.py:30-67`) — o mesmo mecanismo que
`build_reorder_access_url` (`:88`) usa hoje.

### 5.4. Entrega grátis: a lacuna está no pricing, não aqui

Hoje frete grátis só existe por **limiar de subtotal**:
`shop.defaults.rules.free_delivery_above_q` zera a taxa efetiva
(`shopman/shop/modifiers.py:1002-1015`), e a taxa vira uma **linha** `__DELIVERY_FEE__`
(`:941`) porque `Order.total_q` é a soma das linhas (`:912-915`).

`Promotion.TYPE_CHOICES` só tem `percent` e `fixed`
(`shopman/storefront/models/promotions.py:11-13`). **Não existe "entrega grátis" como
promoção.** Essa é uma capacidade faltante do domínio de preço, e a campanha **não pode
inventá-la** — seria a segunda regra de frete, e o `DeliveryFeeModifier` passaria a ter duas
fontes onde tem uma.

Caminho correto: um item de trabalho no pricing (novo `Promotion.type = "free_delivery"`
resolvido dentro do `DeliveryFeeModifier`, ou um modifier de renúncia lendo o cupom
aplicado). A campanha só carrega `coupon_code`, e o cupom entra pelo caminho que já existe:
`cart.apply_coupon_code` (`shopman/shop/services/cart.py:235-270`).

Nota de fronteira: `Promotion` **não tem `ref` textual** (`shopman/storefront/models/promotions.py:8-64`
— só `name` e o `pk`). Apontar para ela a partir de `Campaign` exige ou adicionar
`Promotion.ref` (slug único), ou apontar para `Coupon.code`, que já é `unique=True`
(`:71`). A segunda opção é a mais barata e respeita a ADR-004.

### 5.5. Endereço: sugerir sim, confirmar nunca

`CheckoutDefaultsService.get_defaults` já devolve `delivery_address_id`
(`shopman/shop/services/checkout_defaults.py:22, 47-63`), inferido do histórico a partir de
3 pedidos e 70% de confiança (`:39-42`), e `CustomerAddress.is_default` existe
(`packages/guestman/shopman/guestman/models/address.py:110`). **O checkout já sugere.**

A campanha entrega uma pessoa autenticada no carrinho; a confirmação do endereço é do
checkout e **precisa continuar sendo uma confirmação**. Pré-confirmar endereço em nome do
cliente é o sistema mentindo sobre o mundo (constituição §2.3) e é o tipo de atalho que
produz uma entrega no endereço errado — o custo de um clique a menos não paga isso.

---

## 6. Arte + copy com IA

### 6.1. Onde a IA já está

`ai_assist_field` (`shopman/backstage/services/catalog.py:753-796`): sugestão **por campo**,
provedor Anthropic, `AI_ASSIST_PROVIDER` / `AI_ASSIST_API_KEY` / `AI_ASSIST_MODEL`
(`config/settings.py:938-940`), com `AiAssistNotConfigured` quando não há chave. Já cobre
`social_caption` e `hashtags` (`:686-701`), com contexto do produto montado a partir do que
já está preenchido (`_ai_assist_context`, `:704-728`).

### 6.2. Adapter, não core, não superfície

- **Não é superfície.** O texto que o cliente vai ler é **dado**: entra em
  `Announcement.content["body"]`, é aprovado, é despachado, é auditável. Superfície que
  gerasse copy inventaria conteúdo de marca — exatamente o que a ADR-012 (`adr-012:53`)
  proíbe ("se uma superfície precisa decidir ... qual CTA ..., a resposta deve vir de uma
  Projection").
- **Não é core.** Nenhum pacote de `packages/` pode nascer dependendo de um provedor de LLM
  (ADR-001 §4; constituição §10: *"nenhuma integração externa define a semântica do core"*).
- **É adapter no orquestrador.** ADR-001 §3 exige razão concreta para um Protocol: aqui há
  **uma implementação real e um estado desligado real**, e **dois chamadores** (catálogo e
  campanha). Portanto o movimento honesto é *extrair* o que já existe para
  `shopman/shop/adapters/copy_assist.py`, com a assinatura mínima
  `suggest(prompt: str, *, system: str, max_tokens: int) -> str`, e fazer os dois consumirem.
  Não é backend "para o futuro"; é o backend que já existe ganhando o segundo cliente.

### 6.3. A voz da marca sai do código

`_AI_ASSIST_VOICE` (`shopman/backstage/services/catalog.py:645-651`) codifica *"Nelson
Boulangerie"*, *"padaria artesanal brasileira"*, *"primeira pessoa do plural"*. Vive em
`shopman/backstage` (framework), então não é violação de core — mas é **default de instância
com aparência de verdade do produto**, que a constituição §2.6 e §10 recusam, e a campanha
precisará do mesmo texto. Correção: um campo em `Shop`, ao lado de `tagline` e `description`
(`shopman/shop/models/shop.py:134-137`):

```python
brand_voice = models.TextField("voz da marca", blank=True, help_text="...")
```

Editável no Admin, um dono, dois consumidores. É também literalmente o que o dono pediu
("voz da marca").

### 6.4. Dado × apresentação (ADR-014)

Régua proposta, testável:

> **Se o cliente final vai ler a string, ela é dado** (orquestrador, `Announcement.content`).
> **Se só o gestor vai ler a string, ela é apresentação** (superfície, `presentation/`).

Aplicação:

| String | Camada | Onde já está |
|---|---|---|
| corpo do post, hashtags, link, CTA | **dado** | `shopman/shop/services/broadcast.py:161-171` |
| "12 favoritos, 28 recompra = 43 clientes" | apresentação | `surfaces/broadcast-nuxt/app/presentation/broadcast.ts:23-33` ✔ |
| "expira em 12 min" | apresentação | `.../presentation/broadcast.ts:47-57` ✔ |
| `expires_in_minutes: int` | dado | `shopman/backstage/projections/broadcast.py:79` ✔ |
| rótulo de plataforma ("Google Meu Negócio") | **hoje está errado** | `shopman/backstage/projections/broadcast.py:36-42` — copy PT dentro de projection; a projection deveria carregar só o `ref`. Regra R-B da ADR-014 §6. |

A geração de copy roda **no momento da revisão**, nunca dentro de `evaluate()`: `evaluate`
executa em `transaction.on_commit` do finish da fornada
(`shopman/shop/handlers/broadcast.py:119-120`) e o handler jura não derrubar quem disparou
(`:7-9`). Uma chamada de rede de segundos ali penaliza o operador que está com o pão na mão.
Se algum dia houver auto-post com IA (`requires_approval=False`), o caminho é uma Directive,
não uma chamada inline.

### 6.5. Arte gerada por IA: fora do alpha

Foto de produto continua sendo **ativo real** — `image_source` já modela
product/gallery/custom/none (`shopman/shop/models/broadcast.py:55-59`), resolvido de
`Product.image_url` (`shopman/shop/services/broadcast.py:294-301`). Imagem sintética de um
pão que não é aquele pão é o sistema mentindo sobre o mundo (§2.3) e contradiz a decisão já
tomada em FOMO-BROADCAST-SPECS:667 (*"FOMO falso destrói confiança. Urgência real ou nada"*).
O que cabe no alpha é **seleção** e **recorte** de foto existente, não síntese.

---

## 7. O que NÃO fazer

**Limites reafirmados (não reabrir):**

- **Não é um Hootsuite** (FOMO-BROADCAST-SPECS:37-38): sem inbox, sem DM, sem analytics de
  engajamento, sem gestão de comunidade. O canal é unidirecional.
- **Sem B.I.**: nenhuma tabela de agregação, snapshot, warehouse, gráfico ou app de
  relatório (ADR-017 §8; decisão reafirmada em 2026-08-07). Os quatro números do painel
  (`BroadcastStatsProjection`, `shopman/backstage/projections/broadcast.py:85-92`:
  `pending_count`, `published_today`, `audience_reached_today`, `failed_today`) são
  **contagens operacionais** — quantas decisões esperam, quantas saíram, quantas falharam.
  Ficam exatamente esses quatro. Impressões, curtidas, alcance, CTR e funil de UTM: não.
  O parâmetro UTM no deep link (FOMO-BROADCAST-SPECS:620) continua permitido **como
  parâmetro**; um relatório construído sobre ele é o B.I. vetado.
- **ManyChat não vira dono de nada** (ADR-009:129-131): pode carregar copy conversacional e
  botões; conteúdo de campanha, elegibilidade, audiência e preço continuam no Shopman.

**Novos limites que este plano fixa:**

- **`audience_rules` é vocabulário fechado e plano.** Sem AND/OR aninhado, sem construtor de
  segmento arbitrário. No dia em que alguém precisar de árvore booleana, o que está sendo
  construído é um CDP, e a resposta é não.
- **Campanha nunca escreve preço, nunca segura estoque, nunca cria pedido.** Ela aponta para
  `Promotion`/`Coupon` e emite `Action`.
- **Sem A/B test, sem otimização de horário além do `preferred_hour` que já existe**
  (`shopman/shop/services/audience.py:217-238`). Otimizar horário sem medir conversão é
  superstição; medir conversão é B.I.
- **Sem lista de destinatários persistida.** A regra atual (`shopman/shop/models/broadcast.py:180-183`)
  vale para as fontes novas também.

**O que da visão do dono cai fora ou muda de forma:**

| Pedido | Veredito |
|---|---|
| "criar um carrinho ... já definido" | **Muda de forma**, não cai: vira `Action` (§5). O cliente ganha o mesmo um-clique; o sistema não ganha um lifecycle paralelo. |
| "entrega grátis já definida" | **Bloqueado por dependência**, não por doutrina: depende de uma capacidade de pricing que não existe (`Promotion.type` só tem percent/fixed). Fase 3. |
| "já sugere e confirma [o endereço]" | **Sugere sim, confirma não** (§5.5). |
| "arte ... com auxílio de IA" | **Copy sim, arte não** no alpha (§6.5). |
| "promoção relâmpago em faixa de horário" | **Cabe**, com granularidade de ~5 min (§4.3). |
| "filtros de canais específicos" | **Cabe**, via `Campaign.channel_ref` — mas note que hoje `platforms` (onde publicar) e canal de venda (onde a oferta vale) são coisas diferentes que ninguém separou. |

---

## 8. Ordem de implementação

Cada fase entrega valor sozinha e passa `make test`.

**F0 — Rename.** Zero mudança de comportamento. `BroadcastRule→Campaign`,
`BroadcastPost→Announcement`, `PostTemplate→AnnouncementTemplate`, permissão, topics de
Directive, canal SSE, diretório da superfície, settings. Reset/squash das 3 migrations +
data migration de permissão (§1.4). *Valor sozinho:* o nome para de mentir antes de qualquer
consumidor externo existir, e todo trabalho posterior nasce com a palavra certa.

**F1 — Disparo manual com público escolhido.** `Trigger.MANUAL`; `audience.resolve()` muda de
assinatura; `audience_rules` ganha `customer_refs`, `groups`, `rfm_segments`,
`bought_skus`/`bought_collections`; Action "Criar campanha" na superfície. Sem IA, sem
oferta, sem plataforma nova. *Valor sozinho:* o gestor dispara hoje, para quem ele escolher,
por WhatsApp (já ligado) e TV (já ligada).

**F2 — Agendamento.** Vocabulário `once`/`recurring` em `schedule`; `Campaign.next_run_at`;
`Announcement.occurrence_key` com unique parcial; `fire_due_campaigns` entra em
`MAINTENANCE_COMMANDS` (`maintenance_worker.py:40-56`); `once` vira Directive com
`available_at`. *Valor sozinho:* promoção relâmpago recorrente funciona sem oferta atrelada
— o anúncio já leva ao produto.

**F3 — Entrega grátis como capacidade de pricing.** *Fora deste app; dono é pricing.*
`Promotion.ref` (ou uso de `Coupon.code`), renúncia de taxa resolvida dentro do
`DeliveryFeeModifier`. *Valor sozinho:* a padaria passa a poder dar frete grátis por cupom
em qualquer canal, com ou sem campanha.

**F4 — A oferta acionável.** `Campaign.offer`, `Campaign.channel_ref`, `Action` em
`Announcement.content["actions"]`, endpoint no idioma do reorder, magic link para o carrinho.
Depende de F3 para o frete. *Valor sozinho:* o disparo passa a terminar em carrinho montado
com um clique.

**F5 — Copy com IA.** Extrair `shopman/shop/adapters/copy_assist.py`; mover a voz da marca
para `Shop.brand_voice`; ligar `use_ai_generation`/`ai_prompt` no momento da revisão; catálogo
passa a consumir o adapter. *Valor sozinho:* o gestor deixa de escrever do zero, e o catálogo
herda a voz editável.

**F6 — Posting externo.** `posting_meta` e `posting_google` — escopo já definido em
FOMO-BROADCAST-SPECS §5 e §7 (F5/F6), gated por credencial
(`SHOPMAN_BROADCAST_META`, `config/settings.py:645-653`; hoje `get_adapter("posting", ...)`
devolve `None` e o handler grava `pending_manual`, `shopman/shop/handlers/broadcast.py:199-206`).
Este plano não o altera.

**Depois do alpha:** geração de imagem por IA; granularidade sub-minuto (gatilho T6 da
ADR-003); qualquer forma de atribuição ou medição de engajamento (não entra nunca sem
reabrir o veto de B.I.).

---

## 9. Perguntas abertas para o dono

1. **Nome.** `campaign` como identificador (models, permissão, diretório da superfície),
   mantendo o rótulo PT "Marketing" no Hub — ou o rótulo também vira "Campanhas"? E o host
   público `broadcast.` acompanha o rename ou fica onde está por ora?

2. **Entrega grátis.** Aceita que ela nasça como capacidade de *pricing* (cupom/promoção,
   Fase 3), o que adia a "promo relâmpago completa" — ou prefere um atalho só para campanha,
   assumindo que o frete passa a ter duas fontes de regra?

3. **Opt-in e "clientes específicos".** Confirma que escolher a pessoa na tela **não**
   dispensa o opt-in de marketing (LGPD + a invariante em
   `shopman/shop/services/audience.py:9-13`)? Ou quer uma exceção auditada para quem tem
   pedido recente?

4. **Granularidade da relâmpago.** ~5 minutos (ciclo do `maintenance_worker`) resolve, ou
   existe caso real que exija o minuto exato?

5. **Aprovação da campanha manual.** A campanha que o próprio gestor cria ainda passa por
   `requires_approval`, ou quem cria publica direto — deixando a revisão só para o que a
   operação gerou sozinha (fornada, estoque baixo)?

---

## Referências

- [Constituição Semântica](../constitution.md) — §2.1, §2.2, §2.3, §2.5, §2.6, §3.1, §3.3, §5, §8.3, §10
- [ADR-001 — Protocol/Adapter e fronteiras de core](../decisions/adr-001-protocol-adapter.md)
- [ADR-003 — Directives sem Celery](../decisions/adr-003-directives-sem-celery.md)
- [ADR-004 — String refs cross-domain](../decisions/adr-004-string-refs.md)
- [ADR-009 — WhatsApp via ManyChat](../decisions/adr-009-whatsapp-via-manychat.md)
- [ADR-011 — Formula sem FormulaPlan](../decisions/adr-011-formula-and-cashshift.md)
- [ADR-012 — Contrato headless: Projection com Actions](../decisions/adr-012-headless-surface-contract.md)
- [ADR-014 — Corte dado/apresentação](../decisions/adr-014-surface-data-presentation-cut.md)
- [ADR-015 — Backward-compat pós-produção](../decisions/adr-015-backward-compat-policy-post-prod.md)
- [ADR-016 — Tempo real por SSE](../decisions/adr-016-sse-first-realtime.md)
- [ADR-017 — Qualidade é resultado da produção](../decisions/adr-017-quality-as-production-outcome.md)
- [FOMO-BROADCAST-SPECS](FOMO-BROADCAST-SPECS.md)
