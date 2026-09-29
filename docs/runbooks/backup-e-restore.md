# Backup antes do `migrate`, e restore ensaiado

> **O que este runbook cobre:** o banco Postgres gerenciado da DigitalOcean —
> backup automático, point-in-time recovery, o que olhar antes de um deploy com
> migração de risco, e como ensaiar uma restauração de verdade.
>
> **O que ele NÃO cobre:** o *cofre de dados curados* (catálogo, receitas,
> fornecedores, regras, copy) exportado em XLSX pelo `export_backup`. Isso é
> outra camada, com outra finalidade, e vive em
> [`docs/guides/backup-and-restore.md`](../guides/backup-and-restore.md). As
> duas se complementam: o Postgres salva o **histórico**, o cofre salva o
> **trabalho humano**. Nenhuma das duas substitui a outra.

**Por que ele existe.** Todo merge no `main` dispara um deploy, e o job
`release` (PRE_DEPLOY) roda `migrate --noinput` contra o banco real, em ~6
minutos, sem ninguém olhando. O runbook de
[rollback de deploy](rollback-de-deploy.md) manda, para migração destrutiva,
"restaurar o banco do snapshot pré-deploy" — e até 22/09/2026 **nenhum passo do
processo tirava esse snapshot**, nem dizia onde procurá-lo. Este documento fecha
essa ponta: o snapshot existe (a DO o tira sozinha), o que faltava era saber
**qual** ponto no tempo usar, ter isso anotado antes, e ter alguém que já tenha
feito o restore uma vez.

---

## 1. O que existe hoje

Dois clusters *managed* de PostgreSQL 16 na DigitalOcean:

| Ambiente | Cluster | Onde está declarado |
|---|---|---|
| Alpha | `shopman-staging-postgres` | `.do/app.alpha-subdomains.yaml` (`databases:`) |
| Produção | `shopman-headless-postgres` | `.do/app.subdomains.yaml` (`databases:`) |

O que a DigitalOcean entrega por padrão, sem nada a instalar e sem custo extra
(cada afirmação com a página de onde veio):

- **Backup diário automático, retido por 7 dias.** "PostgreSQL cluster backups
  run automatically once per day and are retained for seven days"
  ([restore-from-backups](https://docs.digitalocean.com/products/databases/postgresql/how-to/restore-from-backups/)).
  O horário do backup é escolhido pela DO e **não pode ser mudado** (mesma
  página).
- **Point-in-time recovery de 7 dias, com granularidade de segundos.** "Full
  cluster backups are taken daily and write-ahead-logs are maintained to allow
  you to restore to any point-in-time within the previous seven days"
  ([features](https://docs.digitalocean.com/products/databases/postgresql/details/features/));
  "Point-in-time-recovery (PITR) is limited to the last 7 days"
  ([limits](https://docs.digitalocean.com/products/databases/postgresql/details/limits/));
  o seletor do painel tem "Date, Hrs, Mins, and Secs"
  ([fork-clusters](https://docs.digitalocean.com/products/databases/postgresql/how-to/fork-clusters/)).
- **Restaurar cria sempre um cluster NOVO.** "Restoring creates a new copy of
  the cluster's primary node… restoring into the existing primary node would
  create multiple database timelines" (restore-from-backups). Não existe
  restauração *in place*. O cluster restaurado nasce com nomes de banco e
  usuários iguais aos da origem, mas **host, porta e senha novos**.
- **Restore e fork são o mesmo mecanismo.** "Creating a database from a backup
  is the same as forking a database in the control panel"
  ([API reference](https://docs.digitalocean.com/reference/api/reference/databases/)).
  É por isso que o caminho automatizável se chama `fork`.

### O que isto cobre e o que não cobre

| Cobre | Não cobre |
|---|---|
| Deploy que corrompeu ou apagou dado nos últimos **7 dias** | Qualquer estrago descoberto **depois de 7 dias** — a janela expira e o dado vai junto |
| Voltar a um instante exato antes do `migrate` | Voltar **só uma tabela**: o restore é do cluster inteiro |
| Perda do nó primário (a DO recupera sozinha) | O Valkey/cache: "Backups are also not supported for Caching or Valkey clusters" ([API reference](https://docs.digitalocean.com/reference/api/reference/databases/)) — o cache é descartável por desenho |
| Erro humano no banco (DELETE sem WHERE, migração ruim) | **Destruir o cluster**: "Destroying a database cluster destroys the backups of that database" (restore-from-backups). Apagar o cluster apaga a rede junto com ele |

⚠️ **O limite de clusters é uma trava operacional real.** O padrão da conta é
**10 clusters**; quando ele é atingido, a opção "Restore from backup" nem
aparece no painel
([limits](https://docs.digitalocean.com/products/databases/postgresql/details/limits/)).
Descobrir isso na hora do incidente é tarde: confira a folga durante o ensaio
(seção 3), não durante o desastre.

### O que dá para fazer por API/`doctl` e o que só existe no painel

| Ação | API v2 | `doctl` | Painel |
|---|---|---|---|
| Listar backups de um cluster | `GET /v2/databases/{uuid}/backups` | `doctl databases backups <cluster-id>` | sim |
| Criar cluster a partir de backup / PITR | `POST /v2/databases` com o objeto `backup_restore` (`database_name` + `backup_created_at`) | `doctl databases fork <nome> --restore-from-cluster-id <uuid> [--restore-from-timestamp "2026-09-23 14:05:00 +0000 UTC"] --wait` | Actions → **Restore from backup** → **Restore to New Cluster** |
| Valores válidos de região/plano/versão | `GET /v2/databases/options` | — | sim |

Fontes: [fork-clusters](https://docs.digitalocean.com/products/databases/postgresql/how-to/fork-clusters/),
[doctl databases fork](https://docs.digitalocean.com/reference/doctl/reference/databases/fork/),
[doctl databases backups](https://docs.digitalocean.com/reference/doctl/reference/databases/backups/),
[API reference](https://docs.digitalocean.com/reference/api/reference/databases/).

**Não existe `doctl databases restore` nem endpoint `.../restore`.** A página
"Restore from Backups" documenta só o caminho do Control Panel; o equivalente
automatizável é o `fork`, e a própria DO diz que são a mesma coisa. Quem quiser
script usa `fork`; quem quiser clicar usa o painel.

**Escopo de token** ([API scopes](https://docs.digitalocean.com/reference/api/scopes/database/create/)):
listar backups pede `database:read`; criar o fork é um `POST /v2/databases` e
pede `database:create` mais os acompanhantes obrigatórios `database:read`,
`regions:read`, `sizes:read` e `actions:read` — e `database:view_credentials`
para ler a connection string do cluster novo.

> ⚠️ **Medido em 22/09/2026:** os tokens do contexto `shopman-alpha-deploy`
> nesta máquina **não têm escopo de database** — qualquer `doctl databases …`
> devolve 403. Tudo nesta seção veio da documentação da DO, não de medição na
> conta. Antes do ensaio, gere um token com os escopos acima (é a primeira
> tarefa da seção 3) — ou faça tudo pelo painel, onde a permissão é a do login.

---

## 2. Antes de um deploy com migração de risco

"De risco" tem definição, não é sentimento: é migração que contém
`RemoveField`, `DeleteModel`, `RenameField`, `RenameModel` ou `AlterField` — a
lista do [ADR-015](../decisions/adr-015-backward-compat-policy-post-prod.md).
Migração aditiva volta por redeploy da versão anterior e não precisa disto.

### 2.1 Saber o que o deploy vai fazer no banco

```bash
# leitura pura; não escreve nada, não migra nada
DATABASE_URL='postgresql://…' make migrations-pending
```

A connection string sai no painel da DO (cluster → **Connection details**) ou,
com token de escopo `database:view_credentials`, em
`doctl databases connection <cluster-id>`. A saída separa o que é aditivo do que
é destrutivo, nomeando a operação:

```
migration-safety: clear
política ADR-015: inativa (pré-go-live) — tag go-live-v1 ausente e SHOPMAN_GO_LIVE não declarada
banco 'default': 3 migração(ões) pendente(s), 1 com operação destrutiva.
  [aditiva   ] orderman.0021_order_observation
  [DESTRUTIVA] orderman.0022_remove_order_note (RemoveField)
  [aditiva   ] shop.0044_ruleconfig_window
```

`make migrations-plan` mostra o plano cru do Django (`showmigrations --plan`),
aplicadas e pendentes, quando você quiser ver a fila inteira.

**Nenhuma destrutiva na lista → siga o deploy normal.** O resto desta seção é
para quando há.

### 2.2 Anotar o ponto no tempo

Esta é a parte que nenhum código faz por você, e é a parte que salva o dia.

1. Confirme que existe backup recente do cluster:
   ```bash
   doctl databases backups <cluster-id>          # size + created_at de cada um
   ```
   Pelo painel: cluster → **Backups**.
2. Anote, no PR do deploy ou no canal de operação, **três coisas**:
   - o **instante UTC** imediatamente anterior ao deploy (é o alvo do PITR —
     ele aceita qualquer segundo dos últimos 7 dias, então o que importa é ser
     um instante *antes* de o `migrate` começar);
   - o **cluster de origem** (`shopman-headless-postgres` ou
     `shopman-staging-postgres`);
   - a **contagem de referência** para conferir depois:
     ```sql
     SELECT count(*) FROM orderman_order;
     SELECT id, ref, created_at FROM orderman_order ORDER BY created_at DESC LIMIT 1;
     ```
3. Declare esse ponto no ambiente que roda o `release`, na variável
   `SHOPMAN_MIGRATION_BACKUP_REF` (App Platform → Settings → componente
   `release` → Environment Variables):
   ```
   SHOPMAN_MIGRATION_BACKUP_REF=PITR 2026-09-23T14:05:00Z — shopman-headless-postgres
   ```

O conteúdo é texto livre e legível por gente — a trava não valida formato, ela
exige que **exista e diga alguma coisa** (`-`, `n/a`, `TBD` e vazio não contam).
O ponto não é agradar um parser; é que, às 3h da manhã, o instante de
restauração esteja escrito em algum lugar que não seja a memória de quem deu o
deploy.

### 2.3 A trava que recusa o deploy

O job `release` roda, **antes** do `migrate`:

```
python manage.py check --deploy && python manage.py migration_safety && python manage.py migrate --noinput && …
```

O `migration_safety`
([`shopman/shop/migration_safety.py`](../../shopman/shop/migration_safety.py))
lê o mesmo plano que o `migrate` vai executar e recusa o deploy — saída
diferente de zero, `PRE_DEPLOY` vermelho, versão nova não sobe — em duas
situações:

- migração destrutiva pendente **e** `SHOPMAN_MIGRATION_BACKUP_REF` vazia, com a
  política do ADR-015 armada;
- não deu para ler o plano de migração. Um portão que não enxerga recusa, em vez
  de dizer "pode passar".

**Quando a política está armada:** `SHOPMAN_GO_LIVE=true` no ambiente (a imagem
do app não carrega o `.git`, então a tag `go-live-v1` não é legível lá dentro —
declarar essa env é item do [cutover](go-live-cutover.md)). Em dev e na CI vale
a tag; `SHOPMAN_ADR015_FORCE=1`/`0` força, para simulação.

**Antes do go-live a trava não segura nada** — ela só imprime o plano no log do
release, marcando cada destrutiva. É de propósito: a política do ADR-015 vale a
partir da tag, e armá-la antes seria inventar uma regra que o projeto não tomou.
A visibilidade, essa vale desde já.

⚠️ **O `run_command` do job mora no spec, não no código.** Mudá-lo no
repositório não muda o app vivo: alguém precisa aplicar o spec
(`doctl apps update`). Enquanto isso não acontece, a trava existe no `main` e
está **inerte no ar** — ver seção 4.

### 2.4 Se der errado depois do deploy

Classifique a mudança e siga o [rollback de deploy](rollback-de-deploy.md).
Para o caso destrutivo, o caminho é o da seção 3 com um detalhe que muda tudo:
**você não restaura por cima**. Você cria o cluster restaurado, valida, e só
então reaponta o app (`DATABASE_URL` / bloco `databases:` do spec) para ele.
Enquanto valida, congele novos deploys e preserve o cluster atual — ele é a
evidência do que aconteceu, e destruí-lo destrói os backups dele junto.

---

## 3. Ensaio de restauração

Um backup nunca restaurado é uma esperança, não um backup. O ensaio é o que
transforma "a DO faz backup" em "nós sabemos restaurar". Faça **contra o alpha**
(`shopman-staging-postgres`), com o app de produção intocado.

**Tempo estimado:** 40–60 min, quase tudo esperando o cluster nascer.

### Passo 0 — token com escopo (uma vez)

Gere em **API → Tokens** um token com `database:read`, `database:create`,
`database:view_credentials`, `regions:read`, `sizes:read`, `actions:read`. Sem
isso, faça tudo pelo painel — é o mesmo procedimento, clicando.

### Passo 1 — anotar a verdade do cluster de origem

Conecte no alpha e guarde os números que você vai conferir depois:

```sql
SELECT count(*) FROM orderman_order;                                     -- total de pedidos
SELECT id, ref, created_at FROM orderman_order ORDER BY created_at DESC LIMIT 1;  -- último pedido
SELECT count(*) FROM django_migrations;                                  -- migrações aplicadas
SELECT app, name FROM django_migrations ORDER BY id DESC LIMIT 5;        -- as cinco últimas
```

Anote também o **instante UTC** deste momento — é o alvo do PITR.

### Passo 2 — criar o cluster restaurado

```bash
doctl databases list                       # pegue o uuid de shopman-staging-postgres
doctl databases backups <cluster-id>       # confirme que há backup recente

doctl databases fork shopman-restore-drill \
  --restore-from-cluster-id <cluster-id> \
  --restore-from-timestamp "2026-09-23 14:05:00 +0000 UTC" \
  --wait
```

Sem `--restore-from-timestamp`, a DO usa o backup mais recente
([doctl databases fork](https://docs.digitalocean.com/reference/doctl/reference/databases/fork/)).

Pelo painel: cluster → **Actions** → **Restore from backup** → "Create a new
cluster from a backup" → escolher *latest transaction* ou *point in time* →
**Restore to New Cluster**. O nome padrão sai como
`originalname-aug-13-backup`.

⚠️ Se **Restore from backup** não aparecer: ou você abriu o menu de um nó
read-only em vez do primário, ou a conta bateu no limite de 10 clusters
([restore-from-backups](https://docs.digitalocean.com/products/databases/postgresql/how-to/restore-from-backups/)).

**Dimensione o cluster de ensaio no menor plano** (1 GiB / 1 vCPU) — o ensaio
não precisa aguentar carga. Ele tem 22 conexões de backend
([limits](https://docs.digitalocean.com/products/databases/postgresql/details/limits/)),
suficiente para um `psql` e um `manage.py`.

### Passo 3 — conferir que o dado voltou

Pegue a connection string do cluster novo (painel → **Connection details**, ou
`doctl databases connection <novo-uuid>`) e refaça **as mesmas quatro consultas
do passo 1**. O que tem que bater:

- [ ] `count(*)` de `orderman_order` igual ao da origem (ou menor por exatamente
      os pedidos criados entre o instante do PITR e agora — e essa diferença
      tem que fazer sentido);
- [ ] o último pedido é o mesmo `ref`, com o mesmo `created_at`;
- [ ] `count(*)` de `django_migrations` igual, e as cinco últimas idênticas;
- [ ] o Django concorda que o schema está em dia:
      ```bash
      DATABASE_URL='<connection string do cluster novo>' make migrations-pending
      ```
      Deve dizer **0 migração(ões) pendente(s)**. Se disser mais que zero, o
      cluster restaurado é de antes de algum deploy — o que também é uma
      resposta válida do ensaio, desde que seja a que você pediu no timestamp.

Registre as saídas: é a evidência que fecha o item "Backup e restore testado
para PostgreSQL" de [security-readiness](security-readiness.md).

### Passo 4 — descartar o cluster de ensaio

**No mesmo dia.** A cobrança só para quando o cluster é destruído — "Billing
stops when you destroy the cluster"
([fork-clusters](https://docs.digitalocean.com/products/databases/postgresql/how-to/fork-clusters/)).

```bash
doctl databases delete <novo-uuid>
```

Pelo painel: cluster → Settings → **Destroy**.

⚠️ Confira o UUID **duas vezes** antes de apertar: destruir um cluster destrói
os backups dele junto (restore-from-backups). O nome do cluster de ensaio é
diferente de propósito (`shopman-restore-drill`) — não use nome parecido com o
do cluster vivo.

### Custo do ensaio

| Item | Valor | Fonte |
|---|---|---|
| Menor plano de Managed Postgres (1 GiB RAM / 1 vCPU, 10–30 GiB) | **US$ 0,02254/h · US$ 15,15/mês** | [pricing da DO](https://www.digitalocean.com/pricing/managed-databases) |
| Degrau seguinte (2 GiB / 1 vCPU) | US$ 0,04531/h · US$ 30,45/mês | mesma página |
| Tráfego de/para o banco | não conta na franquia de banda | [pricing (docs)](https://docs.digitalocean.com/products/databases/postgresql/details/pricing/) |

**Ensaio de 1 hora no menor plano ≈ US$ 0,03. De uma tarde inteira (4h) ≈ US$
0,09.** É pro-rata por hora, e a tela de criação mostra o custo mensal e a
prorata horária antes de confirmar (fork-clusters).

Duas ressalvas honestas:

- Se o fork nascer **no mesmo plano do cluster de origem** em vez do menor, o
  custo é o daquele plano. O plano do `shopman-staging-postgres` não está
  medido aqui (o token desta máquina não lê database) — confira na tela antes
  de confirmar e escolha o menor plano explicitamente.
- A conversão hora↔mês acima é aritmética sobre os dois números da página de
  pricing (0,02254 × 672 h = 15,15), não uma frase da DO.

Isto atende a regra de custo da casa: **nenhum componente novo na DO sem provar
necessidade**. O cluster de ensaio é temporário por definição, custa centavos, e
o passo 4 é parte do procedimento — não uma boa intenção.

---

## 4. Quem faz o quê

### Um agente consegue fazer sozinho

- Ler o plano de migração de um banco cuja `DATABASE_URL` lhe foi dada
  (`make migrations-pending`, `make migrations-plan`) — é leitura.
- Classificar a mudança do deploy (aditiva / destrutiva / data migration).
- Escrever e testar a trava, o comando e este procedimento.
- Rodar as consultas de conferência do passo 3 e relatar as saídas.

### Exige a palavra ou a credencial do dono

| O quê | Por quê |
|---|---|
| **Gerar o token com escopo de database** | Credencial dele; os tokens desta máquina dão 403 em `doctl databases`. |
| **Aplicar o spec** (`doctl apps update`) para a trava sair do papel | Muda o ambiente vivo. ⚠️ Use `apps spec get` **com escopo de banco** como base e preserve os `EV[…]`: um spec reenviado sem os valores atuais [quebra o deploy inteiro](conferir-spec-digitalocean.md). |
| **Declarar `SHOPMAN_MIGRATION_BACKUP_REF`** antes de um deploy destrutivo | É a declaração de que o ponto de restauração foi anotado — é a palavra dele, não um default. |
| **Declarar `SHOPMAN_GO_LIVE=true`** no cutover | Arma a política do ADR-015 no ambiente. Item do [go-live-cutover](go-live-cutover.md) §6. |
| **Criar o cluster de ensaio** (`fork`) e **destruí-lo** | Cria e apaga recurso pago na conta dele. Custo na tabela acima. |
| **Reapontar o app para um cluster restaurado** | É a virada de chave de um incidente: muda o banco de produção. |
| **Destruir qualquer cluster que não seja o de ensaio** | Destrói os backups junto. Irreversível. |

---

## 5. Evidência mínima

Para o ensaio: data, cluster de origem, timestamp do PITR pedido, nome e UUID do
cluster criado, as quatro conferências do passo 3 com as saídas reais, a saída
de `make migrations-pending` contra o cluster restaurado, o horário do
`doctl databases delete` e o custo cobrado.

Para um deploy com migração destrutiva: a saída de `make migrations-pending`
antes do deploy, o valor de `SHOPMAN_MIGRATION_BACKUP_REF`, o trecho do log do
job `release` com o relato do `migration_safety`, e as contagens de referência
de antes e de depois.

---

## Referências

- [ADR-015 — backward-compat e migrations pós-produção](../decisions/adr-015-backward-compat-policy-post-prod.md)
- [production-upgrades.md](../guides/production-upgrades.md) — expand-contract, rollback por tipo de mudança
- [rollback-de-deploy.md](rollback-de-deploy.md) — o que fazer quando o deploy quebrou
- [go-live-cutover.md](go-live-cutover.md) — a virada de chave
- [backup-and-restore.md](../guides/backup-and-restore.md) — o cofre de dados curados (a outra camada)
- [conferir-spec-digitalocean.md](conferir-spec-digitalocean.md) — antes de `doctl apps update`
- [`shopman/shop/migration_safety.py`](../../shopman/shop/migration_safety.py) · [`migration_safety` (comando)](../../shopman/shop/management/commands/migration_safety.py) · [testes](../../shopman/shop/tests/test_migration_safety.py)
