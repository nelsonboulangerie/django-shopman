# IFOOD-B - vínculo como resolvedor de identidade

- **id:** IFOOD-B
- **sessão:** frente 6, turno 2 de 19/10/2026 (Codex)
- **branch / PR:** não abertos, por dependência explícita
- **estado:** adiado pela #1905 aberta e vermelha
- **data:** 2026-10-19

## Objetivo

Fazer o vínculo vigente decidir `item_id`, `product_id` e `category_ref` no envio ao iFood, com
fallback derivado apenas quando não houver vínculo no mesmo escopo.

## Bloqueio confirmado

A ordem exige a #1905 mergeada antes desta frente porque ambas alteram
`shopman/shop/adapters/catalog_projection_ifood.py`. Em 19/10, depois de concluir a frente C, a
#1905 continuava aberta, sem auto-merge e com falhas em `Shop rest`, `Testes (test-shop)` e
`Coverage Gate`. A própria ordem também diz para não tocar nesse PR.

Abrir a frente agora criaria exatamente a colisão que a dependência evita e não permitiria cumprir
a instrução de partir do `main` com `imagePath` já integrado. Por isso não houve branch, código ou
PR dormente.

## Próximo passo objetivo

Quando a #1905 mergear:

1. atualizar `origin/main`;
2. criar `codex/ifood-vinculo-resolvedor` em worktree próprio;
3. preservar `imagePath` e adicionar o resolvedor único de identidade;
4. executar as quatro provas da ordem e colocar o PR verde na fila.

## Perguntas ao dono

nada; o bloqueio é a dependência técnica já determinada na ordem
