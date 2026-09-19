# Chamado iFood 33298264

Enviado em 12/09/2026 às 21:18 BRT com autorização de Pablo. Portal confirmou sucesso e status Em análise. Categoria API - Problema gerais; subcategoria Erros 403 - Forbidden. Conteúdo enviado abaixo.

Tipo: Incidente

Assunto: HTTP 403 HTML intermitente em Order durante teste de integração

Estamos testando a integração própria Nelson Boulangerie - Shopman para homologação Order/Events via polling. A aplicação usa OAuth centralizado e consulta a cada 30 segundos em um único worker DigitalOcean.

App de teste: NB Teste (C), clientId 662ff49d-64d0-47be-bee3-d405e577a810. Merchant de teste: f36a17d0-e10b-4fdd-a16d-c8ffd866e59b (Teste - Nelson Boulangerie, ID 2512433). OAuth e consulta de merchant respondem 200; a lista de merchants autorizados contém essa loja.

Em 12/09/2026, entre 22:06 e 23:38 UTC, observamos HTTP 403 com HTML Access Denied de forma intermitente em /order/v1.0/events:polling, consulta de detalhes do pedido, acknowledgment, cancellationReasons e requestCancellation. A mesma operação volta a funcionar sem alteração de credenciais, após retry.

Ensaio oficial gerado pelo Developer Portal: pedido c3c5c7a4-96e1-40f8-8148-d5cd50a3df73; evento PLC 261d28c3-2c92-4169-ae4c-32402b82738d. Às 23:34:44 UTC recebemos PLC, mas os detalhes falharam 403. Às 23:35:16 o pedido foi persistido, mas ACK falhou 403. Às 23:35:47 a reentrega foi deduplicada e ACK aceito. requestCancellation teve falha 403 e sucesso em retry às 23:38:04; CAN foi processado às 23:38:17.

Solicitamos diagnóstico do bloqueio intermitente de borda/origem e orientação sobre endpoint e cabeçalhos oficiais. A resposta difere do JSON forbidden citado no FAQ; não houve ampliação de merchants nem remoção do filtro x-polling-merchants. Não estamos solicitando exceção às regras de segurança, apenas a configuração correta para acesso autorizado.

A tentativa oficial de homologação ainda não foi iniciada. Podemos fornecer request IDs de novas ocorrências por este chamado. Não anexamos access token, client secret, Authorization ou dados de clientes reais.

---

## Medição de 19/09/2026 — a resposta do suporte não explica o que acontece

O suporte respondeu que o erro é "Token sem permissão", pedindo para conferir se
o merchant revogou o acesso e para **gerar um token novo**, porque o atual pode
ter sido criado antes da aprovação. A medição abaixo refuta essa hipótese.

### O que foi medido

Log do `ifood-poll-worker` publicado, uma hora corrida de 19/09/2026 (09:41 a
09:58 UTC), lido com `doctl apps logs`:

| Grandeza | Valor |
|---|---|
| Consultas de polling | 36 |
| Recusas `HTTP 403` | 15 (42%) |
| Respostas boas (`204`) | 21 |
| Renovações de token no período | **1** (na subida do worker, 09:41:46) |

As recusas e os sucessos são **intercalados**, não sequenciais: 09:42:16 `204`,
09:42:46 `204`, 09:43:16 `403`, 09:43:46 `204`, 09:44:16 `403`. Todos com o
mesmo token.

Em paralelo, do IP local (fora da DigitalOcean), com o mesmo `clientId`, o mesmo
merchant e um token novo: **24 de 24 consultas responderam `204`** — 12 em
`/order/v1.0/events:polling` e 12 em `/events/v1.0/events:polling`. As duas
rotas se comportam igual.

### O que a medição permite concluir

1. **Não é permissão do token.** Um token sem escopo não devolve `204` às 09:42
   e `403` às 09:43. O mesmo token foi aceito 21 vezes e recusado 15.
2. **Não é revogação do merchant.** A revogação seria permanente, não sorteada.
3. **Não é a rota.** As duas rotas de polling se comportam igual do IP limpo.
4. **Não é o User-Agent.** O mesmo User-Agent passa do IP local e é recusado da
   DigitalOcean.
5. **É recusa de borda, por origem da conexão.** O corpo da recusa é a página
   HTML `Access Denied` do edge, não o JSON de erro da API do iFood — quem
   recusa é o edge, antes da origem. O app na DigitalOcean não tem IP de saída
   dedicado (conferido na spec: sem `egress`), então sai por um conjunto
   compartilhado de NAT; a taxa de ~42% é compatível com parte desses IPs estar
   recusada e o sorteio acontecer por requisição.

### Por que o chamado ficou sem a prova

A página do Akamai traz um `Reference #`, que é o identificador com que o
suporte do iFood encontra a regra que bloqueou e o IP que eles viram. Duas
camadas nossas apagavam esse dado antes de ele chegar ao log:

- o log cortava a resposta em 200 caracteres — e o corte caía no meio da URL,
  **antes** da linha da referência;
- o que sobrasse ainda passaria pelo redator de telemetria, que lê o timestamp
  Unix da referência como corrida de dez dígitos e o troca por `[phone]`.

Ambas foram corrigidas. A referência agora chega inteira ao log, ao lado do
status e dos cabeçalhos de rastreio.

### O que já foi feito do nosso lado

O polling e o reconhecimento passaram a retentar a recusa de edge com backoff
(`shopman/shop/services/ifood_http.py`). Com ~58% de sucesso por tentativa, três
tentativas levam a falha de 42% para ~7%. Isso torna a integração utilizável,
**mas é contorno, não conserto**: a recusa continua existindo do lado do iFood.

### O que ainda depende do iFood

Com as referências em mãos, o chamado 33298264 pode ser respondido pedindo:

1. a regra de borda que recusa as requisições vindas da DigitalOcean, a partir
   das referências que enviarmos;
2. a confirmação do IP de origem que eles registram nessas recusas;
3. se existe faixa de IP que precise ser liberada para integração própria.

Decisão que depende do Pablo: contratar IP de saída dedicado na DigitalOcean
daria uma origem estável para o iFood liberar, e eliminaria o sorteio — é custo
novo no app, e por isso não foi contratado.
