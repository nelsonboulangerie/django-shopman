# Pagamento na entrega — revisão de 11/09/2026

Registro da primeira implementação. O contrato individual de maquinhas que substitui a referência genérica está em `PDV-GESTOR-INTEGRATION-2026-09-11.md`; preservar a base integrada do Gestor.

## Decisão e comportamento

O PDV usa as mesmas linhas e o mesmo teclado para pagamentos no caixa e pagamentos combinados para a entrega. O seletor determina **quando** o recebimento ocorre. Não existe um segundo campo de troco no PDV: o dinheiro informado no teclado alimenta `payment.change_for_q`; o troco é a diferença para a parcela em dinheiro, inclusive numa conta mista.

- No caixa: permanece o fluxo existente de recebimento imediato.
- Na entrega: dinheiro, crédito e débito físicos, inclusive mistos. As linhas permanecem pendentes; fechar a venda não captura intents e não aumenta o dinheiro da gaveta.
- Gestor: o acerto confirma as parcelas no Payman, após conferência do dinheiro e dos comprovantes. Apenas dinheiro gera `cod_settled` no caixa. Troco que saiu continua tendo o ciclo separado `courier_out`/`courier_in`.
- Confirmações repetidas são serializadas pelo bloqueio do pedido e recusadas pelo marcador de acerto. A transação engloba todas as parcelas.
- O nome técnico `settle_delivery_cash` e a chave de contrato `can_settle_delivery_cash` permanecem por compatibilidade; a ação visível passa a ser “Acertar entrega”.

## Maquininha

Reutiliza-se `dispatch.equipment`, sem criar outro controle de custódia. No despacho do Gestor, uma cobrança pendente em crédito/débito exige marcar `card_machine`, configurado em `ChannelConfig.fulfillment.equipment`. É o controle existente por referência de equipamento, não um inventário novo de terminais individuais.

Devolver o aparelho não confirma pagamento. A opção de devolver junto no acerto começa desmarcada. O pagamento pode ser confirmado e o aparelho continuar em trânsito, ou vice-versa. O checkout não pede “já cobrei na maquininha” para uma cobrança futura.

## PIX Efí

Permanece no fluxo antecipado, com confirmação automática. No código atual, a cobrança nasce imediatamente e tem expiração; o portão de pagamento exige captura antes de liberar o trabalho físico. Para cobrar apenas na chegada, seria necessário gerar/exibir o QR naquele momento e tratar vencimento, confirmação e retorno do entregador. Não foi convertido em recebimento manual nem habilitado como promessa de pagamento futuro. PIX da maquininha não foi adicionado como método Efí.

## Interface

Desconto e Dividir conta permanecem no mesmo grupo, agora também com Receber no caixa e Receber na entrega quando aplicável. Mesma geometria, ícones e estados; sem título visível “Ajustes da conta”. São dois botões normalmente e quatro na entrega; sem tipos de desconto no contrato, Desconto permanece visível e desabilitado. Avisos e rótulos das cédulas distinguem dinheiro previsto de dinheiro recebido.

## Verificação

Testes cobrem dinheiro, crédito, débito e misto do fechamento do PDV até despacho e acerto, valores da gaveta, troco misto, repetição, devolução independente do aparelho e rejeição de gateways online na entrega. Também foram executados contratos de superfície, conclusão comercial e fila do Gestor, testes das duas interfaces, TypeScript e Ruff. Preview local conferido visualmente. Nenhuma cobrança real, SEFAZ ou hardware usado. Alterações ainda não publicadas.
