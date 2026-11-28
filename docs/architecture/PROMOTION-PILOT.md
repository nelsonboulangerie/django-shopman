# Piloto de extração — pedido mínimo de promoção

Estado: **piloto executado e aceito**. O primeiro commit congelou cenário e baseline sem
mover código de produção; a extração foi feita somente no commit seguinte.

Este artefato executa a etapa 3 do WP-7 antes da extração. Ele separa a métrica de
localidade de uma mudança futura da pegada transitória do PR que fará a extração.

## Cenário S1 congelado

Hipótese controlada: uma decisão futura muda a elegibilidade no ponto exato em que o
subtotal de mercadorias é igual ao pedido mínimo, de inclusiva (`subtotal >= mínimo`)
para exclusiva (`subtotal > mínimo`). A mudança é apenas uma sonda de localidade: o
piloto preservará a regra inclusiva atual e não altera política comercial.

Vetores congelados:

| `min_order_q` | subtotal | regra atual |
| ---: | ---: | --- |
| 0 | 0 | elegível |
| 3.000 | 2.999 | não elegível |
| 3.000 | 3.000 | elegível; caso mutante de S1 |
| 3.000 | 3.001 | elegível |

Consumidores reais da mesma decisão:

1. preço contextual do catálogo, por `PromotionPricingBackend`;
2. desconto percentual ou fixo no carrinho/PDV, por `DiscountModifier`;
3. renúncia promocional de frete, por `_free_delivery_covers_order`.

Não entram no piloto models, migrations, Admin, offerman, validade temporal, canal,
segmento de cliente, aniversário, SKU, coleção ou tipo de atendimento.

## Regra de contagem

Conta-se um arquivo quando S1 exige editar a implementação da decisão ou uma asserção
que fixa o caso mutante. Não se contam formatação, documentação, manifesto ou testes de
delegação que continuariam válidos. A pegada transitória da extração será publicada à
parte e não será apresentada como a métrica de localidade futura.

## Antes

Produção — **2 arquivos**:

- `shopman/shop/adapters/pricing.py`: comparação do preço contextual;
- `shopman/shop/modifiers.py`: comparações de desconto, cupom fixo e frete grátis.

Verdade de teste do caso exato — **1 arquivo**:

- `shopman/shop/tests/test_free_delivery_promotion.py`: o pedido de 10.000 é aceito
  exatamente no mínimo de 10.000.

Os testes de cupom fixo exercitam valores estritamente abaixo ou acima do mínimo; não
mudariam em S1 e, por isso, não são inflados artificialmente no baseline. Também não há
asserção de igualdade para o preço contextual do catálogo hoje.

Métrica composta do cenário único:

- soma: **3 arquivos**;
- mediana: **3 arquivos**;
- união: **3 arquivos**.

## Desenho executado

Uma unidade `promotion.minimum-order-eligibility`, com um único verbo público puro:

```python
promotion_minimum_eligible(*, min_order_q: int, merchandise_subtotal_q: int) -> bool
```

O verbo é a única implementação da comparação e tem teste direto sem Django,
banco ou `DJANGO_SETTINGS_MODULE`. Os três consumidores apenas reúnem os dois inteiros e
delegam. O manifesto tem um entrypoint canônico, responsabilidade `decisão`,
`policy: true` e nenhum domínio, porto, evento, directive ou configuração.

Meta depois: `shopman/shop/policies/promotion.py` mais seu teste puro, portanto soma,
mediana e união de **2 arquivos**. A redução material esperada é **3 → 2 (33%)**; a
produção deve cair de **2 → 1 arquivo**.

## Depois

A meta foi atingida:

- produção: **1 arquivo**, `shopman/shop/policies/promotion.py`;
- verdade do caso limítrofe: **1 arquivo**,
  `scripts/tests/test_promotion_minimum_policy.py`;
- soma: **2 arquivos**;
- mediana: **2 arquivos**;
- união: **2 arquivos**;
- redução: **3 → 2 (33%)**, com a produção reduzida de **2 → 1**.

Os testes de consumidores simulam a resposta do verbo e provam delegação sem duplicar a
semântica do caso limítrofe. Uma busca pelos operadores de comparação junto a
`min_order_q` nos antigos consumidores não retorna ocorrência.

A pegada transitória do PR é deliberadamente maior que dois arquivos: inclui os três
consumidores, o teste de delegação, o manifesto, o inventário, o gate de namespace, sua
fixture negativa e este relatório. Esses arquivos não mudariam para executar S1 depois
da extração, portanto não pertencem à métrica futura.

## Elegibilidade inteira (laudo CORE-SOVEREIGNTY, A7-4)

O piloto extraiu só o mínimo; a elegibilidade continuava com três implementações
(`DiscountModifier._matches`, `services/cart.customer_eligible_for_promotion` e
`services/fomo._promotions_for_sku`), mais uma quarta, parcial, no anúncio do Marketing
(`services/marketing_facts._promotion`). Agora há uma só:

```python
promotion_matches(promo, PromotionContext(...)) -> bool
```

em `shopman/shop/policies/promotion.py`. O contexto diz quais eixos fazem parte da
pergunta (cliente sempre; item, atendimento e mínimo quando presentes; promessa a
qualquer visitante no selo da vitrine). Consumidores: carrinho da loja e do PDV
(`DiscountModifier`), preço contextual do catálogo (`PromotionPricingBackend`), frete
grátis (`_free_delivery_covers_order`), cupom do site e da concierge
(`customer_eligible_for_promotion`, via `validate_and_apply_coupon`), selo FOMO e
anúncio do Marketing.

### Métrica calculada, não declarada (A7-6)

`scripts/check_orchestrator_units.py` conta os arquivos de produção (em `shopman/shop`,
`storefront` e `backstage`) que TESTAM um campo de alvo da promoção (`skus`,
`collections`, `fulfillment_types`, `customer_segments`, `birthday_only`,
`min_order_q`) e imprime `policy_decision_files`. O gate reprova qualquer arquivo além do
módulo da política (salvo as leituras de exibição listadas com motivo em
`POLICY_FIELD_EXEMPTIONS`), e o teste
`test_canonical_promotion_decision_lives_in_one_file` fixa o número em **1**.

O mesmo detector, rodado sobre `origin/main@355a713c2` (antes desta extração), conta
**5** arquivos: a política, `modifiers.py`, `services/cart.py`, `services/fomo.py` e
`services/marketing_facts.py`. Os mutantes do laudo (segunda comparação de
`min_order_q` no `DiscountModifier`; `coupon_minimum_eligible` em `services/cart.py`,
com ou sem declaração no manifesto) viraram testes que precisam reprovar.

## Regra de aborto

Abortar e reverter a extração, preservando este artefato como evidência, se ocorrer
qualquer uma destas condições:

- a produção não cair de dois arquivos de decisão para um;
- a união futura não cair de três para no máximo dois arquivos;
- qualquer consumidor conservar uma comparação local com `min_order_q`;
- o novo verbo apenas encaminhar para `DiscountModifier` ou outro código anterior;
- o teste isolado precisar de Django, banco ou configuração Django;
- surgir ciclo entre a política, adapters e modifiers;
- o manifesto exigir exceção ad hoc para descrever imports ou entrypoint;
- catálogo, carrinho/PDV ou frete deixarem de preservar os quatro vetores congelados.
