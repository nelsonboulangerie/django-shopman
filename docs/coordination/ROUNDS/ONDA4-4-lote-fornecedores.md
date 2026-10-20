# ONDA4-4: lote de fornecedores

Ordem: `ORDERS/next-onda4.md`, frente 4. Branch: `codex/lote-fornecedores`. PR: [#1957](https://github.com/nelsonboulangerie/django-shopman/pull/1957).

A Base permite marcar os fornecedores da página e Arquivar/Desarquivar em um POST
`purchase/suppliers/batch/`, com confirmação. A barra canônica ocupa a toolbar na
mesa e a base no celular. A seleção se limpa quando o recorte muda. Desfazer usa
`OperatorTimedButton`, recibo assinado com prazo de 15 segundos, ator e revisão.
Reenvio usa a mesma intenção; revisão divergente recusa o lote inteiro. A auditoria
é `django.admin.LogEntry`, gravada em lote dentro da mesma transação da alteração.
Nenhuma migração, alteração de Core ou área reservada da ordem.

## Evidência

- Backend: `test_purchase_supplier_bulk.py`, **7 passed**. Arquiva/desfaz, reenvio
  idempotente, revisão obsoleta, permissão, seleção inválida, recibo adulterado,
  ator diferente, prazo vencido e rollback integral se a auditoria falhar.
- Componente: `PurchaseSupplierBulkBar.test.ts`, **2 passed**.
- `nuxt typecheck`: exit 0. ESLint dos arquivos alterados e Ruff: exit 0.
- Navegador Chromium, build de produção, transporte hermético: **4 passed**
  (claro/escuro, 1280×720 e 390×844), confirmação, uma ida de escrita, Desfazer,
  nenhum 4xx/5xx. A escrita em banco é provada separadamente nos testes da API.
- Antes, dez POSTs individuais: **188 consultas**, `projection;dur=195.97`,
  `db;dur=12.22`. Depois, um POST em lote: **30 consultas**,
  `projection;dur=24.08`, `db;dur=2.21` (milissegundos, SQLite local).
- Escalabilidade: dois e quarenta fornecedores dão **28 consultas em ambos**;
  `projection;dur=15.70/22.72`, `db;dur=5.46/3.34`. O teste reprova crescimento.
- Capturas abertas e inspecionadas: `surfaces/purchase-nuxt/test-results/visual/`
  `supplier-bulk-lote-fornecedores-onda4-4-{light,dark}-{desktop,mobile}/`
  `onda4-4-fornecedores-{antes,depois}-{light,dark}-{desktop,mobile}.png`.
  Sem baseline novo; teste reproduz as oito capturas.
- Sem migração nova. A checagem de prefixos retorna duplicatas históricas
  0023 a 0039 já presentes na base, nenhuma criada nesta frente.

## D1 a D12

D1: tabela outline existente, sem cartão adicional; selos sem variant explícito.
D2: sem cabeçalho/rodapé de cartão destacado.
D3: ações neutras outline, conjunto mínimo; botões sem esticar na mesa.
D4: seleção usa a toolbar/base canônica e a tabela existente.
D5: par Arquivar/Desarquivar no mesmo grupo, altura igual.
D6: rótulos completos e ícones/dicas do kit; confirmação conta fornecedores.
D7: nenhum campo novo; controles do kit.
D8: erro descreve o motivo e pode ser dispensado.
D9: Arquivar/Desarquivar confirmam e oferecem Desfazer com prazo/revisão.
D10: Arquivar, Arquivado, Desarquivar; texto sem travessão.
D11: OperatorTable, OperatorBulkBar, OperatorTimedButton, Nuxt UI canônicos.
D12: oito capturas claro/escuro mesa/celular abertas e verificadas.

## Correção do gate antes de entrar na fila real

O job `operator-kit` (run 39497839136, job 118888858793) recusou o aviso de erro
por faltar `variant="subtle"` explícito. GraphQL confirmou `isInMergeQueue=false`:
a solicitação automática existia, mas o PR vermelho ainda não estava na fila real.
O mesmo PR recebeu o atributo canônico; `guardrails.minimalSet.test.ts`: **10 passed**.


## Evidência preservada no repositório

As capturas antes/depois foram copiadas do cache local para EVIDENCE/onda4-base.

- [onda4-4-fornecedores-antes-dark-desktop.png](../EVIDENCE/onda4-base/onda4-4-fornecedores-antes-dark-desktop.png)
- [onda4-4-fornecedores-antes-dark-mobile.png](../EVIDENCE/onda4-base/onda4-4-fornecedores-antes-dark-mobile.png)
- [onda4-4-fornecedores-antes-light-desktop.png](../EVIDENCE/onda4-base/onda4-4-fornecedores-antes-light-desktop.png)
- [onda4-4-fornecedores-antes-light-mobile.png](../EVIDENCE/onda4-base/onda4-4-fornecedores-antes-light-mobile.png)
- [onda4-4-fornecedores-depois-dark-desktop.png](../EVIDENCE/onda4-base/onda4-4-fornecedores-depois-dark-desktop.png)
- [onda4-4-fornecedores-depois-dark-mobile.png](../EVIDENCE/onda4-base/onda4-4-fornecedores-depois-dark-mobile.png)
- [onda4-4-fornecedores-depois-light-desktop.png](../EVIDENCE/onda4-base/onda4-4-fornecedores-depois-light-desktop.png)
- [onda4-4-fornecedores-depois-light-mobile.png](../EVIDENCE/onda4-base/onda4-4-fornecedores-depois-light-mobile.png)
