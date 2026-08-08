# ADR-018 - Superficie e canal: uma entidade, com politica comercial

**Status:** Proposto
**Data:** 2026-08-08
**Escopo:** `shopman/shop` (`Channel`, `Showcase`, `ChannelConfig`, `CatalogSyncState`, projections de
menuboard e feed), `shopman/backstage` (matriz de catalogo), `offerman` (nenhuma mudanca de model)
**Supersede:** a separacao `Channel` x `Showcase` declarada em `shopman/shop/config.py:35-36` e
`shopman/shop/models/showcase.py:1-13`
**Prepara:** ADR-019 (a oferta e seu dono) e ADR-020 (campanha anuncia, nao vende)

---

## Contexto

A operacao gerencia disponibilidade de produto em duas familias de superficie: **canais de venda**
(web, PDV, iFood) e **feeds de exibicao** (menuboard da loja, catalogo do Google, catalogo da
Meta). Hoje sao dois models, e a pergunta que originou este ADR foi se o feed deveria virar canal
nao transacional para ter acesso a Listing, preco e promocao.

Quatro fatos do codigo delimitam a resposta.

**Primeiro: o read model ja unificou; so o write model esta partido.** A projection da matriz de
catalogo tem **um** eixo, `surfaces`, e concatena canais e feeds na mesma lista
(`shopman/backstage/projections/catalog.py:330`), carregando o papel num booleano `transactional`
dentro de `SurfaceProjection` (`:36-53`). O tipo da superficie ja e um so no contrato
(`surfaces/orders-nuxt/app/types/catalog.ts:6`).

Como os models sao dois, tudo em volta e duplicado: dois construtores de superficie na projection
(`:269-316` para feed, `:218-258` para canal), dois caminhos de service
(`shopman/backstage/services/catalog.py:79-88` e `:90-111`), dois admins e dois vocabularios de
enumeracao. A diferenca de conteudo entre uma celula de feed e uma de canal e **legitima** — o feed
nao tem preco (`projections/catalog.py:366-386` versus `:389-422`) — mas ela nao exige duas
entidades: exige um discriminador.

**Segundo: o feed le a fonte de preco errada — hoje sem consequencia, e essa e a janela.** Os dois
renderizadores usam `Product.base_price_q` direto — o XML de Google/Meta em
`shopman/shop/views/product_feed.py:83` e o menuboard em
`shopman/shop/projections/menuboard.py:79` — enquanto o canal vende pelo `ListingItem.price_q`
(`packages/offerman/shopman/offerman/models/listing.py:98-102`).

**Verificado em 2026-08-08 contra o banco de desenvolvimento: dos 153 `ListingItem`, zero tem preco
diferente do `base_price_q` do produto.** Ou seja, o defeito e **latente**, nao ativo: as duas fontes
coincidem porque ninguem ainda precificou por canal. Ele se torna real no primeiro dia em que alguem
usar a capacidade que o `ListingItem` sempre teve — e nesse dia o feed do Google passa a anunciar um
preco que a loja nao cobra, o que a constituicao §2.3 proibe (nenhum pacote mente sobre o mundo), o
que reprova item em Merchant Center por divergencia com a landing page, e o que a ADR-014 ja nomeou
como o sintoma preco-vitrine x preco-carrinho.

Consertar agora custa um passo de migracao e muda zero preco exibido. Consertar depois de alguem
precificar por canal significa corrigir precos publicos ja anunciados.

**Terceiro: a maquina de preco ja e generica por canal.** `CatalogService.unit_price` resolve
`effective_listing = listing or channel` (`packages/offerman/shopman/offerman/service.py:104`) e
cai em `_get_price_from_listing` (`:184-212`). Nao falta mecanismo de preco por superficie: falta o
feed **ser** uma superficie que a maquina reconhece. A convencao que sustenta isso ja existe e ja e
cobrada por system check — `Listing.ref == Channel.ref`
(`packages/offerman/shopman/offerman/models/listing.py:20-22`), verificada com `SHOPMAN_W004` em
`shopman/shop/checks.py:523-554`.

**Quarto: `platform` significa tres coisas.** `CatalogSyncState.platform` esta documentado como
*"platform / projection channel ref (== listing_ref): ifood, meta, google, whatsapp"*
(`shopman/shop/models/catalog_sync.py:27-28`), com unique `(sku, platform)` (`:42-44`) — mas `ifood`
e ref de `Channel` enquanto `meta` e `Showcase.kind`: **uma coluna, dois tipos de chave**. O
parametro `?platform=meta` do feed e um terceiro uso, seletor de dialeto
(`shopman/shop/views/product_feed.py:27-30`). E `platforms` do broadcast e um quarto
(`shopman/shop/models/broadcast.py:114-117`).

Ha ainda um sinal social: o codigo da tela pede desculpa pelo nome. *"No backend o model do feed
chama-se `Showcase` — dai os nomes internos aqui"*
(`surfaces/orders-nuxt/app/pages/catalog.vue:30-32`), e o proprio model ja tem
`verbose_name = _("feed")` (`shopman/shop/models/showcase.py:48-49`). Comentario que se desculpa por
um nome e prova de que o nome esta errado.

---

## Decisao

### 1. Nao existe `Showcase`. Superficie e `Channel`

Aplicando a constituicao §8.3 ("isto e core do dominio? plugin do dominio? conveniencia de
framework?"): exibir catalogo com preco e responder a mesma pergunta que vender — *o que esta sendo
ofertado, em que apresentacao, com qual preco e elegibilidade* (§4.1). O que difere entre um feed e
um canal nao e a **natureza** da superficie; e **ate onde a interacao comercial vai**.

Duas entidades para uma pergunta produzem o que o codigo ja exibe: maquinaria duplicada em volta de
uma diferenca que caberia num discriminador. E dar preco ao `Showcase` sem unificar criaria um segundo
mecanismo para "o que esta superficie mostra e a que preco" — o erro que a ADR-011 nomeou ao recusar
`FormulaPlan`.

O discriminador e a **politica comercial**: nao *o que a superficie e*, mas *ate onde a interacao
comercial vai nela*.

### 2. `Channel.commerce_policy` — coluna indexada, nunca chave de config

```python
class CommercePolicy(models.TextChoices):
    DISPLAY = "display", _("somente exibicao")
    ORDER   = "order",   _("venda completa")

commerce_policy = models.CharField(
    _("politica comercial"),
    max_length=16,
    choices=CommercePolicy.choices,
    default=CommercePolicy.ORDER,
    db_index=True,
)
```

O nome segue o precedente `Product.availability_policy`
(`packages/offerman/shopman/offerman/models/product.py:125`): `<substantivo>_policy`, nao
`<adjetivo>_policy` — por isso `commerce_policy` e nao `commercial_policy`, pela mesma razao que
`availability_policy` nao e `available_policy`. Valores tersos seguem
`ChannelConfig.Pricing.policy` (`shopman/shop/config.py:139-143`).

**E coluna e nao chave de `Channel.config` por dois motivos.** O `ChannelConfig` e uma cascata de
overrides — defaults do codigo, depois `Shop.defaults`, depois `Channel.config`
(`shopman/shop/models/channel.py:60-85`). Politica comercial nao e ajuste de comportamento: e a
natureza do canal, e natureza nao pode ser herdada, senao um default de loja torna o Google
transacional em silencio. Alem disso ela passa o criterio de **query indexada**: os sites de
enumeracao filtram por ela.

`default=ORDER` e deliberado: toda linha existente e canal de venda, entao a migration nao precisa
de passo de dados e nada muda de comportamento no dia do deploy.

### 3. `intent` nao entra agora, mas a forma o admite

Existem superficies com compra parcial — catalogo de WhatsApp que produz intencao de compra por
mensagem, checkout nativo de Instagram/Facebook que nao opera no Brasil. Nenhuma esta implementada,
e a constituicao §8.3 e clara: se a resposta e "nao sei", ainda nao entra. Por isso o terceiro valor
**nao e criado**.

O que muda e a **forma**: `TextChoices` em vez de `is_transactional: bool`. Um booleano mentiria no
meio — intencao de compra nao e exibicao nem venda — e a constituicao §2.4 proibe estado que embute
multiplas preocupacoes. A escolha do enum e o que permite `intent` entrar depois como terceiro valor
sem quebra semantica. A forma admite o futuro; os valores nao o inventam.

### 4. Canal `display` nao tem preco proprio: ele anuncia o preco de um canal transacional

O feed manda o cliente para a loja — `link = f"{base}/produto/{sku}"`
(`shopman/shop/views/product_feed.py:80`). Logo o preco correto do feed **nao e um preco dele**: e o
preco do canal onde a pessoa vai transacionar. E isso que a especificacao de Merchant Center exige
(feed tem de casar com a landing page) e e isso que o menuboard tambem quer — mostrar o que se paga
no balcao.

Portanto um canal `display` **nao ganha Listing**. Ele ganha um ponteiro textual (ADR-004) para o
canal cujo preco anuncia, e os renderizadores resolvem preco por esse alvo:

```
Channel(ref="google", commerce_policy=display, config.display.prices_from="web")
```

`views/product_feed.py:83` e `projections/menuboard.py:79` param de ler `base_price_q` e passam por
`unit_price(sku, qty, channel=prices_from)`, que cai em `base_price_q` quando o alvo nao tem
`ListingItem` (`packages/offerman/shopman/offerman/service.py:104-110`). **Zero codigo novo de
pricing, e um ponteiro em vez de N linhas.**

O ganho e estrutural, nao de curadoria: com o preco resolvido do canal de destino, divergencia entre
feed e landing page **deixa de ser possivel**, em vez de virar um dever que alguem precisa cumprir
item por item.

### 5. Membresia do canal `display` sao colecoes associadas

A curadoria continua sendo por conjunto, como hoje (`Showcase.collections`,
`shopman/shop/models/showcase.py:34-36`), e a excecao por SKU continua existindo
(`options["paused_skus"]`, `:63-76`). O que muda e so onde isso mora: passa a ser o aspecto
`Display` do canal.

Forcar o feed a ter `ListingItem` para obter simetria com os canais de venda seria achatar uma
distincao real — **canal `display` nao tem preco proprio**, e a linha de listing existe para
carregar preco. A assimetria e informacao, nao descuido: e a mesma licao que a ADR-017 registrou ao
recusar o prefixo `quality_` em `batch_ref`.

O comportamento atual, alias, ja estava certo: a projection devolve `price_q=None` na celula de feed
(`shopman/backstage/projections/catalog.py:366-386`) e o service recusa editar preco ali
(`shopman/backstage/services/catalog.py:84-85`). O que estava errado era o **preco exibido**, nao a
forma da celula.

### 5.1. Menuboard e superficie interna; feed e superficie publica

As quatro rotas de exibicao sao hoje totalmente publicas — `View` puro, sem auth nem permissao
(`shopman/shop/views/product_feed.py:90`, `shopman/shop/views/menuboard.py:22` e `:37`,
`shopman/shop/menuboard_urls.py:15-29`, montadas em `config/urls.py:84`). Isso e aceitavel para o XML,
que **precisa** ser publico para Google e Meta buscarem. Nao e aceitavel para o menuboard.

A decisao 4 eleva o risco: com `prices_from` apontando para o PDV, um menuboard publico **publica uma
segunda tabela de precos** a quem tiver a URL. No Brasil, publicidade suficientemente precisa vincula
o fornecedor, entao preco alcancavel publicamente e preco a honrar. O agravante e o SSE:
`/menuboard/<ref>/events/` inscreve qualquer visitante no canal `stock-catalog`
(`menuboard_urls.py:22-28`), entregando o ritmo operacional da loja — o que esta esgotando e quando a
fornada entra.

Portanto: **as rotas de menuboard passam a exigir dispositivo confiavel**, pelo mecanismo de device
trust que o `doorman` ja tem e que o quiosque de producao ja usa. Provisiona-se a TV uma vez e o
cookie duravel resolve o resto — tela na parede nao faz login interativo. O XML permanece publico.

E um system check amarra as duas pontas: **canal rastreado publicamente so pode tirar preco de canal
cujo preco e publico.** Sem ele, alguem configura `prices_from="pos"` num canal Google e o preco do
balcao vai para o mundo.

### 5.2. Canal `display` so anuncia oferta incondicional

Um feed e anonimo: nao ha cliente no momento em que o XML e gerado. Logo ele so pode anunciar oferta
que nao depende de quem olha. Promocao com `customer_segments` ou `birthday_only`
(`shopman/storefront/models/promotions.py:46-56`) **nunca** entra em canal `display`.

Isso e invariante, nao filtro de conveniencia: sem ele, o sistema anunciaria desconto de
aniversariante para o mundo — mentira sobre o mundo (§2.3) e promessa que a loja nao honra.

### 6. `Showcase` inteiro vira o 9o aspecto do `ChannelConfig`

O que o `Showcase` carregava — dialeto de saida, curadoria e excecoes — descreve **como o canal
exibe**, nao o que ele e. Ninguem filtra canal por nenhum desses valores. Portanto e exatamente o que
o `ChannelConfig` existe para carregar:

```python
@dataclass
class Display:
    format: str = ""            # "" | "google_merchant" | "meta_catalog" — dialeto do XML
    collections: list = ...     # refs de Collection — a curadoria (era Showcase.collections)
    prices_from: str = ""       # ref do canal transacional cujo preco e anunciado
    paused_skus: list = ...     # excecoes por SKU (era Showcase.options["paused_skus"])
```

`format` seleciona **dialeto de XML**, e por isso `menuboard` nao e um valor dele: menuboard e
**rota**, nao dialeto. `/menuboard/<ref>/` renderiza HTML com SSE e `/feed/<ref>.xml` renderiza XML —
a rota ja escolhe o renderizador, e o que resta ao `format` e dizer se o XML segue a especificacao do
Google ou a da Meta. Valores explicitos em vez de `google`/`meta`, que nao dizem *Google o que*. Com o
dialeto no canal, o parametro `?platform=` do feed sai.

As rotas continuam nomeando o **artefato** (`feed`, `menuboard`), nunca o acesso. Nomear rota por
acesso poria a politica em dois lugares — o gate na view e a palavra na URL — e no dia em que
divergissem a URL mentiria.

O resultado e que **`Channel` ganha exatamente uma coluna** (`commerce_policy`) e todo o resto da
absorcao acontece em config. A assimetria e informacao: **uma coluna** para a natureza da superficie,
**um aspecto de config** para o comportamento dela, cada uma pelo motivo certo. A regra 1 do "Core e
Sagrado" pede JSONField para o contextual; a natureza nao e contextual, o comportamento e.

### 7. `CatalogSyncState.platform` vira `channel_ref`

Com uma entidade so, o alvo de sincronizacao e sempre ref de canal. O campo passa a `channel_ref`
com unique `(sku, channel_ref)` (hoje `:42-44`), no formato de ponteiro textual da ADR-004 e alinhado
a convencao `Listing.ref == Channel.ref`. A ambiguidade "ora canal, ora kind" morre porque as duas
coisas viraram uma — nao por convencao nova.

**Depois disto, `platform` tem exatamente um sentido em `shopman/shop`**: a lista de alvos de
publicacao da campanha (`instagram`, `facebook`, `google_business`, `whatsapp`). Esse uso e o mais
limpo dos tres — nenhuma daquelas strings e `Channel.ref` — e por isso a ADR-020 **nao** o renomeia.
Matar os outros dois sentidos aqui e o que torna o nome correto la, sem tocar nele.

### 8. Enumeracao de canal passa a ser explicita, nunca por exclusao

Toda enumeracao filtra por politica. Sao seis sites: `shopman/shop/checks.py:504` e `:536`,
`shopman/shop/handlers/_sse_emitters.py:60`, `shopman/backstage/projections/catalog.py:163` e
`:225`, `shopman/backstage/services/catalog.py:55`. Todo o resto do codigo usa
`Channel.objects.get(ref=X)`, lookup por chave que nunca sera chamado com ref de exibicao.

O antipadrao a proibir esta no seed:
`happy_hour.channels.set(Channel.objects.exclude(ref="web"))`
(`config/management/commands/seed.py:5112`). Enumerar "todos menos um" passaria a incluir Google e
Meta. Aqui seria inocuo — feed nao transaciona — mas a forma e fragil por construcao. Selecao de
canal e por politica, nunca por exclusao.

### 9. Canal `display` nunca entra no espaco transacional

O medo que justificava a separacao (`config.py:35-36`: *"Exibicao/feed nao sao canais"*) era poluir
pedido, PDV e regra. Ele continua valido como **invariante**, e passa a ser cobrado por system check
em vez de por separacao de model: canal `display` nao aparece em seletor de canal de operador, nao
recebe `Order` e nao entra em `RuleConfig.channels`. O que era garantido pela ausencia do model passa
a ser garantido por um teste — mais barato e mais explicito do que dois models.

---

## Consequencias

### Positivas

- Some um model e some uma entidade da ontologia, com **uma unica coluna nova** no lugar.
- Divergencia de preco entre feed e landing page deixa de ser possivel por construcao, em vez de virar
  dever de curadoria.
- A curadoria por colecao continua auto-atualizavel: adicionar produto na colecao continua aparecendo
  no feed.
- `_build_showcase_surfaces()` (`projections/catalog.py:269-316`) desaparece: a matriz passa a ter um
  unico construtor de superficie.
- Promocao passa a alcancar canal `display` (ADR-019): a relampago fica descobrivel no Google e na
  Meta, hoje impossivel porque o feed so conhece preco de tabela.
- A palavra `platform` perde dois dos seus tres sentidos sem custo proprio.
- `offerman` nao muda em nada: `Listing`, `ListingItem` e `Collection` ja estavam certos, e sao
  justamente o que faz a unificacao funcionar.

### Negativas

- Uma migration em `shopman/shop` com coluna nova, absorcao de `Showcase` em `Channel.config` e rename
  de `CatalogSyncState.platform`.
- `prices_from` vazio faz o canal cair em `base_price_q`, que e o comportamento errado de hoje. Feed
  novo criado sem apontar destino nasce mentindo — precisa de check.
- A celula da matriz continua com semantica diferente por politica (feed nao tem preco). A
  unificacao acaba com dois **models**, nao com a diferenca real entre exibir e vender.
- Promocao segmentada nunca aparece em feed, entao parte do catalogo promocional fica invisivel para
  Google e Meta por decisao de projeto.

### Mitigacoes

- A janela e agora: `go-live-v1` nao existe (a tag mais avancada e `v0.1.0-alpha`), logo a ADR-015
  ainda nao vigora e o rename e barato. Depois do alpha, o mesmo trabalho exige expand-contract.
- `default=ORDER` garante que nenhum canal existente muda de comportamento no deploy da coluna.
- System check novo: canal `display` com `prices_from` vazio ou apontando para canal inexistente vira
  warning, na mesma familia do `SHOPMAN_W004` de paridade Listing/Channel
  (`shopman/shop/checks.py:523-554`).
- A absorcao e verificavel: mesma lista de SKUs no XML de cada feed antes e depois.

---

## Invariantes

- Nao existe `Showcase`. Superficie e `Channel`, discriminada por `commerce_policy`.
- Canal `display` nunca recebe `Order`, nunca aparece em seletor de operador e nunca entra em
  `RuleConfig.channels`.
- Politica comercial e coluna, nunca chave de `Channel.config`: natureza nao se herda pela cascata.
- Comportamento de exibicao e aspecto de `ChannelConfig`, nunca coluna: renderizacao nao e natureza.
- Canal `display` nao tem `Listing` nem preco proprio. Ele anuncia o preco de um canal transacional.
- Nenhum renderizador de superficie le `Product.base_price_q` diretamente; todos passam por
  `unit_price(..., channel=prices_from)`, que cai em `base_price_q` quando o alvo nao tem
  `ListingItem`.
- Membresia de canal `display` sao colecoes; de canal `order` sao `ListingItem`s. A diferenca segue a
  politica, e a politica existe para isso.
- Canal `display` nunca anuncia oferta condicional (`customer_segments`, `birthday_only`).
- Canal rastreado publicamente (`format` preenchido) so tira preco de canal cujo preco e publico.
- Rota de menuboard exige dispositivo confiavel. Rota de feed XML e publica.
- Rota nomeia o artefato (`feed`, `menuboard`), nunca o acesso. Acesso se aplica no gate.
- `menuboard` nao e valor de `format`: e rota. `format` so distingue dialeto de XML.
- Selecao de canal e por politica, nunca por exclusao de ref.
- `intent` nao existe enquanto nao houver implementacao.
- A palavra `platform` nao designa superficie em nenhum lugar do codigo.

---

## Migracao

Ordem obrigatoria; cada passo entrega valor sozinho e passa `make test`.

1. **Coluna.** Migration em `shopman/shop` com `commerce_policy`, `default=ORDER`, indexada. Nada
   consome ainda; comportamento identico.
2. **Aspecto `Display` no `ChannelConfig`.** Novo dataclass em `config.py` com os quatro campos,
   defaults vazios. Nada consome ainda.
3. **Absorcao.** Data migration: cada `Showcase` vira `Channel(commerce_policy=display)` com
   `config.display` recebendo `collections`, `paused_skus`, `format` (vazio para menuboard,
   `google_merchant`/`meta_catalog` para os demais) e `prices_from` — **o canal da loja para os feeds,
   o canal do PDV para os menuboards**, porque a TV está fisicamente na loja e tem de concordar com o
   balcao. Nenhum `Listing` e criado. Comportamento identico: os renderizadores ainda leem
   `base_price_q`.
3.1. **Trava do menuboard.** As tres rotas de menuboard passam a exigir dispositivo confiavel, e o
   system check de preco publico entra junto. Vem **antes** do passo 4 de proposito: a trava precede a
   exposicao do preco do PDV, nunca o contrario.
4. **Renderizadores.** `product_feed.py` e `menuboard.py` passam a resolver preco por
   `prices_from`. **Este e o passo que corrige o preco mentiroso**, e e o unico que muda numero
   exibido — de propria intencao, e verificavel item por item contra a pagina de destino.
5. **Matriz.** `_build_showcase_surfaces()` sai; a matriz constroi superficie por um caminho unico,
   lendo `config.display` em vez do model. O toggle de feed continua escrevendo excecao de SKU, agora
   em `config.display.paused_skus`.
6. **`CatalogSyncState`.** Rename `platform` -> `channel_ref` com a unique correspondente, e
   `?platform=` sai da rota do feed.
7. **Gates.** System check e teste de fronteira para os invariantes do item 9; enumeracoes passam a
   filtrar por politica; o `exclude(ref="web")` do seed vira selecao explicita.
8. **Remocao.** `Showcase`, seu service, sua projection de board e seu admin saem. Zero residual.

---

## Criterios de aceite

- `make test` e `make admin` verdes; `test_import_boundaries` sem excecao nova.
- `make test-migrations` verde: schema limpo do zero e grafo consistente.
- `grep -ri "showcase" shopman/ surfaces/ config/` retorna vazio.
- `grep -rn "platform" shopman/shop/ shopman/backstage/` so retorna ocorrencias de broadcast.
- `grep -rn "base_price_q" shopman/shop/views/ shopman/shop/projections/` retorna vazio.
- Antes e depois do passo 3, o XML de cada feed tem exatamente a mesma lista de SKUs.
- Produto com `ListingItem.price_q` diferente do `base_price_q` no canal apontado por `prices_from`
  aparece no feed com o preco daquele canal — o mesmo valor da pagina de destino.
- Adicionar um produto a uma colecao do feed faz o produto aparecer no XML sem nenhum outro ato.
- Promocao com `customer_segments` ou `birthday_only` nunca altera preco em canal `display`.
- Canal `display` nao aparece no seletor de canal do PDV, e tentar criar `Order` nele falha com erro
  de dominio.
- Canal `display` sem `prices_from` valido emite warning de system check.
- Canal com `format` preenchido e `prices_from` apontando para canal de preco nao publico falha no
  system check.
- `/menuboard/<ref>/`, `/data/` e `/events/` respondem 403 sem dispositivo confiavel; `/feed/<ref>.xml`
  continua respondendo 200 sem credencial.
- A TV do balcao exibe o mesmo preco que o PDV cobra, para todo SKU com preco proprio no PDV.
- Matriz de catalogo: a celula de feed e a de canal passam pelo mesmo construtor.

---

## Alternativas descartadas

**Manter `Showcase` como model, dando-lhe uma fonte de preco.** Resolveria o preco mentiroso sem
unificar. Mas mantem duas entidades para uma pergunta, mantem dois construtores de superficie na
matriz, e exigiria em `Showcase` a mesma politica, o mesmo ponteiro de preco e o mesmo gate de
enumeracao que o `Channel` ja tem — ou seja, reimplementaria `Channel` sob outro nome.

**Dar `Listing` e `ListingItem` ao canal `display`.** Foi o primeiro desenho deste ADR, e estava
errado. Simetria com os canais de venda parecia limpeza, mas achata uma distincao real: canal
`display` nao tem preco proprio, e `ListingItem` existe para carregar preco. Custava uma
materializacao de N linhas por feed, matava a curadoria auto-atualizavel por colecao, e deixava a
divergencia de preco possivel — bastava alguem esquecer de curar um item. O ponteiro `prices_from`
resolve o mesmo problema com uma chave em vez de N linhas, e torna a divergencia impossivel em vez de
improvavel.

**`prices_from` como coluna em vez de config.** Ninguem filtra canal por ele e ele so faz sentido em
canal `display`; coluna que e nula na maioria das linhas e coluna sem criterio (regra 1 do "Core e
Sagrado").

**Renomear `menuboard` para `display` (rota e demais referencias).** Tentador, porque unificaria o
vocabulario num termo generico. Recusado por escopo: **o feed do Google e `commerce_policy=display` e
nao e um menuboard**. `display` e a politica — o genero, que cobre Google, Meta e as telas —, enquanto
`menuboard` e um renderizador dela, uma especie. Usar a mesma palavra para o genero e para uma especie
recria exatamente a patologia que este ADR e a ADR-020 estao eliminando em `platform`, `channel` e
`broadcast`. A regra fica: `commerce_policy` responde *o que este canal pode fazer*; a rota responde
*como ele e renderizado*; `format` responde *em qual dialeto o XML sai*. E "menuboard" e o termo padrao
da industria para quadro digital de menu — preciso, nao jargao. Sao 121 ocorrencias, todas mantidas.

**Nomear as rotas por acesso (`/feed/public/`, `/feed/local/`).** Tentador porque a diferenca de
acesso e real. Recusado por dois motivos. Poe a politica em dois lugares — o gate na view e a palavra
na URL — e quando divergirem a URL mente; acesso se aplica, nao se anuncia (nao chamamos `/admin/` de
`/private-admin/`). E colapsa dois eixos independentes numa palavra: quem consome (maquina ou pessoa)
e quem pode acessar. Um menu publico legivel por pessoa — QR na mesa — seria publico *e* humano, e nao
teria casa nesse esquema. `feed` e `menuboard` ja sao os termos precisos dos dois artefatos, e manter
as rotas e a opcao de menor custo e maior verdade.

**`is_transactional: bool`.** Mais barato e mais legivel hoje, mas mente no meio: catalogo de WhatsApp
com intencao de compra nao e exibicao nem venda. A constituicao §2.4 proibe estado que embute varias
preocupacoes, e trocar booleano por enum depois custa mais do que nascer enum.

**`commercial_policy`.** Adjetivo onde o precedente do repo usa substantivo: `availability_policy`,
nao `available_policy`. Manter a forma faz `grep _policy` devolver a familia inteira.

**`commerce` sem sufixo.** Terso, mas nao diz que e politica: `commerce = "display"` le mal, e o campo
perde o parentesco visivel com `availability_policy` e com `Pricing.policy`.

**`surface_kind` / `SurfaceKind` como nome da coluna.** Descreve taxonomia, nao compromisso, e
colidiria com `SurfaceKind` do contrato da matriz
(`surfaces/orders-nuxt/app/types/catalog.ts:6`) e com o diretorio `surfaces/`. Alem disso "kind"
convida a virar saco de tipos; politica convida a ter poucos valores com consequencia clara.

**Deixar `Showcase.kind` como coluna no `Channel`.** Formato de saida nao e natureza e ninguem filtra
por ele; seria coluna sem criterio, contra a regra 1 do "Core e Sagrado".

**Derivar o formato do `ref` do canal.** Formula de string para inferir comportamento e o antipadrao
que a ADR-017 §5 desmontou no `batch_ref`: admite exatamente um caso por nome e quebra no dia em que
houver dois feeds Google.

---

## Referencias

- [Constituicao Semantica](../constitution.md) — §2.1, §2.3, §2.4, §2.6, §3.1, §4.1, §8.3, §10
- [ADR-001 - Protocol/Adapter e fronteiras de core](adr-001-protocol-adapter.md)
- [ADR-004 - String refs para identificadores cross-domain](adr-004-string-refs.md)
- [ADR-011 - Formula sem FormulaPlan](adr-011-formula-and-cashshift.md)
- [ADR-012 - Contrato headless de superficie](adr-012-headless-surface-contract.md)
- [ADR-014 - Corte dado/apresentacao](adr-014-surface-data-presentation-cut.md)
- [ADR-015 - Backward-compat pos-producao](adr-015-backward-compat-policy-post-prod.md)
- [ADR-017 - Qualidade e o resultado da producao](adr-017-quality-as-production-outcome.md)
