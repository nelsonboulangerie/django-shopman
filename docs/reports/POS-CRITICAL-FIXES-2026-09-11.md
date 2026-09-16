# Correções do PDV — revisão de 12/09/2026

Integração isolada em `codex/pos-critical-fixes-20260911`, PR619 em rascunho. Checkout compartilhado preservado. Frentes de identidade, autenticação, pagamentos e fiscal trabalharam em worktrees próprios. A tarefa dedicada de layouts entregou outro preview e não foi incorporada a este PR. Sem merge, deploy ou alteração de dados reais.

## Comportamento resultante

| Demanda | Solução |
| --- | --- |
| Pedido de troco | Alerta canônico `cash_change_requested` para operações, com terminal, operador, valor e denominações; atendimento/cancelamento resolve o alerta e atualiza via SSE. Não altera saldo. |
| Relogins | Bootstrap preserva o hash quando a senha é a mesma. Além disso, uma aba ociosa do PDV não pode mais travar outra em atendimento: atividade e proteção do pagamento são coordenadas entre abas do mesmo origin. Cadeado manual e bloqueio por inatividade real permanecem. |
| Balcão | Venda para levar agora, sem pergunta de retirada a cada venda; cliente opcional. Nova venda começa nesse modo. |
| Encomendas | Reutiliza cadastro, recebimento, agenda e pagamento existentes. Antes dos produtos, exige cliente ativo selecionado, escolha explícita retirada/entrega e data válida; entrega pede endereço. Hoje é uma escolha explícita. Horário continua podendo ficar a combinar. |
| Troca e retomada | Mantém itens e cliente ao mudar o modo. Voltar ao Balcão exige confirmação e remove contexto de agendamento/entrega/cobrança futura. Modo persiste por comanda. Encomenda de retirada hoje segue no preparo, sem entrega automática ao cliente. |
| Identidade | Telefone, CPF e e-mail de outro cadastro exigem escolha explícita, inclusive quando o nome não foi informado. Busca e cadastro novo ficam separados. Enter não pode selecionar um resultado que ainda não chegou. Corrigir conserva o rascunho. Autosave não cadastra rascunhos; é preciso concluir o cadastro explicitamente. |
| CPF da nota / e-mail do comprovante | Se o dado existir em outro cadastro, pergunta entre usar apenas no documento e associar o cliente. Apenas documento não associa cliente nem altera contatos/preferências fiscais. A escolha é vinculada a valor, dono, cliente atual e venda; mudanças invalidam a escolha. Mesmo cliente já associado dispensa pergunta redundante. Canal de e-mail desligado não consulta nem grava o campo. |
| Pagamento | Reutiliza antecipação, Pix/link pendente e cobrança na entrega. Cartão na entrega informa levar maquininha; dinheiro conserva troco para/valor a levar. Retirada com pagamento pendente usa os fluxos Pix/link existentes; não foi criado novo mecanismo de crédito na retirada. |
| Filipeta | Resultado de encomenda oferece impressão operacional mesmo antes de pagar e permanece disponível para conferência. A filipeta não substitui o documento fiscal. O layout anterior desta branch inclui endereço antes dos itens, métodos de cobrança e troco. O redesenho visual dedicado está em outra tarefa. |
| Fiscal da entrega | Entrega grátis continua classificada como entrega. Dados fiscais/endereço incompletos geram erro explícito e alerta; não reclassifica como presencial nem reduz frete/pagamento. Retry de emissão falhada recompõe os dados corrigidos preservando histórico; documento autorizado não é reconstruído. Detalhes e fontes no relatório fiscal abaixo. |
| Pix Storefront | Sem mudança: configuração versionada mantém mock com confirmação manual, `SHOPMAN_MOCK_PIX_AUTO_CONFIRM=false`. Não se confunde pedido registrado com pagamento confirmado. |

## Validação

- Testes backend cobrem identidade, dados de documento, modo, agenda, transferências, cozinha, handoff, fiscal/retry, alertas e sessões.
- Testes frontend cobrem decisões em sequência, respostas atrasadas, invalidação por dado/cliente/venda, preservação do rascunho, modo, retomada, pagamentos, impressão e coordenação de abas.
- Validação final backend: **427 passaram, 1 skip** (POS, identidade, fiscal, handoff e expiração de pagamento).
- Frontend final: 908 testes passaram e um teste ainda esperava o popover removido; a expectativa foi corrigida e a suíte do checkout revalidada. Typecheck Nuxt passou. Verificações de diff/Ruff executadas sobre os arquivos alterados.
- Smoke real em navegador local: telefone da Ana de teste não associou automaticamente; corrigir preservou os dados. Retirada hoje exigiu as três etapas. Pedido `PDV-260912-F10` ficou com Pix pendente e ação de filipeta. Venda `PDV-260912-L92` usou CPF e e-mail existentes exclusivamente no documento após duas escolhas; consulta ao banco confirmou `customer_ref` ausente, `customer={}`, CPF em `fiscal.tax_id` e e-mail em `receipt.email`.
- Prévia: `http://localhost:13619/`, API em `18619`, Gestor em `13620`. SQLite e dados sintéticos isolados em `/tmp/shopman-pdv-preview-619/`; fiscal simulado e notificações externas desativadas para testes. Não houve impressão física nem emissão fiscal real.

A coordenação de inatividade cobre abas do mesmo origin do PDV. Não promete resolver toda causa possível de perda de conexão ou expiração. Em entrega, a emissão continua usando somente o CPF pedido para o documento; cadastro identificado não autoriza puxar CPF silenciosamente. Dados fiscais insuficientes deixam pendência explícita até correção e nova tentativa.

## Publicação e migrações

Frontend e backend precisam ser publicados juntos. Nenhum reseed, credencial ou variável nova é necessário em produção. `sales_mode` usa JSON existente (`Session.data.pos` e `Order.data.pos`), sem coluna nova. O snapshot selado da sessão fornece o modo durante os callbacks iniciais do pedido.

A migração `0063_cash_change_request_alert` e a Concierge `0064_concierge_alert_labels` foram conciliadas por `0065_merge_cash_change_concierge_alerts`, fixando a união das choices. Após integrar o PR #623, `0066_merge_pos_concierge_identity_alerts` concilia os dois ramos 0065 e preserva também o alerta de identidade Concierge. Migrações anteriores preservadas. Rollback deve reverter código sem apagar eventos de caixa, alertas ou histórico de pagamento.

Referência fiscal: [Integridade da entrega fiscal](execution/pos-20260912/fiscal-delivery-integrity.md).

## Iteração final: identidade e cadastro ao validar o pedido

Uma única janela de 360 px reúne CPF e e-mail. Dados novos oferecem cadastrar e vincular; um titular oferece vínculo; dois titulares oferecem escolher um. Se já existe cliente no pedido, dados novos oferecem salvar no cadastro, sem copiar os dados pertencentes a terceiros. A opção final usa os dados somente no pedido. Os campos não exibem mais ofertas inline de salvar.

Botões secundários neutros ficam empilhados. 1/2/3 seguem a ordem visual; Tab/setas navegam; Enter aciona o botão focado; Esc volta sem aceitar. O foco inicial é no título para evitar aceitar com o Enter usado para abrir. Associação/criação exige confirmação. Troca de CPF mostra o anterior e o novo e confere o anterior sob lock no servidor.

A criação aceita CPF ou e-mail sem inventar nome; a interface mostra o identificador quando não há nome. Dados do documento permanecem separados da identidade do pedido. Respostas atrasadas não associam outro pedido. Retry de criação após resposta perdida encontra o cadastro já criado e pede vínculo explícito.

O backend conserva os campos legados do erro e acrescenta `conflicts`. Autorizações de uso avulso continuam vinculadas a dado, titular, cliente atual e identificação do pedido. Não há migração adicional para esta iteração.

Validação local: CPF da Ana + e-mail do Bruno exibiram ambos os titulares na mesma janela; antes, o Bruno não existia na fixture do preview. Criação usando apenas `bi.preview619@example.org` gerou um cadastro único com nome/sobrenome vazios e vínculo visível no pedido. Nenhuma emissão ou mensagem externa foi usada nesses testes.
