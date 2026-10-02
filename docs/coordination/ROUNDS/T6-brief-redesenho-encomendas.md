# T6 — PDV > Encomendas: o brief do redesenho

- **id:** T6
- **sessão:** coordenacao-pedidos-4f89d4 (redigido por subagente, revisado pela sessão)
- **branch:** claude/coordenacao-pedidos-4f89d4
- **PR:** #1379
- **estado final:** esperando decisão do dono: P1 a P7 (D43)
- **início / fim (UTC):** 2026-10-02 16:36 / 2026-10-02 16:45

## O que mudou
`docs/plans/WP-POS-ENCOMENDAS-REDESENHO-BRIEF.md`: tarefas do operador por frequência com o custo em gestos,
o que se vê de relance, controles que saem/ficam, primitivas (`OperatorSchedulePicker`: venda e reagendar já
divergiram, o reagendar não respeita o limite de dias; `OperatorReasonDialog`: cancelar do PDV + `OrderReasonDialog`
do Gestor, que usa confirmação nativa do navegador), restrições da casa, o que não regride do #1231, e as
fatias S2 a S9. Nada de código.

## Prova
Citações conferidas em `e62b1dec6`; `grep -c "—\|–"` = 0.

## O que ficou de fora
Duas redundâncias novas achadas: R6 (variante compacta sem consumidor; já saiu no #1382) e R7 (dia vazio da
semana diz a mesma coisa duas vezes; fatia S3).

## Perguntas ao dono
D43 (P1 a P7, respondíveis com sim/1/2), no PENDING-DECISIONS.

## Armadilhas novas
Os 4 retratos visuais das Encomendas mudam de novo no redesenho: só regera quem tem o Chromium do lock.

## Próximo passo
Aval do dono; depois as fatias S2 a S9 e a Frente 7.
