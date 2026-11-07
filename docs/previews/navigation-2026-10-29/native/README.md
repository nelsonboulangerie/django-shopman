# PDV nativo: conciliação reversa, rodada 2

Somente prévias. Entrada: `../pdv-native.html`. Não é implementação no produto.

## Isolamento e reprodução

Fonte fixada em `origin/main` `e0c22ba1ffe28e20c5c453db09160e941dfae8c6`.
Com Node 22 no PATH, executar `bash docs/previews/navigation-2026-10-29/native/run.sh`.
As portas 38792, 4188 e 4189 precisam estar livres. O script extrai POS e kit para
um diretório temporário exclusivo, instala os locks e compila o atual antes de
aplicar a proposta. Não modifica `surfaces/` na worktree.

`apply-preview.mjs` aplica somente:

- `PosPreordersShell.vue`: controles em card rolável, cabeçalho compacto, título
  específico do detalhe preservado e busca global no detalhe.
- `PosSettingsTabs.vue`: mesmos destinos, tabs roláveis e aba ativa sempre à vista.
- `composition.css`: espaçamentos nas telas de apoio, textos de estações sem
  truncamento e grade diária em duas colunas quando há largura. O modo lista fica.
- Rótulo contextual `Recortes` no seletor de Encomendas.
- `simulator.html`: controles de demonstração separados das telas do produto.

Sem troca de tokens, cards, botões, badges, formulários, diálogos ou callbacks.
Comandas, Venda e Checkout não foram reescritos. Caixa conserva os grupos por
tarefa; Fim do dia conserva seu corredor, contagem cega e ferramentas atuais.

## Simulador

`prepare-mock.mjs` estende uma cópia do `tests/visual/mockBackend.mjs` original.
`mock-extension.mjs` simula contratos e estados em memória. Não importa Core,
não se conecta ao Django real nem executa integrações externas.

Cobertura adicionada:

- Datas disponíveis, janela indisponível com motivo e limite de agendamento.
- Reagendamento com agenda/detalhe/histórico coerentes, revisão e repetição segura.
- Busca de encomendas abertas/concluídas e resultados do PDV na busca da suíte.
- Comentário, recebimento/entrega, cancelamento com motivo e edição com prévia.
- Favoritos de filtros: criar, alterar e excluir.
- Impressoras, maquininhas, envio automático e atalhos gravados para releitura.
- Salão com o payload de deltas real, revisão, histórico e capacidade recalculada.
- Abertura/fechamento do turno, movimentos, troco, contas e devoluções simuladas.
- Assinatura fictícia para sangria, cancelamento pago e atendimento de troco.
- Fechamento do dia com todos os itens preenchidos: vazio difere de zero.
- Falha única programável e restauração da demonstração.

A gerência é **fictícia**: usuário `demo`, nome `Gerência de demonstração`, PIN
`0000`. Nenhuma credencial real é necessária. Rotas não cobertas retornam 501,
em vez de um sucesso vazio. Os dados são compartilhados entre A e B para comparar
o mesmo cenário; restaurar altera somente esta demonstração.

O simulador não pretende reimplementar as políticas reais do orquestrador.
Conflitos, assinatura e idempotência aqui são cenários para exercitar a interface,
não evidência de correção do domínio. Pagamento, impressão física, gaveta,
câmera/leitor, autenticação, offline real, fiscal e entregador exigem validação
nas integrações apropriadas. Central e Admin não estão conectados.

## Evidência

Comandos executados:

```
node native/prepare-mock.mjs <mock original> <cópia temporária>
node native/verify-mock.mjs <cópia temporária>
```

Os caminhos acima são relativos a esta pasta. Saída efetiva registrada em
`verification-round2.txt`: 13 cenários passaram. São testes de contrato/estado
do simulador, não testes ponta a ponta de todo o produto.

O build Nuxt da proposta concluiu. No navegador pelo túnel:

- Reagendamento confirmado no mobile: nova data/horário e histórico após salvar.
- Cadastro de maquininha confirmado na lista após salvar.
- Falha de cadastro manteve os campos; repetir concluiu o cadastro.
- Impressora gravada, abas percorridas e atalhos gravados.
- Terminal, cozinha, planta do Salão, sessão, relatório de caixa e corredor Fim do dia inspecionados.
- Controle remoto de restauração executado e confirmado.
- Tab Atalhos de venda visível após navegar ao último destino.

Medições e capturas:

- 390px: card 149px; primeiro pedido y=326. Antes desta rodada, y=354.
- 320px: card 149px; na rodada anterior o card media 233px.
- Sem overflow horizontal do documento em 320/390px ou 1440px.
- Desktop 1440×900: grade diária em duas colunas de 578,5px.
- A busca explícita ainda custa espaço inicial em relação ao app atual (primeiro
  card y=271 em 390px). O ganho aparece durante a rolagem dos controles.
- Viewport restaurado após a inspeção.

Capturas `round2-*` são desta rodada. Capturas sem esse prefixo documentam a
rodada anterior. Ainda sem aprovação global do PDV, merge ou deploy.
