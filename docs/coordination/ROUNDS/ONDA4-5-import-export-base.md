# ONDA4-5: importar e exportar a Base

Ordem: `ORDERS/next-onda4.md`, frente 5. Branch `codex/import-export-base`. PR [#1964](https://github.com/nelsonboulangerie/django-shopman/pull/1964).
PR empilhado sobre `codex/lote-fornecedores` (#1957) até a base chegar ao main.

Os menus da Base de Insumos e Fornecedores abrem as peças existentes
`OperatorCsvImport` e `OperatorCsvExportButton`. A exportação inclui todos os
cadastros, em uso e arquivados, sem limitar à página ou ao recorte atual, com esse
alcance dito no diálogo. Cabeçalhos em português, separador ponto e vírgula, BOM
UTF-8 e vírgula decimal. `Arquivado=Sim` significa `is_active=False`.
Não havia importador antigo nessas telas para retirar.

O POST `purchase/{materials,suppliers}/csv/` dá a prévia sem gravar. O mesmo caminho
aplica com intenção idempotente e revisão assinada do CSV, ator e registros
observados. A revisão expira em 30 minutos; qualquer alvo alterado ou criado por
outra pessoa exige nova prévia. Erro por registro impede o lote inteiro. Os campos
e validadores existentes do cadastro são reutilizados; o porteiro de coerência de
unidade entre compra e venda é avaliado com mapa em lote. Escrita e auditoria são
uma transação; a falha da auditoria desfaz as gravações. Limite declarado de 1.000
registros/1 MB por importação. Campos ausentes preservam os dados existentes.

## Evidência

- `test_purchase_csv.py`: **14 passed**: prévia/aplicação/reenvio para ambas as
  entidades, vírgula decimal, export, erro por registro sem escrita parcial,
  revisão obsoleta/CSV alterado, preservação de metadata, SKU/unidade, duplicata,
  permissão/cabeçalho, corpos JSON que não são objeto e rollback da escrita se a auditoria falhar.
- `PurchaseCsvTools.test.ts`: **4 passed**. Prévia antes de aplicar, reenvio com a mesma intenção
  após resposta perdida, resultado em processamento sem aplicação anunciada,
  erro por registro e exportação pelo botão do kit.
- Typecheck, ESLint e Ruff aprovados. Guard `minimalSet`: **10 passed**. Suíte unitária completa do operator-kit: **108 arquivos, 1.319 testes aprovados**.
- Navegador Chromium, build de produção, transporte hermético: **8 passed**
  (duas entidades × claro/escuro × 1280×720/390×844). Upload, prévia sem escrita,
  uma aplicação e download CSV real. Nenhum 4xx/5xx. A transação em banco é provada
  separadamente pelos testes da API.
- Antes, dez cadastros individuais: **300 consultas**, Server-Timing agregado
  `projection;dur=64.75`, `db;dur=5.50`. Depois, uma aplicação: **22 consultas**,
  `projection;dur=3.87`, `db;dur=0.36` (ms, SQLite local).
- Dois/quarenta registros: prévia/aplicação/exportação **5/22/5 consultas em ambos**.
  Server-Timing de aplicação: `projection;dur=2.75/6.79`, `db;dur=0.25/0.58`.
  O teste reprova crescimento com os registros.
- Capturas: `surfaces/purchase-nuxt/test-results/visual/`
  `base-csv-onda4-5-CSV-{materials,suppliers}-{light,dark}-{desktop,mobile}/`
  `onda4-5-{materials,suppliers}-{antes,depois,export}-{light,dark}-{desktop,mobile}.png`.
  Capturas estáveis, animações concluídas, abertas e inspecionadas. Sem baseline novo.

## D1 a D12

D1: cartão da prévia é o do kit; tabela interna `in-card` soft; sem selo novo.
D2: não se adicionou cabeçalho/rodapé destacado a cartão.
D3: botões canônicos das peças do kit; sem esticar na mesa.
D4: mantém tabela e toolbar da Base; importação no painel canônico.
D5: controles irmãos do próprio kit.
D6: rótulos completos Importar CSV/Exportar CSV/Baixar CSV; alcance da exportação visível.
D7: campo de arquivo do kit; nenhum campo de formulário próprio.
D8: erro explica o próximo gesto; Cancelar/fechar dispensa o aviso.
D9: escolha do arquivo fora da tabela, em painel; prévia e Aplicar/Cancelar antes de gravar.
D10: português, vírgula decimal, Arquivado, texto sem travessão.
D11: OperatorCsvImport e OperatorCsvExportButton reutilizados, NuxtModal canônico para exportar.
D12: capturas antes/depois/export de ambas as entidades nos dois temas e tamanhos inspecionadas.

Sem alteração de Core ou migração. As duplicatas históricas de prefixo 0023 a 0039
em shop já estavam na base; esta frente não criou nenhuma.

Validação após empilhar a frente 4: **21 testes API passaram** (14 CSV + 7 lote de fornecedores), **6 testes de componente passaram** (4 CSV + 2 lote), typecheck e oito cenários Chromium passaram novamente.
