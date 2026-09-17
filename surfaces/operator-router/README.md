# operator-router

Launcher + roteador por `Host` dos contêineres de grupo de apps de operador
([ADR-030](../../docs/decisions/adr-030-operator-nuxt-dois-servicos.md)). Node puro, zero
dependências.

| Grupo (`OPERATOR_GROUP`) | Apps (id → surface) |
|---|---|
| `operator-floor` | `pos`, `kds`, `orders`, `production`, `hub` |
| `operator-office` | `marketing`, `bi`, `purchase` |

A lista vive em [`groups.json`](groups.json) e é a mesma que o `deploy-images.yml` lê.

## Variáveis

| Chave | De quem | O que faz |
|---|---|---|
| `OPERATOR_GROUP` | roteador | grupo do contêiner (a imagem já traz) |
| `OPERATOR_HOSTS` | roteador | `app=host,app=host`; todo app precisa de ≥ 1 host |
| `<APP>__<CHAVE>` | só o app `<APP>` | chega a ele como `<CHAVE>` (ex.: `POS__NUXT_PUBLIC_ORDERS_URL`) |
| qualquer outra | todos os apps do grupo | inclui as envs do nível do app na DO |
| `PORT`, `HOST` | roteador | onde o roteador escuta; os filhos recebem porta própria em 127.0.0.1 |
| `OPERATOR_CHILD_PORT_BASE` | roteador | filhos em base+1…base+N (default 3100) |
| `OPERATOR_HEALTH_CACHE_MS` / `_TIMEOUT_MS` | roteador | cache (2 s) e timeout (2 s) da sonda agregada |
| `OPERATOR_SHUTDOWN_DRAIN_DELAY_MS` / `_GRACE_MS` / `_CHILD_KILL_MS` | roteador | 3 s / 15 s / 5 s |
| `OPERATOR_RESTART_BASE_MS` / `_MAX_MS` / `_STABLE_MS` | roteador | backoff 0,5 s → 30 s; zera após 60 s de pé |

`<APP>` é o id em maiúsculas. Prefixo de app de outro grupo, prefixo desconhecido em
chave `NUXT_`/`NITRO_`/`NODE_` e `<APP>__PORT`/`HOST` saem com código 78 e o motivo no log.

## Saúde

Pedido com `Host` que não é de app (a sonda da plataforma):

- `GET /health/live` → 200 só se todos os filhos estão de pé e o `/health/live` de cada um
  responde 200 **em JSON**;
- `GET /health/ready` → o mesmo, com o `readyPath` do app (Marketing: `/health/ready`).
  Serve diagnóstico; os probes da plataforma usam só `/health/live` (P1).

O corpo diz qual app falhou. No hostname de um app, os mesmos caminhos são do app.

## Rodar

```bash
npm test                                   # node --test, sem instalar nada
OPERATOR_GROUP=operator-office \
OPERATOR_APPS_DIR=../ \
OPERATOR_HOSTS=marketing=mkt.localhost,bi=bi.localhost,purchase=compras.localhost \
PORT=3000 node src/main.mjs                # com os .output/ já construídos
```

Log: uma linha JSON por evento (`boot`, `child_up`, `child_exit`, `group_unhealthy`,
`shutdown_*`); a saída dos Nitro sai prefixada com `[app]`.
