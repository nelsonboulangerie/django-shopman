# FASE 4 — Plano de squash de migrations (com coordenação)
> 2026-11-10 · Documento de PLANO, não execução

## Contexto (medido)
- shop/migrations: prefixos 0023–0039 duplicados (17 pares); backstage: 0036/0058/0065.
- JÁ allowlisted em LEGACY_PREFIX_COLLISIONS (check_migrations.py) e guardado para novas
  colisões (migration_prefix_check). Não é bug urgente; é dívida estacionada pré-go-live.
- 262 worktrees ativas + dezenas de branches: tocar migration agora colide com trabalho em voo.

## Plano
1. **Congelar as frentes de migration.** Coordenar (make inflight / BOARD) para que nenhuma
   frente esteja criando/renumerando migration no momento do squash. Janela curta, combinada.
2. **Baseline por app.** Para cada app com colisão: `makemigrations` gerando um único 0001_initial
   (ou squash) que reproduz o schema atual. Verificar `make test-migrations` (schema limpo do
   zero + grafo consistente).
3. **Remover as 17+3 duplicatas** e substituir pela baseline; apagar as entradas de
   LEGACY_PREFIX_COLLISIONS que deixarem de existir (o gate passa a cobrir só o que restar).
4. **Re-seed** (seed é regenerável) e rodar a suíte completa.
5. **PR único** com o squash + a limpeza do allowlist, para não fragmentar.

## Por que NÃO fazer às cegas (registrado)
- Squash sobre checkout defasado (65b658d3) + 262 worktrees = conflito garantido e risco de
  apagar migration de outra frente (o incidente de 12/08 e 19/08).
- O squash é pré-go-live e barato AGORA; após go-live vira expand-contract (ADR-015). Por isso
  entra antes, mas nunca por cima de trabalho alheio.

## Execução (F5, 11/11/2026)
O plano acima previa baseline `0001_initial` + reseed. Não foi assim: o banco do alpha vira
produção e não pode ser recriado nem reseedado sem a palavra do dono. O squash usa o
mecanismo nativo do Django (`replaces`), que vale sobre o banco que já rodou tudo.

- `shop.0023_squashed_0044_merge_marketing_excellence` substitui 39 migrations (os dois
  ramos 0023–0039, as 0040–0043 e a merge 0044). `backstage.0036_squashed_0066_merge_pos_concierge_identity_alerts`
  substitui 34 (os ramos 0036, 0058 e 0065 e as merges até 0066). Só as faixas com
  colisão: squash do app inteiro custaria portar ~50 RunPython e reescrever dezenas de testes
  de migração para ganhar segundos no `migrate` do zero (366 migrations levam ~21 s).
- As substituídas saíram do repositório na mesma PR; `replaces` fica. Banco que aplicou
  todas reconhece a squashada sem rodar nada e o `migrate` grava o nome dela.
- `LEGACY_PREFIX_COLLISIONS` ficou vazio: qualquer duplicata reprova.
- **Passo seguinte (etapa 3):** apagar `replaces` das duas squashadas, depois que o deploy
  desta PR rodou o `migrate` no alpha (o `django_migrations` dele passa a ter as duas linhas
  `*_squashed_*`). Sem isso, um banco que só tem os nomes antigos veria as squashadas como
  pendentes.
