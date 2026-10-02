# T0 — Ordem 0 do turno: ordem durável, BOARD, HANDOFF da observação por linha

- **id:** T0
- **sessão:** coordenacao-pedidos-4f89d4
- **branch:** claude/coordenacao-pedidos-4f89d4
- **PR:** #1379
- **estado final:** na fila #1379
- **início / fim (UTC):** 2026-10-02 16:29 / 2026-10-02 17:00

## O que mudou
- A ordem do turno ficou durável em `docs/coordination/ORDERS/2026-10-03-turno.md` (e o contrato em
  `ORDERS/README.md`, que só existia solto no checkout principal); o `next.md` do principal foi esvaziado.
- HANDOFF (`docs/reports/go-live-acceleration-20260929/HANDOFF.md:75`): a observação por item é
  `PUT /api/v1/cart/lines/<line_id>/notes/` (`shopman/storefront/api/urls.py:150`, `CartLineNotesView`
  em `surface.py:1334`), por LINHA de propósito (`shopman/shop/services/cart.py:384-386`). Dizia
  `cart/skus/<sku>/notes/`, rota que não existe.
- BOARD do turno; D43 (perguntas do brief T6) no PENDING-DECISIONS; o brief T6.

## Prova
`grep -n "lines/<line_id>/notes" HANDOFF.md` → linha 75. `git grep "skus/<sku>/notes" origin/main -- docs` só achava essa linha.

## O que ficou de fora
nada

## Perguntas ao dono
nada (as do brief estão em T6)

## Armadilhas novas
nada

## Próximo passo
nada
