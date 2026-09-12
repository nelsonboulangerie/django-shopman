# Minuta de chamado iFood, ainda não enviada

Tipo: Incidente

Assunto: HTTP 403 HTML intermitente em Order durante teste de integração

Estamos testando a integração própria Nelson Boulangerie - Shopman para homologação Order/Events via polling. A aplicação usa OAuth centralizado e consulta a cada 30 segundos em um único worker DigitalOcean.

App de teste: NB Teste (C), clientId 662ff49d-64d0-47be-bee3-d405e577a810. Merchant de teste: f36a17d0-e10b-4fdd-a16d-c8ffd866e59b (Teste - Nelson Boulangerie, ID 2512433). OAuth e consulta de merchant respondem 200; a lista de merchants autorizados contém essa loja.

Em 12/09/2026, entre 22:06 e 23:38 UTC, observamos HTTP 403 com HTML Access Denied de forma intermitente em /order/v1.0/events:polling, consulta de detalhes do pedido, acknowledgment, cancellationReasons e requestCancellation. A mesma operação volta a funcionar sem alteração de credenciais, após retry.

Ensaio oficial gerado pelo Developer Portal: pedido c3c5c7a4-96e1-40f8-8148-d5cd50a3df73; evento PLC 261d28c3-2c92-4169-ae4c-32402b82738d. Às 23:34:44 UTC recebemos PLC, mas os detalhes falharam 403. Às 23:35:16 o pedido foi persistido, mas ACK falhou 403. Às 23:35:47 a reentrega foi deduplicada e ACK aceito. requestCancellation teve falha 403 e sucesso em retry às 23:38:04; CAN foi processado às 23:38:17.

Solicitamos diagnóstico do bloqueio intermitente de borda/origem e orientação sobre endpoint e cabeçalhos oficiais. A resposta difere do JSON forbidden citado no FAQ; não houve ampliação de merchants nem remoção do filtro x-polling-merchants. Não estamos solicitando exceção às regras de segurança, apenas a configuração correta para acesso autorizado.

A tentativa oficial de homologação ainda não foi iniciada. Podemos fornecer request IDs de novas ocorrências por este chamado. Não anexamos access token, client secret, Authorization ou dados de clientes reais.
