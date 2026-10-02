# S2, S5, S6 — Encomendas: selo pelo tema, detalhe com painel (P3), etiqueta única (P5)

- **id:** S2, S5, S6
- **sessão:** coordenacao-pedidos-4f89d4 (Claude; um subagente em worktree próprio, um PR por vez)
- **branch:** claude/kit-selo-por-token · claude/encomendas-detalhe-painel · claude/encomendas-etiqueta-unica
- **PR:** #1394 · #1396 · #1397
- **estado final:** mergeados #1394, #1396 e #1397
- **início / fim (UTC):** 2026-10-02 20:50 / 2026-10-02 23:10

## O que mudou
- S2: `surfaces/operator-kit/app/presentation/orderDetail.ts:39`, `toneBadge` pelos tokens do tema
  (`destructive`, `warning`, `success`, `info`). O Gestor fica um tom mais quente e menos saturado, igual ao PDV.
- S5: `surfaces/pos-nuxt/app/pages/preorders/[ref].vue`: painel do Balcão à direita em tela larga (23rem, fixo na
  rolagem; antes do detalhe em tela estreita, uma árvore só), receber e entregar na largura toda, Reagendar /
  Imprimir Via Pedido / Editar lado a lado (:228), Cancelar separado no pé (:298), atalho de comentar (:290).
  Kit e Gestor intocados.
- S6: `OperatorOrderDetail.vue` ganhou `showStatus` (padrão igual a hoje); o PDV passa `false` (`[ref].vue:317`).

## Prova
S2: sem a mudança 2 reprovam no kit e 1 no Gestor; com ela kit 1037, Gestor 496, PDV 1484. S5: 6 testes novos (4
reprovam sem), `tests/visual/preorderDetail.spec.ts` novo confere geometria em 375/390/768/1024/1440 (pegou um
"Editar encomenda" vazando em 1024, corrigido); PDV 1497. S6: 1 teste no kit e 1 no PDV, ambos reprovam sem; kit
1038, PDV 1498, Gestor 496. CI obrigatória verde nos três.

## O que ficou de fora
Quando a situação é "A receber", a etiqueta repete a palavra do saldo: é copy de situação do servidor, fora destas fatias.

## Perguntas ao dono
nada

## Armadilhas novas
nada

## Próximo passo
nada
