# Redis fora ou SSE sem fanout

## Sintoma visivel

Painel nao atualiza em tempo real, rate limit nao e compartilhado entre
processos, ou `/health/ready/` do app vivo aponta `cache` em `fail`.

## Impacto

Operador pode trabalhar com tela stale; webhooks e pedidos podem estar corretos
no banco, mas invisiveis ate refresh manual.

## Onde cada comando age

O cache do app vivo e o cluster Valkey `cache` do spec (`shopman-staging-cache`).
Os alvos `make deploy-*` e `make diagnose-*` sao **locais**: medem o Redis do
`.env` desta maquina, nao o Valkey vivo, e `make deploy-up` sobe o docker local.
`make diagnose-runtime target=1` imprime o equivalente no vivo sem executar.

## Diagnostico (leitura, qualquer agente)

```bash
curl -s https://api.boulangerie.com.br/health/ready/
doctl --context shopman-do-app-admin apps logs 40b86e35-bafe-4a1a-a1b0-e124d3d9fd0f web-operator --type run --tail 200
doctl --context shopman-do-app-admin databases list --format Name,Engine,Status
```

Confirme `cache` no `/health/ready/` e o estado do cluster `shopman-staging-cache`
na lista de bancos (`online`). No log, procure erro de conexao com o Redis/Valkey
e falha do eventstream. Em producao, `LocMemCache` nao e aceitavel.

## Acao imediata segura

1. Pedir refresh manual da tela operacional enquanto o cache volta.
2. Nao reiniciar banco para resolver problema de cache.
3. Se o Valkey esta `online` e o app segue sem cache, reiniciar os componentes
   web **muda o ambiente**: quem age e o incident commander (Pablo), ou um agente
   com a palavra dele dada no momento. Pelo painel: App Platform →
   `shopman-nelson` → componente → Actions → Restart. Equivalente:

```bash
doctl --context shopman-do-app-admin apps restart 40b86e35-bafe-4a1a-a1b0-e124d3d9fd0f --components web-operator,web-storefront
```

4. Se o cluster Valkey esta fora, a acao e no painel da DO (cluster → status) ou
   chamado ao suporte: e conta do dono.

## Recuperacao

Quando `/health/ready/` voltar com `cache` `ok`, conferir backlog e pagamentos
(so leitura, conexao direta `25060`, nunca o pool `25061`):

```bash
DJANGO_DEBUG=true DATABASE_URL='<conexao direta 25060>' make diagnose-worker
DJANGO_DEBUG=true DATABASE_URL='<conexao direta 25060>' make diagnose-payments
```

## Escalar

Escalar se o Valkey esta acessivel mas o componente nao tem `REDIS_URL`
(`${cache.REDIS_URL}` no spec; e dele que sai o `EVENTSTREAM_REDIS`), se o
cache falha repetidamente, ou se a UI segue stale com o cache OK.

## Evidencia minima

Horario, saida do `/health/ready/`, estado do cluster, trecho do `doctl apps
logs`, impacto observado na tela, acao feita e quem a autorizou.
