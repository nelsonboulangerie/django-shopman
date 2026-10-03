# UX-H1: a Central vira a fila das filas

**Estado:** em execução (03/10/2026)
**Branch:** `claude/ux-h1-central-fila`
**Plano:** `docs/plans/SUITE-UX-FUNCTION-PLAN.md` §4.1 (FILA), §6 (navegação e Central), §9 (postos), §16 (nome);
fichas H01 a H04 em `docs/plans/suite-ux-v2/funcoes/kds-hub.md`; prévia `docs/plans/suite-ux-v2/v4/hub.jpg`.

## Objetivo

Decisão do dono: a Central (`surfaces/hub-nuxt`) passa a ser "a fila das filas". No topo,
"Precisa de você": a soma das filas dos papéis deste operador, o item exato primeiro, ordenado por
urgência entre apps, com o essencial da decisão, o tempo esperando (âmbar quando estoura) e um
gesto que abre o lugar exato no app certo. Embaixo, os blocos dos apps, calmos, cada um com uma
linha de estado que concorda com a fila.

Só fontes que já existem e que respeitam as permissões do operador; backend no backstage, nunca no Core.
