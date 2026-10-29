# Corrida no ensaio de venda sem conexão

O teste verificava a tela de resultado depois da contagem de auto-avanço de 5 segundos. A venda era enviada, mas a tela já voltava às comandas. A prova exige cancelar a contagem com um toque no resultado antes de aguardar o envio, conforme o contrato existente do componente.

Evidência: merge group da #2039, run 40923535458, job 123626529609. A asserção do toast de envio e a fila vazia passaram; falhou somente a presença do resultado, e o trace mostrou a tela de comandas. `PosSaleResult.vue` mantém o contrato de cancelar a contagem em `pointerdown.capture`; o teste agora usa esse gesto antes de abrir a lista pelo cabeçalho.

Validação local com Chromium 1243, portas 18554/19554 isoladas: `npm run test:e2e -- tests/e2e/offline-sale.spec.ts --repeat-each=3`, seis cenários passaram (três repetições dos dois testes). Nenhum retrato foi regenerado e nenhum comportamento do produto foi alterado.
