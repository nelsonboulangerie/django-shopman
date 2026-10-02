# S3 — PDV > Encomendas: a tela da seção

- **id:** S3
- **sessão:** coordenacao-pedidos-4f89d4 (Claude; subagente em worktree próprio)
- **branch:** claude/encomendas-tela-da-secao
- **PR:** #1388
- **estado final:** na fila #1388 (checks obrigatórios verdes)
- **início / fim (UTC):** 2026-10-02 18:10 / 2026-10-02 19:05

## O que mudou
Em `surfaces/pos-nuxt/`: Período na barra (`PosPreordersShell.vue:53-66`, some na busca); linha "Hoje"
(`todayOf`/`todayFacts` em `presentation/preorders.ts`; sem leitura nova de API); recortes de um toque A receber,
Sem Via Pedido, Retiradas, Entregas (P1, `PosPreorderFilters.vue`), com o "Filtrar" do kit só para o resto; linha
da encomenda numa forma só (`PosPreorderRow.vue`, janela primeiro, "N itens", "Via impressa" escrito); resumo com
rótulo; nota de escopo como legenda; R7; "Incluir concluídas" só com busca.

## Prova
21 testes novos: com `app/` do main `24 failed | 72 passed (96)`; com a mudança `97 passed (97)`. PDV
`Tests 1447 passed` (Node 22); operator-kit `1029 passed` (Node 22). Sem rolagem lateral em 375, 390, 768, 1024 e
1440 px. Os 4 retratos `preorders-*.png` regerados com chromium-1243. Nenhum teste do #1231 removido (cinco adaptados).

## O que ficou de fora
O resumo dos itens ("2x Pão") saiu da linha (o brief desenha "N itens"; os itens seguem no detalhe). Os botões de
um toque ficam no PDV até haver um segundo consumidor.

## Perguntas ao dono
nada

## Armadilhas novas
O `#end` da barra do kit não encolhe: em 390 px vazava 5 px. Use `#start` ou um slot que quebre linha.

## Próximo passo
S4 (o lote), sobre este.
