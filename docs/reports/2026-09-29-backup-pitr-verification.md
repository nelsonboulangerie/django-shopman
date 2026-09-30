# Verificação somente leitura de backup e PITR

- `auditoria_id`: `R8-D1-BACKUP-PITR-2026-09-29`
- `janela_observada`: `2026-09-29T08:54:00Z`–`2026-09-29T09:08:24Z`
- `baseline_git`: `991f92fe63902da1bc2ca5eb5572b490e4031c9f`
- `ambiente_observado`: app DigitalOcean `shopman-nelson`, ainda no perfil
  técnico de staging
- `modo`: somente leitura; nenhum fork, restore, snapshot, cluster, conexão ao
  banco ou alteração de configuração foi criado

## Resultado

| Critério | Estado | Evidência sanitizada |
|---|---|---|
| Cluster PostgreSQL do ambiente observado | **VERIFICADO** | O app liga `DATABASE_URL` ao componente App Platform `postgres`. No mesmo contexto de conta, o único cluster PostgreSQL é `shopman-staging-postgres`: PostgreSQL 16, `nyc3`, `online`, uma instância, plano `db-s-1vcpu-1gb`. |
| Backup automático | **VERIFICADO** | A API oficial retornou 8 backups diários consecutivos, de `2026-09-22T00:13:28Z` a `2026-09-29T00:13:26Z`. O mais recente tinha aproximadamente 0,247 GB. |
| Retenção | **VERIFICADO** | A janela observada cobre os sete dias anteriores, coerente com o contrato oficial de retenção de 7 dias da DigitalOcean. |
| PITR | **VERIFICADO** | Para PostgreSQL gerenciado, a DigitalOcean mantém WAL e oferece restauração a qualquer instante dos 7 dias anteriores. A API não expõe uma flag separada: PITR é capacidade do serviço PostgreSQL com esses backups. |
| Ensaio recente de restore isolado | **NÃO VERIFICÁVEL / NO-GO** | Não existe artefato datado no repositório, cluster restaurado presente ou evento suficiente para provar um ensaio anterior. Um clone já excluído também não seria demonstrável pela listagem atual. |

Assim, o item **backup/PITR** deixa de ser desconhecido e passa a
**VERIFICADO para o ambiente técnico observado**. O gate separado de
**restore ensaiado** continua **NO-GO**: a existência do backup não prova que
a equipe mediu o tempo de recuperação e validou os dados restaurados.

Isto não verifica um futuro banco comercial diferente. Se o cutover trocar o
cluster, a mesma leitura deve ser repetida no cluster final imediatamente antes
da decisão de GO.

## Acesso e escopos

O 403 do pré-flight R8 era uma limitação do contexto usado, não evidência
de ausência de backup:

- `shopman-alpha-deploy` (contexto removido do doctl local em 30/09/2026) continua sem `database:read` e recebe 403 em
  `GET /v2/databases`;
- o contexto já existente `shopman-spec-update` acessa os mesmos apps e possui
  leitura de databases/backups; nenhum token ou valor secreto foi exibido;
- listar backups exige `database:read`, conforme a API oficial.

Para um ensaio real via fork, a documentação exige
`database:create`, `database:read`, `regions:read`, `sizes:read` e
`actions:read`; `database:view_credentials` é necessário para conectar e
validar o clone. A auditoria não tentou inferir permissão de escrita criando
recurso.

## Evidência reproduzível sem segredo

Os identificadores internos do app e do cluster foram resolvidos em memória e
não aparecem na saída. Os comandos abaixo são de leitura:

```bash
doctl --context shopman-spec-update apps list --output json
doctl --context shopman-spec-update databases list --output json
doctl --context shopman-spec-update databases get <cluster-id> --output json
doctl --context shopman-spec-update databases backups <cluster-id> --output json
doctl --context shopman-spec-update databases events list <cluster-id> --output json
```

Fontes do contrato do provedor:

- [restauração de PostgreSQL](https://docs.digitalocean.com/products/databases/postgresql/how-to/restore-from-backups/);
- [recursos de PostgreSQL](https://docs.digitalocean.com/products/databases/postgresql/details/features/);
- [limites de PostgreSQL](https://docs.digitalocean.com/products/databases/postgresql/details/limits/);
- [fork/PITR](https://docs.digitalocean.com/products/databases/postgresql/how-to/fork-clusters/);
- [API de backups](https://docs.digitalocean.com/reference/api/reference/databases/).

## Próximo gate mínimo

O owner deve autorizar explicitamente um fork temporário com custo, em ponto
UTC escolhido, e a sua remoção ao final. O ensaio precisa usar conexão direta,
comparar contagens e migrations com a origem, registrar RTO/RPO e guardar o
receipt sanitizado. Até isso acontecer, **não promover o gate de restore para
GO**.
