# iFood: preparação para homologação, 13/09/2026

## Situação

Homologação oficial ainda não iniciada. O app PDV **Nelson Boulangerie - Shopman**, slug `nelson-boulangerie-shopman`, está preparado para Order e Events. Elegibilidade do app não comprova aprovação ou funcionamento de todos os cenários.

O domínio público definido é `menu.nelsonboulangerie.com.br`. A API continua em `api.boulangerie.com.br`; são funções distintas da arquitetura.

O chamado técnico **33298264**, sobre HTTP 403 HTML intermitente, foi enviado com autorização do responsável e consta **Em análise**. Os testes reais mostraram falha e sucesso posteriores nos mesmos fluxos. Não há diagnóstico definitivo do iFood nem justificativa para alterar permissões ou contornar controles de acesso.

No aplicativo de teste **NB Teste (C)**, desativado o webhook obsoleto de staging, cujo hostname não resolvia. Status desativado confirmado após recarregar. O fluxo deste ensaio usa polling; não foram trocadas credenciais nem concedida permissão à loja real.

## Correções complementares

- CFM confirma pelo serviço canônico; DSP reflete o despacho apenas quando o pedido de entrega está pronto. Eventos anteriores ao pedido ou incompatíveis continuam sem ACK para reentrega.
- Evidências remotas impedem callbacks em eco. Callbacks de progresso atrasados ficam inertes após término do pedido.
- Dispatch só é enviado para entrega explicitamente MERCHANT. ReadyToPickup atende retirada e entrega IFOOD. Proprietário ausente não é presumido.
- Gestor e expedição KDS compartilham os bloqueios de cancelamento pendente, horário de preparo e retirada pelo entregador iFood.
- Pedidos SCHEDULED preservam preparação e janela em UTC. Preparo espera o instante exato, inclusive no mesmo dia e na virada de data. Dados ausentes/inválidos bloqueiam a operação e geram orientação.
- Reserva usa a data autoritativa da janela; sem janela válida, espera o preparo. KDS e baixa não começam antes do horário nem durante cancelamento pendente. O despertador permanece na fila enquanto aguarda decisão remota, sem consumir tentativas de erro.
- Novos pedidos recebem uma chave interna determinística para o KDS. Pedidos históricos não têm campo imutável reescrito.
- Gestor apresenta responsável pela entrega e horários de preparação/janela ao lado das informações financeiras iFood.

## Limites do ensaio

O ensaio publicado anterior recebeu e recusou o pedido `IFOOD-260912-L55`, com PLC, repetição sem duplicação, callback de cancelamento e CAN. Não houve aceite, preparo ou despacho. Evidências estão no relatório anterior.

`is_test=true` não isola automaticamente o sistema interno. A expedição lista pedidos READY de todos os canais, e a conclusão pode acionar fidelidade. Com a configuração observada, pagamento externo e ausência de gatilhos fiscais não geram emissão fiscal; courier none não chama provedor e SKUs sem holds não baixam estoque. Essas constatações não autorizam tratar a produção como ambiente isolado.

O ciclo físico completo deve ser exercitado em banco isolado. O teste local de contrato não substitui os cenários executados no portal oficial.

## Critério para abrir a tentativa oficial

1. Correções integradas pelos checks protegidos e imagem publicada verificada.
2. Recebimento/cancelamento novamente verificados no aplicativo e merchant de teste.
3. Ciclos de confirmação, entrega própria, entrega iFood, retirada, agendamento e reentrega verificados; ambiente do ensaio completo isolado da operação real.
4. Instabilidade 403 esclarecida ou evidência suficiente de conectividade confiável, sem afirmar que um sucesso pontual resolveu a causa.
5. Somente então iniciar o wizard de Order/Events e registrar o resultado oficial. Não prometer homologação com base nos testes locais.

## Documentação oficial consultada

- [Homologação Order FOOD](https://developer.ifood.com.br/en-US/docs/food/guides/modules/order/homologation)
- [Homologação Events](https://developer.ifood.com.br/en-US/docs/guides/modules/events/homologation)
- [Workflow de pedidos](https://developer.ifood.com.br/pt-BR/docs/guides/modules/order/workflow/)
- [Pedidos agendados](https://developer.ifood.com.br/en-US/docs/food/guides/modules/order/scheduled-orders)
- [Polling](https://developer.ifood.com.br/en-US/docs/guides/modules/events/polling-overview)
- [Eventos de pedidos](https://developer.ifood.com.br/pt-BR/docs/guides/modules/events/order-events/)

Leitura realizada em 12/09/2026 BRT. Páginas oficiais às vezes responderam 403; conteúdos oficiais indexados e telas autenticadas foram usados em conjunto. Não inferir endpoints de conclusão ou ações não documentadas.

## Validação realizada nesta revisão

O PR #633 foi integrado pelo merge queue em `d85c9e241ba4b1436e243ebe7e67ae28f5226809`, com todos os checks aprovados. O deploy automático é acompanhado separadamente; merge não equivale a imagem ativa.

- Backend shop: 4.643 testes aprovados, 32 skips, 31 deselected e 18 subtests. Ajustes adicionais de KDS/notas foram verificados nas suítes específicas posteriores.
- Admin canônico: checker e 270 testes aprovados.
- Frontend: 310 testes, typecheck e lint dos arquivos alterados sem erros.
- Navegador: sete testes aprovados, incluindo viewport 375px e conferência visual. A toolbar agora quebra linha no celular, eliminando rolagem horizontal que escondia controles.
- PostgreSQL 16.14 efêmero: 35 testes aprovados, sem skips; o segundo fire aguardou o lock da Order antes de consultar/criar tickets. Cluster local removido após o ensaio.
- Ensaio de domínio isolado: dois ciclos completos aprovados. Estoque, KDS e fulfillment reais no banco pytest; HTTP interceptado e backend fiscal local. Confirmação/preparo/despacho/conclusão e cancelamento/CAN não duplicam efeitos; cancelamento confirmado devolve estoque e encerra tickets. Essa prova não representa comunicação com SEFAZ ou conclusão oficial no iFood.
- Observações, opções e customizações FOOD agora chegam às notas KDS. Teste com combo da fixture capturada confirma instruções no ticket real, preservando os dados de origem.

Suíte final combinada iFood + KDS + contratos: **467 passed, 1 skipped, 8 subtests passed**. O skip é a prova de row lock no SQLite, executada com sucesso separadamente em PostgreSQL.
