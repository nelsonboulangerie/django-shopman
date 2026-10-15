# GRUPOS-CLIENTE PLAN — relação N:N cliente ↔ grupo e vantagens tipadas (Core)

> Frente §7.1 / onda 5 (parte CORE) do `docs/plans/CADASTRO-TURBO-INVENTARIO.md`.
> Branch `claude/grupos-core`, base `origin/main` `ad256f041`.
> As decisões do dono de 14/10/2026 estão em `docs/plans/COORDENACAO-GO-LIVE.md` §7.1
> e NÃO se reabrem.

## 0. Reconciliação com o que já está no main (#1803 / #1804 / #1805)

Antes de escrever Core, leitura do que o trilho turbo do Gestor já entregou:

`shopman/backstage/services/customer_groups.py`, `shopman/backstage/api/customer_groups.py`,
`shopman/backstage/projections/customer_groups.py`, `shopman/shop/admin/price_tier.py`,
`shopman/shop/services/customer_groups.py`, `surfaces/orders-nuxt/app/pages/customers/groups.vue`
e `CustomerGroupFormPanel.vue`, mais `shopman/shop/management/commands/setup_commercial_groups.py`.

**(a) O N:N no Core já existia? NÃO.** Confirmado no main `ad256f041`:
`Customer.price_tier` era FK ÚNICA (`models/customer.py:84`, `on_delete=PROTECT`) e o
`PriceTier` não tinha coleção de clientes (só o reverso `customers` da própria FK); as
migrações do guestman paravam na `0005`. Faltava o vínculo N:N. É o que esta frente entrega.

**(b) Como o framework representava “grupo”.** O grupo é `guestman.PriceTier`. O desconto é
uma `Promotion` comum com `ref=grupo-<tier.ref>` e `customer_segments=[tier.ref]`, derivada por
`shop/services/customer_groups.py::sync_group_discount`; a lista de preço é `PriceTier.listing_ref`
(cascata de `shop/handlers/pricing.py`); o resto (`discount_kind`, `rounding`, `savings_message`)
vive em `PriceTier.metadata`. O #1804 é o CRUD do grupo no Gestor: `backstage/services/customer_groups.py`
→ `backstage/api/customer_groups.py` (permissão `shop.manage_customers`) → `backstage/projections/customer_groups.py`
→ Nuxt. O vínculo cliente↔grupo no turbo era UM só: `priceTierRef` em `backstage/services/customers.py`.

**O que esta frente faz com isso.** ESTENDE o que o #1804 trouxe, sem caminho paralelo:

| Peça | Situação |
|---|---|
| Entidade do grupo | **reusa** `guestman.PriceTier` (nada de grupo novo) |
| Desconto do grupo | **reusa** a `Promotion` `grupo-<ref>` e o `sync_group_discount` |
| Lista de preço | **reusa** `PriceTier.listing_ref` (agora escolhida pelo melhor grupo) |
| CRUD do grupo no Gestor | **reusa** `backstage/services/customer_groups.py` + API + projection |
| Core novo MEDIDO | `Customer.price_tiers` (M2M, migração `0006`) e `PriceTierAdvantage` |
| Motor | `shop/services/promotions.py` e `shop/modifiers.py` passam a resolver MELHOR por tipo |
| Vínculo no Gestor | `backstage/services/customers.py` grava o M2M (o form segue com UM grupo) |
| Fora desta frente (onda 5b, UI) | expor N:N e `PriceTierAdvantage` na API/projection/Nuxt |

Ou seja: a API e a tela do grupo continuam as mesmas; o que muda é o modelo por baixo e o
motor. A exposição de vários grupos e das vantagens tipadas na superfície Nuxt é a onda 5b.

## 1. O que o dono decidiu (14/10/2026)

- Cliente pode pertencer a **mais de um grupo** comercial.
- Vale a **melhor vantagem por tipo, sem acumular** (dois descontos não somam).
- **Sem sobrepreço por grupo**: só desconto.
- **Equipe −30% só na retirada**; **Aliança Francesa −15%**.
- Arredondamento do preço final para o R$ X,00 ou R$ X,50 mais próximo.

## 2. O defeito de Core que esta frente resolve

Hoje `guestman.Customer.price_tier` é uma **FK única** (`models/customer.py:84`) e o
desconto do #1766 é por faixa: o motor grava `Promotion.customer_segments=[tier.ref]` e
`shop/modifiers.py` casa **uma** faixa por cliente. "Cliente em mais de um grupo, melhor
vantagem por tipo" exige relação N:N no Guestman e um motor que resolva a lista.

Medição (inventário §3, onda 5): é a **única** mudança de `packages/` da frente.

## 3. Desenho

### 3.1 Vínculo N:N (guestman)

- `Customer.price_tiers = ManyToManyField(PriceTier, related_name="customers")` passa a ser
  a **fonte canônica** do vínculo. A FK `Customer.price_tier` sai.
- `Customer.primary_price_tier` = o grupo de maior `priority` (desempate por `name`), para
  leitura de tela/PDV que ainda fala "o grupo do cliente". É derivado, sem coluna.
- O default continua: cliente novo sem grupo recebe o `PriceTier.is_default`.
- Lista carregada em lote (`prefetch_related("price_tiers")`): uma consulta por
  precificação, nunca uma por item.

### 3.2 Vantagens tipadas (guestman)

`PriceTierAdvantage` — uma vantagem tipada por grupo:

| Campo | Papel |
|---|---|
| `tier` | grupo dono (`related_name="advantages"`) |
| `kind` | tipo: `free_shipping`, `exclusive_collections`, `exclusive_notifications` |
| `priority` | desempate entre os grupos do MESMO cliente |
| `is_active` | liga/desliga sem apagar |
| `config` | payload tipado por `kind` (chaves em `docs/reference/data-schemas.md`) |

`UniqueConstraint(tier, kind)`: uma vantagem de cada tipo por grupo.

**Fronteira deliberada:** o **desconto** do grupo continua sendo a `Promotion` `grupo-<ref>`
(domínio de preço do `shop`, com canal, janela e o BI lendo `discount_kind`) e a **lista de
preço** continua em `PriceTier.listing_ref` (cascata do Offerman). O modelo tipado cobre as
demais vantagens; o resolvedor trata os tipos de forma uniforme.

### 3.3 Melhor vantagem por tipo (shop/services/promotions.py)

- `customer_group_promotion(price_tier_refs, channel_ref=...)` passa a receber a LISTA de
  grupos do cliente e devolve o **melhor** desconto entre eles (percentual > fixo > valor).
- `best_group_advantage(price_tier_refs, kind, ...)` resolve, por tipo:
  - `discount` → a melhor `Promotion` `grupo-<ref>` dos grupos;
  - `price_list` → o melhor `PriceTier.listing_ref` (maior `priority`);
  - demais tipos → a `PriceTierAdvantage` ativa de maior `priority`.
- Nada acumula: o motor já aplica **um** desconto vencedor por linha ("maior desconto
  ganha"); o que muda é o universo de candidatos, que passa a ser a união dos grupos.

### 3.4 Motor

- `CustomerPricingModifier` publica `ctx["price_tiers"]` (lista) além do grupo primário e
  do mapa `ref → metadata`; `DiscountModifier._matches` casa `customer_segments` contra
  qualquer grupo do cliente.
- O arredondamento e o `discount_kind` vêm do grupo **vencedor** da linha (promoção
  `grupo-<ref>`), não do primário.
- A cascata de preço (`shop/handlers/pricing.py`) usa o melhor `listing_ref` dos grupos.

### 3.5 Migração (guestman `0006`)

1. Cria `PriceTierAdvantage`.
2. Adiciona o M2M.
3. `RunPython`: copia `Customer.price_tier_id` → `price_tiers`.
4. Remove `Customer.price_tier`.

Sem migração em `shop`: a `Promotion` derivada e `listing_ref` não mudam de lugar.
Numeração conferida (`guestman` para em `0005`; `shop` não é tocado).

### 3.6 Admin

- `PriceTierAdmin` (gestor e Unfold) ganha inline de `PriceTierAdvantage`.
- `CustomerAdmin` troca o filtro/campo `price_tier` pelo M2M `price_tiers`.

## 4. Impacto de Core e blast radius

Muda `packages/guestman` (modelo + migração). Toda leitura de `customer.price_tier*` passa
para `primary_price_tier` / `price_tiers`: `guestman` (services, api, admin, merge, insights),
`shop` (modifiers, handlers, cart, sessions, pos, audience, order_edit), `backstage`
(projections/services) e `storefront` (identity, account_export). Os testes que criam
`Customer(price_tier=...)` passam a `price_tiers=[...]`.

## 5. Testes

- Guestman: N:N (cliente em dois grupos), default, primário, lista de preço, limpar grupos.
- Promoções: cliente em Equipe (−30%) **e** Aliança (−15%) paga **só** os −30% (não soma);
  o arredondamento vem do grupo VENCEDOR, não do primário.
- Vantagens tipadas: melhor por tipo entre grupos (prioridade), sem acumular.
- Suítes verdes: guestman 511, shop 11.802 (as 10 falhas iniciais eram classificação nova
  em `config/synthetic_purge.py` e logger do except — corrigidas), storefront 2.705.

## 6. Ordem dos commits

1. Este plano + `docs/reference/data-schemas.md`.
2. Modelo N:N + vantagens tipadas + migração (guestman).
3. `shop/services/promotions.py` (melhor por tipo) + motor.
4. Leituras fora do Core (backstage/storefront) + admin.
5. Testes.
