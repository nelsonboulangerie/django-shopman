# ONDA4-1: vínculos do produto

Ordem: `ORDERS/next-onda4.md`, frente 1. Base `65b658d31`. Branch
`codex/produto-vinculos`, worktree própria `produto-vinculos`.

## Entrega

- Aba Vínculos no painel: preço, quantidade mínima, publicado e vendável por canal.
  Usa `catalog/cell/`, com a ação observada, revisão por campo e recibo existente.
- Mostra também canal sem vínculo. A intenção específica de ausência autoriza a inclusão
  pelo mesmo escritor, inicialmente oculto e pausado; outra intenção antiga conflita.
- Coleções manuais: incluir por modal, retirar, escolher primária e ordem do produto na
  coleção. Usa o PATCH do detalhe, revisão do conjunto e transação com o recibo.
  Coleção não publica o produto em canal. Coleção automática continua dirigida por regra.
- Mínimo positivo com até três casas decimais, sem colisão com outro patamar. Preserva
  histórico do ListingItem e solicita reprojeção completa quando muda a estrutura do preço.
- Canal espelhado explica que a edição pertence ao canal de origem. Identificação técnica
  do canal fica recolhida. Nenhuma migração ou alteração no Core.
- Aplicar/Cancelar independentes, rascunho preservado na recusa. Salvar geral e fechar são
  protegidos durante a gravação local. Releitura de coleção renova apenas sua revisão;
  releitura de canal preserva revisões e dados dos demais rascunhos. Teste cobre nome
  alterado por terceiro enquanto se aplica a curadoria.

## Verificação

- Regressão ampliada final: **118 passed, 3 skipped** (locks concorrentes exigem PostgreSQL).
- Backend direcionado: **10 passed**, incluindo intenção obrigatória, replay, conflito,
  troca de primária, retirada, rollback se recibo falha, mínimo inválido e colisão de patamar.
- Componentes: **26 passed**. Composable: **27 passed**, incluindo revisão seletiva.
- Ruff, ESLint e typecheck passaram. `export_orders_schema` regenerado sem diferença:
  os novos campos do detalhe são espelhados em `app/types/catalog.ts`.
- Navegador Chromium 1243, prévia Nuxt com respostas de API de fixture Django real,
  ambiente local, sem dados vivos. Antes/depois em claro e escuro, edição inline,
  curadoria no celular (390px), escolha em modal: zero 4xx/5xx, sem erro de página e
  sem overflow horizontal. Todas as imagens foram abertas; capturas do modal refeitas
  após a transição para evitar registrar um frame translúcido.
- Evidência versionada em `../EVIDENCE/ONDA4-1-produto-vinculos/`.
- Testes de locks concorrentes PostgreSQL não são demonstrados pelo SQLite local;
  os casos de revisão/replay/rollback são exercitados. CI segue sendo a validação do runtime.

## Desempenho

Sonda temporária executou a função `_detail_payload` e `_read` da base `65b658d31`
e as novas funções no mesmo processo e sob o mesmo `ServerTimingMixin`:

| leitura | consultas | projection | db |
|---|---:|---:|---:|
| base instrumentada | 17 | 21,42 ms | 1,77 ms |
| com vínculos | 20 | 17,13 ms | 1,00 ms |

A base não enviava `Server-Timing`; o detalhe agora usa o mixin canônico.
A comparação de duração é observacional em máquina concorrida, sem alegar ganho.
O custo novo de leitura é fixo: teste aumenta de zero para **30 vínculos** e mantém
**20 → 20 consultas**, reprovando crescimento por linha. Sonda removida depois da medição.

## D1 a D12

- D1 OK: cartões de topo outline; blocos internos soft sem borda; selo sem variant.
- D2 OK: cartões com conteúdo contínuo, sem cabeçalho/rodapé destacado.
- D3 OK: botões md do conjunto solid/outline/ghost, sem esticar.
- D4 OK: alinhamento nas bordas do bloco e colunas com mesmo intervalo.
- D5 OK: campos e botões irmãos de mesma altura.
- D6 OK: rótulos escritos completos; sem ação só por ícone nova.
- D7 OK: inputs na altura canônica dos botões.
- D8 OK: validação junto ao campo, aviso explica o alcance por canal; sem aviso solto.
- D9 OK: editar inline com Aplicar/Cancelar; incluir coleção usa modal de escolha.
- D10 OK: português da casa, sem travessão em copy, IDs recolhidos.
- D11 OK: primitivas Nuxt UI canônicas, sem overlay manual.
- D12 OK: capturas claro/escuro abertas, desktop/celular, campos/modal conferidos.

## Estado da esteira

PR **#1960** publicado. Implementação e verificação local concluídas; acompanha CI e fila pelo PR.
