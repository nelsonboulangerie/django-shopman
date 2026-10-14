# PRECO-POR-GRUPO PLAN — grupos de clientes com vantagens comerciais (preço)

> Frente §7.1 do `docs/plans/COORDENACAO-GO-LIVE.md`. Branch
> `claude/preco-por-grupo`, base `origin/main` `0e9acc7e3`.
> As decisões do dono de 14/10/2026 estão aqui registradas e NÃO se reabrem.

## 1. O que o dono decidiu (14/10/2026)

- **Só desconto**, sem sobrepreço por grupo.
- **Equipe −30% só na retirada.**
- **Aliança Francesa −15%.**
- **Arredondamento do preço final** para o R$ X,00 ou R$ X,50 mais próximo
  (pode subir ou descer até R$ 0,25; o teste cobre os dois lados).
- **A melhor vantagem vence por tipo e não acumula.**
- A lista de preço diferenciada do grupo tem um dono canônico:
  `offerman.Listing` (o preço) apontado por `guestman.PriceTier.listing_ref`
  (de quem é), orquestrado pela cascata de `shop/handlers/pricing.py`, com o
  cliente no contexto em TODO canal (PDV e loja online).

## 2. Desenho

### 2.1 Sem Core novo

A `guestman.PriceTier` já é o grupo comercial: tem `listing_ref`, `priority` e
`metadata`. O desconto do grupo já é uma `Promotion` comum, ligada ao grupo por
`customer_segments` e derivada no Admin (`shop/admin/price_tier.py`,
`sync_group_discount`, ref `grupo-<ref do grupo>`). Esta frente NÃO cria campo
nem migração em modelo do Core.

As chaves novas vivem em `PriceTier.metadata` (JSONField que já existe),
documentadas antes do uso em `docs/reference/data-schemas.md`:

| Chave | Tipo | Papel |
|---|---|---|
| `discount_kind` | `str` | Classificação do desconto do grupo para o B.I. (`equipe`, `parceiro`, ...). Copiada para `pricing.discount.items[].discount_kind` na linha vencedora. |
| `rounding` | `int` (centavos) | Passo do arredondamento do preço unitário final do grupo. `50` = R$ 0,50; `0` desliga. Ausente = 50 (a regra da casa). |
| `savings_message` | `str` | Texto da economia por grupo, com os marcadores `{amount}` e `{group}`. Vazio cai no copy global `CHECKOUT_GROUP_SAVINGS`. Editável no Admin. |

### 2.2 Cliente no contexto de preço (defeito latente)

Hoje `ItemPricingModifier` lê `ctx["customer"]`, mas **nenhum chamador preenche
a chave**; com isso `OffermanPricingBackend.get_line_prices` sempre recebe
`customer=None` e a cascata "faixa do cliente → listing" nunca muda preço.

Conserto sem Core: um modifier novo de orquestração, `CustomerPricingModifier`
(`code = "pricing.customer"`, `order = 5`), resolve o cliente da sessão UMA vez
(`select_related("price_tier", "insight")`) e deixa no `ctx` o `customer`, o
`price_tier` (ref), o `metadata` da faixa, o segmento RFM e o aniversário. O
`ItemPricingModifier` (ordem 10) passa o cliente ao backend e o
`DiscountModifier` (ordem 20) reusa o contexto em vez de reler a linha. Vale
para PDV e loja online porque a sessão é a fonte nos dois.

### 2.3 Cascata de preço em lote

`get_line_prices` já lê TODAS as faixas e o preço base de todas as linhas numa
consulta por origem (faixa do cliente, vitrine do canal, base). O conserto só
liga a ponta que faltava (o cliente). O cardápio anônimo continua igual:
sem cliente, o modifier sai sem consultar e a cascata é a do canal.

### 2.4 Arredondamento e tipo do desconto

No `DiscountModifier`, quando o percentual vencedor é o desconto do PRÓPRIO
grupo (ref `grupo-<ref>`), o preço unitário final é arredondado ao passo
`rounding` (ROUND_HALF_UP) e o desconto efetivo passa a ser a diferença real. O
arredondamento entra na disputa "maior desconto ganha" já líquido, para a linha
nunca cobrar diferente do que arbitrou. O tipo (`discount_kind`) vai no registro
por linha (`pricing.discount.items[]`) e a economia do grupo é consolidada em
`pricing.discount.savings`.

### 2.5 Aposentadoria da EmployeeRule

A `EmployeeRule` (`shop/rules/pricing.py`, faixa `staff`, 20%, só retirada) e
o `EmployeeDiscountModifier` saem inteiros. O grupo Equipe vira
`PriceTier(ref="staff")` + `Promotion` `grupo-staff` (−30%,
`customer_segments=["staff"]`, `fulfillment_types=["pickup"]`), editável no
Admin. Uma regra só para o mesmo cliente.

### 2.6 Mensagem de economia

Quando `pricing.discount.savings.amount_q > 0`, o checkout (loja online) e o
comprovante (PDV) mostram "Hoje você economizou R$ X por ser [grupo]". O texto
por grupo é `PriceTier.metadata.savings_message`; o padrão é o copy
`CHECKOUT_GROUP_SAVINGS`. O comprovante lê o snapshot do pedido, que é imutável.

## 3. Impacto de Core

Nenhum. Não muda `packages/` (guestman, offerman, orderman ficam como estão);
não há campo novo nem migração de modelo. As leituras usam as APIs existentes do
`offerman` (`Listing`/`ListingItem`) e do `orderman` (registry de modifiers).

## 4. Desempenho

- Uma consulta para a faixa/preço do cliente identificado por reprecificação
  (nunca uma por item); as faixas e o preço base de todas as linhas saem em
  lote (`bulk_listing_tiers`, `bulk_product_base_prices`).
- Cardápio anônimo igual e cacheável: sem cliente, nenhuma consulta nova.
- Teste de contagem de consultas no padrão
  `shopman/storefront/tests/web/test_catalog_nplus1_measure.py`: reprova se a
  contagem crescer com o número de itens.

## 5. Ordem dos commits

1. Este plano + `docs/reference/data-schemas.md`.
2. Cliente no `ctx` em todo canal + cascata `listing_ref` (teste ponta a ponta).
3. `discount_kind`/`rounding`/`savings_message` no Admin do grupo + seed Equipe.
4. Aposentadoria da `EmployeeRule`/`EmployeeDiscountModifier`.
5. Arredondamento R$ 0,50 + `discount_kind` e `savings` no `pricing.discount`.
6. Mensagem de economia no checkout e no comprovante.
