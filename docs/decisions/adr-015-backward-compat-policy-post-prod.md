# ADR-015 - Política de backward-compat e migrations pós-produção

**Status:** Accepted; ativa a partir do go-live (`git tag go-live-v1`)
**Data:** 2026-06-26
**Escopo:** migrations, renames, política de código pós-produção, WP-GAP-07

> O [WP-GAP-07](../plans/WP-GAP-07-pre-prod-migration-playbook.md) previa um
> `adr-011`; o número 011 já é `formula-and-cashshift`. Esta é a ADR equivalente,
> com o próximo número livre (015).

---

## Contexto

O projeto operou toda a fase de dev solo sob duas regras do `CLAUDE.md`:

- *"Zero residuals em renames — migrações serão resetadas."*
- *"Zero backward-compat aliases — projeto novo, sem consumidor externo legado."*

Ambas são corretas **enquanto não existe banco de produção com dado real**:
refactor é barato, migrations são descartáveis, não há cliente para quebrar.

No segundo em que existir um banco de produção da Nelson com pedidos, clientes,
ordens de produção e ledger de pagamento reais, essas duas regras passam a ser
**perigosas**: um `reset` apaga histórico, e remover um nome num único deploy
quebra qualquer leitura em voo (request, worker, sessão serializada).

Esta ADR formaliza a virada de política descrita no WP-GAP-07.

## Decisão

A virada **só vale a partir do go-live** (quando `git tag go-live-v1` for
aplicado). Antes disso, as regras atuais do `CLAUDE.md` seguem valendo.

### 1. Migrations são append-only pós go-live

- A última migration `reset`/`squash` é **evento único**, executada no go-live
  (WP-GAP-07). Depois dela, **nunca mais** `reset`.
- Toda mudança de modelo vira migration incremental versionada.
- **Nunca editar uma migration já aplicada em produção.** Correção é uma
  migration nova.

### 2. Backward-compat aliases permitidos em janela explícita

A partir do go-live, aliases/compat temporários são **permitidos** durante uma
janela de transição explícita (referência: 1 sprint), com:

- marcador no código `# DEPRECATED(remove by YYYY-MM-DD)` e
- TODO rastreável com prazo de remoção.

> **Atualização (2026-08-26):** o marcador é **por data**, não por versão. O
> projeto não versiona releases semânticas (o `version` do `pyproject.toml` é
> estático em `0.1.0`; deploy é contínuo), então `remove in v{version}` era um
> prazo que nunca chegava. O formato único aceito pelo gate é
> `# DEPRECATED(remove by YYYY-MM-DD)` — data vencida ou marcador fora desse
> formato reprovam a CI pós-go-live.

Isso habilita o padrão **expand-contract** para renames sem downtime (adicionar
o novo → backfill → migrar leituras/escritas → remover o antigo no deploy
seguinte). Detalhe operacional em
[`docs/guides/production-upgrades.md`](../guides/production-upgrades.md).

### 3. Renome de chave em `Session.data` / `Order.data`

JSONFields seguem o mesmo padrão expand-contract: data migration de backfill +
lookup condicional (lê chave nova, cai para a antiga) durante a janela, até a
remoção. Respeitar o contrato `CommitService._do_commit` (Core é sagrado).

### 4. O gate `make test-migrations`

[`scripts/check_migrations.py`](../../scripts/check_migrations.py) prova schema
limpo do zero + grafo consistente em todo deploy. A partir do go-live ganha o
replay de baseline (`SHOPMAN_MIGRATIONS_BASELINE`) — validar que o dado real
sobrevive ao upgrade.

## Enforcement

A política não é prosa: três checks na CI armam-se pela **existência da tag
`go-live-v1`** (antes dela, cada um é no-op verde com a linha de log
"pré-go-live: política ADR-015 inativa"). O job *Quality + deploy contract* do
Runtime Gate faz `git fetch` explícito da tag antes de rodá-los, porque o
checkout do runner é raso e sem tags.

1. **Migrations append-only** — [`scripts/check_adr015.py`](../../scripts/check_adr015.py)
   reprova o PR (ou merge group) cujo diff contra a base **modifica ou remove**
   arquivo existente em `*/migrations/`; só adição passa. Correção de migration
   aplicada é migration nova.
2. **Operação destrutiva exige marcador expand-contract** — dentro do
   [`scripts/check_migrations.py`](../../scripts/check_migrations.py)
   (`make test-migrations`, check `migrations.expand_contract`): migração
   adicionada **depois da tag** contendo `RemoveField`, `DeleteModel`,
   `RenameField`, `RenameModel` ou `AlterField` precisa declarar no próprio
   arquivo `# expand-contract: <fase> — <link do plano>`, com `<fase>` em
   {expand, backfill, migrate, contract} e o link apontando o plano/PR que
   agenda a fase contract ([production-upgrades.md](../guides/production-upgrades.md)).
3. **DEPRECATED com prazo** — o mesmo `check_adr015.py` varre os marcadores
   `# DEPRECATED(remove by YYYY-MM-DD)` no código rastreado e reprova prazo
   vencido ou marcador fora do formato.

Testes dos três caminhos: `shopman/shop/tests/test_adr015_gate.py`. Para
simular a política localmente sem tag: `SHOPMAN_ADR015_FORCE=1` (ou `0`).

## Consequências

- Refactor pós-prod fica mais caro e mais disciplinado — é o preço de ter dado
  real. O custo é intencional.
- Agentes futuros precisam saber que "zero backward-compat" foi **superado** no
  go-live; por isso o `CLAUDE.md` aponta para esta ADR.
- A janela de transição precisa de disciplina de remoção: alias sem prazo vira
  dívida permanente. O marcador `# DEPRECATED(remove by YYYY-MM-DD)` é
  obrigatório, não decorativo — e o gate da CI reprova prazo vencido.

## Referências

- [WP-GAP-07 pre-prod migration playbook](../plans/WP-GAP-07-pre-prod-migration-playbook.md)
- [GO-LIVE-READINESS-PLAN](../plans/GO-LIVE-READINESS-PLAN.md)
- [production-upgrades.md](../guides/production-upgrades.md)
