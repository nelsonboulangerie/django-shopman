# ADR-019 - A promocao tem um dono: orquestrador, escopada por canal, com renuncia de frete

**Status:** Proposto
**Data:** 2026-08-08
**Escopo:** `shopman/shop` (`Promotion`, `Coupon`, `DeliveryZone`, `DeliveryDistanceBand`,
`modifiers.py`, `adapters/promotion.py`, `adapters/pricing.py`, `rules/`), `shopman/storefront`
(remocao dos models e do admin), `config` (seed), `offerman` (nenhuma mudanca)
**Depende de:** ADR-018 (canal `display` para que promocao alcance feed)
**Prepara:** ADR-020 (`Campaign.promotion_ref`)

---

## Contexto

A padaria precisa de promocao relampago escopada por canal e com entrega gratis. Nenhuma das duas
coisas existe hoje, e a razao e a mesma: **a regra de preco mora numa superficie.**

Quatro fatos do codigo.

**Primeiro: `Promotion` e `Coupon` vivem em `shopman/storefront`** (`shopman/storefront/models/promotions.py:8`
e `:68`), um app de superficie. O motor de preco do orquestrador os alcanca por um adapter cuja
docstring declara exatamente esse contorno: *"Separa shop/ de storefront/ nos modifiers. Adapters podem
importar de qualquer app; modifiers e services de shop/ nao devem."*
(`shopman/shop/adapters/promotion.py:4-5`). O gate de fronteira permite, porque libera
`shop/adapters/` (`shopman/shop/tests/test_import_boundaries.py:136-149`) — legal pela regra, invertido
pela constituicao: regra de preco depende de vitrine.

E o contorno ja vazou: `shopman/shop/adapters/pricing.py:41` importa `Promotion` direto, usa
`Promotion.PERCENT` (`:70`, `:97`) e chama metodos **privados** do `DiscountModifier` — `_matches`
(`:74`) e `_calc_discount` (`:76`). Uma costura que um modulo do proprio lado ja contorna nao esta
protegendo nada.

**Segundo: promocao nao tem escopo de canal nenhum.** A lista de campos e completa e nao ha
channel/listing: `name`(`:15`), `type`(`:16`), `value`(`:17`), `valid_from`(`:21`),
`valid_until`(`:22`), `skus`(`:23`), `collections`(`:29`), `min_order_q`(`:35`),
`fulfillment_types`(`:40`), `customer_segments`(`:46`), `birthday_only`(`:52`), `is_active`(`:57`).
`get_active_promotions` filtra so `is_active` e janela (`adapters/promotion.py:12-24`), e o
`DiscountModifier` nunca chama `get_channel_rule_params`. **Uma relampago da web aplica no PDV e no
iFood hoje.** O unico freio e grosso: `ChannelConfig.Rules.modifiers` (`shopman/shop/config.py:155-171`,
aplicado em `packages/orderman/shopman/orderman/services/modify.py:104-120`) desliga *todas* as
promocoes automaticas de um canal, sem escolher qual.

**Terceiro: entrega gratis existe, mas so como configuracao de logistica.** Tres caminhos:
`DeliveryZone(mode="override", fee_q=0)` — cujo help_text diz *"0 = entrega gratis"*
(`shopman/storefront/models/delivery.py:76-80`) —, `DeliveryDistanceBand(fee_q=0)` (`:157-161`) e o
limiar `free_delivery_above_q` (`shopman/shop/modifiers.py:927`). Nenhum e escopavel por publico,
cupom ou janela, porque `Promotion.TYPE_CHOICES` tem apenas `percent` e `fixed`
(`storefront/models/promotions.py:11-13`).

**Quarto: `RuleConfig` `promotion_discount` e um interruptor que nao interrompe.** Existe no seed com
prioridade 20 (`config/management/commands/seed.py:5057-5063`) e `PromotionRule` esta declarada
(`shopman/shop/rules/pricing.py:33-42`, com `__init__` que so faz `pass`), mas o `DiscountModifier`
jamais consulta o motor de regras: apenas `AvailabilityDiscountModifier` (`modifiers.py:209`) e
`TimeWindowDiscountModifier` (`:272`) chamam `get_channel_rule_params`. **Desligar a regra no Admin nao
desliga promocao nem cupom.** E a mesma "mentira de admin" que a ADR-017 recusou em
`use_ai_generation`.

---

## Decisao

### 1. `Promotion` e `Coupon` voltam para `shopman/shop`

Nao vao para `offerman`, apesar de a constituicao §4.1 atribuir a ele um *"pricing core: preco base,
preco contextual, promocoes e politicas futuras"*. O motivo e dependencia: os campos da `Promotion` sao
de tres dominios estrangeiros ao offerman — `customer_segments` guarda segmento RFM ou ref de grupo do
guestman (casado em `modifiers.py:601-604`), `birthday_only` le `Customer.birthday` do guestman,
`fulfillment_types` e conceito de orderman. So `skus`/`collections` sao offerman. Levar o model para la
importaria tres vocabularios alheios num pacote kernel, e
`test_kernel_packages_do_not_import_host_layers` (`test_import_boundaries.py:96-112`) barra na hora.

Promocao e **cross-domain por natureza**: offerman x guestman x orderman. E a ADR-005 §3 e explicita
sobre onde dominios se encontram — *"o framework e o UNICO lugar onde dominios se encontram"*.

A §4.1 fica satisfeita sem contradicao, porque offerman **ja declara o buraco** para preco contextual
em vez de possuir a tabela: `OFFERMAN["PRICING_BACKEND"]`
(`packages/offerman/shopman/offerman/conf.py:86-105`), preenchido neste deployment em
`config/settings.py:853` e cobrado por system check (`shopman/shop/checks.py:477-485`). Offerman e dono
do preco de tabela e das faixas por vitrine; promocao e injetada pela costura. **A deriva nunca foi
"nao esta no offerman" — foi "esta numa superficie".**

E e um retorno, nao uma novidade: os dois models **nasceram** no orquestrador
(`shopman/shop/migrations/0001_initial.py:72` e `:233`) e sairam para a superficie por
`DeleteModel`+`CreateModel` (`shop/migrations/0010_remove_cashmovement_session_and_more.py:22-23`,
`:58-62`; `storefront/migrations/0001_initial.py:16-37`).

### 2. A geografia de entrega vem no mesmo bonde, e o adapter deixa de existir

`DeliveryZone` e `DeliveryDistanceBand` (`storefront/models/delivery.py:8` e `:131`) tambem vao para
`shopman/shop`. Nao sao pricing, mas seus unicos consumidores reais estao no orquestrador:
`DeliveryFeeModifier` (`modifiers.py:890-913`) e `DeliveryZoneRule`
(`shopman/shop/rules/validation.py:232-233`).

Com as quatro tabelas em `shop`, **`shop/adapters/promotion.py` e apagado inteiro** — suas seis funcoes
(`:12`, `:27`, `:45`, `:63`, `:72`, `:79`) passam a ser chamadas diretas de service, e o setting
`SHOPMAN_PROMOTION_ADAPTER` (`shopman/shop/adapters/__init__.py:34`, `:54`) sai. Isso obedece a ADR-001:
adapter existe para 2+ implementacoes reais, nunca para contornar uma fronteira que esta no lugar
errado. O vazamento de `adapters/pricing.py:41` desaparece junto, e o backend passa a se chamar
`PromotionPricingBackend` — ele preenche a costura de preco contextual do offerman, e nao tem mais nada
de storefront.

`shop/adapters/audience_sources.py` (`:16`, `:37`, `:53`) continua sendo adapter legitimo:
`CustomerFavorite` e `StockAlertSubscription` sao dados de superficie de cliente, nao regra de preco.

### 3. `Promotion.ref`

```python
ref = models.SlugField(_("codigo"), max_length=64, unique=True, db_index=True)
```

Hoje `Promotion` so tem `name` e `pk` (`storefront/models/promotions.py:15`), o que viola a
constituicao §3.1: *"`ref` deve ser o identificador canonico exposto a operacoes, logs e
integracoes"*. E e o que a `Campaign` aponta (ADR-020).

Apontar para `Coupon.code` seria mais barato — ja e unique (`:71`) — e esta errado: cupom e o
**ativador** de uma promocao, nao a promocao. Uma relampago automatica nao tem codigo nenhum, e
amarrar a campanha ao cupom obrigaria a inventar um codigo so para poder anunciar.

### 4. `Promotion.channels` — M2M, vazio = todos

```python
channels = models.ManyToManyField("shop.Channel", blank=True, verbose_name=_("canais"))
```

Copia exata de `RuleConfig.channels` (`shopman/shop/models/rules.py:38-42`), inclusive a semantica
"vazio = todos". Isso preserva o comportamento de **toda** promocao existente: sem data migration, sem
mudanca no dia do deploy, e a relampago passa a poder valer so na web.

Com a ADR-018, `channels` alcanca canal `display`, e por isso a promocao fica descobrivel no Google, na
Meta e no menuboard — hoje impossivel, porque o feed so conhecia preco de tabela.

O nome e `channels` e nunca `platforms`: `RuleConfig.channels` ja e o precedente, e "platform" e a
palavra que a ADR-018 esta eliminando.

### 5. `free_delivery` e o terceiro `type`, renunciado no dono da taxa

```python
FREE_DELIVERY = "free_delivery"
TYPE_CHOICES = [(PERCENT, "Percentual"), (FIXED, "Valor fixo"), (FREE_DELIVERY, "Entrega gratis")]
```

Resolvido **dentro de `_effective_fee_q`** (`modifiers.py:922-936`), nunca como linha de desconto. Isso
e obrigatorio, nao estilistico: `_is_non_merchandise_line` (`:46-48`) blinda a linha
`__DELIVERY_FEE__` contra desconto em dez pontos do arquivo (`:169`, `:224`, `:357`, `:372`, `:379`,
`:476`, `:967`, `:982`, `:1074`, `:1087`), e essa invariante mantem a taxa com **um dono**. Entrega
gratis e renuncia da taxa por quem a calcula, nao desconto aplicado por outro.

O encanamento ja existe. `DeliveryFeeModifier.apply` carrega `session.data` (`:776`), que **ja contem**
`coupon_code` (escrito em `shopman/shop/services/cart.py:238`), e roda em `order=70`, cinquenta slots
depois do `DiscountModifier` em `order=20` (`shopman/shop/handlers/__init__.py:262-273`, ordenados por
`packages/orderman/shopman/orderman/registry.py:150-152`). O cupom ja esta resolvido e estampado em
`session.pricing["coupon"]` (`modifiers.py:513-517`) quando a taxa e calculada. **Zero encanamento
novo.**

E o resultado aparece certo de graca: taxa zerada **remove a linha** em vez de gerar uma de R$ 0,00
(`:851-856`).

**`value` ganha semantica em vez de virar campo morto.** Para `free_delivery`, `0` significa renuncia
total e `> 0` significa teto da renuncia em centavos — "entrega gratis ate R$ 8,00". Reusa a coluna que
ja existe (`:17`), sem migration extra, e cobre o caso real de padaria que quer subsidiar frete curto
sem bancar o longo.

**`clean()` exige `fulfillment_types` compativel.** Promocao de entrega gratis com
`fulfillment_types=["pickup"]` nao quer dizer nada; validacao na borda evita configurar mentira.

**Duas politicas, um dono.** `_effective_fee_q` passa a resolver renuncia de duas fontes: o limiar
permanente (`free_delivery_above_q`, `:927`, lido de `Shop.defaults` via
`shopman/shop/projections/cart.py:509-525`) e a promocao ativa. Isso **nao** e segundo dono da taxa —
e um dono lendo duas politicas, e vence a que renuncia mais, na mesma convencao best-wins que o projeto
ja usa para desconto.

### 6. O `RuleConfig` decorativo e apagado, nao consertado

Duas saidas eram possiveis para o interruptor que nao interrompe: fazer o `DiscountModifier` consultar
`get_channel_rule_params("promotion_discount")`, ou remover a regra.

**Remover.** Com `Promotion.channels`, escopo de canal por promocao passa a ter dono. Ligar tambem o
gate de `RuleConfig` criaria **duas** formas de dizer "esta promocao nao vale neste canal" — o segundo
source of truth que a ADR-011 recusou. O liga-desliga global por canal continua existindo, e continua
em `ChannelConfig.Rules.modifiers` (`config.py:155-171`), que e o lugar certo para "este canal nao roda
promocao automatica".

Saem: a linha `promotion_discount` do seed (`seed.py:5057-5063`) e a classe `PromotionRule`
(`rules/pricing.py:33-42`). `D1Rule`, `EmployeeRule` e `HappyHourRule` ficam — as duas ultimas sao
consumidas de verdade.

### 7. A elegibilidade de cupom sai da superficie

`CartService.apply_coupon` (`shopman/storefront/cart.py:322-378`) hoje valida quatro portas na
superficie — existencia (`:334`), esgotamento (`:337`), janela (`:344`) e
`_customer_eligible_for_promo` (`:355`) — antes de chamar o kernel. Isso e regra de negocio em app de
vitrine, e o PDV nao a executa: o operador nao tem caminho de cupom nenhum.

A validacao passa inteira para `shopman/shop/services/cart.py`, junto de `apply_coupon_code`
(`:218-253`). A superficie volta a ser o que a ADR-012 pede: interpretacao de request e apresentacao de
erro no dialeto `{detail, field, errors}`. Efeito colateral desejado: **o PDV ganha cupom** sem
reimplementar nada.

### 8. Nao existe preco por grupo de cliente

`PriceTier.listing_ref` esta declarado (`packages/guestman/shopman/guestman/models/price_tier.py:24-29`)
e **consumido por ninguem** em `shopman/`; `metadata` ate documenta
`{"discount_percent": 10}` como exemplo (`:38-41`). Este ADR **nao** liga essa costura e **nao** a
apaga: promocao por segmento ja e resolvida por `customer_segments` (`promotions.py:46`), que tem
consumidor real. Ligar `listing_ref` criaria um terceiro caminho de preco por publico sem pedido que o
justifique (§8.3).

---

## Consequencias

### Positivas

- Regra de preco deixa de depender de app de superficie; a inversao sancionada some.
- Um adapter inteiro e um setting desaparecem (`adapters/promotion.py`, `SHOPMAN_PROMOTION_ADAPTER`).
- O vazamento de `adapters/pricing.py:41` — import direto e chamada de metodo privado — deixa de
  existir por construcao.
- Relampago passa a ser escopavel por canal, e visivel em Google, Meta e menuboard (ADR-018).
- Entrega gratis passa a ser oferta, com toda a elegibilidade que a `Promotion` ja tem: janela, SKU,
  colecao, segmento, aniversario, pedido minimo e cupom.
- O PDV ganha cupom de graca.
- Some um interruptor que mentia no Admin.
- `offerman` nao muda: a costura `PRICING_BACKEND` que ele ja declarava passa a ser preenchida por um
  modulo com o nome certo.

### Negativas

- Migration de mudanca de app para quatro models, com rename de quatro tabelas.
- Os nomes de URL do Admin `admin:storefront_promotion_changelist` e `..._coupon_changelist` mudam, e
  estao hardcoded em `shopman/backstage/admin/navigation.py:168-169` e afirmados em
  `shopman/shop/tests/test_rules.py:446,453`.
- ~15 arquivos de teste importam de `shopman.storefront.models`, seis deles em `shopman/shop/tests/`.
- `config/management/commands/seed.py` toca em tres pontos: import (`:82`), teardown (`:744-745`) e
  ~75 linhas de fixture (`:4597-4682`).
- `shopman/storefront/presentation/catalog.py:560-568` faz preload proprio de `Promotion` (a correcao
  de N+1) e passa a chamar service.
- `DeliveryFeeModifier` passa a resolver promocao, ganhando uma consulta no caminho de checkout.

### Mitigacoes

- A janela e agora: `go-live-v1` nao existe (a tag mais avancada e `v0.1.0-alpha`), logo a ADR-015 nao
  vigora. Depois do alpha, mover model exige expand-contract.
- A mudanca de app usa `SeparateDatabaseAndState` + `AlterModelTable`, **nao** o
  `DeleteModel`+`CreateModel` que foi usado na ida (`shop/migrations/0010:22-23`). Aquilo foi
  destrutivo; aqui ha dado de staging que o dono edita a mao.
- **Nao ha FK cross-app para reescrever.** O unico FK e interno (`Coupon.promotion`,
  `promotions.py:72`); todo vinculo com pedido e por string em JSON — `Session.data["coupon_code"]`
  (`services/cart.py:238`), `Session.pricing["coupon"]["code"]` (`modifiers.py:513-517`),
  `Order.snapshot["pricing"]["coupon"]` e `Order.data["coupon_use_recorded"]` (`lifecycle.py:332`,
  `:344`). Nenhuma dessas strings muda.
- `channels` vazio = todos garante zero mudanca de comportamento no deploy.

---

## Invariantes

- `Promotion`, `Coupon`, `DeliveryZone` e `DeliveryDistanceBand` moram em `shopman/shop`. Nenhum app de
  superficie define regra de preco ou de frete.
- Nao existe adapter de promocao. Regra de preco no orquestrador chama service, nao costura.
- Nenhum modulo importa `Promotion` para chamar metodo privado de modifier.
- A taxa de entrega tem **um** dono: `DeliveryFeeModifier`. Renuncia acontece em `_effective_fee_q`,
  nunca como linha de desconto.
- `free_delivery` nunca produz linha de desconto sobre `__DELIVERY_FEE__`.
- Escopo de canal de uma promocao vive em `Promotion.channels`, e em nenhum outro lugar.
- `channels` vazio significa todos os canais, jamais nenhum.
- Promocao com `customer_segments` ou `birthday_only` nao se aplica em canal `display` (ADR-018 §5.2).
- Validacao de cupom mora em `shop/services/cart.py`. Superficie interpreta request e formata erro.
- `Promotion` tem `ref`. A `Campaign` aponta para o `ref` da promocao, nunca para o codigo do cupom.
- Percentual de promocao nao vive em constante de codigo.

---

## Migracao

Ordem obrigatoria; cada passo entrega valor sozinho e passa `make test`.

1. **`ref` e `channels`.** Migration em `shopman/storefront` acrescentando `Promotion.ref` (data
   migration preenchendo por slug do `name`) e `Promotion.channels` M2M vazio. Comportamento
   identico, porque vazio = todos.
2. **Mudanca de app.** `SeparateDatabaseAndState` retirando os quatro models do estado de
   `storefront` e criando-os no estado de `shop`, mais `AlterModelTable` renomeando
   `storefront_promotion` -> `shop_promotion`, `storefront_coupon` -> `shop_coupon`,
   `storefront_deliveryzone` -> `shop_deliveryzone`, `storefront_deliverydistanceband` ->
   `shop_deliverydistanceband`. Nenhum dado se move.
3. **Imports e admin.** Todos os consumidores passam a importar de `shopman.shop.models`; o admin
   sai de `storefront/admin/promotions.py` para `shopman/shop/admin/`; os nomes de URL em
   `backstage/admin/navigation.py:168-169` e em `test_rules.py:446,453` acompanham.
4. **Morte do adapter.** `shop/adapters/promotion.py` e apagado, os seis chamadores passam a chamar
   service, `SHOPMAN_PROMOTION_ADAPTER` sai do mapa, e `StorefrontPricingBackend` vira
   `PromotionPricingBackend` sem o import direto nem o uso de metodo privado.
5. **Elegibilidade no orquestrador.** As quatro portas de `storefront/cart.py:322-378` migram para
   `shop/services/cart.py`; a superficie so interpreta e formata erro. O PDV ganha o endpoint de
   cupom.
6. **`free_delivery`.** Terceiro `type`, renuncia em `_effective_fee_q` lendo `session.data`, `value`
   como teto, `clean()` exigindo `fulfillment_types` compativel.
7. **Limpeza da regra decorativa.** `PromotionRule` e a linha `promotion_discount` do seed saem.
8. **Seed.** Fixture de promocao passa a declarar `ref` e `channels`, e ganha uma promocao
   `free_delivery` de exemplo escopada a um canal.

---

## Criterios de aceite

- `make test` e `make admin` verdes; `make test-migrations` verde com schema limpo do zero.
- `grep -rn "shopman.storefront.models import" shopman/shop/` retorna vazio, exceto
  `adapters/audience_sources.py`.
- `shopman/shop/adapters/promotion.py` nao existe; `grep -rn "SHOPMAN_PROMOTION_ADAPTER"` retorna
  vazio.
- `grep -rn "_matches\|_calc_discount" shopman/shop/adapters/` retorna vazio.
- `grep -rn "PromotionRule\|promotion_discount"` retorna vazio.
- Promocao com `channels` vazio aplica em todos os canais; com `channels=[web]` nao altera preco em
  pedido de PDV nem de iFood.
- Cupom de `free_delivery` num pedido de entrega zera a taxa e **remove** a linha
  `__DELIVERY_FEE__` — nao gera linha de R$ 0,00.
- `free_delivery` com `value=800` num frete de R$ 12,00 deixa R$ 4,00 de taxa.
- Nenhuma linha `__DELIVERY_FEE__` recebe desconto em nenhum caminho.
- Limiar de subtotal e promocao de frete simultaneos: vence a renuncia maior.
- Aplicar cupom pelo PDV produz o mesmo desconto que pela loja, com o mesmo dialeto de erro.
- `Order` fechado antes da migracao continua legivel: `snapshot["pricing"]["coupon"]` intacto.

---

## Alternativas descartadas

**`Promotion` em `offerman`.** E o que a constituicao §4.1 sugere ao dar a offerman um "pricing core",
mas os campos da promocao sao de tres dominios estrangeiros a ele (`customer_segments` de guestman,
`birthday_only` de guestman, `fulfillment_types` de orderman). Um pacote kernel nao pode importar tres
irmaos, e o gate de fronteira barra. A §4.1 e honrada pela costura `PRICING_BACKEND` que offerman ja
declara.

**Deixar onde esta e so acrescentar `channels` e `free_delivery`.** Entregaria as duas capacidades sem
a mudanca de app. Mas manteria regra de preco numa superficie, manteria o adapter que existe so para
contornar a fronteira, e manteria `adapters/pricing.py` chamando metodo privado — divida que fica mais
cara depois da tag.

**Apontar `Campaign` para `Coupon.code` em vez de criar `Promotion.ref`.** Mais barato, porque `code`
ja e unique. Errado por semantica: cupom e ativador, nao oferta. Obrigaria toda relampago automatica a
inventar um codigo que ninguem vai digitar.

**`free_delivery` como linha de desconto sobre `__DELIVERY_FEE__`.** Reusaria o `DiscountModifier`,
mas exigiria furar `_is_non_merchandise_line`, que hoje protege a linha em dez pontos do arquivo. A
taxa passaria a ter dois donos — quem a calcula e quem a desconta — e o `Order.total_q`, que e soma de
linhas, ficaria dependendo da ordem em que os dois rodaram.

**`free_delivery` com campo proprio de teto.** Uma coluna nova para um valor que a coluna `value` ja
pode carregar, num tipo em que ela estaria vazia. Reusar `value` mantem o model com tres tipos e um
significado por tipo.

**Ligar o gate de `RuleConfig` no `DiscountModifier`.** Faria o interruptor do Admin funcionar, mas
criaria a segunda forma de escopar promocao por canal, ao lado de `Promotion.channels`. O desligamento
global por canal ja tem dono em `ChannelConfig.Rules.modifiers`.

**Mover tambem `CustomerFavorite` e `StockAlertSubscription`.** Sao dados de superficie de cliente, nao
regra de preco; `adapters/audience_sources.py` e adapter legitimo e continua.

**Ligar `PriceTier.listing_ref` para preco por faixa.** Terceiro caminho de preco por publico, sem
consumidor que o peca. Fica declarado e inerte, como esta.

---

## Referencias

- [Constituicao Semantica](../constitution.md) — §2.1, §3.1, §3.2, §4.1, §8.3, §10
- [ADR-001 - Protocol/Adapter e fronteiras de core](adr-001-protocol-adapter.md)
- [ADR-004 - String refs para identificadores cross-domain](adr-004-string-refs.md)
- [ADR-005 - Orquestrador como centro de coordenacao](adr-005-orchestrator-as-coordination-center.md)
- [ADR-011 - Formula sem FormulaPlan](adr-011-formula-and-cashshift.md)
- [ADR-012 - Contrato headless de superficie](adr-012-headless-surface-contract.md)
- [ADR-015 - Backward-compat pos-producao](adr-015-backward-compat-policy-post-prod.md)
- [ADR-018 - Superficie e canal, com politica comercial](adr-018-surface-is-channel-with-commerce-policy.md)
