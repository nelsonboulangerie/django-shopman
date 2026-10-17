# CORE-SOVEREIGNTY — WP-7: inventário e evidência de aborto

**Base:** `3cfc8d017f05ca9b8af03acbd968137cc8b2cef3` (`main`, 2026-10-17)
**Resultado:** WP-7 abortado pelo critério aprovado; nenhum código foi movido.

## Inventário físico

O universo medido é todo `shopman/shop/**/*.py` de produção, excluindo somente
`tests/`, `migrations/` e `projections/`. Projections são read-side e estão fora deste WP
por decisão explícita do plano.

| Área | Fontes |
|---|---:|
| raiz | 54 |
| `services` | 173 |
| `management` | 74 |
| `adapters` | 52 |
| `handlers` | 41 |
| `models` | 23 |
| `admin` | 15 |
| `rules` | 7 |
| `webhooks` | 7 |
| `backup` | 6 |
| `views` | 6 |
| `omotenashi` | 5 |
| `templatetags` | 2 |
| **Total** | **465** |

Exclusões medidas: 22 projections, 561 testes e 115 migrations. Pela AST, 249 fontes
não importam kernel diretamente, 140 importam um kernel e 76 importam dois ou mais.

O estado formal é **0% classificado**: não há inventário versionado, schema, manifesto ou
gate de unidades. Logo há 465 fontes órfãs para os fins do aceite proposto. O diretório não
permite inferir a responsabilidade semântica com honestidade: decisões aparecem em
`shopman/shop/marketing_policy.py:MarketingPolicy:80`,
`shopman/shop/operator_capacity_policy.py:OperatorCapacityPolicy:40`,
`shopman/shop/purchase_policy.py:PurchasePolicy:43` e
`shopman/shop/services/cancellation.py:OperatorCancelPolicy:141`; composição aparece em
`shopman/shop/lifecycle.py:dispatch:318` e
`shopman/shop/production_lifecycle.py:dispatch_production:62`; contrato e configuração se
sobrepõem em `shopman/shop/config.py:ChannelConfig:62`.

Não foi criado um inventário parcial com classificação heurística. Isso transformaria
incerteza semântica em dado aparentemente autoritativo e deixaria lixo de governança após
o aborto.

## Mapa atual da decisão `promotion`

- persistência/configuração: `shopman/shop/models/promotion.py:Promotion:23`;
- promoções ativas: `shopman/shop/services/promotions.py:get_active_promotions:20`;
- cupom ativo: `shopman/shop/services/promotions.py:get_coupon_promotion:193`;
- decisão e aplicação na cesta: `shopman/shop/modifiers.py:DiscountModifier:797`;
- elegibilidade por item: `shopman/shop/modifiers.py:DiscountModifier._matches:1211`;
- cálculo monetário: `shopman/shop/modifiers.py:DiscountModifier._calc_discount:1243`;
- preço contextual: `shopman/shop/adapters/pricing.py:PromotionPricingBackend:12`;
- validação antecipada do cupom:
  `shopman/shop/services/cart.py:customer_eligible_for_promotion:447`;
- renúncia promocional de frete:
  `shopman/shop/modifiers.py:resolve_delivery_fee_waiver:1617`;
- registro no pipeline: `shopman/shop/handlers/__init__.py:_register_pricing_modifiers:320`.

O adapter de preço já delega elegibilidade e cálculo aos métodos do modifier em
`shopman/shop/adapters/pricing.py:81-83`. É um acoplamento invertido a método privado, mas
não são duas implementações independentes da mesma conta.

## Baseline congelada

Foram usados cenários históricos causais, não o total bruto de commits que misturaram
defeitos:

| Cenário | Commit | Arquivos causais |
|---|---|---:|
| promoção restrita a fulfillment antes da escolha | `afb5a1d31` | 2 |
| desconto fixo por pedido, não por unidade | `0f40e6cfe` | 2 |
| segmento/grupo em cupom, cesta e vitrine | `4262f02d6` | 8 |
| escopo de canal coerente entre card, PDP, badge e cesta | `18412b5bf` | 5 |

Métrica composta: **soma 17; mediana 3,5; união 14 arquivos**.

Os conjuntos congelados são auditáveis abaixo. `P` é o novo
`shopman/shop/policies/promotion.py`; `PT` é seu teste puro
`shopman/shop/tests/test_promotion_policy.py`.

1. Fulfillment ausente — antes:
   `shopman/shop/modifiers.py`,
   `shopman/shop/tests/test_discount_modifier.py`.
   Depois: `P`, `PT`. **2 → 2**.
2. Fixo por pedido — antes e depois:
   `shopman/shop/modifiers.py`,
   `shopman/shop/tests/test_coupon_fixed_order_level.py`.
   A extração pura de elegibilidade/cálculo não move rateio nem mutação de sessão.
   **2 → 2**.
3. Segmento/grupo — antes:
   `shopman/shop/modifiers.py`,
   `shopman/shop/services/cart.py`,
   `shopman/storefront/cart.py`,
   `shopman/storefront/identity.py`,
   `shopman/storefront/presentation/catalog.py`,
   `shopman/storefront/presentation/product_detail.py`,
   `shopman/storefront/tests/e2e/test_persona_2_group_pricing.py`,
   `shopman/storefront/tests/e2e/test_persona_2_loyal.py`.
   Depois: esses mesmos oito paths mais `P` e `PT`: o modifier continua responsável por
   carregar o contexto do cliente, enquanto a policy precisa conhecer e testar o novo eixo
   de elegibilidade. **8 → 10**.
4. Canal — antes e depois:
   `shopman/shop/adapters/pricing.py`,
   `shopman/shop/projections/catalog_context.py`,
   `shopman/shop/services/fomo.py`,
   `shopman/storefront/presentation/catalog.py`,
   `shopman/storefront/tests/web/test_promotion_channel_scope_display.py`.
   A policy de item não substitui o transporte do canal nem a consulta centralizada em
   `services.promotions`. **5 → 5**.

O vetor depois é, portanto, **[2, 2, 10, 5]**: soma **19**, mediana **3,5** e união
**15 arquivos** (`P` e `PT` entram; nenhum dos 14 paths anteriores pode sair do conjunto
composto). Soma e união pioram; a mediana não melhora.

O recorte de cinco paths de `18412b5bf` é deliberado e reproduzível pela mensagem e pelo
diff do commit: adapter/PDP, projection, FOMO/badge, catálogo/card e o teste de paridade de
canal. As mudanças em `modifiers.py` e nos outros três testes pertencem aos dois defeitos
de rateio descritos separadamente no mesmo commit. Contar os dez arquivos integrais seria
inflar artificialmente o ganho.

## Por que uma policy maior não resolve

As regras dispersas respondem perguntas diferentes:

- `services/cart.py:customer_eligible_for_promotion:447`: o cliente pode ativar o cupom?
- `services/fomo.py:_promotions_for_sku:175`: a promoção pode ser anunciada sem
  conhecer o cliente?
- `modifiers.py:_free_delivery_covers_order:1702`: a promoção pode renunciar o frete?

Uni-las exigiria flags de propósito/modo e produziria uma god-policy. Manter os métodos
antigos como façade também seria reter a dispersão sob outro nome. Ambos violam o critério
de aborto e a regra de zero legado.

## Riscos descobertos, não corrigidos neste WP

`PromotionPricingBackend` reconstrói o contexto em
`shopman/shop/adapters/pricing.py:PromotionPricingBackend.get_price:21`, mas omite
`is_birthday` e `price_tiers`, que
`shopman/shop/modifiers.py:DiscountModifier._matches:1211` lê. A superfície hoje fornece
apenas `price_tier` e `customer_segment` em
`shopman/storefront/presentation/catalog.py:_build_items:469` e
`shopman/storefront/presentation/product_detail.py:build_product_detail:225`. Corrigir ou declarar esse
comportamento precisa de caracterização própria; fazê-lo durante o piloto contaminaria a
medição arquitetural.

O aceite “nenhuma constante específica de instância” também não é verdadeiro no estado
atual. Exemplos: `shopman/shop/adapters/_sms.py:DEFAULT_CODE_MESSAGE:20`,
`shopman/shop/adapters/courier_machine.py:USER_AGENT:46`,
`shopman/shop/watchman_infrastructure.py:ExternalMonitoringContractCheck.run:94`,
`shopman/shop/brand_tokens.py:_BRAND_LIGHT:72`,
`shopman/shop/services/receiving_position.py:DEFAULT_REFS:33` e
`shopman/shop/services/business_calendar.py:DELIVERY_SLOT_MINUTES:240`. Esses achados vão
para o WP-6, cujo objeto é tornar a Instância dado de runtime. O alias morto de
compatibilidade `shopman/shop/brand_tokens.py:_YELLOW:65`, encontrado na base e sem
consumidores, foi removido nesta mudança sob a regra de zero legado; marca e sua fronteira
seguem para WP-10/WP-11. Nenhum desses resíduos legitima a retomada do WP-7.

## Decisão

O piloto não foi executado porque o replay enumerado prova que sua condição necessária —
redução material dos arquivos a mudar — não pode ser satisfeita pela extração prevista.
Implementá-lo apenas para obter o mesmo número produziria churn descartável.

Por consequência, conforme o critério vinculante do plano:

- o piloto e o WP-7 estão **abortados**;
- não foram criados `policies/`, schema, manifestos, gate ou fixtures;
- nenhum model, migration, Admin, service ou adapter foi movido;
- este inventário físico e esta evidência permanecem como registro, sem alegar o aceite de
  100% de classificação;
- qualquer retomada exige novo plano com cenário cujo ganho possa ser medido antes da
  implementação, e não uma reorganização cosmética.
