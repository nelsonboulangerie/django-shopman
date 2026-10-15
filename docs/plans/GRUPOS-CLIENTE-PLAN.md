# GRUPOS-CLIENTE PLAN — relação N:N cliente ↔ grupo e vantagens tipadas (Core)

> Frente §7.1 / onda 5 (parte CORE) do `docs/plans/CADASTRO-TURBO-INVENTARIO.md`.
> Branch `claude/grupos-core`, base `origin/main` `ad256f041`.
> As decisões do dono de 14/10/2026 estão registradas em
> `docs/plans/COORDENACAO-GO-LIVE.md` §7.1 e NÃO se reabrem.

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

- Guestman: N:N (cliente em dois grupos), default, migração de dados.
- Promoções: cliente em Equipe (−30%) **e** Aliança (−15%) paga **só** os −30% (não soma);
  o vencedor é o melhor; prioridade no empate.
- Vantagens tipadas: melhor por tipo entre grupos (prioridade), sem acumular.
- Contagem de consultas do reprice não cresce com o número de itens.

## 6. Ordem dos commits

1. Este plano + `docs/reference/data-schemas.md`.
2. Modelo N:N + vantagens tipadas + migração (guestman).
3. `shop/services/promotions.py` (melhor por tipo) + motor.
4. Leituras fora do Core (backstage/storefront) + admin.
5. Testes.
