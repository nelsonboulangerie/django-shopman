# Incidente 14/10/2026: pool de banco esgotado no alpha

> Resumo para quem continua o trabalho. Leia antes de mexer em `web-operator`,
> `web-storefront`, SSE, sondas de saúde ou no spec da DigitalOcean.

## O que aconteceu

- **15:06 UTC:** o `web-operator` (PDV, Cozinha, Gestor, Admin) esgotou o pool de
  conexões com o banco. Todo request esperava 10 s e caía com
  `OperationalError: couldn't get a connection after 10.00 sec`. A loja online
  (`web-storefront`) seguiu respondendo.
- **15:38 UTC:** a coordenação reiniciou só o `web-operator` (com a palavra do dono).
  Voltou em ~3 min. Fora do ar: ~32 min.
- **Não era a primeira vez:** o Sentry mostra o mesmo erro em 11/10 ~13:09 UTC e, ~3
  dias antes, no `web-storefront` (issues SHOPMAN-N, P, R, S, T, V).
- O login `admin/admin` não existe no alpha (usuário técnico desativado). O dono
  entra com o usuário dele.

## Causa (provada em bancada, #1778)

Não era o SSE. Sob ASGI, quando o cliente desiste no meio do request (aba fechada,
troca de página, o BFF abortando), o Django dispara `request_finished`, mas a thread
do request continua e abre a conexão **depois** disso. Ninguém a fecha. Com o pool
psycopg (#1632, 10/10), cada uma é vaga perdida para sempre; algumas dezenas de
requests abortados param o processo. Os dois serviços Django rodam a mesma imagem e
tinham o mesmo defeito.

## O que mudou (tudo no `main` e no alpha)

| PR | O quê |
|---|---|
| #1778 | `shopman/shop/orphan_connections.py`: no início de cada request, devolve ao pool as conexões cuja thread dona já morreu (custo ~2 µs por request, zero consulta). |
| #1779 | Referência forte no registro de donos (o GC levava a órfã sem devolver); liveness `/health/live/` falha só quando o pool não entrega conexão há ≥ 30 s **e** o banco responde por conexão direta (banco fora não reinicia em loop); SSE com vida máxima de 30 min e teto de 12 streams por sessão (429 no excedente); listener sai junto quando o cliente fecha. Envs no `.env.example`, runbook atualizado. |
| #1713 (aplicado pelo painel, 14/10 ~16h UTC) | readiness `/health/database/` e `SHOPMAN_ACCESS_LOG=true` nos dois serviços Django. Spec vivo e arquivo batem (só sobra `MACHINE_COMPANY_NAME`, de outra frente). |

Conferido no alpha às 18:50 UTC, depois do deploy do #1779: `/ready/`, `/health/live/`
e `/health/database/` em 200; Admin em 0,35 s; nenhum `PoolTimeout` no log.

## O que observar no log (`doctl ... apps logs ... --type run`)

- `db_connection_orphan_reclaimed`: algumas por hora é normal.
- `liveness_pool_stuck_restart` (ERROR): a sonda pediu reinício; deve vir seguido de
  reinício no painel. `liveness_pool_stuck_but_database_down`: ninguém reinicia, de
  propósito.
- `sse_stream_refused reason=per_session_cap`: não deve aparecer em uso normal.
- Se `PoolTimeout` voltar **sem** `orphan_reclaimed` antes, é outro vazamento (thread
  viva segurando conexão); a liveness reinicia sozinha em ~2 a 2,5 min.

## O que isso abriu

- [`docs/plans/WP-WATCHMAN.md`](../plans/WP-WATCHMAN.md) e o
  [adendo 1](../plans/WP-WATCHMAN-ADENDO-1.md): o dono não terá webmaster; o sistema
  tem de se curar sozinho, sem custo de desempenho, com verificação externa, alerta
  por taxa, aviso que se repete e destino `ti@`. A WP generaliza o mecanismo do #1779.
- Regra que ficou: mudança no spec vivo da DigitalOcean vai pelo painel, no Chrome do
  dono, com a palavra dele; terminal escrevendo no vivo é barrado.
