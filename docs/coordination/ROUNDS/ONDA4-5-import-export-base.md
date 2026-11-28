# ONDA4-5: importar e exportar a Base

Estado final: MERGED no #1964 em 2026-10-21 00:02:27 UTC.
Commit de merge: `921d70c3275872b87a238199f9ddfd2e8beae760`.

Ordem: `ORDERS/next-onda4.md`, frente 5. Branch `codex/import-export-base`. PR [#1964](https://github.com/nelsonboulangerie/django-shopman/pull/1964).
O PR foi preparado sobre `codex/lote-fornecedores` (#1957), depois direcionado ao
main e validado na fila após o merge do pai.

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

- `test_purchase_csv.py`: **15 passed**: prévia/aplicação/reenvio para ambas as
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
- Dois/quarenta fornecedores: prévia/aplicação/exportação **5/22/5 consultas em ambos**. Dois/quarenta insumos: **6/23/5 em ambos**, incluindo o mapa de unidade do catálogo.
  Server-Timing de aplicação: `projection;dur=2.75/6.79`, `db;dur=0.25/0.58`.
  O teste de ambas as entidades reprova crescimento com os registros.
- Capturas versionadas em `docs/coordination/EVIDENCE/onda4-base/`:
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

Validação: **15 testes CSV passaram**, além dos **8 testes de lote de fornecedores** aprovados com a guarda de corpo descrita abaixo, **6 testes de componente passaram** (4 CSV + 2 lote), typecheck e oito cenários Chromium passaram novamente.

## Robustez do lote herdado da frente 4

Este PR também protege o endpoint de lote de fornecedores contra corpo JSON que
não seja objeto. A guarda vem antes de `dict(request.data)` e devolve 400 no dialeto
`detail/field/errors`, sem escrita. Um caso autenticado `["x"]` comprova a recusa;
os oito testes do lote passaram. A correção acompanha a #1964 para não reiniciar
os checks finais da #1957. A superfície e o gesto do lote não mudam.


## Evidência preservada no repositório

As capturas antes/depois foram copiadas do cache local para EVIDENCE/onda4-base.

- [onda4-5-materials-antes-dark-desktop.png](../EVIDENCE/onda4-base/onda4-5-materials-antes-dark-desktop.png)
- [onda4-5-materials-antes-dark-mobile.png](../EVIDENCE/onda4-base/onda4-5-materials-antes-dark-mobile.png)
- [onda4-5-materials-antes-light-desktop.png](../EVIDENCE/onda4-base/onda4-5-materials-antes-light-desktop.png)
- [onda4-5-materials-antes-light-mobile.png](../EVIDENCE/onda4-base/onda4-5-materials-antes-light-mobile.png)
- [onda4-5-materials-depois-dark-desktop.png](../EVIDENCE/onda4-base/onda4-5-materials-depois-dark-desktop.png)
- [onda4-5-materials-depois-dark-mobile.png](../EVIDENCE/onda4-base/onda4-5-materials-depois-dark-mobile.png)
- [onda4-5-materials-depois-light-desktop.png](../EVIDENCE/onda4-base/onda4-5-materials-depois-light-desktop.png)
- [onda4-5-materials-depois-light-mobile.png](../EVIDENCE/onda4-base/onda4-5-materials-depois-light-mobile.png)
- [onda4-5-materials-export-dark-desktop.png](../EVIDENCE/onda4-base/onda4-5-materials-export-dark-desktop.png)
- [onda4-5-materials-export-dark-mobile.png](../EVIDENCE/onda4-base/onda4-5-materials-export-dark-mobile.png)
- [onda4-5-materials-export-light-desktop.png](../EVIDENCE/onda4-base/onda4-5-materials-export-light-desktop.png)
- [onda4-5-materials-export-light-mobile.png](../EVIDENCE/onda4-base/onda4-5-materials-export-light-mobile.png)
- [onda4-5-suppliers-antes-dark-desktop.png](../EVIDENCE/onda4-base/onda4-5-suppliers-antes-dark-desktop.png)
- [onda4-5-suppliers-antes-dark-mobile.png](../EVIDENCE/onda4-base/onda4-5-suppliers-antes-dark-mobile.png)
- [onda4-5-suppliers-antes-light-desktop.png](../EVIDENCE/onda4-base/onda4-5-suppliers-antes-light-desktop.png)
- [onda4-5-suppliers-antes-light-mobile.png](../EVIDENCE/onda4-base/onda4-5-suppliers-antes-light-mobile.png)
- [onda4-5-suppliers-depois-dark-desktop.png](../EVIDENCE/onda4-base/onda4-5-suppliers-depois-dark-desktop.png)
- [onda4-5-suppliers-depois-dark-mobile.png](../EVIDENCE/onda4-base/onda4-5-suppliers-depois-dark-mobile.png)
- [onda4-5-suppliers-depois-light-desktop.png](../EVIDENCE/onda4-base/onda4-5-suppliers-depois-light-desktop.png)
- [onda4-5-suppliers-depois-light-mobile.png](../EVIDENCE/onda4-base/onda4-5-suppliers-depois-light-mobile.png)
- [onda4-5-suppliers-export-dark-desktop.png](../EVIDENCE/onda4-base/onda4-5-suppliers-export-dark-desktop.png)
- [onda4-5-suppliers-export-dark-mobile.png](../EVIDENCE/onda4-base/onda4-5-suppliers-export-dark-mobile.png)
- [onda4-5-suppliers-export-light-desktop.png](../EVIDENCE/onda4-base/onda4-5-suppliers-export-light-desktop.png)
- [onda4-5-suppliers-export-light-mobile.png](../EVIDENCE/onda4-base/onda4-5-suppliers-export-light-mobile.png)
