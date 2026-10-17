# Piloto de extração — pedido mínimo de promoção

Estado no primeiro commit: **cenário e baseline congelados; nenhum código de produção movido**.

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

## Desenho candidato, ainda não executado neste commit

Uma unidade `promotion.minimum-order-eligibility`, com um único verbo público puro:

```python
promotion_minimum_eligible(*, min_order_q: int, merchandise_subtotal_q: int) -> bool
```

O verbo deve ser a única implementação da comparação e ter teste direto sem Django,
banco ou `DJANGO_SETTINGS_MODULE`. Os três consumidores apenas reúnem os dois inteiros e
delegam. O manifesto terá um entrypoint canônico, responsabilidade `decisão`,
`policy: true` e nenhum domínio, porto, evento, directive ou configuração.

Meta depois: `shopman/shop/promotion_policy.py` mais seu teste puro, portanto soma,
mediana e união de **2 arquivos**. A redução material esperada é **3 → 2 (33%)**; a
produção deve cair de **2 → 1 arquivo**.

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
