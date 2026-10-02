# T5 — PDV > Encomendas: as redundâncias R1 a R5 saíram

- **id:** T5
- **sessão:** coordenacao-pedidos-4f89d4 (Claude; frentes T1 a T5 executadas por subagentes em worktree próprio)
- **branch:** claude/encomendas-sem-redundancia
- **PR:** #1382
- **estado final:** na fila #1382 (auto-merge ligado, CI rodando às 16:55 UTC)
- **início / fim (UTC):** 2026-10-02 16:41 / 2026-10-02 16:56

## O que mudou
- R1: fica o `OperatorPeriodPicker` (`pages/preorders/index.vue:308`), junto do ‹ ›; saem as abas Dia|Semana
  do `PosPreordersShell.vue` e `modeSections` (`presentation/preorders.ts:121-132`).
- R2: fica o item do rail (`PosFunctionRail.vue:58-67`, decisão de 26/09, com selo); o "Encomendas" da barra virou título.
- R3: uma frase e um peso só, "A receber R$ X" (`TO_RECEIVE_CLASS`), em `index.vue:322`, `:456` e `PosPreorderRow.vue:103`;
  parcial vira "A receber R$ 11,00 de R$ 36,00". O modo `compact` sem consumidor saiu.
- R4: linha e detalhe usam `toneBadge` do kit (`operator-kit/app/presentation/orderDetail.ts:36`); as cópias de `TONE_CLASS` morreram.
- R5: fica só o da `FilterBar` (X do chip e "Limpar filtros").
- No kit: a barra do topo não desenha moldura de navegação vazia sem seções (uma linha, com teste).

## Prova
Travas em `tests/pages/preorders.test.ts` (R1 a R5 na tela montada) e `tests/railPreorders.test.ts` (varredura do
fonte). pos-nuxt `Tests 1422 passed`; orders-nuxt (detalhe compartilhado, #1231) `Tests 496 passed`; typecheck 0.
Os 4 retratos das Encomendas regerados com Playwright 1.63.0 / chromium-1243 (o do lock); o PDV não roda visual na CI.

## O que ficou de fora
O tamanho do valor no detalhe (`[ref].vue`, `text-base`) e a etiqueta "A receber" que repete a palavra da linha
de dinheiro: decisão de desenho, foi para o brief T6.

## Perguntas ao dono
nada

## Armadilhas novas
Trocar Dia↔Semana custa 2 toques agora (Semana→dia continua 1, pelo cabeçalho do dia na grade).

## Próximo passo
nada
