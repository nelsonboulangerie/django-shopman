# ONDA4-3F: rascunhos de custos e mínimos fora do filtro

Seguimento concreto do #1959, autorizado pela coordenação. Branch
`codex/tabelao-insumos-hidden-errors`, iniciado em `32a2cdbbd`.
Estado: PR #1968 draft empilhado no #1959, aguardando o merge do pai para seguir a esteira.

## Problema e correção

Digitar um valor inválido no creme, um custo válido no chocolate e filtrar só
Chocolate deixava Salvar desabilitado por um erro que não estava na tela. Além
disso, o payload já mandava apenas o recorte visível, mas o sucesso limpava também
os rascunhos ocultos. O mesmo desacordo existia no lote de mínimos.

A validação agora usa exatamente as linhas visíveis do payload. O sucesso remove
somente os rascunhos das linhas enviadas, preservando valores, conversões de
compra e a pilha de Desfazer dos demais. O `clear(keys)` opcional do kit confirma
um subconjunto de células; `clear()` continua a descartar tudo explicitamente.
Nenhum endpoint, contrato HTTP, modelo ou migração mudou. Continua um POST por lote.

## Evidência

- Browser real com o build anterior do #1959: dois testes falham em claro/escuro
  porque Salvar fica desabilitado depois de esconder o valor inválido.
- Build corrigido: dois testes passam, enviando somente CHOC-70, preservando o
  rascunho inválido de CREME-35 ao retirar o filtro, e permitindo desfazê-lo.
  Nenhuma resposta 4xx/5xx. Capturas em `../EVIDENCE/ONDA4-3F-rascunhos-filtrados/`.
- Compras: **19 arquivos, 190 testes passaram**.
- Kit: **171 arquivos, 1872 testes passaram**, incluindo confirmação parcial sem
  ressuscitar célula já gravada ao desfazer as demais.
- Dois testes de componente cobrem custos e mínimos: erro oculto não bloqueia o
  recorte, o rascunho oculto e seu Desfazer sobrevivem ao salvamento.
- Typecheck e lint do Compras passaram. Sem impacto em consultas: a correção é
  inteiramente local, com o mesmo payload e a mesma única requisição do recorte.

O primeiro ensaio completo do kit encontrou 63 falhas de montagem do runtime
Nuxt causadas pelo node_modules compartilhado por symlink. As dependências do kit
foram instaladas isoladamente na worktree e a suíte inteira passou. Não houve
mudança de fonte para contornar esse problema de ambiente.

## D1 a D12

D1: cartões e selos existentes preservados. D2: nenhum destaque novo de cabeçalho
ou rodapé. D3: mesmos botões canônicos. D4: tabela continua na largura disponível.
D5: altura das ações preservada. D6: mesmos rótulos completos. D7: altura dos
campos preservada. D8: erro reaparece junto ao insumo quando o filtro o revela.
D9: salvar confirma só o recorte, Desfazer das outras células é preservado, Limpar
continua explícito. D10: nenhuma nova copy de produto. D11: helper canônico do kit.
D12: seis capturas antes/depois claro/escuro abertas e conferidas.
