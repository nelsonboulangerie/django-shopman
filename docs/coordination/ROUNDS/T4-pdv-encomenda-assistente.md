# T4 — PDV: o modo Encomendas vira assistente

- **id:** T4
- **sessão:** coordenacao-pedidos-4f89d4 (Claude; frentes T1 a T5 executadas por subagentes em worktree próprio)
- **branch:** claude/pdv-encomenda-assistente
- **PR:** #1384
- **estado final:** na fila #1384 (auto-merge ligado, CI rodando às 16:55 UTC)
- **início / fim (UTC):** 2026-10-02 16:58 / 2026-10-02 17:10

## O que mudou
`surfaces/pos-nuxt/app/components/PosOrderEntry.vue` reescrito no molde do `CampaignForm`: Cliente,
Recebimento, Endereço (só na entrega), Data e horário; trilha com `aria-current="step"`, seções com `v-show`,
rodapé "Etapa X de N" com Voltar/Continuar e "Montar encomenda" na última; avança sozinho e leva o foco pelo
`useNextFocus`. A prontidão vem só de `orderSetupIssue` (`presentation/orderSetup.ts`, novo, não lê o carrinho;
teste trava). Invalidações: cliente sai volta à etapa 1; retirada→entrega reabre Endereço; dia apagado reabre a data.
`PosScheduleModal` intocado; nada no kit.

## Prova
`orderSetupPresentation.test.ts` (11), `PosOrderEntry.test.ts` (9), `usePosSale.orderSetupWizard.test.ts`:
contra o `PosOrderEntry.vue` do main `Tests 10 failed (10)`; com a mudança o pos-nuxt inteiro `Tests 1436 passed`;
typecheck 0; eslint 0. NÃO VERIFICADO no navegador (o fluxo exige Django com PIN).

## O que ficou de fora
Trocar o dia limpa a janela, mas a regra não exige janela: a etapa segue pronta e diz "Horário a combinar.".
Fazê-la voltar a pendente seria reescrever a regra (proibido pela ordem). Itens e pagamento depois de
"Montar encomenda" não mudaram.

## Perguntas ao dono
nada (se a janela deve ser obrigatória na encomenda, é decisão de regra, não de tela)

## Armadilhas novas
`tests/e2e-live/copy-overflow.live.spec.ts` agora espera "Identificar cliente": "Montar encomenda" só aparece na última etapa.

## Próximo passo
Quando o brief T6 for aprovado (P4), o passo de data passa a usar o `OperatorSchedulePicker` (T7).
