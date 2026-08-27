# NOTIFICATION-ROBUSTNESS-PLAN

## Estado atual

- O storefront registra "Me avise" em `StockAlertSubscription` via `POST /api/v1/availability/<sku>/notify/`.
- O gatilho `stock_back` roda em `post_save` de `stockman.Move`; quando o SKU fica compravel, `notify_back_in_stock()` envia `stock_arrived`.
- O gatilho `production_ready` roda em `production_changed(action="finished")` e envia `production_ready`.
- O envio passa por `shopman.shop.notifications.notify`, com backend resolvido por `ChannelConfig` e fallback para ManyChat.
- Em `DEBUG`, adapters externos ficam inertes salvo opt-in explicito; em staging/producao, o envio depende de `MANYCHAT_API_TOKEN`, resolver de subscriber e fluxo ManyChat publicado.

## Gap operacional imediato

O codigo ja sabe registrar e disparar o aviso, mas o lado ManyChat ainda precisa de um fluxo publicado que:

1. receba/atualize o contato com WhatsApp valido;
2. exponha campos customizados para `product_name`, `product_sku`, `product_image_url`, `available_qty` e `action_url`;
3. envie a mensagem `stock_arrived`/`production_ready` para o subscriber resolvido;
4. use o `action_url` do Shopman como CTA para o produto;
5. trate falha de subscriber inexistente ou fora da janela de conversa como erro observavel.

## Abordagem robusta proposta

1. Criar um `NotificationDelivery` persistente para cada tentativa, com `event`, `recipient`, `backend`, payload renderizado, status, erro, provider id, timestamps e dedupe key.
2. Transformar `notify()` em outbox transacional: regra de negocio grava entrega pendente; worker processa retry/backoff; UI/admin mostra estado.
3. Separar `Subscription` de `Delivery`: uma assinatura pode gerar zero ou mais tentativas, sem perder auditoria quando o provider falha.
4. Normalizar identidade de canal: guardar `customer_ref`, telefone E.164 e `manychat_subscriber_id` quando conhecido; resolver subscriber antes do envio, mas cachear com validade.
5. Dar contrato explicito para templates por canal: variaveis obrigatorias, fallback por canal e teste que renderiza todas as mensagens sem placeholder cru.
6. Implementar teste de staging para `Me avise`: criar assinatura, simular reposicao, processar worker e exigir uma entrega `sent` ou uma falha classificada.
7. Adicionar painel operacional: fila pendente, ultimas falhas, reenviar, cancelar assinatura e remover contato por LGPD.

## Primeiro marco

Fechar o fluxo ManyChat de `stock_arrived` para alpha:

- configurar campos customizados no ManyChat;
- validar `MANYCHAT_API_TOKEN`;
- validar o resolver `MANYCHAT_SUBSCRIBER_RESOLVER`;
- cadastrar uma assinatura real de teste;
- repor estoque do SKU;
- confirmar que `notified_at` so e marcado apos sucesso.
