# ONDA4-F6: componentes de combo

- Data: 2026-10-20. Branch: `codex/produto-combo`.
- PR: #1961, pronto para revisão, empilhado no #1960. Main das frentes 2 e 3 integrado via head 81fa9f9f7 do pai. Aguarda merge da frente 1 para retarget ao main e fila.
- Ordem: `ORDERS/next-onda4.md`, frente 6.

O painel Vínculos lista componentes e quantidades por unidade do combo. O editor inline usa Aplicar/Cancelar, busca em modal e confirmação ao retirar, com Desfazer por 10 segundos. O aviso explica que a alteração muda o estoque necessário nas próximas vendas. O rascunho da aba Geral é preservado ao salvar composição.

A gravação usa a intenção, recibo e revisão canônicos do detalhe. A revisão considera SKU, quantidade e unidade de cada filho e unidade do pai; renomear o filho não causa conflito. Alterar unidade causa conflito. ProductComponent mantém a validação canônica de ciclo/profundidade. Escrita, revisão, recibo e signal de projeção/outbox são atômicos; falha no outbox reverte tudo. Locks ordenados dos produtos serializam mudanças cruzadas no grafo. A busca leve de opções retorna até 20 produtos ativos, sem montar a matriz rica.

## Provas

- Backend integrado: **30 passed**, incluindo API/recibo/replay, conflito de composição, revisão independente, quantidades inválidas, ciclos e profundidade, rollback do recibo e composição quando outbox falha, busca limitada e unidade do pai/filho.
- Frontend integrado: **34 testes de componentes** e **28 do composable** aprovados. Typecheck, lint e ruff aprovados.
- Navegador real com BFF e fixture sintética autenticada: salvar quantidade, Desfazer, buscar componente e preservar rascunho Geral, em desktop e celular, nos dois temas. Zero erro HTTP e zero pageerror. Nenhuma credencial ou dado do alpha usado.
- Prévia local em Nuxt dev; a build de produção permanece coberta pela esteira. Não houve migração nem edição das áreas reservadas.

## Desempenho

Leitura do detalhe instrumentada por Server-Timing. Antes: **20 consultas com 0 e com 60 componentes**, projection 6,68→6,81 ms e db 0,40→0,38 ms. Depois: **21 consultas com 0 e com 60 componentes**, projection 7,28→9,10 ms e db 0,39→0,41 ms. A leitura acrescenta uma consulta em lote constante e devolve os 60 componentes. Não há alegação de ganho de latência; a trava permanente cobre ausência de N+1.

## D1 a D12

- **D1:** cartão externo outline; linhas internas soft sem borda.
- **D2:** cartão sem cabeçalho/rodapé destacado.
- **D3:** ações mínimas, centradas e sem largura esticada.
- **D4:** bloco acompanha a largura do painel.
- **D5:** linhas de componentes usam o mesmo arranjo e altura.
- **D6:** rótulos explícitos com nome, quantidade e unidade; contexto por unidade do combo.
- **D7:** quantidade compacta; busca acompanha a largura útil do modal canônico.
- **D8:** impacto de estoque explicado junto à composição; erros preservam rascunho e permitem correção.
- **D9:** Aplicar/Cancelar inline; escolher componente em modal; retirada exige confirmação e oferece Desfazer.
- **D10:** português da casa, sem travessão ou jargão do protocolo.
- **D11:** NuxtCard, NuxtButton, NuxtInput, NuxtModal e OperatorTimedButton canônicos.
- **D12:** abertos e conferidos os antes/depois claro/escuro, edição e busca desktop e celular. Uma captura transitória durante resolução de merge exibiu overlay do compilador e foi descartada e refeita após integração limpa.

Capturas únicas em `img/onda4-f6-produto-combo/`: `onda4-f6-before-{light,dark}.png`, `onda4-f6-{after,edit,choose}-{light,dark}.png` e `onda4-f6-{after,edit,choose}-mobile-{light,dark}.png`.

## Integração com main das frentes 2 e 3

Head do pai `81fa9f9f7` integrado: só BOARD teve conflito, com registros preservados. Revalidação: 30 backend, 64 testes em quatro arquivos frontend e typecheck aprovados. Schema regenerado sem diferença. Mock ecoa order/date_from/date_to; navegador desktop e celular em ambos os temas repetiu salvar, Desfazer, busca e preservação do rascunho Geral sem erros HTTP/pageerror. Ruff e diff-check aprovados.
