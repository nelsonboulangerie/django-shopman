# Directive worker parado

## Sintoma visivel

Pedidos entram, mas notificacao, fulfillment, estoque, loyalty ou timeouts nao
avancam. `Directive` fica `queued`, `running` antigo ou `failed`.

## Impacto

O pedido pode estar salvo e pago, mas a operacao ao redor nao acontece.

## Onde cada comando age

O incidente acontece no app vivo `shopman-nelson` (componente `directive-worker`
do spec). Os alvos `make deploy-*` e `make diagnose-*` sao **locais**: falam com o
docker e o `.env` desta maquina, nao com a DigitalOcean. `make deploy-up` no meio
do incidente nao reinicia o worker vivo. Para ver o comando do vivo sem executar
nada, acrescente `target=1` (por exemplo `make diagnose-worker target=1`).

## Diagnostico (leitura, qualquer agente)

```bash
curl -s https://api.boulangerie.com.br/health/ready/
doctl --context shopman-do-app-admin apps logs 40b86e35-bafe-4a1a-a1b0-e124d3d9fd0f directive-worker --type run --tail 200
doctl --context shopman-do-app-admin apps logs 40b86e35-bafe-4a1a-a1b0-e124d3d9fd0f directive-worker --type run_restarted --tail 200
doctl --context shopman-do-app-admin apps get 40b86e35-bafe-4a1a-a1b0-e124d3d9fd0f
```

No `/health/ready/`, `checks.queue` em `fail` com `queue_lag` diz que a fila
envelheceu sem consumo. O log diz se o worker morreu, reinicia em laco ou trava
num handler. O sintoma `relation "orderman_directive" does not exist` e o
`search_path` grudado no pool depois de um `pg_dump` pela porta `25061`: veja o
CLAUDE.md e [o incidente do pool](incidente-2026-10-14-pool-de-banco.md).

Para o diagnostico completo (`ready backlog`, `stuck running`, `failed
directives`), rode o script desta maquina contra o banco vivo, so leitura, pela
**conexao direta** (porta `25060`, banco `shopman`), nunca pelo pool `25061`:

```bash
DJANGO_DEBUG=true DATABASE_URL='<conexao direta 25060>' make diagnose-worker
```

## Acao imediata segura

1. Nao editar payload de directive manualmente.
2. Reiniciar o `directive-worker` vivo **muda o ambiente**: quem age e o incident
   commander (Pablo), ou um agente com a palavra dele dada no momento para este
   restart. Pelo painel: App Platform → `shopman-nelson` → `directive-worker` →
   Actions → Restart. Por linha de comando, o equivalente:

```bash
doctl --context shopman-do-app-admin apps restart 40b86e35-bafe-4a1a-a1b0-e124d3d9fd0f --components directive-worker
```

3. Ao subir, o reaper canonico reseta para retry as diretivas `running` antigas
   quando seguro. Se o worker reinicia em laco, nao reinicie de novo: leia o log
   e escale.

## Recuperacao

Depois do worker ativo, repita o diagnostico e confira pagamentos:

```bash
curl -s https://api.boulangerie.com.br/health/ready/
DJANGO_DEBUG=true DATABASE_URL='<conexao direta 25060>' make diagnose-worker
DJANGO_DEBUG=true DATABASE_URL='<conexao direta 25060>' make diagnose-payments
```

Se uma directive segue `failed`, tratar pelo tema do topico: pagamento,
notificacao, estoque ou fulfillment.

## Escalar

Escalar se a mesma directive falha ate `MAX_ATTEMPTS`, se `handler_not_found`
aparece, ou se existe backlog crescendo com worker ativo.

## Evidencia minima

IDs das directives, topicos, attempts, error_code, idade, saida do diagnostico,
trecho do `doctl apps logs`, quem autorizou o restart e horario da retomada.
