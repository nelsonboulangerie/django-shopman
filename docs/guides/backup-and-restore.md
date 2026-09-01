# Backup e restore — as três camadas

O dado do Shopman tem duas naturezas, e cada uma tem a rede certa:

- **Transacional** (pedidos, ledger de estoque, livro-caixa, pagamentos,
  histórico importado): grande, imutável ou append-only, e sem sentido fora do
  banco. A rede é o **backup do Postgres** (camada 1).
- **Curadoria manual** (catálogo, receitas, fornecedores, custos, regras,
  canais, copy, promoções, de-paras do B.I.): pequena, preciosa e **não
  reconstruível** — é trabalho humano acumulado. A rede é o **cofre de dados
  curados** (camadas 2 e 3): legível, editável e restaurável por gente.

## Camada 1 — Postgres gerenciado (DigitalOcean)

Os clusters `shopman-headless-postgres` (prod) e `shopman-staging-postgres`
(alpha) são *managed databases* da DO: backup diário automático com retenção de
7 dias e point-in-time recovery. Não há nada a instalar — mas há duas
obrigações operacionais que **nenhum código cumpre por nós**:

```bash
doctl databases list
doctl databases backups <database-id>
```

1. **Conferir que os backups existem** (comando acima, de tempos em tempos).
2. **Testar um restore antes do go-live** (restore para um cluster novo,
   apontar um app de teste, abrir o Admin). Item aberto em
   `docs/runbooks/security-readiness.md`. Um backup nunca testado é uma
   esperança, não um backup.

Recuperação de desastre, rollback de migration destrutiva e cópia
prod → staging são desta camada — ver
[production-upgrades.md](production-upgrades.md) e
[docs/runbooks/rollback-de-deploy.md](../runbooks/rollback-de-deploy.md).

## Camada 2 — o cofre de dados curados

Um arquivo XLSX (ou diretório de CSVs) com **uma aba por entidade curada**,
identidade por **chave natural** (`ref`/`sku`/`code`/`key`), FKs e M2M
atravessando a planilha pela chave natural do alvo — nunca por id de banco.
Módulo: `shopman/shop/backup/` (registry + resources + workbook).

### Exportar

```bash
.venv/bin/python manage.py export_backup                # var/backups/backup-<data>.xlsx
.venv/bin/python manage.py export_backup --format csv   # um CSV por entidade (diff em git)
.venv/bin/python manage.py export_backup --only products,recipes
```

Num deploy sem shell, o gestor baixa o mesmo arquivo em
`GET /api/v1/backstage/backup/export/` (permissão fina
`backstage.export_backup`; superusuário já tem).

### Restaurar / aplicar

```bash
.venv/bin/python manage.py import_backup var/backups/backup-XXXX.xlsx           # dry-run: só relata
.venv/bin/python manage.py import_backup var/backups/backup-XXXX.xlsx --apply   # escreve
```

O import é um **upsert por chave natural**: cria o que não existe, atualiza o
que mudou, relata o que ficou igual. Ele **não apaga** linha nenhuma — remover
entidade é gesto de Admin, não de planilha. E falha fechado:

- **dry-run é o padrão** — sem `--apply`, nada é escrito;
- **aba desconhecida e coluna renomeada são erro**, antes de qualquer linha
  (o import-export ignoraria a coluna em silêncio; aqui ela grita);
- **cada linha passa por `full_clean()`** — choice inválido e constraint
  violada falham com o número da linha;
- **`--apply` é uma transação única** — erro em qualquer aba desfaz o arquivo
  inteiro; restore pela metade não existe;
- **em produção, `--apply` exige `--force`** (mesmo contrato do `seed`).

### O que entra, o que não entra

Entram as ~32 entidades registradas (a lista viva sai de
`export_backup --only nada` — o erro lista todas): catálogo Offerman completo
(produtos com `metadata` fiscal/social e `keywords`, listings, preços,
coleções, componentes), receitas, fornecedores/insumos/conversões/custos,
canais, regras, promoções/cupons, zonas de entrega, copy, templates, campanhas,
de-paras do B.I., vocabulário de consumo e salão.

Ficam fora, de propósito:

- **`Shop.integrations`** — segredos de gateway não entram em planilha que
  circula. Backup de segredo é o spec do deploy + o cofre de senhas do dono.
- **Clientes e fidelidade** — PII/LGPD; a rede deles é a camada 1.
- **Transacional** (pedidos, moves, caixa, work orders, tickets) — idem.
- **Credenciais** (doorman) — efêmeras por natureza.

### Estender o cofre

Entidade nova = um `ModelResource` com `import_id_fields` de chave natural +
uma chamada `registry.register(nome, Resource, tier=N)` no `ready()` do app
(tier = ordem de import; referencie só tiers menores). O backstage registra as
dele em `shopman/backstage/backup_resources.py` — backstage importa shop,
nunca o contrário. Testes de contrato em `shopman/shop/tests/test_backup.py`.

## Camada 3 — Google Sheets (e migração assistida)

O XLSX do cofre **é** a integração com o Sheets, sem API, credencial ou
dependência nova: `drive.google.com` → upload → o arquivo abre com uma aba por
entidade, editável. Para voltar: **Arquivo → Fazer download → .xlsx** e
`import_backup` (dry-run primeiro, sempre).

Esse ciclo cobre os três usos que motivaram o cofre:

1. **Backup periódico da curadoria** — baixar do endpoint do backstage e
   guardar no Drive;
2. **Correção/manipulação consciente em massa** — editar no Sheets com
   fórmulas e olhos humanos, conferir no dry-run, aplicar;
3. **Migração** — exportar de um ambiente, importar no outro. Chaves naturais
   tornam o arquivo portável; as poucas abas chaveadas por `id` (zonas,
   campanhas, conversões) preservam os ids no restore, então o arquivo inteiro
   permanece consistente também num banco vazio.

Push automático para o Drive (service account + agendamento no
`maintenance_worker`) é uma extensão possível e deliberadamente adiada: exige
credencial Google no deploy, e o ganho sobre "o gestor baixa e solta no Drive"
é pequeno enquanto a casa é uma.
