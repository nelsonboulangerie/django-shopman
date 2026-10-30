# Webhooks — códigos de status na falha de autenticação

Cada webhook é um contrato próprio com o gateway. Rejeição de credencial ausente ou inválida:

| Webhook | Arquivo | Falha de auth | Modelo |
|---|---|---|---|
| Efí (PIX) | [efi.py](../../shopman/shop/webhooks/efi.py) | **401 Unauthorized** | token compartilhado |
| iFood (eventos) | [ifood_events.py](../../shopman/shop/webhooks/ifood_events.py) | **401 Unauthorized** | assinatura HMAC (`X-IFood-Signature`) |
| Stripe (cartão) | [stripe.py](../../shopman/shop/webhooks/stripe.py) | **400 Bad Request** | assinatura HMAC |

- **401** é o código de "a autenticação falhou — credencial ausente/inválida", e é o que
  a [doc do iFood](https://developer.ifood.com.br/pt-BR/docs/guides/modules/events/webhook-signature/)
  exige para assinatura inválida (403, na semântica do iFood, é merchant sem autorização).
- O Stripe é legitimamente diferente: rejeita por falha de assinatura HMAC, e 400 é o
  correto para corpo/assinatura inválidos.

O iFood entra pelo polling (`ifood_poll`, caminho primário) e, opcionalmente, pelo push
assinado em `/api/webhooks/ifood/events/`. Não existe outra rota de webhook do iFood. Ver
[IFOOD-DIRECT-INTEGRATION-PLAN](../plans/IFOOD-DIRECT-INTEGRATION-PLAN.md).
