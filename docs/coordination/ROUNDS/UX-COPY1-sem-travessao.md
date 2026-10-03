# UX-COPY1: copy de operador sem travessão

- **id:** UX-COPY1
- **sessão:** reforma SUITE-UX, onda 1 (Claude, subagente em worktree próprio)
- **branch:** claude/ux-copy1-sem-travessao
- **PR:** (a abrir)
- **estado:** em execução
- **início / fim (UTC):** 2026-10-03 / -

## Objetivo
Regra da casa (CLAUDE.md, "Copy sem travessão"): nenhum texto visível ao operador usa travessão.
Achado real: `OperatorPushSettings.vue` ("Peça a quem cuida do sistema para ligá-lo — enquanto
isso, ..."). Varrer os 8 apps de operador + kit + router e o backend que chega à tela do operador,
reescrever cada frase, e pôr uma trava que olhe o texto visível (template e literais exibidos),
não só comentários.
