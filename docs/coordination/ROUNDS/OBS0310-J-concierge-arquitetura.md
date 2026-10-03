# OBS0310-J: Concierge, arquitetura alvo (estudo)

- **id:** OBS0310-J
- **sessão:** shopman-improvements-fixes-bd04d4 (Claude; subagente em worktree próprio)
- **branch:** claude/obs0310-concierge-arquitetura
- **início (UTC):** 2026-10-03
- **tipo:** análise e proposta; nenhum código de produção

## Entrega
`docs/plans/CONCIERGE-ARQUITETURA-ALVO.md`: sistema atual medido, o que é o Jev, onde precisa de
LLM, ManyChat AI / Anota AI / Deeliv com fontes, melhores práticas, arquitetura em camadas (C1 a C7),
custo e latência estimados, plano em seis fatias (F1 pronta) e cinco decisões do dono.

## Medições (alpha, conexão direta 25060, banco `shopman`, transação somente leitura)
- Conversa 1 (04/09): 24 respostas, cerca de US$ 0,59 (piso; a escrita de cache não é gravada,
  `service.py:1041-1046`), US$ 0,025 por resposta.
- Latência inbound→resposta: p50 3,4 s sem ferramenta; 7,3 a 8,8 s com uma; 14 a 36 s com várias.
- 168 entradas observadas (26/09 a 03/10, 84 conversas): 42% cortesia, 28% intenção reconhecida,
  15% outras, 11% link/mídia, 4% resposta curta de contexto.
- Jev em sombra: p50 166 ms, p95 226 ms, zero erro; 121/168 sem intenção acima de 0,5.

## Fontes externas
Pesquisa web feita por subagente; links no documento (seção 4 e 5). Páginas do ManyChat
recusaram leitura direta (403): fatos vêm de trechos indexados e da comunidade.

## Estado
PR de documentação, na fila. Decisões do dono na seção 8 do estudo.
