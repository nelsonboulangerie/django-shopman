# MKT-051 — gate de publicação do canário Alpha

**Estado:** autorizado; aguardando CI e backup fresco antes do deploy

**Autorização humana:** em 2026-09-10, o proprietário do ambiente respondeu
“Sim confirmo! Pode publicar!” à proposta contextual completa do canário Alpha.

## Escopo autorizado

- app: `shopman-alpha` (`40b86e35-bafe-4a1a-a1b0-e124d3d9fd0f`);
- superfícies: `web` e `marketing-nuxt`; nenhum outro componente será publicado;
- código funcional aprovado: `6375642bf4242ef7ee5f05ad6dc9a2bae59ec5e4`, acrescido apenas
  dos registros do gate e das correções exigidas pela própria CI antes do build;
- janela: 2026-09-10, 21:20–22:30, `America/Sao_Paulo`;
- ação: push da branch isolada, PR, CI bloqueante e `Deploy Images` manual na mesma
  branch com `components=web,marketing-nuxt`;
- banco: `shopman-staging-postgres`, PostgreSQL 16 gerenciado;
- efeito de Marketing: zero destinatários, zero mensagens, zero publicações públicas.

## Condições de entrada e failsafe

O deploy só pode começar se o PR estiver verde, não houver outro deployment ativo e
existir backup automático posterior a `2026-09-11T00:13:00Z`. O gate local de migrations
passou em banco vazio e preserva as folhas paralelas por migrations de merge. Qualquer
falha de CI, backup ausente, deployment concorrente, migration reprovada ou correlação
de digest incerta resulta em `no-go` sem tentativa de contorno.

O primeiro run do PR #597 foi bloqueado pelo gate de “meia-correção”: duas degradações
registravam exceções somente em `DEBUG`, uma ao consultar o flow ManyChat e outra ao
derivar o tipo de alerta de estoque. Ambas passaram a emitir `WARNING` seguro, sem PII;
o checker dirigido e 69 testes de ManyChat/campanha/alerta passaram antes do novo push.

O segundo run encontrou seis violações mecânicas do `ruff` e revelou no gate CSP que
`CustomerInsight` declarava um `GinIndex` sem instalar `django.contrib.postgres`. Os
imports e comprehensions foram normalizados, e a app PostgreSQL foi registrada tanto
no runtime integrado quanto no settings isolado do Guestman. `ruff check .`, os dois
system checks e `makemigrations --check --dry-run` passaram localmente antes do push.

`SHOPMAN_MARKETING_OUTBOX_CONSUMER_ENABLED` e
`SHOPMAN_MARKETING_DELIVERY_CONSUMER_ENABLED` permanecem ausentes e `false` por default;
o app não possui worker de entrega Marketing. `SHOPMAN_MARKETING_TEST_TARGETS_JSON`
permanece ausente, os adapters do ledger permanecem vazios e a assistência de IA fica
desligada. Consentimento, autorização, CSRF, redaction, unicidade e freeze não são
afrouxados.

## Smoke e decisão

Depois da correlação dos digests com o deployment, o executor verifica
`/ready/`, `/health/live`, `/health/ready`, login, Projection e diagnóstico agregado sem
PII/provider. O canário recebe `go` somente com HTTP 200, migrations concluídas, zero
alerta crítico, zero efeito externo e nenhuma regressão P0. O proprietário acompanha
esta tarefa como Release Manager/on-call; o executor monitora e interrompe ao primeiro
critério de abort.

## Rollback autorizado para este canário

Antes da publicação serão reconfirmados e preservados os digests atuais. A referência
inicial é o par imutável de `origin/main`:

- `web-02727dfb4c10601123e9ec5c68c26c755c404748` —
  `sha256:9537fbab00bafa9f2e332c00810726b7ebf098082545e57b4cfd8342e7b76e34`;
- `marketing-02727dfb4c10601123e9ec5c68c26c755c404748` —
  `sha256:cea9e73f646b02b68538db83653dcaa669e6bad4d7a891c9f66c4d135f7fcb38`.

Rollback congela qualquer avanço, mantém consumers desligados e retagia esses dois
artefatos, sem apagar receipts, filas, targets ou migrations aditivas. Reativação exige
novo gate; nenhum envio real faz parte desta autorização.
