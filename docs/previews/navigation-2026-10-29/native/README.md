# PDV: conciliação reversa com o app real

Rodada de 30/10/2026. Somente prévia. Não é implementação no produto.

## Base e isolamento

Fonte fixada em `origin/main` `e0c22ba1ffe28e20c5c453db09160e941dfae8c6`.
`run.sh` extrai POS e operator-kit para um diretório temporário exclusivo, instala
os locks existentes com Node 22 e compila dois apps. O primeiro é byte a byte da
fonte arquivada. O segundo substitui **somente** `PosPreordersShell.vue` pela
composição desta pasta. Nenhum arquivo de `surfaces/` é alterado na worktree.

O backend é `tests/visual/mockBackend.mjs` da mesma fonte, com `MOCK_SCENARIO=sale`.
Não usa Django real, banco, credenciais nem APIs reais de pagamento/entregador.
As portas são loopback: fixture 38792, atual 4188, proposta 4189.
Os túneis apontam somente aos apps de demonstração.

A fonte de Comandas, Venda, Checkout, produtos, carrinho, resultados, Caixa,
Ajustes, cards de Encomendas e respectivos diálogos é a mesma nas duas versões.
A preservação é da árvore de componentes e de seus contratos/callbacks; não é
uma alegação de teste ponta a ponta de todas as funções de negócio.

## Experimento

- Cabeçalho de Encomendas acompanha a rolagem, com título e ações existentes.
- Busca específica sai do cabeçalho e fica em card com filtros, recortes,
  período, favoritos, visualização e resumo. O card rola junto do conteúdo.
- No detalhe, a busca global existente continua disponível no cabeçalho.
- Alertas mantêm componente, cor semântica, texto e ações nativas no topo.
- Slots, props e callbacks das ações permanecem. Não se reescrevem formulários.
- Dia e semana são comparados nos mesmos recortes. O link Hoje usa `mode=day`
  explicitamente. Nenhum default do produto foi alterado.

## Limites e achados pendentes

O simulador visual original devolve `{}` para endpoints não cobertos. Por isso,
alguns diálogos abrem com dados incompletos; por exemplo, o calendário de reagendar.
Não interpretar resposta vazia como sucesso de uma operação. Backend de demonstração
não foi ampliado nesta rodada. Impressora, scanner, PIX, caixa físico, entregador,
login real, Central e Admin não foram conectados. Não testar contato externo com
os telefones/e-mails das fixtures.

Isso não autoriza aprovação global nem implantação. Esta primeira comparação
nativa se concentra na **moldura das Encomendas**. O restante está acessível como
referência fiel e ainda requer propostas específicas, especialmente:

1. Agenda: período inicial, dias vazios, ordenação das janelas e densidade. O mock
   tem janelas fora de ordem e detalhes cujo total não bate com a soma dos itens;
   corrigir a fixture antes de avaliar precisão financeira da tela.
2. Detalhe: prioridade do recebimento/entrega versus reagendar, imprimir, editar,
   comentar e cancelar. Preservar os bloqueios do servidor e aprovações gerenciais.
3. Busca: contexto da busca entre todas as datas versus filtros do período,
   resultado único, leitor de código e retorno ao mesmo recorte.
4. Caixa e Fim do dia: distinguir consulta e operação, preservar contagem cega,
   diferença entre vazio e zero, destinos e retomada. Nenhum redesign feito aqui.
5. Ajustes: tabs roláveis, legibilidade de estações/impressoras/maquininhas,
   explicações e permissões. Nenhum redesign feito aqui.
6. Comandas/Venda/Checkout: referência de preservação, não candidatos a padronização
   por simplificação. Revalidar teclado, leitor, peso, adicionais, descontos,
   transferências, envio parcial, pagamentos e modo offline antes de qualquer
   implementação futura.

## Verificação desta rodada

As duas compilações Nuxt concluíram. No navegador pelo túnel foram inspecionados
agenda diária, filtros nativos, detalhe e abertura do diálogo Reagendar em 390px.
O diálogo revelou a lacuna do simulador descrita acima. Não foi confirmado
reagendamento, cancelamento, pagamento, impressão ou chamada de entregador.

Página de comparação: `../pdv-native.html`. Os links de túnel são temporários e
precisam ser atualizados ao reiniciar a infraestrutura. A página de avaliação
fica separada das telas do PDV, sem consumir espaço vertical dentro delas.

Medições no navegador: em 390px, o primeiro card do dia começa em y=271 na
versão atual e y=354 na proposta. O card da proposta custa 83px na abertura,
mas desaparece durante a rolagem, deixando somente a barra de título no topo.
Não tratar a proposta como ganho inequívoco de espaço inicial. Em 320px e 390px
não houve overflow horizontal do documento. Desktop inspecionado em 1440×900;
a grade diária ainda tem áreas vazias importantes que este experimento não corrige.
A busca nativa foi aberta no desktop. Capturas nesta pasta: atual/proposta mobile,
proposta rolada e proposta desktop. Viewport restaurado após a inspeção.
