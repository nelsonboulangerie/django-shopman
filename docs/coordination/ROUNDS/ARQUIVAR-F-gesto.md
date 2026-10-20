# ARQUIVAR-F: gesto confirmado no cadastro do produto

- **id:** ARQUIVAR-F
- **branch:** `codex/arquivar-gesto`
- **PR:** #1948
- **estado:** draft publicado; aguarda #1945 e #1947 no `main`
- **início:** 2026-10-20

## O que entrou

- O painel do produto oferece **Arquivar** ou **Desarquivar** na barra de ações. O estado não é
  campo do rascunho e não existe `input`/checkbox para `is_active`.
- O tabelão permite selecionar produtos do mesmo estado e enviar um único lote. A matriz principal
  continua sem botão de arquivamento.
- A confirmação canônica explica que o produto sai do cardápio, dos canais e das listas, enquanto
  histórico e vínculos ficam guardados. Desarquivar explica a restauração dos estados publicado e
  vendável já existentes.
- O recibo volta por linha, separando aplicados, conflitos e erros. O **Desfazer** usa
  `OperatorTimedButton`, relógio do servidor e prazo absoluto de 10 segundos.
- A API exige `shop.manage_catalog`, intenção idempotente, revisão-base e o mesmo operador que leu a
  tela. A escrita usa uma transação, trava os produtos, grava simple-history, cria `LogEntry` e só
  dispara `product_updated` depois do commit.

## Prova funcional e desempenho

- Django direcionado: 37 passaram, 2 ignorados (`test_catalog_archive_gesture`, intenções,
  preservação do patch e lista paginada).
- Gesto Django novo: 4 passaram. Cobre permissão, idempotência, auditoria, histórico, conflito por
  linha, produto ausente, preservação de publicado/vendável e desfazer.
- Consultas do lote: 2 produtos e 10 produtos usam a mesma contagem. São 6 consultas com o
  `ContentType` aquecido e no máximo 7 na primeira auditoria.
- Nuxt direcionado: 21 testes de componentes e 26 do composable passaram. A confirmação e o
  desfazer usam as peças reais do kit; o contrato HTTP, a intenção e a releitura canônica também
  são exercitados. A suíte completa do Orders passou com 83 arquivos e 814 testes.
- `nuxi typecheck`, ESLint e Ruff passaram sem erro. `make admin` passou: 300 testes, a fronteira
  Admin e o gate Unfold canônico. `makemigrations --check --dry-run` confirmou que não há mudança
  de modelo sem migração.
- Navegador real com backend hermético: rota de arquivados, seleção e ação de desarquivar verificadas;
  nenhuma resposta 4xx/5xx e nenhum erro da aplicação. O único log de erro observado veio da extensão
  SingleFile do Chrome, fora da aplicação.

## Capturas antes/depois

- Claro: `img/arquivar-gesto-1948-before-light.jpg` e
  `img/arquivar-gesto-1948-after-light.jpg`.
- Escuro: `img/arquivar-gesto-1948-before-dark.jpg` e
  `img/arquivar-gesto-1948-after-dark.jpg`.

## D1 a D12

- **D1:** o slideover não ganhou cartão de topo; o recibo usa alerta soft e o estado usa selo soft.
- **D2:** não há cabeçalho ou rodapé destacado dentro de cartão.
- **D3:** Arquivar é `error/solid`, Desarquivar é `primary/solid` e Desfazer usa a peça canônica; os
  botões têm largura do conteúdo.
- **D4:** tabela, alerta e barra inferior continuam alinhados às bordas do slideover.
- **D5:** linhas e células irmãs preservam altura e alinhamento.
- **D6:** os atos têm rótulo completo; os ícones são complementares e não substituem a palavra.
- **D7:** os campos de preço não crescem além da célula ou dos botões da barra.
- **D8:** conflito e erro aparecem no recibo acionável, sem cor decorativa desconectada do ato.
- **D9:** Arquivar/Desarquivar confirma antes de escrever e oferece Desfazer cronometrado; cancelar
  mantém o estado atual.
- **D10:** copy da casa, inequívoca, em português, sem travessão, “desativar” ou “inativo”.
- **D11:** `NuxtButton`, `NuxtBadge`, `NuxtAlert`, `OperatorTable`, `useConfirm` e
  `OperatorTimedButton`; nenhuma primitiva paralela.
- **D12:** as quatro capturas foram abertas. Não há corte do novo ato, sobreposição, borda duplicada
  ou contraste ilegível em claro/escuro.

## Fora daqui

- A filtragem e o selo da matriz pertencem à Frente C (#1947).
- O campo, a migração e a vendabilidade canônica pertencem à Frente A (#1945).
- O adapter iFood e todos os territórios reservados ficaram intocados.
