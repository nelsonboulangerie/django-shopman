# WP07: ícones nativos CSS com precedência correta

Base f531fd9f0, mesma fixture rica500, Chromium desktop, Nitro3005, Daphne8015
(fonte56f169108), PG/Redis próprios.20 navegações por variante, mesmos filtros,
contagens, ações e payload canônico. Antes de cada rodada há2 provas de retorno
à fila (link/history); os3 testes funcionais passaram em todas as variantes.
Não houve poda de cards, paginação, cache ou alteração de regra/permissão.

| Variante | p50 utilizável ms | p95 ms | HTML encoded aproximado | Resultado |
| --- | ---: | ---: | ---: | --- |
| SVG, configuração anterior | 2273,5 | 3016 | 4,19MB | acima1500ms |
| CSS sem layer | 1467,5 | 1568 | 3,04MB | rejeitada visualmente |
| CSS em layer base | 1541 | 1951 | 3,04MB | melhora mantida, acima1500ms |

Configuração CSS é do @nuxt/icon instalado, com os mesmos76 ícones locais.
A primeira candidata venceu classes hidden/size do Tailwind: dois ícones de
estado apareciam juntos e size5 media16px. Screenshot/JSON negativos preservados.
cssLayer=base deixa utilitários de tamanho/visibilidade prevalecerem. Screenshot
final inspecionado;3376 instâncias de ícones, nenhuma sem máscara/background.
Não é prova de contraste/AT físico em todos os aparelhos.

Regressão browser protege ícone20px, alternância exclusiva por hover/foco e
link de retorno44px. Essa última área era40px (controls-before.txt); o rail
compartilhado agora usa size-control. A medição de desempenho com layer antecede
essa alteração de4px no link; a rodada integrada final a inclui.

Validação final:303 Vitest Orders6,44s,228 kit3,89s,typecheck/build,
**29 integrações1,2min**. O screenshot rico500 foi coletado em paralelo a parte
dessa última suíte funcional; tempos da integração não são novo benchmark.
20 amostras por variante não provam campo nem isolam toda variação do host.
O ganho observado não aprova1500ms e não muda o budget backend500ms/10 clientes.

Sem DDL/efeito externo. Rollback: restaurar mode=svg/remover cssLayer só no Gestor;
preservar token44, recibos, fontes e guards. Demais apps conservam seu modo de
ícones, pois a configuração é local a orders-nuxt. Sem dependência nova.
