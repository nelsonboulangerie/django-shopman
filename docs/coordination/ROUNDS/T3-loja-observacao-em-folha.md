# T3 — Loja: a observação por item vira folha

- **id:** T3
- **sessão:** coordenacao-pedidos-4f89d4 (Claude; frentes T1 a T5 executadas por subagentes em worktree próprio)
- **branch:** claude/loja-observacao-em-folha
- **PR:** #1383
- **estado final:** na fila #1383 (auto-merge ligado, CI rodando às 16:55 UTC)
- **início / fim (UTC):** 2026-10-02 16:40 / 2026-10-02 16:53

## O que mudou
`surfaces/storefront-nuxt/app/components/CartLineNote.vue` reescrito sobre o `BottomSheet` (max-width md,
"Observação de {nome}"): fecha por X, alça, fundo e Esc sem exigir salvar; texto alterado e válido grava pelo
mesmo PUT por linha em segundo plano e fecha na hora; erro reabre com o rascunho e `role="alert"`;
"Remover observação"; contador N/280 com `aria-live`; descarte com confirmação só quando difere do salvo.
`CartLineNoteMark.vue` (novo, selo outline + linha) na sacola e na revisão do checkout (`finalizar.vue:2202`).
`setLineNotes` intocado. O teste achou e o PR corrigiu um PUT duplo no mesmo gesto de fechar.

## Prova
`tests/components/cartLineNote.test.ts` reescrito: contra o main `9 failed | 2 passed (11)`; com a mudança
`11 passed`. Storefront inteiro sob Node 22: `Tests 1043 passed`. Navegador (Django sqlite + seed, Nuxt dev,
desktop): Esc gravou `PUT /api/v1/cart/lines/L-R8GHQHBE/notes/` 200, persiste após recarregar, Cancelar pede
confirmação, Remover funciona.

## O que ficou de fora
NÃO VERIFICADO no navegador: a marca na revisão do checkout (coberta por teste) e a folha no celular com o
teclado virtual. Fechar por gesto com o texto apagado pede confirmação em vez de remover (remover é sempre gesto explícito).

## Perguntas ao dono
nada

## Armadilhas novas
nada

## Próximo passo
Conferir no celular, no alpha, depois do deploy.
