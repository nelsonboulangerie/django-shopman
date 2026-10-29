# PDV: recuperação da PR #2022

Em 29/10/2026, a PR #2041 preserva os três commits da #2022 e integra
`origin/main`, sem alterar o branch que já tinha merge automático ligado.

A CI anterior falhava por dois motivos independentes:

- `Shop rest`: o teste de reutilização da leitura de estoque simulava
  `PromiseDecision` com `SimpleNamespace` incompleto, sem `available`. O teste
  passa a construir o contrato real e informar o estoque pronto.
- `Quality + deploy contract`: `_started_lot_qty` e `_lot_stage` não estavam
  atribuídos à unidade de revisão da venda. O inventário agora inclui os dois
  auxiliares e a leitura do domínio Craftsman.

`Testes (test-shop)` e `Coverage Gate` falhavam como consequência do primeiro
problema; não houve relaxamento de gate. O teste original de leitura sem
consulta duplicada e os testes de aviso de lote continuam sendo exigidos.

O registro de validação e o estado da fila ficam na PR #2041.
