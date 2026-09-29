# R8 — pré-flight somente leitura do cutover comercial

- `auditoria_id`: `R8-C0-C2-2026-09-29`
- `janela_observada`: `2026-09-29T04:37:38Z`–`2026-09-29T04:45:00Z`
- `baseline_git`: `ab148fbd85d50865bf107e95298b712decd9d7f4`
- `ambiente_observado`: app DigitalOcean `shopman-nelson`
- `modo`: somente leitura no ambiente vivo; fixtures apenas em banco local
  descartável/rollback transacional
- `decisão técnica`: **NO-GO — BLOCKED HUMAN GATE**

Esta auditoria executou somente C0, C1 e a parte segura de C2 do
[WP de cutover comercial](../plans/WP-COMMERCIAL-GO-LIVE-CUTOVER-2026-09-28.md).
Ela não alterou spec, credencial, 2FA, DNS, tag, banco, deployment ou provider;
não criou pedido, promoção, envio, corrida, cobrança, estorno ou documento
fiscal.

`GO` abaixo vale apenas para a linha aferida. Não é autorização de cutover.
Ausência de prova é `UNKNOWN`; configuração incompatível ou pré-condição
obrigatória ausente é `NO-GO`.

## C0 — comando e janela

| Entrada obrigatória | Estado | Evidência / lacuna |
|---|---|---|
| Data e janela de cutover | UNKNOWN | Nenhuma janela comercial assinada foi localizada. |
| Incident commander humano | UNKNOWN | A matriz canônica não registra nome/aceite contextual. |
| Escopo v1 fechado | NO-GO | iFood, ManyChat/Concierge, Machine, fiscal e Marketing continuam sem inclusão/exclusão assinada. |
| Canais incluídos/excluídos | UNKNOWN | Não há matriz de canais aprovada para a janela. |
| Teto financeiro dos canários | UNKNOWN | Nenhum valor ou owner foi registrado. |
| Telefones/emails de teste | UNKNOWN | Nenhum conjunto autorizado foi registrado; nenhum contato foi inferido de dados vivos. |
| Critérios de aborto | GO | O WP enumera 5xx crítico, divergência financeira/fiscal, worker parado, auth e corrupção de estoque; falta o aceite do incident commander. |
| Janela de rollback | UNKNOWN | O deployment anterior é identificável, mas a duração/owner da janela não foi assinada. |
| Comunicação interna | UNKNOWN | Canal, executor e observador não foram nomeados. |
| Política iFood | GO | Escrita/publicação permanece proibida sem autorização específica do diff remoto. |

O gate C0 não fecha: incident commander, janela, escopo, canais, tetos e contatos
de teste são decisões humanas inevitáveis.

## C1 — auditoria do ambiente vivo

| # | Critério | Estado | Evidência sanitizada |
|---:|---|---|---|
| 1 | SHA e tag candidata | GO | `origin/main` = `ab148fbd85d5`; tag remota `go-live-v1` ausente, portanto ADR-015 ainda inativa. |
| 2 | CI e merge queue | GO | Merge-group do SHA: Runtime, Surfaces, Omotenashi, Security, Production Contract e Operator Groups verdes; Coverage verde. GitHub tinha zero issue aberta com label `P0`, sem substituir triagem humana. |
| 3 | Imagens e digests | GO | [Deploy Images 36521413976](https://github.com/nelsonboulangerie/django-shopman/actions/runs/36521413976) publicou `web` `sha256:023988…43cda`, `operator-office` `sha256:b5e4d1…ff78b2` e `marketing` `sha256:4e7a97…dfac8`, todos para o SHA candidato. |
| 4 | Deployment ativo | GO | Deployment `02527053-d135-4bd3-9d32-d09dd367be19`, criado `04:25:44Z`, `ACTIVE` `04:31:54Z`, correlacionado ao digest `web`; predecessor `2353933b-73c7-4dff-b480-6d85ef533005` identificado. |
| 5 | Spec vivo sanitizado | NO-GO | `check_do_spec_drift.py` saiu `1`: há chaves somente no vivo que um `apps update --spec` apagaria, chaves somente no arquivo e valores divergentes. Nunca aplicar o spec versionado enquanto o drift não for composto a partir do vivo. |
| 6 | Componentes, release job e workers | NO-GO | Serviços e três workers têm uma instância e o deployment está ativo. Porém o `release` vivo executa `check --deploy`, `migrate`, `setup_groups`, `bootstrap_whatsapp_channel` e `efi_webhook --soft`, sem `migration_safety`; o último comando pode recadastrar webhook. |
| 7 | PostgreSQL, Redis/Valkey e migrations | UNKNOWN | `/ready/` retornou 200 com `database`, `cache`, `migrations` e `queue` = `ok`. O critério completo não fecha porque cluster, plano pendente e conexão direta não puderam ser inspecionados: API de databases respondeu 403. |
| 8 | Backup/PITR e último restore | UNKNOWN | `doctl databases list` respondeu 403 por falta de `database:read`. Não existe evidência datada de backup/PITR nem restore isolado. |
| 9 | Filas e backlog | UNKNOWN | `/ready/` informou `queue=ok`, mas backlog, retries e reinícios por worker não têm artefato datado nesta auditoria. |
| 10 | Flags mock/debug/autopilot | NO-GO | Vivo: `DJANGO_DEBUG=false`, porém `SHOPMAN_ENVIRONMENT=staging`, mock adapters permitidos, captura mock exposta e OTP de debug exposto. Auto-confirmação Pix e staging autopilot estão desligados. |
| 11 | Adapters | NO-GO | Pix seleciona `payment_mock`; Efí está em sandbox; cartão seleciona Stripe; fiscal seleciona Focus NFe, mas o ambiente Focus não está declarado no vivo e cai no default de homologação. Machine não está configurada. |
| 12 | Webhooks | UNKNOWN | Endpoints vivos: health Efí GET 200; Stripe/iFood recusam GET com 405 e aceitam POST. Segredos são declarados sem leitura de valores. Registro real, replay no provider e homologação externa não foram comprovados. |
| 13 | Operadores e 2FA | UNKNOWN | `SHOPMAN_ADMIN_REQUIRE_2FA` não está declarado no vivo; enrollment/recovery dos operadores e `check_admin_2fa_ready` no banco alvo não têm evidência. |
| 14 | Observabilidade | UNKNOWN | Sentry e email de alerta estão declarados; nenhum alerta sintético autorizado foi emitido/recebido. Health e ready estão verdes. |
| 15 | Domínios, TLS, cookies, CSRF e proxy | NO-GO | Certificados públicos válidos e Django com redirect HTTPS, trusted proto, proxy depth 2, cookie de operador `.boulangerie.com.br` e origens CSRF explícitas. A raiz de `gestor.boulangerie.com.br` respondeu sem HSTS, CSP, `X-Frame-Options` ou `Referrer-Policy`, diferente de `mkt.` e das superfícies Django. |
| 16 | Catálogo, estoque, preço e cupom | UNKNOWN | Smoke confirmou menu com produto/disponibilidade e checkout não mutante. Correção do catálogo/estoque/preço real, parâmetros fiscais e aprovação do owner não foram aferidas. Não foi comprovado um kill-switch global de cupons para a janela. |
| 17 | Presença de `go-live-v1` | GO | Tag ausente, exatamente como esperado antes do gate C7; não foi criada. |

### Drift que impede qualquer `apps update --spec`

O relatório sanitizado registrou como **somente no vivo** as chaves de
observação/privacidade do Concierge, `DOORMAN_MESSAGE_SENDER_CLASS`, flags de
delivery WhatsApp de Marketing e as três chaves de recibo de privacidade no
serviço `web`. Também há chaves de proxy BFF/VAPID somente no arquivo e valores
divergentes em Concierge e consumers de Marketing. Valores secretos não foram
lidos nem registrados.

Há ainda um risco operacional pré-existente: consumers de Marketing e flags de
publicação/delivery estão habilitados no vivo, WhatsApp está em modo `open` e o
canário de publicação está desligado. Esta auditoria não criou campanha,
promoção, público ou envio e não alterou essas flags.

## C2 — ensaio seguro

| Ensaio | Estado | Evidência |
|---|---|---|
| Full CI no SHA convergido | GO | Merge-group verde; `test-shop`, `test-backstage`, `test-storefront`, runtime PostgreSQL/Redis, E2E e Admin CSP concluíram com sucesso. |
| Production Contract hermético | GO | CI [run 36519134576](https://github.com/nelsonboulangerie/django-shopman/actions/runs/36519134576) verde; repetição local passou com credenciais sintéticas e socket externo bloqueado. |
| Migrations desde banco vazio | GO | `check_migrations.py --json`: 3 pass, 0 fail; grafo aplicado do zero e `migrate --check` limpo. Replay de baseline e regra pós-tag foram explicitamente skipped. |
| Migration safety no deployment vivo | NO-GO | O comando existe no spec versionado, mas não no `run_command` vivo do release job. |
| Restore rehearsal em cluster temporário | UNKNOWN | Não executado: o token atual não possui `database:read`; criar/forkar cluster exige escopo, custo e autorização. Teste local do cofre curado passou (`2 passed`), mas não substitui PITR Postgres. |
| Rollback de código | UNKNOWN | Deployment predecessor foi identificado, mas nenhum rollback/redeploy foi disparado ou ensaiado em app isolado. |
| Webhook duplicado/fora de ordem | GO | 7 fixtures herméticas de Stripe, Efí e iFood passaram, incluindo replay, disputa tardia e dupla contabilização. Nenhum provider foi chamado. |
| Reconciliação dry-run | GO | Teste prova que `reconcile_financial_day --dry-run` não persiste nem alerta; suíte de 2FA/readiness relacionada: `20 passed, 1 skipped`. Não foi rodado contra dados vivos. |
| Carga proporcional | UNKNOWN | Não executada contra o ambiente vivo: faltam janela/alvo aprovados e o teste geraria tráfego. O CI funcional verde não substitui carga. |
| Smoke de checkout sem cobrança | GO | [Pre-go-live Smoke 36521633479](https://github.com/nelsonboulangerie/django-shopman/actions/runs/36521633479) verde no SHA candidato; POST vazio termina 403 canônico e não cria pedido. |
| Indisponibilidade e fallback | UNKNOWN | Existem testes de contrato, porém falta exercício datado com aparelho, rede degradada e operação física. |

### `production-readiness` ainda não é estritamente read-only

O comando não possui `--read-only`. Ele chama o gateway smoke local, que usa
`get_or_create` e outras escritas dentro de uma transação marcada para rollback.
Isso é hermético para CI/local, mas não atende à exigência do WP de **zero
escrita no banco alvo**. Por isso o comando não foi executado contra o ambiente
vivo. Antes do corte, é necessário implementar/provar um modo de leitura pura
ou executar o perfil em clone descartável restaurado.

## Decisão e gate humano mínimo

Estado final: **NO-GO — BLOCKED HUMAN GATE**.

Antes de nova auditoria, são necessárias estas ações mínimas:

1. Owner nomeia incident commander e aprova janela, escopo v1 por integração,
   canais, teto dos canários, contatos de teste, comunicação e rollback.
2. Plataforma obtém evidência sanitizada de backup/PITR e autorização para um
   restore em cluster descartável usando conexão direta, nunca PgBouncer.
3. Owner autoriza a composição segura do spec vivo: preservar todas as
   `EV[...]`, remover affordances de staging/mock/debug, selecionar adapters e
   ambientes comerciais aprovados, corrigir o release job e revisar as flags de
   Marketing. É proibido aplicar o arquivo versionado sobre o vivo.
4. Engenharia entrega `production-readiness` estritamente read-only e repete o
   gate no clone/ambiente alvo final.
5. Operação anexa 2FA, alerta sintético, catálogo/estoque/preço/fiscal, aparelhos
   e equipamentos físicos. Só depois se solicita autorização contextual para
   tag, deploy e canários financeiros/fiscais.

Nenhuma dessas ações fica autorizada por este relatório.
