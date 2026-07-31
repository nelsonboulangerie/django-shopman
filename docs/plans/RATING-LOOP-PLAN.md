# RATING-LOOP-PLAN — a avaliação do cliente não chega em ninguém

**Status:** achado de auditoria (2026-07-31), não executado.
**Origem:** revisão do acompanhamento; Pablo pediu para verificar se o sistema de
avaliação funciona de fato.

## Veredito curto

**O lado do cliente funciona de ponta a ponta. O lado da loja não existe.**
A nota é gravada e nunca lida por ninguém da padaria: não há tela de operador,
coluna no Admin, relatório, notificação nem agregado. A copy do sheet diz *"Sua
nota ajuda a loja a melhorar"* — hoje isso é falso, porque a loja não vê.

Pedir feedback que ninguém recebe é pior do que não pedir.

## O que existe (verificado)

Fluxo completo do cliente:

1. `_can_rate` (`shopman/shop/projections/order_tracking.py`) libera quando
   `order.status in {"delivered", "completed"}` e ainda não há nota.
2. A ação `rate_order` entra em `order.actions`; o botão "Avaliar pedido" abre um
   `BottomSheet` com estrelas + comentário
   (`surfaces/storefront-nuxt/app/pages/pedido/[ref]/index.vue`).
3. `rateAndClose` → `POST /api/v1/orders/<ref>/rate/` (`OrderRateView`,
   `shopman/storefront/api/tracking.py`), com mutação idempotente.
4. O endpoint revalida pela projeção (409 `order_not_rateable` se não puder) e
   grava em `Order.data["customer_rating"]`:
   `{rating, comment, submitted_at, source}`.
5. Devolve o payload de acompanhamento atualizado; a ação some (já avaliado).

Ou seja: persiste, é idempotente, valida, e não deixa avaliar duas vezes.

## O buraco

Busca por `customer_rating` em todo o repo devolve **dois** lugares:

- `storefront/api/tracking.py` — a escrita.
- `shop/projections/order_tracking.py:_rating_data` — a leitura, usada **só**
  para impedir o cliente de avaliar de novo.

Nenhum consumidor em `backstage/`, `admin/`, relatórios ou notificações. A nota e
o comentário morrem dentro do JSONField.

## O que fechar o loop pede

Em ordem de valor por esforço:

1. **Ver a nota no pedido (Admin/Unfold).** Coluna + display no `OrderAdmin`,
   lendo de `Order.data`. É o mínimo para a nota existir para a loja. Respeitar o
   gate canônico do Unfold (ver `CLAUDE.md`).
2. **Avisar quando a nota for baixa.** Sinal/directive em avaliação ≤ 2, para o
   gestor agir enquanto o cliente ainda lembra. Encaixa no registro de
   notificações existente.
3. **Agregado no dashboard do gestor.** Média móvel + últimos comentários. Só
   depois de (1) e (2), senão vira número sem ação.
4. **Corrigir a copy se (1) demorar.** Enquanto a loja não vê, *"Sua nota ajuda a
   loja a melhorar"* não se cumpre — ver [ADR de anti-overpromise no
   acompanhamento] e a regra de nunca prometer o que o sistema não faz.

## Resíduo de nomenclatura (barato)

No `index.vue`, o sheet de avaliação é controlado por uma ref chamada
`supportOpen` — herança de quando o overlay era de suporte. Funciona, mas o nome
mente para quem lê. Renomear para `ratingOpen`.

## Onde mexer

- `shopman/shop/projections/order_tracking.py` — `_can_rate`, `_rating_data`
- `shopman/storefront/api/tracking.py` — `OrderRateView`
- `surfaces/storefront-nuxt/app/pages/pedido/[ref]/index.vue` — sheet e ação
- consumidor novo: `shopman/backstage/` (Admin/Unfold) e/ou dashboard do gestor
