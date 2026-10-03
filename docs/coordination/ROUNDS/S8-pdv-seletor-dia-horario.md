# S8 — PDV: um seletor de dia e horário para a venda e o reagendar

- **id:** S8
- **sessão:** coordenacao-pedidos-4f89d4 (Claude; subagente em worktree próprio)
- **branch:** claude/pdv-seletor-dia-horario
- **PR:** #1387
- **estado final:** mergeado #1387 (02/10 18:35 UTC)
- **início / fim (UTC):** 2026-10-02 18:10 / 2026-10-02 18:35

## O que mudou
`surfaces/pos-nuxt/app/components/PosSchedulePicker.vue` (novo, peça do PDV pela P4 = 1): dia pelo
`OperatorDayPicker` do kit com o limite de dias da casa, frase de prontidão uma vez, "A combinar", janelas
impossíveis apagadas com o motivo, três estados do vazio, aviso de horário impossível; trocar o dia limpa a
janela. `PosScheduleModal.vue:82-96` (interface externa igual) e `PosPreorderRescheduleDialog.vue` usam a peça;
o reagendar ganhou o limite de dias e o aviso. `presentation/schedule.ts` ganhou `lastBookableDate`.

## Prova
Contra os componentes do main: `Tests 5 failed | 3 passed (8)`; com a mudança, os 3 arquivos passam (42).
PDV `Tests 1455 passed` sobre o main com o #1384; typecheck, lint (0 erros), build ok. CI obrigatória verde.

## O que ficou de fora
O kit (P4 = 1).

## Perguntas ao dono
nada

## Armadilhas novas
nada

## Próximo passo
nada
