# WP07 — feedback, resultado local e recuperação de resposta

Fonte 1d84dcc5b, um operador autenticado, um pedido sintético accepted, nota da
cozinha. Chromium 149, Node22.23.1, Apple M2/8 CPUs lógicas/8GiB, macOS arm64,
viewport1440×1000. Nitro próprio3007→Daphne8014→PostgreSQL55439/Redis56389.
Suíte ampla SQLite/xdist2 rodava em outro checkout: carga concorrente declarada;
não é aparelho/rede piloto nem comparação estatística de pessoas.

`probe.mjs`, no cwd da execução, usa login real do lab e o pedido de
`legacy_browser/seed.py`. Cada rodada: 20 comandos normais e 20 respostas cortadas
**depois** de route.fetch confirmar commit200/applied. GET de receipt mantém a chave;
40 intenções distintas, 40 POSTs, 20 GETs de recuperação e exatamente40 eventos
kitchen_note_changed no livro de OrderEvent. Nenhum campo é redigitado na recuperação,
nenhum clique adicional; cada valor novo é digitado uma vez. Fakes só cortam a
resposta ao navegador, não substituem Django/DB. Sem fornecedor real.

## Distribuição com oportunidade de renderização

| Medida | n | p50 ms | p95 ms | máximo ms | Budget proposto |
| --- | ---: | ---: | ---: | ---: | --- |
| DOM acusa busy |40|0,900|1,100|2,500|Não confundir mutação DOM com pintura |
| Dois animation frames após busy |40|29,700|32,300|32,800|100ms |
| Resultado conhecido + leitura + saída de busy, normal |20|76,200|112,600|112,800|800ms |
| Mesmo resultado após resposta perdida + receipt + leitura |20|85,800|110,600|113,500|2.000ms após transporte disponível |

MutationObserver parte do evento click; dois requestAnimationFrame dão oportunidade
de pintura, não medem fótons no display. Saída de busy é observada no botão de avanço,
que só volta a habilitar depois de act/refresh. Canonical GET verifica o texto e
SQL readonly verifica diferença exata de eventos. Os primeiros40 comandos mediram
só DOM (normal p95 188,400ms, recuperação126,800ms); repetidos com novas intenções
para acrescentar a medição de frames. Ambas as rodadas estão preservadas, sem
selecionar a mais rápida como “ganho”. Ordem normal→perda fixa; não inferir vantagem
de falhar a resposta a partir das diferenças pequenas de warmup/escalonamento.

O tempo automatizado de login+navegação está no JSON separado; não foi omitido do
registro nem subtraído de um tempo humano. Não há medição de T humano, abandono,
compreensão ou aprovação G06. O ensaio verifica sub-budgets técnicos em uma ação;
não prova todos os endpoints, 500pedidos/10clientes, rede móvel ou ganho≥30% J02–J15.

Sem mudança de produto neste incremento, sem migration. Relatório derivado de
trilhas existentes; rollback não remove eventos/recibos nem notas confirmadas.
Ruff do helper Python aprovado. O Node executou integralmente as duas rodadas.
