# ONDA4-F2: preço com vigência

- **Data:** 2026-10-20.
- **Branch:** `codex/preco-vigencia`.
- **Ordem:** `ORDERS/next-onda4.md`, frente 2.
- **PR:** [#1958](https://github.com/nelsonboulangerie/django-shopman/pull/1958).
- **Estado final:** MERGED em 2026-10-20 22:26:48 UTC.
- **Commit de merge:** `3d0a10a57fdc69a539c3a881111d97037bca4d78`.

## Entrega

A matriz projeta `Listing.valid_from` e `valid_until` nas células de canal. A linha
do produto mostra um selo por janela distinta, identificando os canais que a
compartilham, com as duas datas ou a única ponta definida. Agrupar evita repetir
um selo de várias linhas em cada coluna estreita. Feed não recebe preço nem
vigência inventada.

A lista abre em Hoje e ordenada pelo início da vigência, com atalhos do
OperatorFilterPanel, período personalizado e a opção Qualquer data para consultar
também cadastros sem preço vinculado a canal. A janela ativa fica escrita no topo.
Escolher outro período reativa o recorte quando Qualquer data estava marcado.

A janela cruza vigências com limites inclusivos, no banco. As duas pontas precisam
casar na mesma Listing. O filtro de canal restringe a mesma consulta; paginação,
contagem e facetas continuam no servidor. Membros de feed explicitamente
selecionado continuam no recorte, pois curadoria não tem vigência de preço. A
resposta informa a janela consultada para conferir a identidade da leitura.

## Provas

- Backend amplo: **118 passed** e uma falha inicial no guard de chaves fixas da
  matriz. O guard foi atualizado com as datas do contrato; reexecução das provas
  de vigência e desse guard: **9 passed**. Caso adicional feed com preço expirado
  no canal de venda: **1 passed**.
- Frontend focado: **80 passed**. Após agrupar os canais no selo, apresentação:
  **43 passed**, incluindo a prova nova do agrupamento de janelas distintas.
- Typecheck e ESLint dos arquivos alterados passaram. Build final de produção
  passou. Ruff e `git diff --check` passaram.
- Browser de produção: Arquivados e vigência **2 passed**; após a compactação,
  vigência com seleção Próximos 7 dias e Qualquer data **1 passed**, zero HTTP
  4xx/5xx. Carga do catálogo no celular, inclusive HTML sem JavaScript: **5 passed**.
- As quatro capturas foram abertas e inspecionadas, em
  `img/onda4-f2-vigencia/onda4-f2-vigencia-{antes,depois}-{light,dark}.png`.
- `export_orders_schema` executado: nenhum diff em ordersContract.ts, pois a matriz
  usa o mirror types/catalog.ts, alterado junto do guard de contrato desta frente.
- Nenhuma migração criada. A checagem de prefixos de shop/migrations acusa
  duplicidades históricas 0023 a 0039 já presentes na base, fora desta fatia.

## Desempenho medido

O endpoint da base não emitia Server-Timing. A frente liga o ServerTimingMixin
canônico. Uma sonda temporária carregou a função da base `65b658d31` sob a mesma
instrumentação da API atual, sem alterar o código-base, para comparar três leituras
aquecidas de página de 10 linhas sobre 62 produtos com ListingItems.

| medida | base instrumentada | depois |
|---|---:|---:|
| consultas por leitura | 32 | 32 |
| mediana projection (ms) | 86,91 | 176,38 |
| mediana db (ms) | 3,85 | 8,18 |
| intervalo projection das três leituras (ms) | 77,20 a 96,17 | 88,80 a 182,85 |

A máquina estava sob pressão de memória por verificações concorrentes. A amostra
não demonstra ganho de latência e não serve de orçamento de produção. O teste
permanente é estrutural: com a janela e ordenação novas, o total cresce de **2
para 62 produtos**, a página cresce até **10 linhas**, e as consultas ficam em
**32 para 32**. Crescer com as linhas reprova o teste. A sonda temporária foi removida.

## D1 a D12

- **D1:** selos neutros sem variant explícito; nenhum cartão novo.
- **D2:** nenhum cabeçalho ou rodapé de cartão acrescentado.
- **D3:** controles do FilterPanel canônico, sem botão esticado.
- **D4:** a matriz mantém o conteúdo de borda a borda.
- **D5:** controles das colunas continuam alinhados; datas agrupadas na linha evitam
  ampliar cada célula do mesmo produto.
- **D6:** canais e datas escritos por completo, sem depender de ícone ou tooltip.
- **D7:** período personalizado usa os campos dimensionados pelo kit.
- **D8:** sem aviso novo; erros de data seguem o contrato canônico da API.
- **D9:** esta frente é de leitura e filtro, sem nova escrita ou destruição.
- **D10:** copy em português, sem travessão e sem termo técnico exposto.
- **D11:** OperatorFilterPanel e NuxtBadge canônicos.
- **D12:** antes/depois claro/escuro abertos e conferidos; a primeira tentativa
  de selo por célula foi substituída depois da inspeção visual.

## CI

O draft inicial teve PWA-orders vermelho por três testes de catálogo: o mock
hermético ainda não devolvia a janela e a ordenação consultadas e o cenário de
vigência dependia de uma variável externa. O log do job foi lido. O mock agora ecoa
o recorte em todos os cenários e o teste liga/desliga seu cenário próprio. Os
casos Arquivados, vigência e carga no celular foram reconferidos localmente.
O push final reexecutou a esteira, e o #1958 foi mergeado após a validação da fila.
