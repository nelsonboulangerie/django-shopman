# Plano de execucao — superficie, oferta e campanha

**Status:** Ativo
**Data:** 2026-08-08
**Supersede:** [BROADCAST-EVOLUTION-PLAN.md](BROADCAST-EVOLUTION-PLAN.md) (levantamento original)
**Decide por:** [ADR-018](../decisions/adr-018-surface-is-channel-with-commerce-policy.md),
[ADR-019](../decisions/adr-019-promotion-belongs-to-the-orchestrator.md),
[ADR-020](../decisions/adr-020-campaign-announces-it-does-not-sell.md)
**Janela:** pre-alpha. `go-live-v1` nao existe (a tag mais avancada e `v0.1.0-alpha`), logo a ADR-015
nao vigora e rename ainda e barato. **Isto muda na tag.**

---

## 0. O que mudou desde o levantamento original

Registrado para que ninguem reabra o que ja foi decidido, e para que os erros do levantamento nao sejam
recopiados.

### Correcoes de fato

| Levantamento dizia | Realidade verificada |
|---|---|
| "frete gratis so existe por limiar de subtotal" (§5.4) | Existem tres caminhos, e um e documentado como entrega gratis: `DeliveryZone(mode="override", fee_q=0)` (`shopman/storefront/models/delivery.py:76-80`), `DeliveryDistanceBand(fee_q=0)` (`:157-161`) e o limiar (`shopman/shop/modifiers.py:927`). O que falta e escopo por publico/cupom |
| citacoes de `config/settings.py` e `shopman/shop/modifiers.py` | Deslocadas 76-95 linhas: o levantamento foi escrito contra arvore com trabalho nao mergeado. As citacoes dos modulos de broadcast estao corretas |
| "Colunas novas em `Campaign` (4)" (§2.4) | Listava tres |
| `channel_ref` como coluna (§2.4) **e** dentro do JSON da oferta (§5.3) | Mesma pergunta, dois donos. Resolvido: nao existe `Campaign.channel_ref`; canal e da promocao |

### Achados que o levantamento nao viu

1. **`broadcast_optin` nao tem escritor.** A chave existe so na constante e na docstring
   (`shopman/shop/services/audience.py:34-35`, `:10`); nao esta no seed nem em nenhuma API. So o teste
   a cria (`shopman/shop/tests/test_audience.py:32`). Em producao, **so assinante de alerta de estoque
   recebe campanha**.
2. **Consentimento tem dois donos.** O toggle que o cliente usa escreve `CommunicationConsent`
   (`shopman/shop/services/account.py:199-219`), que a audiencia nunca le. Cliente que revoga WhatsApp
   continua recebendo.
3. **`Promotion` nao tem escopo de canal.** Relampago da web aplica no PDV e no iFood hoje.
4. **O feed mente sobre preco.** Renderizadores leem `base_price_q`
   (`shopman/shop/views/product_feed.py:83`, `shopman/shop/projections/menuboard.py:79`) enquanto o
   canal vende por `ListingItem.price_q`.
5. **As quatro rotas de exibicao sao publicas**, incluindo o SSE `stock-catalog`
   (`shopman/shop/menuboard_urls.py:22-28`).
6. **`RuleConfig` `promotion_discount` e decorativo.** `DiscountModifier` nunca chama
   `get_channel_rule_params`; desligar no Admin nao desliga nada.
7. **`discard()` grava `EXPIRED`** (`shopman/shop/services/broadcast.py:380-387`): recusa e vencimento
   sao indistinguiveis.
8. **O canal SSE `broadcast-tv` tem zero consumidores** em todo o repo.

### Mudancas de desenho vindas da conversa

- **A oferta e entidade, e a campanha aponta.** Cai o JSON `offer`/`proposal`; entra
  `Campaign.promotion_ref` (CharField). O prefill do carrinho vem dos `skus`/`collections` da propria
  promocao.
- **Canal `display` nao tem preco proprio.** Cai a ideia de dar `Listing`/`ListingItem` aos feeds; entra
  `prices_from` apontando para o canal transacional cujo preco e anunciado. Membresia continua sendo
  colecao.
- **Cai `Campaign.next_run_at`.** A proxima ocorrencia e calculada, nao armazenada.
- **Cai `destinations`/`DestinationKind`.** `platforms` fica (sem `tv`); o conserto e registrar a
  costura `posting` que ja existe.

---

## 1. Ordem de execucao

Cada fase entrega valor sozinha e passa `make test`. As dependencias reais sao poucas:

```
F1 consentimento ──→ (destrava toda campanha)
F2 rename ─────────→ (tudo depois nasce com a palavra certa)
F3 canal unico ────→ F4 preco no feed
F5 promocao em casa → F6 cupom · F7 frete gratis
F3 + F5 ───────────→ (promocao alcanca feed)
F5 + F7 ───────────→ F11 oferta acionavel
```

**F1 vem primeiro** porque sem ela todo o resto dispara para ninguem, e porque o defeito de LGPD e o
unico item da lista que esta errado *agora*, em producao.

---

## 2. Fases

### F1 — Consentimento com um dono · ADR-020 §3

`audience.py` passa a ler `CommunicationConsent` por canal, via `ConsentService` (a exportacao de nivel
de pacote, nao `contrib.consent.models`). `broadcast_optin` e apagado, com data migration convertendo
qualquer linha criada a mao no Admin. A porta lateral do `StockAlertSubscription` permanece, e vale so
para o SKU assinado.

*Valor sozinho:* o toggle que o cliente ja usa passa a valer, quem revoga para de receber, e a
audiencia deixa de ser zerada.

### F2 — Rename · ADR-020 §1 e §2

`BroadcastRule`→`Campaign`, `BroadcastPost`→`Announcement`, `PostTemplate`→`AnnouncementTemplate`,
permissao, content type, topics (`announcement.publish`/`announcement.notify`), categoria de
notificacao, diretorio da superficie, settings. Mais as **cinco strings persistidas**: prefixos de
dedupe, `action_url`, chave `action_data`, chave do mapa ManyChat. Zero mudanca de comportamento.

> **Coordenacao:** a ADR-017 §Migracao passo 3 tambem toca `trigger_filter` (rename dos graus de
> qualidade). As duas migrations precisam ser ordenadas entre si, nao concorrentes.

*Valor sozinho:* o nome para de mentir antes de existir consumidor externo. Invisivel ao operador,
porque a UI ja diz "Marketing".

### F3 — Superficie e canal · ADR-018 passos 1 a 3.1

`Channel.commerce_policy` (`display`/`order`, default `order`), aspecto `Display` no `ChannelConfig`,
absorcao de cada `Showcase` em canal + config, e a **trava do menuboard** por dispositivo confiavel do
`doorman`. O system check de preco publico entra aqui.

*Valor sozinho:* some um model e um caminho de escrita; a TV para de ser publica.

### F4 — Preco verdadeiro no feed · ADR-018 passos 4 a 8

Renderizadores passam a resolver preco por `prices_from`. `_build_showcase_surfaces()` sai;
`CatalogSyncState.platform` vira `channel_ref`; `?platform=` sai; `Showcase` e removido.

> **Esta e a unica fase que muda numero exibido, de proposito.** Verificavel item por item contra a
> pagina de destino. A trava do menuboard (F3) precede a exposicao do preco do PDV.

*Valor sozinho:* o feed do Google para de anunciar preco que a loja nao cobra.

### F5 — Promocao volta para casa · ADR-019 passos 1 a 4

`Promotion.ref` e `Promotion.channels` (vazio = todos, sem mudanca de comportamento); mudanca de app das
quatro tabelas por `SeparateDatabaseAndState` + `AlterModelTable`; imports e admin acompanham;
`shop/adapters/promotion.py` e apagado e `StorefrontPricingBackend` vira `PromotionPricingBackend`.

*Valor sozinho:* regra de preco deixa de depender de superficie, o vazamento de `adapters/pricing.py:41`
morre, e a relampago passa a poder valer so na web. Com F3 no ar, alcanca tambem Google, Meta e
menuboard.

### F6 — Cupom no orquestrador · ADR-019 passo 5

As quatro portas de validacao saem de `shopman/storefront/cart.py:322-378` para
`shop/services/cart.py`. Superficie volta a interpretar request e formatar erro no dialeto
`{detail, field, errors}`.

*Valor sozinho:* **o PDV ganha cupom** sem reimplementar nada.

### F7 — Entrega gratis como oferta · ADR-019 passos 6 a 8

`free_delivery` como terceiro `type`, renunciado em `_effective_fee_q`; `value` como teto da renuncia;
`clean()` exigindo `fulfillment_types` compativel; `PromotionRule` e a linha decorativa do seed saem.

*Valor sozinho:* frete gratis por cupom, janela, segmento ou colecao, em qualquer canal.

### F8 — Disparo manual com publico escolhido · ADR-020 passo 3

`Trigger.MANUAL`; `audience.resolve()` muda de assinatura; `audience_rules` ganha `customer_refs`,
`groups`, `rfm_segments`, `churn_risk_min`, `bought_skus`/`bought_collections` e `birthday_today`;
Action "Criar campanha" na superficie.

*Valor sozinho:* o gestor dispara hoje, para quem escolher, por WhatsApp (ja ligado).

### F9 — Agendamento: a vassoura arma, a fila dispara · ADR-020 passo 4

`once`/`recurring` em `schedule`; `Announcement.occurrence_key` com unique parcial; o comando de
varredura passa a **armar** `Directive` com `available_at`; `dispatch_scheduled_broadcasts` sai do
`maintenance_worker`; `handle()` passa a `sleep(interval - elapsed)`.

*Valor sozinho:* relampago das 17h30 sai em segundos, e `publish_at` para de mentir para todo mundo.

### F10 — Recusa como estado · ADR-020 passo 5

`AnnouncementStatus.REJECTED` com `rejected_by` e `rejected_reason`; campanha criada pelo gestor pula
aprovacao.

*Valor sozinho:* o Admin passa a poder responder quantos anuncios foram recusados, e por que.

### F11 — A oferta acionavel · ADR-020 passo 6 · depende de F5 e F7

`Campaign.promotion_ref`; `Action` no contrato da ADR-012 em `Announcement.content["actions"]`; endpoint
no idioma do `reorder`; **deep link nao autenticado** (nunca `build_access_url`, que expira em 5
minutos).

*Valor sozinho:* o disparo termina em carrinho montado com um clique, com preco resolvido no clique.

### F12 — Copy com IA · ADR-020 passo 7

`shopman/shop/adapters/copy_assist.py` extraido de `backstage/services/catalog.py:636-798`;
`Shop.brand_voice`; `use_ai_generation`/`ai_prompt` ganham leitor no momento da revisao; catalogo passa
a consumir o adapter.

*Valor sozinho:* o gestor deixa de escrever do zero, e o catalogo herda voz de marca editavel.

*Bloqueio externo: **nenhum, no codigo**.* Verificado em 2026-08-08: `anthropic>=0.117` esta declarado
(`pyproject.toml:30`) e instalado, `AI_ASSIST_MODEL=claude-opus-4-8` e um ID valido, a chamada em
`backstage/services/catalog.py:784-789` nao passa nenhum parametro que Opus 4.8 rejeite
(`temperature`/`top_p`/`budget_tokens`), e `ai_assist_field()` **funciona de ponta a ponta local**.
O que falta e operacional: `AI_ASSIST_API_KEY` esta no `.env` local mas **ausente da spec LIVE do
staging na DO** — por isso o endpoint responde 503 no ar. Config de deploy se edita na spec LIVE, nunca
na do repo (que apaga segredos).

### F13 — Posting externo · ADR-020 passo 8

Registrar `"posting"` no mapa de adapters e implementar `posting_meta`/`posting_google`. Escopo ja
definido em [FOMO-BROADCAST-SPECS](FOMO-BROADCAST-SPECS.md) §5 e §7.

*Bloqueio externo, estado verificado em 2026-08-08 na spec LIVE do staging:*

| Credencial | Estado |
|---|---|
| `META_PAGE_ID` | **presente** |
| `META_IG_USER_ID` | **presente** |
| `META_PAGE_ACCESS_TOKEN` | **ausente** — e a unica que autentica (`config/settings.py:572`) |
| Google Business | **ausente** por completo (nem o codigo espera env ainda) |

Ou seja: Meta esta a um token de estar completa do lado da config, mas nada publica enquanto a costura
`posting` nao for registrada — hoje `get_adapter("posting", ...)` devolve `None` e todo post externo
fica `pending_manual`.

---

## 3. Riscos

| Risco | Mitigacao |
|---|---|
| F4 muda preco anunciado no Google | F3 (trava) vem antes; F4 e verificavel item a item; rollback e reverter `prices_from` |
| F5 move quatro tabelas com dado de staging que o dono edita a mao | `SeparateDatabaseAndState` + `AlterModelTable`, nao `DeleteModel`+`CreateModel` como foi na ida (`shop/migrations/0010:22-23`). Nenhum dado se move, e nao ha FK cross-app |
| F1 muda quem esta na audiencia | Contagem de elegiveis por canal antes e depois; quem tinha preferencia manual e convertido |
| F2 toca ~610 pontos | Mecanico e concentrado: cinco arquivos respondem por metade. Os pontos que **nao** sao busca-e-substitui estao listados na ADR-020 §1 |
| F2 colide com a onda de qualidade (ADR-017) | Ambas tocam `trigger_filter`; ordenar as migrations |
| Nomes de URL do Admin quebram em F5 | `backstage/admin/navigation.py:168-169` e `shop/tests/test_rules.py:446,453` no mesmo commit |
| `_recompra` faz varredura completa de `CustomerInsight` | Conhecido e aceito nesta escala. A correcao e consulta no banco, **nunca** tabela cliente x sku (seria warehouse, vetado) |

---

## 4. O que fica fora

- **Sem B.I.**: nenhuma tabela de agregacao, snapshot, warehouse ou grafico. As contagens do painel sao
  quatro. UTM continua permitido como parametro; relatorio sobre ele, nao.
- **Sem inbox, DM, analytics de engajamento ou gestao de comunidade** (`FOMO-BROADCAST-SPECS.md:37-38`).
- **Sem A/B test** e sem otimizacao de horario alem do `preferred_hour` que ja existe.
- **Sem sintese de imagem por IA**: so selecao e recorte de foto real.
- **Sem `intent`** como politica comercial enquanto nao houver implementacao.
- **Sem preco por grupo de cliente**: `CustomerGroup.listing_ref` fica declarado e inerte.
- **Sem arvore booleana em `audience_rules`**: vocabulario fechado e plano.
- **Sem granularidade sub-minuto**: F9 entrega segundos; abaixo disso e o gatilho T6 da ADR-003.

---

## 5. Decisoes do dono, registradas

Tomadas na sessao de 2026-08-07/08:

1. **Consentimento:** `CommunicationConsent` por canal e o dono unico. `broadcast_optin` morre.
2. **Rename:** `campaign`/`Announcement` como identificadores; secao visivel "Marketing"; host publico
   `mkt.`. `mkt` nunca entra em identificador Python.
3. **Colunas:** zero tabela nova; so `Campaign.promotion_ref` e `Announcement.occurrence_key`.
4. **Escopo do move:** promocao, cupom **e** geografia de entrega, matando `adapters/promotion.py`.
5. **Frete gratis:** capacidade de pricing, terceiro `type` da `Promotion`.
6. **Granularidade:** armar-e-disparar; segundos, nao minutos.
7. **Aprovacao:** quem cria publica; recusa vira estado proprio.
8. **Menuboard:** preco do PDV (a TV esta fisicamente na loja), e rota travada — nao publica.
9. **Feed:** so oferta incondicional. Promocao segmentada nao vai para Google/Meta.
10. **Rotas:** nomeiam o artefato (`feed`, `menuboard`), nunca o acesso.
11. **Nao mexer:** `Listing`/`Collection` do offerman e a fila `Directive` estao certos.

---

## Referencias

- [ADR-018 — Superficie e canal, com politica comercial](../decisions/adr-018-surface-is-channel-with-commerce-policy.md)
- [ADR-019 — A promocao tem um dono](../decisions/adr-019-promotion-belongs-to-the-orchestrator.md)
- [ADR-020 — Campanha anuncia, nao vende](../decisions/adr-020-campaign-announces-it-does-not-sell.md)
- [Constituicao Semantica](../constitution.md)
- [FOMO-BROADCAST-SPECS](FOMO-BROADCAST-SPECS.md)
- [BROADCAST-EVOLUTION-PLAN](BROADCAST-EVOLUTION-PLAN.md) — levantamento original, superado
