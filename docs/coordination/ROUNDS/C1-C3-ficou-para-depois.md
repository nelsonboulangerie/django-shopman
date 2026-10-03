# C1, C2, C3 — Os "ficou para depois" do redesenho das Encomendas

- **id:** C1, C2, C3
- **sessão:** coordenacao-pedidos-4f89d4 (Claude; dois subagentes em worktree próprio). Dono: "sim para os três" (03/10, chat)
- **branch:** claude/pdv-detalhe-sem-etiqueta-de-dinheiro · claude/pdv-caixa-fechado-volta-ao-pedido · claude/kit-confirmacao-da-casa
- **PR:** #1400 · #1401 · #1402
- **estado final:** mergeados #1400, #1401 e #1402
- **início / fim (UTC):** 2026-10-03 / 2026-10-03

## O que mudou
- C1 (#1400): o detalhe da encomenda usa a mesma regra da lista (`rowShowsSituation`, `surfaces/pos-nuxt/app/pages/preorders/[ref].vue:183-192`): situação de dinheiro fala pela linha do saldo; a etiqueta só aparece para Pronto, Saiu para entrega e Entregue. "Conferir pagamento" também sai: a linha do saldo e o aviso de entrega já dizem.
- C2 (#1401): sem caixa aberto, a ida leva `next` (`app/presentation/cash.ts:125-169`, `openShiftGate`); depois de abrir o caixa, `pages/session/index.vue:238,244` volta para ele. Só caminho interno do PDV (`cashOpenReturnTarget`; esquema, host, `//`, barra invertida e a própria `/session` caem em `/`). Resolve "Nova encomenda" e "Refazer".
- C3 (#1402): `useConfirm()` no kit (`operator-kit/app/composables/useConfirm.ts`, `OperatorConfirmDialog.vue`, montado uma vez em `OperatorPwaRuntime.vue:49`); as 10 chamadas `window.confirm` do Gestor passam a usá-lo, guardas de rota assíncronas; copy revisada. `beforeunload` segue nativo (limite do navegador).

## Prova
C1: teste R5 em `tests/pages/preorders.test.ts` reprova sem (1 falha) e passa com. C2: `tests/pages/sessionOpenReturn.test.ts` (12), 4 reprovam sem; os de destino externo são trava. C3: `guardrails.nativeConfirm.test.ts` reprova com o Gestor do main; kit 1049, Gestor 496, PDV 1498 passed. CI obrigatória verde nos três.

## O que ficou de fora
Dois `window.confirm` da Produção (`production-nuxt/app/components/QcCloseScreen.vue`, `pages/expedite.vue`), declarados com motivo na trava: ficam para a próxima frente da Produção (o de `expedite.vue` confirma qualidade, não descarta).

## Perguntas ao dono
nada

## Armadilhas novas
`vite.resolve.dedupe: ["reka-ui"]` no kit (`nuxt.config.ts:29`): sem ele o Gestor carregava duas cópias do reka-ui e um diálogo aninhado tratava o toque na pergunta como "toque fora". Função de clique que só espera o `useConfirm` não é "clique inerte" (`guardrails.pendingAction.test.ts` ajustado).

## Próximo passo
nada
