# S9 — Encomendas: botão "Nova encomenda" (P6)

- **id:** S9
- **sessão:** coordenacao-pedidos-4f89d4 (Claude; subagente em worktree próprio)
- **branch:** claude/encomendas-nova-encomenda
- **PR:** #1393
- **estado final:** mergeado #1393 (02/10 20:46 UTC)
- **início / fim (UTC):** 2026-10-02 19:50 / 2026-10-02 20:46

## O que mudou
`surfaces/pos-nuxt/app/pages/preorders/index.vue:208-249`: "Nova encomenda" ao lado de "Cliente veio buscar?", leva a `/?new=order` (`presentation/orderSetup.ts:77-89`, vale uma vez, como `?edit=`/`?redo=`). `pages/index.vue` lê o sinal e chama `openNewOrder()` (`usePosSale.ts:1666-1676`): abre a próxima comanda livre e troca o modo pelo mesmo `setSalesMode` do seletor; o assistente (#1384) abre na primeira etapa pendente. A venda de balcão em andamento nunca é tomada (fica na comanda dela).

## Prova
7 testes novos: 6 reprovam sem a mudança, todos passam com ela. PDV 1490 passed; 4 retratos regerados com chromium-1243; sem corte em 390, 768, 1024, 1440; CI obrigatória verde.

## O que ficou de fora
Dia pré-preenchido: não há como passar a data sem estado novo; o dia segue na etapa "Data e horário". Sem caixa aberto, o sinal se perde na antesala (igual ao `?redo=`).

## Perguntas ao dono
nada

## Armadilhas novas
Em 320 px o PDV já passa da borda no main (o toaster); não é desta fatia.

## Próximo passo
nada
