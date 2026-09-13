# iFood FOOD: critérios complementares e ensaio publicado

## Situação de homologação

Nenhuma tentativa oficial foi iniciada. A documentação FOOD classifica negociação e descontos entre os critérios funcionais; código de retirada e documento fiscal se aplicam quando fornecidos. O teste local demonstra integração interna, mas não substitui o ensaio oficial de Order/Events.

Fontes consultadas em 12/09/2026 BRT:

- [Critérios Order FOOD](https://developer.ifood.com.br/en-US/docs/food/guides/modules/order/homologation)
- [Negociação FOOD](https://developer.ifood.com.br/en-US/docs/food/guides/modules/order/handshake-platform)
- [Detalhes de pedido](https://developer.ifood.com.br/en-US/docs/guides/modules/order/details)

Há diferenças entre exemplos históricos e a referência atual. HSS aceita settlement ID do evento quando metadata.id está ausente; disputeId continua obrigatório. ALTERNATIVE_REPLIED é intermediário e não encerra uma negociação nem reabre uma decisão final. Nenhuma ação financeira é inferida pelo vencimento do prazo.

## Ensaio real após o primeiro pacote

PR #633 integrado em main `d85c9e241ba4b1436e243ebe7e67ae28f5226809`. Deployment DigitalOcean `77f643ef-5da5-4152-ae6a-9458006b8f04` ACTIVE em 13/09 às 00:53:27 UTC; hashes de ifood_events.py, ifood_callbacks.py e projeção financeira conferidos dentro do worker, iguais à revisão testada. Domínio menu.nelsonboulangerie.com.br e Gestor responderam 200.

Novo pedido oficial de teste `8d35bd57-3905-40c4-8f3d-96cb6bc859ae`, referência local **IFOOD-260912-N26**, is_test confirmado. Ingestão registrada às 00:55:35 UTC. Gestor apresentou pagamento online R$ 27,00, dividido entre Visa R$ 17,00 e Master R$ 10,00.

Recusa solicitada pelo Gestor às 00:57:08 UTC com motivo oficial Problemas de sistema na loja. Estado permaneceu NEW, com aviso pendente e aceite bloqueado. Directive 20930 concluída em uma tentativa; estado da solicitação sent. Só após CAN, às 00:57:37 UTC, o pedido virou cancelled e a solicitação confirmed, com marcador ifood_cancelled. Não houve aceite, preparo, despacho ou conclusão, nem cobrança local.

Esse resultado comprova a correção de cancelamento antecipado. Não comprova que a causa dos 403 intermitentes foi resolvida; chamado técnico **33298264** continua sendo a referência de suporte.

## Correções desta etapa

- Descontos preservam destino, valor e patrocinadores; a projeção mostra participação iFood/loja/terceiro ou ausência explícita de informação. Totais e pagamentos não são recalculados.
- Código de retirada aparece na operação, preservando zeros iniciais.
- Documento nacional explicitamente fornecido no pedido alimenta fiscal.tax_id. Documento estrangeiro não vira CPF/CNPJ; documento ausente não solicita nota. Validação nacional existente permanece na borda fiscal. Nenhuma nota real foi emitida no ensaio.
- HSD/HSS são persistidos com receipt idempotente antes do ACK. Negociações abertas continuam visíveis após conclusão do pedido.
- Operador escolhe aceitar/rejeitar, motivo e confirmação explícita da consequência. Identidade, permissão, revisão e chave de intenção são verificadas no servidor. Resposta é enfileirada; envio incerto não é repetido automaticamente. HSS registra resolução, CAN continua autoridade de cancelamento.
- Evidências registradas do próprio pedido podem ser consultadas pelo servidor no endpoint oficial, com autenticação apenas no backend, sem redirecionamentos, limite de 10 MiB e formatos raster/PDF. Downloads usam attachment, nosniff e no-store.
- A notificação final de recusa remota só é emitida após CAN; o fluxo local legado preserva sua deduplicação.

## Limites explícitos

Contrapropostas de reembolso, benefício ou tempo adicional são indicadas ao operador, mas este formulário implementa apenas aceite/rejeição. Motivos válidos são os documentados e os recebidos no evento; diferenças entre referências não justificam enviar enums inventados.

O ambiente compartilhado continua sem isolamento automático por is_test. Portanto, aceite/preparo/expedição/fiscal/fidelidade completos foram exercitados em banco isolado com fronteiras externas locais. Ainda faltam a comprovação desses cenários contra o ambiente oficial, a estabilização da conectividade e a aprovação do wizard. Não afirmar prontidão completa com base apenas no CI.

## Validação local

- Suíte iFood/API/contratos final: 455 testes e 8 subtests aprovados.
- make admin: checker canônico e 270 testes aprovados.
- Orders frontend: 318 testes; verificações posteriores do componente 26 testes e typecheck aprovado.
- Proxy: 13 testes, incluindo upstream HTTP → ofetch → H3 → cliente com bytes PNG idênticos e cabeçalhos de download preservados.
- Navegador: 375px e 1280px aprovados, sem rolagem horizontal; screenshots conferidas.
- Ruff e diff --check sem erros. Nenhuma migração, credencial ou alteração global de política fiscal.
