# Webhook falhando

## Sintoma visivel

Pagamento, marketplace ou notificacao externa nao muda o pedido; alertas
`webhook_failed` aparecem no admin; gateway reenvia eventos.

## Impacto

Cliente pode pagar sem receber confirmacao, operador perde confianca na fila e
eventos duplicados podem se acumular.

## Onde cada comando age

Os webhooks chegam em `api.boulangerie.com.br/api/webhooks/…`, servidos pelo
componente `web-operator` do app vivo `shopman-nelson`; o iFood tambem passa pelo
`ifood-poll-worker`. Os alvos `make deploy-*`, `make diagnose-*` e
`make smoke-gateways` sao **locais** (docker e `.env` desta maquina);
`make diagnose-webhooks target=1` imprime o equivalente no vivo sem executar.

## Diagnostico (leitura, qualquer agente)

```bash
curl -s https://api.boulangerie.com.br/health/ready/
doctl --context shopman-do-app-admin apps logs 40b86e35-bafe-4a1a-a1b0-e124d3d9fd0f web-operator --type run --tail 500 | grep -i webhook
doctl --context shopman-do-app-admin apps logs 40b86e35-bafe-4a1a-a1b0-e124d3d9fd0f ifood-poll-worker --type run --tail 200
DJANGO_DEBUG=true DATABASE_URL='<conexao direta 25060>' make diagnose-webhooks
```

A ultima linha roda nesta maquina, so leitura, contra o banco vivo pela
**conexao direta** (porta `25060`), nunca pelo pool `25061`. Verifique `failed
webhook keys`, `stale webhook keys` e alertas ativos. Nao use payload de cliente
como evidencia principal; use `scope`, `id`, `order_ref`, provider e horario.
`make smoke-gateways` (local) ajuda a separar falha do contrato do codigo de
credencial ou sandbox externo ainda bloqueado.

## Acao imediata segura

1. Nao marcar pedido como pago manualmente sem checar o gateway.
2. Se o gateway mostra pagamento confirmado, rode a reconciliacao em dry-run
   **dentro do app vivo** (leitura):

```bash
doctl --context shopman-do-app-admin apps console 40b86e35-bafe-4a1a-a1b0-e124d3d9fd0f web-operator
python manage.py reconcile_payments --since=4h --dry-run
```

3. Rodar sem `--dry-run` muda pedidos no vivo: so com a palavra do incident
   commander (Pablo) dada no momento, e depois de o dry-run apontar a acao
   correta.

## Recuperacao

- Token/secret ausente ou errado (`make production-readiness target=1
  context=shopman-do-app-admin` aponta): trocar segredo e do dono, no painel.
- Garantir o cache/eventstream ativos ([redis-fora](redis-fora.md)) se os eventos
  chegam mas a tela nao atualiza.
- Reenfileirar manualmente apenas depois de confirmar que a chave idempotente nao
  esta `in_progress` recente.

## Escalar

Escalar se houver `in_progress` com mais de 5 minutos, falha recorrente no mesmo
provider, divergencia financeira ou evento pago sem pedido correspondente.

## Evidencia minima

Horario, provider, `scope`, id da chave idempotente, `order_ref`, status no
gateway, saida do diagnostico, trecho do `doctl apps logs` e decisao tomada.
