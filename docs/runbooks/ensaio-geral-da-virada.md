# Ensaio geral da virada

> A virada acontece no próprio app vivo `shopman-nelson`
> (`40b86e35-bafe-4a1a-a1b0-e124d3d9fd0f`, contexto `shopman-do-app-admin`), no
> mesmo banco (D-029), sem data (D-030): quando a
> [matriz](../plans/GO-LIVE-READINESS-PLAN.md) fechar. Este roteiro ensaia a
> virada **inteira sem tocar o app vivo**: copia o banco, sobe o app com a
> configuração do dia D numa máquina local, passa todas as travas e gates, e
> ensaia a volta. É a linha "Uma semana antes" do
> [cutover §0a](go-live-cutover.md#0a-sequência-do-dia-d-painel-de-go-live-10102026).
>
> **O que este roteiro não faz:** nenhum `doctl apps update`, nenhuma mudança no
> painel, nenhum recurso novo na DigitalOcean. Tudo o que fala com a DO é
> leitura (`apps spec get`, `databases connection`, `apps propose`) ou o dump
> pela porta direta. O único passo do rollback que só se ensaia no vivo,
> reapontar o app para um cluster restaurado, é o [cutover §0b](go-live-cutover.md#0b-ensaio-de-reapontar-o-app-para-o-banco-restaurado)
> e é do dono; o passo 4 deixa o arquivo dele pronto.
>
> Medido de ponta a ponta em 13/10/2026 (seção [Medição de 13/10](#medição-de-13102026)).

## Resumo: passos, quem, tempo e quando parar

| Passo | O quê | Quem | Tempo medido (13/10) | Parar se |
|---|---|---|---|---|
| 0 | Preparar a pasta e o código do deployment | agente | 1 min | o SHA não é o do deployment `ACTIVE` |
| 1 | Guardar o spec vivo e copiar o banco pela porta **direta** `25060` | agente | spec 1,4 s; dump 1 min 46 s (6,7 MB) | a URL não é a `25060`; `pg_dump` falha |
| 2 | Restaurar num Postgres 16 de ensaio (local, porta `37201`) | agente | menos de 10 s | contagem diferente da origem |
| 3 | Reapontar um app de ensaio para o banco restaurado (opção 2: local) | agente | 19 s até `/ready/` 200 | `/ready/` diferente de 200 |
| 4 | Delta do spec em modo ensaio: o "depois" sem colar nada | agente | 1 a 2 s por comando | delta não fecha; drift com algo fora do delta; `propose` recusa |
| 5 | Travas e gates: `check --deploy` (E026/E027), `migration_safety`, `production-readiness` | agente | 26 s (travas) + 9 s (gates) | trava que não reprova o que devia; gate do alvo vermelho |
| 6 | QA física e canário em versão de ensaio, no alpha como está | **DONO** + equipe | não medido (estimativa: 3 h) | ✗ que trava; efeito "não sabemos" |
| 7 | Ensaiar a volta: spec anterior e restore | agente | 1 a 2 s por comando | o spec de antes não é aceito |
| 8 | Descartar e registrar | agente | 1 min | (sempre fazer) |

**Tempo total do ensaio:** a trilha técnica (passos 0 a 5, 7 e 8) roda em
cerca de 5 min de máquina; com leitura e anotação, reserve **45 min**. A QA
física e o canário (passo 6) são a parte longa: reserve **meio período** com a
equipe na loja.

Regra geral de parada: parou de bater, para o passo, anota a saída inteira na
[folha de evidência](#evidência) e não tenta de novo antes de entender. Ensaio
que para é achado, não fracasso: é para isso que ele existe antes do dia D.

---

## 0. Preparar

Pasta do ensaio **fora do repositório** (o spec guardado tem segredos cifrados;
os scripts se recusam a escrever dentro do repositório). Portas da faixa do
ensaio: `37201` Postgres, `37202` Redis, `37210` app.

```bash
export E=~/ensaio-virada
mkdir -p "$E" && chmod 700 "$E"
export APP=40b86e35-bafe-4a1a-a1b0-e124d3d9fd0f
export CTX=shopman-do-app-admin
export CLUSTER=dd2ca658-a9bd-4188-8b8a-9eea6618b7c3   # shopman-staging-postgres
date -u +%FT%TZ | tee "$E/t0-inicio.txt"
```

O código do ensaio é o **mesmo SHA do deployment `ACTIVE`**, numa worktree
própria (o checkout principal é chão compartilhado):

```bash
gh run list --workflow "Deploy Images" --branch main --status success --limit 1 --json headSha,createdAt
doctl --context "$CTX" apps list-deployments "$APP" --format ID,Phase,Created --no-header | head -1
git worktree add ~/ensaio-virada-codigo <headSha>
export REPO=~/ensaio-virada-codigo
export PY=<raiz do repositório principal>/.venv/bin/python
PP="$REPO"; for p in "$REPO"/packages/*/; do PP="$PP:$p"; done; export PYTHONPATH="$PP"
```

O `PYTHONPATH` é obrigatório: o `.venv` da raiz aponta os `packages/*` para o
checkout principal, e sem ele o ensaio roda código de outra árvore.

Ferramentas: `doctl`, `pg_dump`/`pg_restore`/`psql` 16 e Postgres 16 local
(`brew install postgresql@16`), `redis-server`, `openssl`.

---

## 1. Guardar o spec e copiar o banco pela porta direta

**Spec vivo** (é também o "antes" do passo 7):

```bash
doctl --context "$CTX" apps spec get "$APP" --format yaml > "$E/antes.yaml"
shasum -a 256 "$E/antes.yaml" | tee "$E/antes.sha256"
```

**Dump pela conexão direta, porta `25060`, banco `shopman`.**
Nunca pelo pool `25061`: o `pg_dump` deixa `search_path=''` grudado na conexão
do PgBouncer e derruba o `directive-worker` (22, 23 e 24/09). O contexto
`shopman-do-app-admin` tem `database:view_credentials` e basta.

```bash
URI=$(doctl --context "$CTX" databases connection "$CLUSTER" --format URI --no-header)
case "$URI" in *:25060/*) echo "ok: porta direta" ;; *) echo "PARAR: não é a 25060"; unset URI ;; esac
URI=$(printf '%s' "$URI" | sed 's#/defaultdb?#/shopman?#')
export PGOPTIONS='-c default_transaction_read_only=on' PGTZ=UTC
date -u +%FT%TZ | tee "$E/t1-inicio.txt"
psql "$URI" -Atc "select count(*) from orderman_order;
  select ref||' '||created_at from orderman_order order by created_at desc limit 1;
  select count(*) from django_migrations;
  select count(*) from information_schema.tables where table_schema='public'" > "$E/verdade-origem.txt"
pg_dump -Fc --no-owner --no-acl -f "$E/alpha.dump" "$URI" && chmod 600 "$E/alpha.dump"
date -u +%FT%TZ | tee "$E/t1-fim.txt"
unset URI
```

O `default_transaction_read_only=on` faz a origem recusar qualquer escrita
desta sessão. Anote o instante de `t1-inicio`: é o "ponto UTC" que o dia D
anota na abertura da janela.

**Parar se:** a URL não for a `25060`, ou o `pg_dump` falhar. Não tente pelo
pool, nem "só desta vez".

---

## 2. Restaurar num banco de ensaio

Postgres 16 descartável, só em `127.0.0.1:37201`, sem socket de arquivo (o
caminho da pasta pode passar do limite de 103 bytes do macOS) e com `LC_ALL=C`
(sem ele o Postgres do Homebrew cai com "postmaster became multithreaded").

```bash
export LC_ALL=C LANG=C
PGBIN=/opt/homebrew/opt/postgresql@16/bin
date -u +%FT%TZ | tee "$E/t2-inicio.txt"
"$PGBIN/initdb" -D "$E/pg" -U shopman --auth=trust -E UTF8 --locale=C >/dev/null
"$PGBIN/pg_ctl" -D "$E/pg" -o "-p 37201 -c listen_addresses=127.0.0.1 -c unix_socket_directories=''" \
  -l "$E/pg.log" -w start
"$PGBIN/createdb" -h 127.0.0.1 -p 37201 -U shopman shopman
"$PGBIN/pg_restore" -j4 --no-owner --no-acl -h 127.0.0.1 -p 37201 -U shopman -d shopman "$E/alpha.dump"
PGOPTIONS= psql -h 127.0.0.1 -p 37201 -U shopman shopman -Atc "select count(*) from orderman_order;
  select ref||' '||created_at from orderman_order order by created_at desc limit 1;
  select count(*) from django_migrations;
  select count(*) from information_schema.tables where table_schema='public'" > "$E/verdade-restaurado.txt"
date -u +%FT%TZ | tee "$E/t2-fim.txt"
diff "$E/verdade-origem.txt" "$E/verdade-restaurado.txt" && echo "contagens batem"
```

**Parar se:** o `diff` mostrar qualquer linha. Com `PGTZ=UTC` nos dois lados,
nem o fuso do `created_at` difere.

> **Restaurar na DO em vez de local** (o fork pelo painel, D-021) prova o
> caminho de PITR, e já foi provado em 01/10 (cerca de 7 min até `online`,
> [backup-e-restore.md](backup-e-restore.md#1b-pelo-fork-no-painel-01102026-fim-da-tarde-feito-bate-com-a-origem)).
> Só faz sentido de novo junto do §0b. **DONO:** no painel,
> `shopman-staging-postgres` → Actions → Restore from backup → Restore to New
> Cluster, e Destroy no mesmo dia.

---

## 3. Reapontar um app de ensaio para o banco restaurado

### As duas opções, com custo

| | Opção 1: app de ensaio na DO | Opção 2: app local (recomendada) |
|---|---|---|
| O que é | Um segundo app no App Platform (`web-operator` + `release`, sem domínios), anexado a um cluster restaurado por fork | O mesmo código (SHA do deployment) rodando nesta máquina com o env do dia D, contra o Postgres do passo 2 |
| Custo medido | `doctl apps propose` (só leitura, 13/10): **US$ 44/mês** só `web-operator` + `release`; **US$ 49/mês** com o `directive-worker`; a cópia inteira, US$ 98/mês (o mesmo do vivo). Mais o cluster de fork, US$ 15,15/mês (US$ 0,02254/h). Pró-rata, cerca de **US$ 0,40 por 4 h**; o mínimo de cobrança do App Platform não foi verificado | **US$ 0** na DO |
| Componente novo na DO | sim, dois (app e cluster), contra a regra do dono (DO já passa de US$ 100/mês) | nenhum |
| O que exige do dono | criar o app e o cluster (o token `shopman-do-app-admin` não tem `database:create`; medido em 01/10), e os segredos: **a DO recusa os `EV[...]` do vivo num app novo** ("secret env value must not be encrypted before app is created", medido no `propose` de 13/10), então cada segredo teria de ser colado de novo ou trocado por sintético | nada |
| O que prova a mais | o pool PgBouncer do cluster restaurado, as fontes confiáveis, a referência `${postgres.…}` do App Platform, a imagem do DOCR | (o resto: config do dia D sobre o dado real, travas, gates, boot) |
| O que atrapalha | domínio `*.ondigitalocean.app` não carrega o cookie `.boulangerie.com.br`, então os apps de operador não entram; os workers (`ifood-poll`, `maintenance`) agiriam com a credencial que recebessem; e ele **não ensaia o rollback de verdade**, que é reapontar o app **vivo** | não exercita PgBouncer nem fontes confiáveis |

**Recomendação: opção 2.** O que a opção 1 provaria a mais (pool, fontes
confiáveis, referência do App Platform) só vale se for provado **no app vivo**,
que é quem reaponta no rollback, e isso já tem roteiro e dono: o
[cutover §0b](go-live-cutover.md#0b-ensaio-de-reapontar-o-app-para-o-banco-restaurado).
Pagar um app novo para ensaiar um app que não é o da virada não fecha linha da
matriz. Medido em 13/10: a opção 2 sobe com a configuração do dia D sobre o
dado restaurado e passa `/ready/` em 19 s.

Dois fatos que o ensaio já deixou anotados para o §0b (13/10, `doctl … databases
pool list` e `firewalls list`): o pool do cluster é `shopman-staging-pool`
(banco `shopman`, modo `transaction`, tamanho 5) e o cluster **não tem fontes
confiáveis**. No cluster restaurado basta recriar o pool com o mesmo nome.

### Opção 2: subir o app local

Redis descartável, certificado sintético da Efí e o env do `web-operator` do
spec do dia D (o "depois" sai no passo 4; rode o passo 4a antes deste bloco):

```bash
redis-server --port 37202 --bind 127.0.0.1 --save '' --appendonly no --daemonize yes \
  --pidfile "$E/redis.pid" --logfile "$E/redis.log"
openssl req -x509 -newkey rsa:2048 -nodes -days 2 -subj '/CN=ensaio-virada.invalid' \
  -keyout "$E/efi.key" -out "$E/efi.crt" 2>/dev/null
cat "$E/efi.key" "$E/efi.crt" > "$E/efi-sintetico.pem" && chmod 600 "$E/efi-sintetico.pem" "$E/efi.key"
for comp in release web-operator; do
  "$PY" "$REPO/scripts/golive_ensaio.py" env --spec "$E/depois.ensaio.yaml" --componente "$comp" \
    --database-url postgres://shopman@127.0.0.1:37201/shopman --redis-url redis://127.0.0.1:37202/0 \
    --efi-cert-path "$E/efi-sintetico.pem" --host-extra 127.0.0.1 --saida "$E/$comp.env"
done
```

O `env` monta o ambiente efetivo do componente (app + componente, como o App
Platform entrega) e **nunca lê segredo**: cada `EV[...]` vira valor sintético
(não autentica em provedor nenhum; o Stripe ganha `sk_live_ensaio_…` quando a
publicável é `pk_live_`), certificados, VAPID, Sentry e SMTP saem, e
`${postgres…}`/`${cache…}` viram as URLs do ensaio. O cabeçalho do arquivo
lista o que foi sintetizado e o que saiu.

Num terminal próprio (fica em primeiro plano):

```bash
cd "$REPO" && . "$E/web-operator.env"
"$PY" -c "import psycopg_pool" 2>/dev/null || export DATABASE_POOL_MAX_SIZE=0
export STATIC_ROOT="$E/static"
"$PY" manage.py collectstatic --noinput -v 0
"$(dirname "$PY")/daphne" -b 127.0.0.1 -p 37210 config.asgi:application
```

O `DATABASE_POOL_MAX_SIZE=0` só entra se o `.venv` local não tiver o
`psycopg_pool` (medido em 13/10: não tinha; a imagem de produção tem). É o
interruptor documentado no `settings` e não muda nada do que o ensaio mede. O
`collectstatic` faz o que o build da imagem faz; sem ele o Admin dá 500
("Missing staticfiles manifest entry").

Conferir, em outro terminal:

```bash
curl -s -w ' %{http_code}\n' http://127.0.0.1:37210/ready/
for p in /api/v1/storefront/menu/ /api/v1/storefront/site/ /admin/login/; do
  curl -s -o /dev/null -w "$p %{http_code}\n" -H 'X-Forwarded-Proto: https' "http://127.0.0.1:37210$p"
done
```

`/ready/` 200 com `database`, `cache`, `migrations` e `queue` `ok`; as três rotas
200. O `X-Forwarded-Proto` faz o papel da borda da DO (sem ele o
`SECURE_SSL_REDIRECT` do dia D manda para `https`).

**Não** rode o `directive-worker` local contra a cópia: as diretivas pendentes
do alpha tentariam avisar clientes, e com credencial sintética só gerariam
erro. O sintoma que importa no worker (`relation … does not exist`, o
`search_path` grudado no pool) é do PgBouncer, e se prova no §0b.

**Parar se:** `/ready/` diferente de 200, ou qualquer das três rotas com 5xx
(o log está no terminal do `daphne`).

---

## 4. O delta do spec em modo ensaio

### 4a. O spec do dia D, sem colar nada

```bash
"$PY" "$REPO/scripts/golive_ensaio.py" depois --antes "$E/antes.yaml" --saida "$E/depois.ensaio.yaml"
```

Escreve o spec como ele fica depois da gravação única do dono: a tabela `DELTA`
de `scripts/golive_spec_delta.py` aplicada ao spec guardado. Segredo que o dia
D troca vira marcador `ENSAIO-NAO-APLICAR-<chave>` (tipo `SECRET`); a
publicável do Stripe vira `pk_live_ENSAIO_NAO_APLICAR`. O arquivo abre com o
aviso **NUNCA aplicar**. Medido em 13/10: 17 mudanças, as mesmas linhas
`[VIRAR]` e `[SEM PROVA]` do delta do vivo.

### 4b. O delta fecha?

```bash
"$PY" "$REPO/scripts/golive_spec_delta.py" --live-spec "$E/antes.yaml"                               # hoje: lista o que falta (sai 1)
"$PY" "$REPO/scripts/golive_spec_delta.py" --live-spec "$E/depois.ensaio.yaml" --baseline "$E/antes.yaml"   # dia D: sai 0
```

O segundo tem de terminar com "Nada obrigatório pendente para esta etapa." e
sair `0`.

### 4c. O que a gravação do dono muda, linha a linha

```bash
"$PY" "$REPO/scripts/check_do_spec_drift.py" --spec "$E/depois.ensaio.yaml" --live-spec "$E/antes.yaml"
```

Sai `1` (é diferença de propósito), e a lista tem de ser **só o delta**. Em
13/10: SUMIRIAM `SHOPMAN_ALLOW_MOCK_PAYMENT_ADAPTERS`,
`SHOPMAN_EXPOSE_MOCK_CAPTURE`, `SHOPMAN_MOCK_PIX_CONFIRM_DELAY_SECONDS`;
nasceriam `SHOPMAN_ADMIN_REQUIRE_2FA`, `SHOPMAN_GO_LIVE`; divergem
`EFI_SANDBOX`, `SHOPMAN_ENVIRONMENT`, `SHOPMAN_PIX_ADAPTER`,
`STRIPE_PUBLISHABLE_KEY`; e `FOCUS_NFE_ENVIRONMENT` aparece como "diferença
declarada" (a nota do drift fala do arquivo versionado; aqui ela muda o valor
para `producao`). Segredos não aparecem: o drift não compara valor cifrado.

### 4d. A DO aceita esse spec? (validação, sem aplicar)

```bash
doctl --context "$CTX" apps propose --spec "$E/depois.ensaio.yaml" --app "$APP" -o json > "$E/propose-depois.json"
grep -o '"app_cost": [0-9.]*\|"detail": "[^"]*"' "$E/propose-depois.json"
doctl --context "$CTX" apps list-deployments "$APP" --format ID,Phase,Created --no-header | head -1
```

O `propose` só valida e devolve o custo; não cria deployment (a última linha
tem de mostrar o mesmo deployment do passo 0). Em 13/10: aceito, `app_cost` 98.
Cuidado ao gerar spec à mão: o PyYAML escreve o CNPJ `02119381000158` sem
aspas e a DO lê como número ("cannot unmarshal number into … envs.value"); o
`golive_ensaio.py` já põe as aspas.

### 4e. O arquivo do §0b (reapontar), pronto para o dono

```bash
"$PY" "$REPO/scripts/golive_ensaio.py" reapontar --antes "$E/antes.yaml" \
  --cluster <nome do cluster restaurado> --saida "$E/reapontado.ensaio.yaml"
```

Troca **só** `databases[postgres].cluster_name`; o resto do spec, inclusive os
`EV[...]`, fica byte a byte o do passo 1. No dia em que o dono ensaiar o §0b,
`check_do_spec_drift.py --spec "$E/reapontado.ensaio.yaml" --context "$CTX"`
tem de mostrar uma linha só, e o `propose` com o cluster já criado tem de
aceitar.

**Parar se (passo 4):** o 4b não sair `0`; o 4c listar qualquer chave fora do
delta; o `propose` recusar. Qualquer um dos três quer dizer que a lista do dia D
está errada: corrigir a tabela e o [delta do spec](go-live-delta-do-spec.md)
antes do dia D.

---

## 5. Travas e gates contra o dado restaurado

### 5a. As travas do release (E026, E027, `migration_safety`)

O job `release` roda `check --deploy && migration_safety && migrate …`. Aqui as
duas primeiras, com o env do dia D, contra o banco restaurado; e duas viradas
pela metade que **têm de** reprovar:

```bash
cd "$REPO" && . "$E/release.env"
"$PY" -c "import psycopg_pool" 2>/dev/null || export DATABASE_POOL_MAX_SIZE=0
"$PY" manage.py check --deploy --fail-level ERROR 2>&1 | grep -E "SHOPMAN_[EW]0|SystemCheckError"
"$PY" manage.py migration_safety
SHOPMAN_ENVIRONMENT=staging "$PY" manage.py check --deploy --fail-level ERROR 2>&1 | grep -E "SHOPMAN_E027"
( unset EFI_SANDBOX; "$PY" manage.py check --deploy --fail-level ERROR 2>&1 | grep -E "SHOPMAN_E026" )
```

Esperado (13/10):

1. **Dia D passa:** sem `SystemCheckError` nem `SHOPMAN_E…`; só os avisos esperados `SHOPMAN_W009`
   (ManyChat sem segredo de webhook) e `SHOPMAN_W019` (sem VAPID; no ensaio o
   `env` tira as chaves).
2. `migration_safety`: `clear`, `política ADR-015: ARMADA — SHOPMAN_GO_LIVE=true`,
   `0 migração(ões) pendente(s)`.
3. **Chave live com `staging`:** `SHOPMAN_E027` (Stripe live, Efí fora do
   sandbox e Focus em produção com porta de teste aberta).
4. **Produção sem `EFI_SANDBOX` escrita:** `SHOPMAN_E026` (e o `SHOPMAN_E022`).

O E022 e o E027 leem também o `Shop.integrations` do **banco**: é por isso que
este passo roda contra a cópia, e não só contra o spec.

**Parar se:** o 1 tiver qualquer `SHOPMAN_E…`; o 3 ou o 4 **não** reprovarem
(trava que não segura é pior que trava nenhuma).

### 5b. O gate do alvo, com o spec do dia D e o app local

```bash
make -C "$REPO" production-readiness target=1 \
  target_spec="$E/depois.ensaio.yaml" baseline="$E/antes.yaml" target_url=http://127.0.0.1:37210
```

Tem de sair `passed` com os 8 checks OK (13/10: 8 de 8). É o mesmo comando do
"depois" do dia D, trocando o `doctl` pelo arquivo e a API pública pelo app
local.

### 5c. O gate de produção lendo o banco (somente leitura)

```bash
cd "$REPO" && . "$E/release.env"
"$PY" -c "import psycopg_pool" 2>/dev/null || export DATABASE_POOL_MAX_SIZE=0
"$PY" scripts/check_release_readiness.py --profile=production --strict-external --read-only
```

É o "`production-readiness read_only=1` no banco alvo" da matriz. O que ele
reprovar sobre **dado** vira fila de divergências para o dono, não aborto do
ensaio. Em 13/10, sobre o alpha restaurado: `production.public_copy_review`
FAIL (6 itens de copy pública sem o aval do dono) e
`catalog.product_image_host` FAIL (44 produtos com foto fora de
`img.nelsonboulangerie.com.br`); `omotenashi.manual` BLOCKED (falta a evidência
do passo 6); `gateways.sandbox` BLOCKED por certificado da NF-e de compra, que
é **artefato do ensaio** (o `env` tira o PFX). Os outros 11 OK.

---

## 6. QA física e canário em versão de ensaio

Roteiro: [qa-fisica-e-canario.md](qa-fisica-e-canario.md), linha **Ensaio
geral** da tabela "Quando usar". Roda **no alpha como ele está** (perfil de
ensaio): só cria pedidos sintéticos, não muda configuração.

- **Folhas 1 a 5** inteiras, cada pessoa no seu papel, Folha 5 (periféricos)
  primeiro. Inclui derrubar a rede do balcão com o PDV vendendo (B8).
- **Folha 6 em versão de ensaio:** os mesmos passos do canário, com dinheiro de
  teste. Pix: Efí em sandbox se o [ensaio do Pix real](go-live-delta-do-spec.md)
  (D-031, `--etapa ensaio-pix`) já estiver no ar; senão o "Simular pagamento",
  e anotar que o Pix da Efí **não** foi provado. Cartão `4242 4242 4242 4242`,
  Focus em homologação, estorno no Stripe em modo teste. Os N0.2 e C3.5/C6.9
  invertem: no ensaio o selo "Ambiente de teste" **tem de** aparecer.
- Cronometre cada folha (hora de início e fim na folha de anotação).

**DONO:** reunir a equipe na loja e conduzir as folhas; no canário de ensaio,
comprar como cliente e dizer "pode" antes de cada passo com dinheiro.

**Parar se:** ✗ que trava o trabalho, pagamento que não anda, efeito "não
sabemos". Vira linha na folha de anotação e item da matriz; o dia D não sai
enquanto não fechar.

---

## 7. Ensaiar a volta

No dia D a volta tem duas camadas: **chaves** (reaplicar o spec de antes) e
**dado** (restaurar o ponto UTC e reapontar). O ensaio prova as duas sem tocar
o vivo.

**Chaves.** O spec de antes é o arquivo da volta:

```bash
"$PY" "$REPO/scripts/check_do_spec_drift.py" --spec "$E/antes.yaml" --live-spec "$E/depois.ensaio.yaml"   # o delta ao contrário
doctl --context "$CTX" apps propose --spec "$E/antes.yaml" --app "$APP" -o json | grep -o '"app_cost": [0-9.]*\|"detail": "[^"]*"'
```

O drift tem de listar exatamente o inverso do 4c; o `propose` tem de aceitar
(13/10: aceito). No dia D, aplicar é `apps update` de arquivo: palavra e mão do
dono (D-009), e um deployment leva cerca de 3,5 min até `ACTIVE` (deployment
`b2bca415`, 10/10: 21:41:19 → 21:44:48 UTC).

**Dado.** Os passos 1 e 2 deste roteiro **são** o restore lógico, cronometrado.
O restore pela DO (fork, cerca de 7 min) mais o reapontar do vivo é o §0b, com
o arquivo do 4e.

**Tempo de volta estimado no dia D** (somando o medido): chaves, cerca de 4 min
(um deployment); dado, cerca de 15 min (fork 7 min + pool + um deployment
reapontado + conferência), mais o que se perder entre o ponto UTC e a volta.

**Critério de aborto no dia D**, para levar ao cutover:

- `check --deploy` do release reprova: o deploy não fica `ACTIVE` e o app segue
  no anterior; não há o que voltar, só corrigir a chave e gravar de novo;
- `production-readiness target=1 … baseline=` vermelho depois de `ACTIVE`:
  voltar as chaves;
- canário com efeito "não sabemos", pagamento duplicado ou nota que não sai:
  NO-GO, voltar as chaves;
- dado errado depois da carga: voltar o dado (§0b).

---

## 8. Descartar e registrar

```bash
pkill -f "daphne -b 127.0.0.1 -p 37210"
redis-cli -p 37202 shutdown nosave
LC_ALL=C /opt/homebrew/opt/postgresql@16/bin/pg_ctl -D "$E/pg" -m fast stop
rm -rf "$E/pg" "$E/static" "$E/alpha.dump" "$E"/*.env "$E"/efi.* "$E/efi-sintetico.pem" \
       "$E/antes.yaml" "$E/depois.ensaio.yaml" "$E/reapontado.ensaio.yaml"
git worktree remove ~/ensaio-virada-codigo
```

O dump é cópia do banco (pedidos, clientes): não fica em disco depois do
ensaio. Guarde só os horários, as contagens e as saídas dos comandos.

## Evidência

Uma linha por passo, no PR ou no canal da virada:

| Passo | Início (UTC) | Fim (UTC) | Resultado | Saída guardada |
|---|---|---|---|---|
| 1 spec + dump | | | sha256 do spec; tamanho do dump | `verdade-origem.txt` |
| 2 restore | | | contagens batem? | `verdade-restaurado.txt` |
| 3 app local | | | `/ready/` | |
| 4 delta | | | 4b sai 0? 4c só o delta? 4d aceito? | |
| 5 travas e gates | | | E026/E027 reprovam o que devem? 5b passed? 5c FAILs | |
| 6 QA física e canário | | | folhas e ✗ | folha de anotação |
| 7 volta | | | drift inverso? `propose` do antes aceito? | |

Atualizar na [matriz](../plans/GO-LIVE-READINESS-PLAN.md) as linhas que o
ensaio fecha (QA física, impressão/gaveta/som) e as que ele abre (a fila de
divergências do 5c).

## O que exige o dono

- **Passo 6:** reunir a equipe e conduzir a QA física e o canário de ensaio na loja (meio período).
- **Passo 5c:** decidir a fila de divergências de dado (em 13/10: aval da copy pública, 6 itens; fotos de 44 produtos fora do host dedicado).
- **Fora deste roteiro, §0b:** criar o cluster pelo fork no painel, autorizar o reapontar do app vivo com o arquivo do 4e, e destruir o cluster no mesmo dia.
- **Só se escolher a opção 1** (não recomendada): autorizar e criar um app e um cluster novos na DO e colar os segredos de novo.

Todo o resto (passos 0 a 5, 7 e 8) o agente faz sozinho com o contexto
`shopman-do-app-admin`, que lê o spec, as credenciais do banco e valida spec
pelo `propose` (medido em 13/10).

## Medição de 13/10/2026

Rodado de ponta a ponta pela frente que escreveu este roteiro, com o código do
`main` em `dfda93b44` (o deployment `ACTIVE` `dfe60573`, 12/10 01:30 UTC), sem
nenhuma mudança no app vivo:

- **Passo 1:** spec vivo, 1.079 linhas, 1,4 s. Dump pela `25060` das 07:47:34
  às 07:49:19 UTC: **1 min 46 s**, 6,7 MB. Origem: 4.819 pedidos, último
  `PDV-261010-A39`, 325 migrações, 195 tabelas.
- **Passo 2:** restore em 2 s; as quatro contagens batem.
- **Passo 3:** `collectstatic` + boot até `/ready/` 200 em **19 s**; menu, site
  e login do Admin 200.
- **Passo 4:** 17 mudanças no "depois"; delta sai 0 com baseline; drift só com o
  delta; `propose` do "depois" aceito (US$ 98/mês, o mesmo do vivo) e nenhum
  deployment novo.
- **Passo 5:** `check --deploy` do dia D sem erro (W009 e W019); E027 e E026
  reprovaram as duas viradas pela metade; `migration_safety` clear com a política
  armada; gate do alvo 8 de 8; gate no banco com os FAILs listados no 5c. As
  quatro rodadas de travas em 26 s; os dois gates em 9 s.
- **Custos da opção 1** pelo `propose` (só leitura), como na tabela do passo 3.
- Tudo descartado no fim (Postgres, Redis, dump, specs e envs).
- **Não medido:** o passo 6 (precisa da loja e da equipe) e o §0b (é do dono).
