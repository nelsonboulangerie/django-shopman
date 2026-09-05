# Referência de Management Commands

> Gerado a partir dos arquivos em `management/commands/` do código atual.

---

## Visão Geral

| Comando | App | Categoria | Descrição |
|---------|-----|-----------|-----------|
| [`release_expired_holds`](#release_expired_holds) | stockman | Manutenção | Libera holds expirados |
| [`compute_product_affinity`](#compute_product_affinity) | shop | Manutenção | Recalcula o que a casa vende junto (cestas do ano, lift) — segura a própria cadência |
| [`propose_product_attributes`](#propose_product_attributes) | shop | Catálogo | Propõe natureza, sabor e temperatura pela coleção primária, para o gestor revisar |
| [`sweep_orphan_holds`](#sweep_orphan_holds) | shop | Manutenção | Libera holds indefinidos órfãos (sem sessão viva ou com data passada) |
| [`sweep_dead_production_stock`](#sweep_dead_production_stock) | shop | Manutenção | Zera pelo ledger o resíduo de processo (target vencida) de WOs mortas |
| [`load_crafting_demo`](#load_crafting_demo) | craftsman | Seed | Carrega dados demo de produção |
| [`bootstrap_recipe_book`](#bootstrap_recipe_book) | craftsman | Seed | Cria no inventário uma receita (versão 1 publicada) para cada ficha que ainda não tem — idempotente |
| [`export_recipe_book_schema`](#export_recipe_book_schema) | backstage | Dev | Regenera o espelho TypeScript do contrato do inventário de receitas (Produção) |
| [`process_directives`](#process_directives) | orderman | Worker | Processa fila de directives |
| [`bootstrap_whatsapp_channel`](#bootstrap_whatsapp_channel) | shop | Operação | Cria/ativa o canal de venda `whatsapp` (e o listing) do concierge no banco vivo, sem reseed |
| [`cleanup_idempotency_keys`](#cleanup_idempotency_keys) | orderman | Manutenção | Remove chaves de idempotência antigas |
| [`customers_cleanup`](#customers_cleanup) | guestman | Manutenção | Remove eventos processados antigos |
| [`auth_cleanup`](#auth_cleanup) | doorman | Manutenção | Remove tokens/códigos expirados |
| [`recalculate_customer_insights`](#recalculate_customer_insights) | shop | Manutenção | Recalcula os insights vencidos por recência — percebe quem PAROU de comprar (1x/dia, madrugada) |
| [`reconcile_payments`](#reconcile_payments) | shop | Operação | Reconcilia pedidos cujo webhook de pagamento pode ter sido perdido |
| [`diagnose_remote_order`](#diagnose_remote_order) | shop | Operação | Diagnostica pedido remoto preso lendo fontes canônicas |
| [`fiscal_audit_catalog`](#fiscal_audit_catalog) | shop | Operação | Lista vendáveis publicados sem classificação fiscal completa (NFC-e) |
| [`check_catalog_visibility`](#check_catalog_visibility) | shop | Manutenção | Alerta produto que sumiu do cardápio porque a coleção dele foi desativada |
| [`inject_ifood_order`](#inject_ifood_order) | shop | Dev | Injeta pedido iFood simulado pela ingestão canônica (apenas DEBUG) |
| [`reconcile_financial_day`](#reconcile_financial_day) | backstage | Operação | Reconcilia pedido, intent, transação e fechamento diário |
| [`smoke_gateways`](#smoke_gateways) | backstage | Operação | Estressa webhooks/gateways com fixtures locais e matriz sandbox |
| [`omotenashi_qa`](#omotenashi_qa) | backstage | QA | Lista matriz manual QA Omotenashi com evidências do seed |
| [`ingest_yooga`](#ingest_yooga) | backstage | B.I. | Aterrissa o export do Yooga em `HistoricalSale`, por lote (hash, validação, uma transação) |
| [`suggest_aliases`](#suggest_aliases) | backstage | B.I. | Propõe de-paras (produto, categoria, forma de pagamento) a partir do histórico; nunca confirma |
| [`refresh_bi_daily_series`](#refresh_bi_daily_series) | backstage | B.I. | Recomputa a série diária materializada (últimos dias no worker; `--all` do início) |
| [`evaluate_bi_alerts`](#evaluate_bi_alerts) | backstage | B.I. | Avalia os alarmes do B.I. (regras no Admin) e avisa o operador quando disparam |
| [`release-readiness`](#release-readiness) | script | Release | Consolida checks locais e bloqueios externos |
| [`export_backup`](#export_backup) | shop | Dados | Exporta o cofre de dados curados (XLSX/CSVs, uma aba por entidade) |
| [`import_backup`](#import_backup) | shop | Dados | Importa o cofre de volta — dry-run por padrão, `--apply` numa transação única |
| [`export_backup_to_drive`](#export_backup_to_drive) | shop | Dados | Banco → Drive: sobe o cofre como Sheets nativo, atualizando no lugar |
| [`import_backup_from_drive`](#import_backup_from_drive) | shop | Dados | Drive → banco: baixa a planilha curada e emenda no `import_backup` (dry-run por padrão) |
| [`convert_material_base_unit`](#convert_material_base_unit) | shop | Dados | Troca a unidade-base de um insumo e reexpressa tudo que o conta (ensaio por padrão) |
| [`seed`](#seed) | shop | Seed | Popula banco com dados da Nelson Boulangerie |
| [`refresh_seed_dates`](#refresh_seed_dates) | config | Seed | Re-ancora um banco SEMEADO em hoje (QA; recusa produção) |
| [`qa_scenarios`](#qa_scenarios) | config | Seed | Arma cenários de vitrine (esgotado, pausado, previsto) num banco SEMEADO, sem reseed |

---

## Detalhes

### release_expired_holds

**App:** `shopman.stockman`
**Arquivo:** `packages/stockman/shopman/stockman/management/commands/release_expired_holds.py`

Libera bloqueios de estoque que ultrapassaram o TTL configurado (`STOCKMAN.HOLD_TTL_MINUTES`).

| Flag | Default | Descrição |
|------|---------|-----------|
| `--dry-run` | — | Mostra quantos holds seriam liberados sem executar |

```bash
# Verificar holds expirados
python manage.py release_expired_holds --dry-run

# Liberar holds expirados
python manage.py release_expired_holds
```

**Recomendação:** Executar via cron a cada 5–15 minutos.

---


### refresh_seed_dates

Re-ancora um banco **semeado** em hoje, sem reseed e sem tocar na história —
o antídoto para o ambiente de QA envelhecido (26/08: alpha com insumo zerado,
409 `material_shortage` em todo finish, nenhuma fornada do dia).

```bash
python manage.py refresh_seed_dates            # só mostra o que faria
python manage.py refresh_seed_dates --apply    # executa
```

Uma âncora de relógio (`timezone.localdate()`), lida uma vez. Repõe **até o
alvo, só o delta**: despensa de insumos (`material_opening_targets()`, a mesma
fonte do seed), mise en place, vitrine e lotes de "sobra de ontem"; avança
feriados que ficaram no passado; cancela (VOID) fornadas planejadas
seed/refresh que apodreceram e planta o horizonte planejado de hoje a +7 no
`PRODUCTION_PLAN` calibrado, com `production_changed` para os dias futuros
virarem estoque planejado. **Não** apaga história, **não** recria a narrativa
demo do dia e **recusa `SHOPMAN_ENVIRONMENT=production` sem flag de override**.
Idempotente: a segunda passada no mesmo dia responde "Nada a fazer".

### qa_scenarios

Arma os estados de **disponibilidade da vitrine** num banco já semeado, para QA
manual. O perfil `qa` do `seed` já nasce com eles, mas chegar lá custa
`seed --flush`; e o alpha roda o perfil `demo`, em que todo produto tem estoque
— então o "Avise-me" não tinha como aparecer na tela para ser testado.

```bash
python manage.py qa_scenarios                     # relatório (não escreve)
python manage.py qa_scenarios --arm               # arma todos os cenários
python manage.py qa_scenarios --arm sold_out      # arma só um
python manage.py qa_scenarios --arm sold_out=BF   # ... num SKU escolhido
python manage.py qa_scenarios --restock BF        # repõe → dispara o "Avise-me"
python manage.py qa_scenarios --reset             # devolve tudo ao alvo do seed
python manage.py qa_scenarios --reset BF          # ... incluindo um SKU pausado à mão
```

| Estado | Como | O que aparece na loja |
|--------|------|-----------------------|
| `sold_out` | sem pronto, sem plano | "Indisponível" + sino **"Avise quando voltar"** |
| `low_stock` | 2 prontos (limiar 5) | badge "Últimas unidades", ainda vende |
| `planned` | sem pronto hoje, fornada amanhã | indisponível hoje, orderável ao escolher data futura |
| `paused` | `Product.is_sellable=False` | aparece, não vende, **sem** sino |
| `paused_channel` | `ListingItem.is_sellable=False` na vitrine `web` | pausado só na loja; segue vendável no PDV |

Os estados são armados pela **mesma função** que o perfil `qa` usa
(`seed.apply_storefront_state`) — o cenário testado à mão é o cenário que a
suíte afirma. O relatório fecha toda execução — sobre os SKUs padrão **e** sobre o que aquela
execução mirou —, com a coluna "amanhã" separando `sold_out` de `planned` (os
dois são `unavailable` com zero pronto) e a lista de avisos pendentes com
telefone mascarado. O `--reset` reencontra sozinho todo SKU que o comando já
mexeu (rastro no `reason` do `Move`); só a **pausa** precisa do SKU nomeado,
porque pausar não gera movimento de estoque.

⚠️ `--restock` é um `Move` de entrada de verdade, igual ao que a fornada faz:
**quem estiver inscrito recebe a mensagem no telefone que informou**. É esse o
teste; só não use com número de terceiro. Recusa
`SHOPMAN_ENVIRONMENT=production` sem flag de override.

### sweep_orphan_holds

**App:** `shopman.shop`
**Arquivo:** `shopman/shop/management/commands/sweep_orphan_holds.py`

Backstop para holds INDEFINIDOS (`expires_at IS NULL` — planejados/demanda, AVAILABILITY-PLAN §8),
que nunca caem no `release_expired_holds`. Libera, com `OperatorAlert`, holds cuja referência é
sessão sem Session aberta (morta/committed/deletada) ou cuja `target_date` já passou. Nunca toca
reservas de produção (`purpose=workorder`) nem holds adotados por pedido (`order:<ref>`).
Roda no ciclo do `maintenance_worker`, entre `cleanup_stale_sessions` e `cleanup_stale_planning`.

| Flag | Default | Descrição |
|------|---------|-----------|
| `--dry-run` | — | Lista os holds candidatos sem liberar |

```bash
python manage.py sweep_orphan_holds --dry-run
python manage.py sweep_orphan_holds
```

---

### sweep_dead_production_stock

**App:** `shopman.shop`
**Arquivo:** `shopman/shop/management/commands/sweep_dead_production_stock.py`

Zera pelo ledger (`stock.adjust`, nunca delete) quants em posição de PROCESSO (ou lote
`started`) com `target_date` vencida cuja WorkOrder está MORTA — void com o ajuste do handler
falho, ou quant órfão sem WO. Esse resíduo conta como `in_production` no `total_promisable`
(estoque fantasma prometido ao cliente até a shelf-life vencer). A janela é "WO morta", nunca
idade: quant de WO viva (planned/started) é matéria de finish tardio e quem cobra é o alerta
`production_unfinished`; quant de WO `finished` com o ledger aberto é território do
`sweep_unrealized_production`; quant com hold ativo espera os liberadores de hold. Roda no
ciclo do `maintenance_worker`, logo depois do `sweep_unrealized_production`.

| Flag | Default | Descrição |
|------|---------|-----------|
| `--dry-run` | — | Lista os quants que seriam zerados sem escrever no ledger |

```bash
python manage.py sweep_dead_production_stock --dry-run
python manage.py sweep_dead_production_stock
```

---

### load_crafting_demo

**App:** `shopman.craftsman`
**Arquivo:** `packages/craftsman/shopman/craftsman/management/commands/load_crafting_demo.py`

Cria dados de demonstração para produção: 4 receitas de padaria (croissant, pão francês, baguette, brioche) com BOM de ingredientes e work orders distribuídas em 10 dias.

| Flag | Default | Descrição |
|------|---------|-----------|
| `--clear` | — | Limpa dados existentes antes de carregar |

```bash
# Carregar dados demo
python manage.py load_crafting_demo

# Limpar e recarregar
python manage.py load_crafting_demo --clear
```

---

### convert_material_base_unit

Troca a **unidade-base** de um insumo num banco já povoado e reexpressa, na mesma
transação, tudo que conta aquele insumo: ledger (`Move`, `Quant`), reservas, alertas de
mínimo, fichas técnicas, o BOM congelado das fornadas **abertas**, o mínimo do Compras e o
custo por fornecedor. Fecha deixando a unidade antiga cadastrada como `MaterialConversion`,
para a nota fiscal seguinte não travar (ADR-024 R4).

**Ensaio por padrão** (como o `refresh_seed_dates`): sem `--apply` ele só relata.

```bash
python manage.py convert_material_base_unit LEITE AZEITE --to kg              # ensaio
python manage.py convert_material_base_unit LEITE AZEITE --to kg --apply      # executa
python manage.py convert_material_base_unit AGUA-FILTRADA --to kg --apply --no-bridge
```

O fator sai da física (`shopman.utils.units`) quando a dimensão é a mesma, e da
`density_g_per_ml` declarada no cadastro quando atravessa volume↔massa. **Sem densidade
declarada ele recusa**, nomeando o que cadastrar; contagem não atravessa nunca. É genérico:
não conhece SKU da Nelson nem tem tabela de densidade embutida.

`--no-bridge` converte sem deixar a conversão para trás. É para insumo que **não entra por
nota** (água de torneira): a ponte só viraria anotação sem informação na tela de separação.

O que ele deliberadamente **não** reescreve, e anuncia a cada rodada: item de fornada já
concluída, a prova de conversão no `Move.metadata`, a `RecipeVersion` publicada do livro de
receitas, o snapshot do `DayClosing` e os `params` de regra. História não se reescreve.

⚠️ **Depois de rodar, re-exporte o cofre** (`export_backup`): uma planilha anterior
reimportada escreve a unidade antiga por cima, e como ela reverte cadastro e ficha juntos,
os dois voltam a concordar e nada grita — só o saldo fica errado. Ver
[WP-BASE-UNIT-LIQUIDS-KG](../plans/WP-BASE-UNIT-LIQUIDS-KG.md).

### bootstrap_recipe_book

Percorre as `Recipe` (fichas de execução) e cria, para cada uma que ainda não tem, uma
`RecipeEntry` com a versão 1 **publicada** e `source.kind="ficha"` — o inventário das
fichas que já existem (ADR-027). A fórmula nasce na forma **base**: partes com ficha
própria (levain, pasta autolisada, yudane) são dissolvidas e sua farinha entra na soma.
Ordem por dependência (partes antes das massas que as usam). **Não escreve na `Recipe`**.

```bash
python manage.py bootstrap_recipe_book             # cria o que falta
python manage.py bootstrap_recipe_book --dry-run   # só conta
```

Idempotente: entry com o mesmo `ref` é pulada. O `seed` chama isto no fim das receitas.

### export_recipe_book_schema

Renderiza as dataclasses de `shopman/backstage/projections/recipe_book.py` em
`surfaces/production-nuxt/app/generated/recipeBookContract.ts`. Mesmo padrão do
`export_production_schema`; o teste de deriva `test_recipe_book_schema_export` falha
quando o arquivo gerado está velho.

```bash
python manage.py export_recipe_book_schema
```

### process_directives

**App:** `shopman.orderman`
**Arquivo:** `packages/orderman/shopman/orderman/management/commands/process_directives.py`

Processa directives enfileiradas usando os handlers registrados. Implementa row-level locking (`skip_locked`), retry com backoff exponencial, e reaping de directives "stuck".

| Flag | Default | Descrição |
|------|---------|-----------|
| `--topic` | *(todos)* | Tópico específico para processar (repetível) |
| `--limit` | `50` | Máx. directives por execução |
| `--watch` | — | Modo contínuo (loop simples) |
| `--interval` | `2` | Segundos entre iterações no modo watch |
| `--max-attempts` | `5` | Máx. tentativas antes de marcar como falha |
| `--reap-timeout` | `10` | Minutos para considerar directive "stuck" |

```bash
# Processar uma vez
python manage.py process_directives

# Modo worker contínuo
python manage.py process_directives --watch

# Processar apenas stock e payment
python manage.py process_directives --topic stock.hold --topic payment.capture

# Worker com configuração customizada
python manage.py process_directives --watch --interval 5 --limit 100 --max-attempts 3
```

**Veja também:** [ADR-003 — Directives sem Celery](../decisions/adr-003-directives-sem-celery.md)

---

### bootstrap_whatsapp_channel

**App:** `shopman.shop`
**Arquivo:** `shopman/shop/management/commands/bootstrap_whatsapp_channel.py`

Põe de pé, no banco vivo, o canal de venda dos pedidos do [concierge de WhatsApp](../guides/whatsapp-concierge.md):
`Channel` ref `whatsapp` (pagamento `["pix","card"]` a `at_commit`, confirmação `auto_confirm` em 5 min)
e o listing `whatsapp` espelhando o da web. Idempotente: cria o que falta, ativa o que está inativo,
não sobrescreve config existente. É o equivalente ao que o `seed` faz num banco novo, para quem
não pode reseedar (produção/alpha).

```bash
python manage.py bootstrap_whatsapp_channel
```

**Veja também:** [WHATSAPP-CONCIERGE-PLAN](../plans/WHATSAPP-CONCIERGE-PLAN.md)

---

### cleanup_idempotency_keys

**App:** `shopman.orderman`
**Arquivo:** `packages/orderman/shopman/orderman/management/commands/cleanup_idempotency_keys.py`

Remove IdempotencyKeys expiradas ou antigas. Limpa 3 categorias: keys com `expires_at` passado, keys antigas (done/failed), e opcionalmente keys "in_progress" órfãs (> 1h).

| Flag | Default | Descrição |
|------|---------|-----------|
| `--days` | `7` | Remove keys mais antigas que N dias |
| `--dry-run` | — | Mostra o que seria removido |
| `--include-in-progress` | — | Inclui keys "in_progress" órfãs (> 1h) |

```bash
# Preview
python manage.py cleanup_idempotency_keys --dry-run

# Cleanup padrão (7 dias)
python manage.py cleanup_idempotency_keys

# Cleanup agressivo incluindo keys órfãs
python manage.py cleanup_idempotency_keys --days 3 --include-in-progress
```

**Recomendação:** Executar via cron diariamente.

---

### customers_cleanup

**App:** `shopman.guestman` (app label: `guestman`)
**Arquivo:** `packages/guestman/shopman/guestman/management/commands/customers_cleanup.py`

Remove ProcessedEvent mais antigos que o threshold configurado (`GUESTMAN.EVENT_CLEANUP_DAYS`, default 90 dias).

| Flag | Default | Descrição |
|------|---------|-----------|
| `--days` | *(da config)* | Override do threshold em dias |
| `--dry-run` | — | Mostra quantos eventos seriam removidos |

```bash
# Preview com default da config
python manage.py customers_cleanup --dry-run

# Cleanup com threshold custom
python manage.py customers_cleanup --days 30
```

**Recomendação:** Executar via cron semanalmente.

---

### auth_cleanup

**App:** `shopman.doorman` (app label: `doorman`)
**Arquivo:** `packages/doorman/shopman/doorman/management/commands/auth_cleanup.py`

Limpa artefatos de autenticação expirados: AccessLinks, VerificationCodes e TrustedDevices.

| Flag | Default | Descrição |
|------|---------|-----------|
| `--days` | `7` | Remove registros mais antigos que N dias |
| `--dry-run` | — | Mostra o que seria removido |

```bash
# Preview
python manage.py auth_cleanup --dry-run

# Cleanup padrão
python manage.py auth_cleanup

# Cleanup conservador
python manage.py auth_cleanup --days 30
```

**Recomendação:** Executar via cron diariamente.

---

### recalculate_customer_insights

O `CustomerInsight` é recalculado no `customer.ensure` de **cada pedido**, então quem
compra está sempre em dia. Quem **parou** de comprar não dispara nada — e ficava
congelado no dia da última visita. Esta varredura existe só para isso.

O que envelhece sozinho é apenas a parte derivada de recência
(`days_since_last_order`, `churn_risk`, `rfm_segment`). Contagem, ticket médio e
favorito só mudam com pedido novo, e esse caminho já está coberto.

**Cadência: 1x/dia, de madrugada.** A escada de recência do RFM é 7/30/90/180 dias
(`guestman/contrib/insights/conf.py`); nada se move em menos de um dia-calendário.

```bash
python manage.py recalculate_customer_insights            # varredura do ciclo
python manage.py recalculate_customer_insights --force    # ignora a janela
python manage.py recalculate_customer_insights --dry-run  # só conta os vencidos
python manage.py recalculate_customer_insights --all      # base inteira (backfill manual)
```

`--all` **recusa** `--dry-run`: `recalculate_all` não tem ensaio, e deixar o par passar
recalcularia a base inteira em silêncio para quem só queria contar.

Roda no `maintenance_worker`, depois do `check_directive_health`. Está no ciclo de 5
min mas **não trabalha a cada 5 min**: carrega a própria janela (03h–05h local) e o
próprio teto de lote (200 por execução). Três decisões valem registro:

- **Cliente sem nenhum pedido fica de fora.** Sem pedido, `r=1, f=1, m=1` cai em
  `lost` — carimbar "Perdido" em quem nunca comprou é mentira, não classificação.
  Para dar insight a cliente importado, use `--all` (ou a ação do CustomerAdmin).
- **Teto de lote porque o worker é serial.** Varrer a base inteira num ciclo atrasaria
  `reconcile_payments` e tudo atrás dela. A janela de 2h drena o resto, do insight mais
  velho para o mais novo.
- **A marca d'água é o próprio dado.** `calculated_at` é `auto_now`, então "quem está
  vencido" é uma query — não há estado novo para guardar nem para desincronizar, e noite
  perdida por worker fora do ar se resolve na noite seguinte.

---

### reconcile_payments

**App:** `shopman.shop`
**Arquivo:** `shopman/shop/management/commands/reconcile_payments.py`

Reconcilia pedidos `new`/`accepted` antigos com `PaymentIntent` quando o
webhook pode ter sido perdido. E idempotente e deve ser rodado primeiro em
`--dry-run` durante incidente.

| Flag | Default | Descrição |
|------|---------|-----------|
| `--since` | `2h` | Considera pedidos criados antes de N tempo (`30m`, `4h`, `1d`) |
| `--dry-run` | — | Lista a acao sem executar transicao |

```bash
# Preview seguro
python manage.py reconcile_payments --since=4h --dry-run

# Executar reconciliacao apos validar gateway/dry-run
python manage.py reconcile_payments --since=4h
```

**Veja também:** [runbook de pedido pago sem confirmacao](../runbooks/pedido-pago-sem-confirmacao.md).

---

### fiscal_audit_catalog

**App:** `shopman.shop`
**Arquivo:** `shopman/shop/management/commands/fiscal_audit_catalog.py`

Responde "quais vendáveis publicados estão fiscalmente incompletos?" — a pergunta
que precisa de resposta **antes** do primeiro dia de emissão obrigatória, e não a
cada nota recusada pela SEFAZ. Varre os produtos publicados+vendáveis em vitrine
ativa de canal de venda (`commerce_policy=order`) e valida a classificação pela
mesma função que o porteiro de publicação e o builder de itens usam
(`shopman.fiscalman.classification.validate_for_emission`): perfil + NCM de 8
dígitos, CEST obrigatório na revenda com ST.

Só lê. Não depende de adapter fiscal nem da chave
`SHOPMAN_FISCAL_REQUIRE_CLASSIFICATION_ON_PUBLISH` — serve justamente para saber
o que aconteceria ao ligar a chave na virada do go-live.

| Flag | Default | Descrição |
|------|---------|-----------|
| `--json` | — | Saída em JSON: `channels`, `ready_to_enforce` (o veredito) e `incomplete` com os erros |
| `--strict` | — | Exit code 1 quando o catálogo não estiver pronto (gate de deploy/CI) |

`--strict` é o **pré-requisito documentado** para ligar
`SHOPMAN_FISCAL_REQUIRE_CLASSIFICATION_ON_PUBLISH`. Ele sai 1 em **duas**
situações, não uma:

1. há vendável publicado com classificação incompleta; **ou**
2. não há canal de venda ativo — a auditoria não varreu nada, logo não atesta nada.

A segunda condição existe porque só ela é satisfeita à toa: sem ela, bastaria rodar
o gate contra um banco sem canal configurado para colher um verde que não significa
"pronto para emitir". Em JSON, o mesmo veredito é `ready_to_enforce`.

```bash
# Leitura humana
python manage.py fiscal_audit_catalog

# Gate antes de ligar a emissão obrigatória
python manage.py fiscal_audit_catalog --strict
```

**Veja também:** [procedimento do flip](settings.md#ligar-o-porteiro-fiscal-do-catálogo) ·
[parametrização fiscal NFC-e](fiscal-parametrizacao-nfce.md) ·
[auditoria do catálogo (19/08)](../reports/auditoria-catalogo-fiscal-2026-08-19.md).

---

### check_catalog_visibility

**App:** `shopman.shop`
**Arquivo:** `shopman/shop/management/commands/check_catalog_visibility.py`

**Propósito:** Avisar o operador sobre o produto que sumiu do cardápio sem ninguém ter
escondido nada. O agrupamento do cardápio põe o produto no grupo de cada coleção **ativa**
e recolhe no fim quem não tem coleção **nenhuma**; quem tem só coleção **desativada** não
cabe em nenhum dos dois e some da loja inteira — publicado, na vitrine, com preço e com
estoque. A política do cardápio não muda: o comando só torna o estado visível.

A regra de detecção mora em `shopman/shop/services/catalog_visibility.py` e é a mesma que
marca a linha do produto no Gestor (`hidden_by_inactive_collection` na matriz do catálogo).

**Uso:**
```bash
python manage.py check_catalog_visibility
python manage.py check_catalog_visibility --hours 12   # janela do dedupe
python manage.py check_catalog_visibility --dry-run    # só reporta
```

**Alerta:** `catalog_hidden_by_inactive_collection` (severidade `warning`), com os SKUs
nomeados (os 8 primeiros e "e mais N") e as coleções a reativar. É alerta de **estado**, não
de evento: o dedupe é a lista de coleções presas, numa janela de 24h que conta também os
alertas já reconhecidos — um aviso enquanto o estado durar, não um por varredura. Coleção
diferente desativada é fato novo e alerta novo. Roda no `maintenance_worker`, depois do
`check_directive_health`.

---

### diagnose_remote_order

**App:** `shopman.shop`
**Arquivo:** `shopman/shop/management/commands/diagnose_remote_order.py`

Diagnostica um pedido remoto especifico lendo `Order`, Payman, Directives,
Stockman holds, channel policy e projection conversacional. O comando nao altera estado; ele imprime `result=OK/WARN/FAIL` e `recommendation=...`.

| Argumento | Descrição |
|-----------|-----------|
| `ref` | `Order.ref` do pedido remoto |

```bash
python manage.py diagnose_remote_order ORDER-REF
```

**Veja também:** [runbook de pedido remoto preso](../runbooks/pedido-remoto-preso.md).

---

### inject_ifood_order

**App:** `shopman.shop`
**Arquivo:** `shopman/shop/management/commands/inject_ifood_order.py`

Monta um payload iFood mínimo com o primeiro produto real do Offerman (para
passar as checagens de estoque/preço de ponta a ponta) e o ingere via
`ifood_ingest.ingest` no canal `ifood`. Ferramenta de dev, gated por DEBUG:
fora de `DEBUG=True` o comando falha. Substitui a antiga admin action
`inject_simulated_ifood_order` do ChannelAdmin.

```bash
python manage.py inject_ifood_order
```

---

### reconcile_financial_day

**App:** `shopman.backstage`
**Arquivo:** `shopman/backstage/management/commands/reconcile_financial_day.py`

Gera auditoria financeira diária cruzando pedidos, `PaymentIntent`,
`PaymentTransaction`, o livro-caixa (`cashman.Entry`) e `DayClosing`. Quando não
está em `--dry-run`, persiste o resumo em
`DayClosing.data["financial_reconciliation"]` e divergências em
`DayClosing.data["financial_reconciliation_errors"]`. Divergência `error` ou
`critical` cria alerta `payment_reconciliation_failed`.

Os checks por pedido somam os intents liquidados (um por **método** numa venda
mista do terminal, ADR-022) contra o total selado; intents sem gateway
(dinheiro, externo, pix/cartão atestados no balcão) passam pelas mesmas
invariantes que os de gateway. O check `cash_ledger_mismatch` cruza o dinheiro
em espécie do dia: `Σ capturas − Σ estornos` dos intents `cash` (pelo
`created_at` da transação) **==** `Σ Entry.amount_q` das linhas `sale`,
`cod_settled` e `refund` (pelo `at`). Na venda do PDV os dois nascem no mesmo
`atomic`, então COD conta no dia do **acerto** nos dois livros; `float_in`,
`cash_in`, `cash_out` e `count` ficam fora (mexem na gaveta, não são
pagamento). A saída humana ganha a linha `Dinheiro (Payman × livro-caixa)` e o
resumo persistido o campo `cash_ledger` (ver
[data-schemas](data-schemas.md#dayclosingdata)).

| Flag | Default | Descrição |
|------|---------|-----------|
| `--date` | ontem | Data local `YYYY-MM-DD` |
| `--dry-run` | — | Gera relatório sem persistir e sem alertar |
| `--require-closing` | — | Ausência de `DayClosing` vira erro |
| `--no-alert` | — | Persiste sem criar `OperatorAlert` |
| `--json` | — | Imprime JSON auditável |

```bash
# Preview seguro de uma data
make reconcile-financial-day date=2026-05-05 dry_run=1

# Rotina pós-fechamento, exigindo DayClosing
make reconcile-financial-day date=2026-05-05 require_closing=1

# JSON para anexar em incidente
python manage.py reconcile_financial_day --date=2026-05-05 --dry-run --json
```

**Veja também:** [runbook de pagamento divergente](../runbooks/pagamento-divergente.md).

---

### smoke_gateways

**App:** `shopman.backstage`
**Arquivo:** `shopman/backstage/management/commands/smoke_gateways.py`

Executa um smoke operacional de gateways usando fixtures locais com rollback:
Efí PIX duplicado e atrasado após cancelamento, Stripe capture/replay/refund
cumulativo fora de ordem e iFood pedido externo duplicado. Também reporta matriz
de prontidão sandbox/staging para Focus NFe homologação, Efí sandbox, Stripe
test e demais provedores, sem marcar provedor real como validado quando faltam
credenciais.

| Flag | Default | Descrição |
|------|---------|-----------|
| `--local-only` | — | Só executa fixtures locais |
| `--sandbox-only` | — | Só avalia credenciais/prontidão sandbox |
| `--require-sandbox` | — | Falha se sandbox estiver bloqueado |
| `--keep-data` | — | Não faz rollback das fixtures locais |
| `--json` | — | Imprime JSON auditável |

```bash
# Smoke local + matriz sandbox, com rollback
make smoke-gateways

# JSON para anexar em release/incidente
make smoke-gateways json=1

# Gate estrito de sandbox/staging real
make smoke-gateways-sandbox
```

Sem credenciais reais, `smoke-gateways-sandbox` retorna
`blocked_by_credentials`; isso é bloqueio honesto, não sucesso falso.

Para staging de POS, a matriz também bloqueia configurações perigosas: Focus NFe
em produção, Efí com `EFI_SANDBOX=false` ou Stripe com chaves `sk_live_` /
`pk_live_`.

---

### omotenashi_qa

**App:** `shopman.backstage`
**Arquivo:** `shopman/backstage/management/commands/omotenashi_qa.py`

Lista a matriz manual QA Omotenashi para mobile, tablet/KDS e desktop gerente,
apontando a URL a abrir e a evidência concreta criada pelo seed Nelson. O modo
estrito falha quando qualquer cenário não tem dado seed correspondente.

| Flag | Default | Descrição |
|------|---------|-----------|
| `--json` | — | Imprime JSON auditável |
| `--strict` | — | Falha se algum cenário estiver sem evidência |

```bash
# Depois do seed, verificar se a rodada manual está pronta
make omotenashi-qa strict=1

# JSON para anexar em release
make omotenashi-qa json=1
```

**Veja também:** [QA Manual Omotenashi E2E](../guides/omotenashi-qa.md).

---

### omotenashi-browser-qa

**Script:** `scripts/run_omotenashi_browser_qa.mjs`

Navega a matriz Omotenashi em Chrome headless usando DevTools Protocol, captura
screenshots por cenário e gera relatório JSON. O servidor Shopman precisa estar
rodando. Em localhost, o script cria uma sessão admin local automaticamente; em
staging/remoto, informe cookie autenticado via `SHOPMAN_SESSION_COOKIE` ou
`--session-cookie`.

| Variável/flag | Default | Descrição |
|---------------|---------|-----------|
| `strict=1` / `--strict` | — | Retorna erro se qualquer cenário ficar em `review` |
| `base_url=...` / `--base-url=...` | `http://127.0.0.1:8000` | Servidor Shopman a navegar |
| `matrix=...` / `--matrix=...` | saída de `omotenashi_qa --json` | Matriz JSON já gerada |
| `screenshots=...` / `--screenshots-dir=...` | `/tmp/shopman-omotenashi-qa-screens` | Destino das screenshots |
| `report=...` / `--report=...` | `/tmp/shopman-omotenashi-qa-browser.json` | Relatório JSON de saída |
| `SHOPMAN_CHROME_PATH` / `--chrome-path=...` | autodetectado | Binário Chrome/Chromium |

```bash
make run
make omotenashi-browser-qa strict=1
```

O target verifica login inesperado, overflow horizontal global e controles fora
da viewport fora de containers roláveis. Rails horizontais intencionais, como os
chips de categoria do cardápio mobile, são registrados sem virar falha.

---

### omotenashi-browser-ci

**Script:** `scripts/run_omotenashi_browser_ci.sh`

Gate reprodutível para CI/local: compila CSS, aplica migrations, recria o seed,
sobe servidor temporário, espera `/ready/` e roda `omotenashi-browser-qa` em modo
estrito. Ele encerra apenas o processo de servidor que criou.

| Variável/flag | Default | Descrição |
|---------------|---------|-----------|
| `port=...` / `SHOPMAN_QA_PORT` | `8001` | Porta local do servidor temporário |
| `SHOPMAN_QA_SERVER_LOG` | `/tmp/shopman-omotenashi-browser-ci-server.log` | Log do `runserver` temporário |

```bash
make omotenashi-browser-ci
make omotenashi-browser-ci port=8010
```

Esse alvo é destrutivo para o banco configurado no ambiente porque executa o
seed com flush. Use-o em ambiente local descartável ou CI.

---

### ingest_yooga

**Propósito:** Faz o export consolidado do Yooga (xlsx, abas `Vendas`/`Itens`/`Produtos`)
aterrissar em `HistoricalSale`/`HistoricalSaleItem`, **por lote** (`ImportBatch`).

**Uso:**
```bash
python manage.py ingest_yooga --file var/yooga-consolidado.xlsx
python manage.py ingest_yooga --file var/yooga-consolidado.xlsx --rebuild
```

**Comportamento (BI-DATA-FOUNDATION-PLAN, P0):**
- Um `ImportBatch` por arquivo (nome, sha256, contagens). **O mesmo arquivo não entra duas
  vezes**: hash já concluído nesta origem é recusa declarada (`CommandError`), não silêncio.
- Validação na fronteira: aba, coluna ou linha inválida é erro com nome da aba e número da
  linha, **nada é gravado**, e o lote fica registrado como `failed` com o motivo.
- Uma transação: vendas e itens entram juntos ou não entram.
- Idempotente e completável: chave natural = `pedido`; um export **novo** insere o que
  falta, completa `metadata` das vendas que já existiam (nunca sobrescreve) e grava itens só
  das vendas que ainda não têm.
- `--rebuild` apaga vendas, itens **e lotes** de `source=yooga` e recarrega do arquivo.
- Telefone do cliente entra só como hash + últimos 4 (`HistoricalSale.metadata`, ver
  data-schemas.md).

O arquivo não entra no git (`var/` é gitignored); o comando abre o xlsx em modo somente
leitura. Lotes e vendas são visíveis no Admin (grupo "B.I."), somente leitura.

### suggest_aliases

**Propósito:** Preenche a fila de curadoria dos de-paras do B.I. (`ProductAlias`,
`CategoryAlias`, `PaymentMethodAlias`) a partir do histórico carregado. **A máquina propõe, a
pessoa confirma** (Admin → B.I. → De-paras); só o confirmado entra na leitura.

**Uso:**
```bash
python manage.py suggest_aliases --dry-run
python manage.py suggest_aliases --source yooga --kind product --min-score 80
```

**Comportamento (BI-DATA-FOUNDATION-PLAN, P1):**
- Produto: SKU exato do catálogo antes de nome parecido (`rapidfuzz.token_set_ratio` sobre nome
  normalizado). Abaixo do corte, a linha entra **sem produto**, com o melhor palpite na nota — a
  fila mostra o que falta mapear. Linha do histórico sem SKU ganha alias pelo nome.
- Categoria e forma de pagamento: propõe só o valor cru que **nenhum trecho existente casa**, sem
  significado (a pessoa decide leitura/coleção ou forma canônica ao confirmar).
- Nunca sobrescreve: chave com alias em qualquer estado (inclusive rejeitado) é pulada.
- Idempotente; `--dry-run` não grava.

As regras **padrão** de categoria (23 trechos) e de forma de pagamento (15) não vêm daqui: vêm
do `seed` / `setup_bi_reference`, já confirmadas (curadoria do dono).

### refresh_bi_daily_series

**Propósito:** Recomputa `DailySalesFact`, a série diária de vendas **materializada** do B.I.
(BI-DATA-FOUNDATION-PLAN, P3), a partir da camada canônica. Uma linha por dia coberto —
dia sem venda entra com zero vendas (presença = cobertura); o leitor (`sales_series.daily_sales`)
só usa a tabela quando a janela está inteira coberta e cai para o cálculo ao vivo se não.

**Uso:**
```bash
python manage.py refresh_bi_daily_series            # últimos 3 dias (o que o worker roda)
python manage.py refresh_bi_daily_series --all      # zera e recomputa do primeiro dia com venda
python manage.py refresh_bi_daily_series --from 2026-08-01 --to 2026-08-18
```

Roda sozinho no `maintenance_worker` (ciclo de 300 s), no fim do `ingest_yooga` (`--all`) e no
fim do `seed`. Recomputável do zero em segundos; nada aqui é fonte de verdade.

### evaluate_bi_alerts

**Propósito:** Avalia cada `BIAlertRule` ativa contra a camada de leitura do B.I.
(BI-DATA-FOUNDATION-PLAN §7.2) e, quando dispara, cria um `OperatorAlert` (o bus de alertas com
reconhecimento) + um `BIAlertEvent` (trilha append-only). Respeita o **cooldown** obrigatório
de cada regra: mede e registra a cada ciclo, mas não avisa de novo antes do silêncio configurado.

**Uso:**
```bash
python manage.py evaluate_bi_alerts
```

**Métricas:** `import_silence` (a origem deveria receber lote concluído a cada N dias e não
recebeu — lote que falhou não conta); `daily_revenue_vs_baseline` (faturamento de **ontem** abaixo
de X% da média do mesmo dia da semana nas últimas N semanas, fora dos dias fechados/atrapalhados;
com menos de 3 dias parecidos a regra **não opina**); `native_overrides_history` (nos últimos N
dias, um dia com até K pedidos nativos apagou mais de M vendas históricas — o guard da fusão,
lido de `DailySalesFact.historical_dropped`); `cash_variance_by_operator` (|Σ quebra| de algum
operador acima da régua em centavos na janela — **apuração**: o aviso ao operador não carrega
nome nem valor, o detalhe fica no disparo e só quem tem `cashman.audit_shift` o vê no Admin);
`curation_pending` (no último lote concluído da origem, % de linhas sem de-para de produto
confirmado acima da régua). Roda no `maintenance_worker` depois do
`refresh_bi_daily_series`. As regras padrão vêm do `seed`/`setup_bi_reference` (a de importação
nasce desligada: o export do Yooga é único até hoje).

## Wrappers de diagnóstico

Os diagnosticos operacionais vivem em `scripts/diagnose_operational.py` e sao
expostos por Makefile para nao exigir conhecimento de Docker:

```bash
make diagnose-runtime
make diagnose-worker
make diagnose-payments
make diagnose-webhooks
make diagnose-health
```

Saida `FAIL` significa acao operacional pendente. Ver
[`docs/runbooks/`](../runbooks/README.md).

---

### release-readiness

**Script:** `scripts/check_release_readiness.py`

Consolida a prontidão de piloto/release em uma saída única. O alvo roda checks
locais leves e reporta bloqueios externos sem fingir validação real. O script
tem perfis: `pilot` (historico), `alpha` (staging tecnico com mocks
explicitos) e `production` (go-live real, sem affordances de teste):

- `django check`;
- migrations pendentes;
- matriz seed Omotenashi;
- smoke local de gateways com rollback;
- prontidão sandbox/staging de gateways;
- evidência manual/física Omotenashi;
- URL/ambiente de pre-prod.

Por padrão, bloqueios externos são informativos e o comando retorna sucesso se
os checks locais passaram. Em modo estrito, bloqueios externos também falham.

| Variável/flag | Default | Descrição |
|---------------|---------|-----------|
| `json=1` / `--json` | — | Imprime JSON auditável |
| `profile=...` / `--profile=...` | `pilot` | `pilot`, `alpha` ou `production` |
| `manual_qa=...` / `--manual-qa-evidence=...` | `SHOPMAN_MANUAL_QA_EVIDENCE` | Relatório manual/físico de QA |
| `preprod_url=...` / `--preprod-url=...` | `SHOPMAN_PREPROD_URL` | URL de staging/pre-prod |
| `--strict-external` | — | Falha também se gateway/manual/pre-prod estiver bloqueado |

```bash
# Local: mostra bloqueios externos sem falhar por eles
make release-readiness
make release-readiness json=1

# Alpha tecnico: aceita Pix/card mockados declarados, mas cobra staging, fiscal/iFood e URL
make alpha-readiness preprod_url=https://staging.example.com

# Release real: exige credenciais/staging/evidência física e remove switches de teste
make production-readiness manual_qa=docs/reports/manual-qa.md preprod_url=https://staging.example.com
make release-readiness-strict manual_qa=docs/reports/manual-qa.md preprod_url=https://staging.example.com
```

Use este alvo como contrato de honestidade: `passed_with_external_blockers`
significa que a árvore local está coerente, mas ainda não há prova de gateway
real, dispositivo físico ou staging.

O script serializa execuções concorrentes com lock de processo porque os smokes
locais escrevem no banco durante transações com rollback. Isso evita falso
negativo `database is locked` quando dois operadores ou automações disparam o
readiness ao mesmo tempo em SQLite local.

---

### export_backup

**App:** `shopman.shop`
**Arquivo:** `shopman/shop/management/commands/export_backup.py`

Exporta o cofre de dados curados — as entidades não reconstruíveis (catálogo,
receitas, fornecedores/custos, regras, canais, copy, promoções, de-paras do
B.I.) — para um XLSX com uma aba por entidade, identidade por chave natural.
Guia completo: [backup-and-restore.md](../guides/backup-and-restore.md).

| Flag | Default | Descrição |
|------|---------|-----------|
| `--out` | `var/backups` | Diretório de saída |
| `--format` | `xlsx` | `xlsx` (um arquivo) ou `csv` (um arquivo por entidade, diff em git) |
| `--only` | — | Entidades específicas, separadas por vírgula |
| `--with-transactional` | — | Inclui abas somente-leitura de conferência (pedidos, ledger, caixa, pagamentos, fornadas); o import as recusa |

```bash
python manage.py export_backup
python manage.py export_backup --format csv --only products,recipes
python manage.py export_backup --with-transactional
```

O mesmo arquivo sai por `GET /api/v1/backstage/backup/export/` (permissão
`backstage.export_backup`) — o caminho sem shell de um deploy.

---

### import_backup

**App:** `shopman.shop`
**Arquivo:** `shopman/shop/management/commands/import_backup.py`

Importa um arquivo do `export_backup` de volta — upsert por chave natural, sem
apagar nada. **Dry-run por padrão**; falha fechado em aba desconhecida, coluna
renomeada e linha inválida (`full_clean` por linha). `--apply` roda numa
transação única: qualquer erro desfaz o arquivo inteiro.

| Flag | Default | Descrição |
|------|---------|-----------|
| `--apply` | — | Escreve de verdade (sem isso, só relata) |
| `--only` | — | Entidades específicas |
| `--force` | — | Obrigatório para `--apply` em produção (mesmo contrato do `seed`) |

```bash
python manage.py import_backup var/backups/backup-20260901-090000.xlsx
python manage.py import_backup var/backups/backup-20260901-090000.xlsx --apply
```

---

### export_backup_to_drive

**App:** `shopman.shop`
**Arquivo:** `shopman/shop/management/commands/export_backup_to_drive.py`

**Banco → Drive.** Sobe o cofre como planilha **Google Sheets nativa**,
atualizando sempre o mesmo arquivo (URL estável). Exige a ponte configurada
(`SHOPMAN_GOOGLE_SERVICE_ACCOUNT_FILE` + `SHOPMAN_BACKUP_DRIVE_FOLDER`); sem
ela, falha fechado apontando o guia. Zero dependência nova (PyJWT +
cryptography, já no lock).

| Flag | Default | Descrição |
|------|---------|-----------|
| `--name` | `shopman-backup` | Nome da planilha na pasta do Drive |
| `--only` | — | Entidades específicas |
| `--with-transactional` | — | Inclui as abas somente-leitura de conferência |

---

### import_backup_from_drive

**App:** `shopman.shop`
**Arquivo:** `shopman/shop/management/commands/import_backup_from_drive.py`

**Drive → banco.** Baixa a planilha curada como XLSX (fica em `var/backups/`,
auditável) e emenda no `import_backup`, que continua mandando: **dry-run por
padrão**, `--apply` numa transação única, `--force` obrigatório em produção.

| Flag | Default | Descrição |
|------|---------|-----------|
| `--name` | `shopman-backup` | Nome na pasta do Drive, ou id de arquivo |
| `--out` | `var/backups` | Onde guardar o XLSX baixado |
| `--apply` | — | Escreve de verdade (sem isso, só relata) |
| `--only` | — | Entidades específicas |
| `--force` | — | Obrigatório para `--apply` em produção |

---

### seed

**App:** `shop`
**Arquivo:** `instances/nelson/management/commands/seed.py`

Popula o banco com dados completos da Nelson Boulangerie: catálogo, estoque,
receitas, clientes, canais, pedidos, pagamentos com `Order.data.payment.intent_ref`,
sessões abertas, alertas, POS/KDS e superuser técnico `admin`.

| Flag | Default | Descrição |
|------|---------|-----------|
| `--flush` | — | Deleta TODOS os dados antes de popular |

```bash
# Popular banco
python manage.py seed

# Resetar e popular do zero
python manage.py seed --flush
```

**Variável de ambiente:** `ADMIN_PASSWORD` — senha do superuser técnico `admin`.
Em `DEBUG=true`, se ausente, cai para `"admin"` apenas para desenvolvimento local.
Fora de DEBUG, o comando falha se `ADMIN_PASSWORD` estiver ausente ou obviamente
fraca; isso evita staging/prod público com `admin/admin`.

Depois do seed em staging, crie o dono nominal e desative o `admin` técnico:

```bash
SHOPMAN_ADMIN_PASSWORD=<senha forte> python manage.py bootstrap_admin \
  --username pablo \
  --email pablo@example.com \
  --deactivate-seed-admin
```

### configure_shop_contact

**App:** `shop`
**Arquivo:** `shopman/shop/management/commands/configure_shop_contact.py`

Configura telefone, email e WhatsApp público da loja singleton de forma
idempotente. Use depois do seed ou em pre-prod/prod para garantir que
`home.public_config.whatsapp_url` esteja projetado no storefront.

| Flag | Default | Descrição |
|------|---------|-----------|
| `--name` | `SHOPMAN_SHOP_NAME` | Nome usado se a loja ainda não existir |
| `--phone` | `SHOPMAN_SHOP_PHONE` | Telefone público em E.164 BR, com ou sem `+` |
| `--email` | `SHOPMAN_SHOP_EMAIL` | Email público da loja |
| `--whatsapp` | `SHOPMAN_SHOP_WHATSAPP` | Número WhatsApp ou URL `wa.me` / `api.whatsapp.com` |
| `--dry-run` | — | Mostra o resultado sem salvar |

```bash
python manage.py configure_shop_contact \
  --phone 554333231997 \
  --email nelson@boulangerie.com.br
```

### bootstrap_admin

**App:** `shop`
**Arquivo:** `shopman/shop/management/commands/bootstrap_admin.py`

Cria ou atualiza um superuser nominal de forma idempotente, sem depender do
`createsuperuser` interativo. Use para bootstrap de staging/pre-prod/prod.

| Flag | Default | Descrição |
|------|---------|-----------|
| `--username` | `SHOPMAN_ADMIN_USERNAME` | Usuário administrativo nominal |
| `--email` | `SHOPMAN_ADMIN_EMAIL` | Email do usuário administrativo |
| `--password-env` | `SHOPMAN_ADMIN_PASSWORD` | Env var que contém a senha |
| `--deactivate-seed-admin` | — | Desativa o usuário técnico `admin` criado pelo seed |

---

## Cron Recomendado

```cron
# Liberar holds expirados (a cada 10 min)
*/10 * * * * cd /app && python manage.py release_expired_holds

# Limpar idempotency keys (diário, 3h)
0 3 * * * cd /app && python manage.py cleanup_idempotency_keys

# Limpar tokens de auth (diário, 3h)
5 3 * * * cd /app && python manage.py auth_cleanup

# Limpar eventos processados (semanal, domingo 4h)
0 4 * * 0 cd /app && python manage.py customers_cleanup

# Reconciliação defensiva de pagamentos (diário, 4h30)
30 4 * * * cd /app && python manage.py reconcile_payments --since=1d

# Auditoria financeira diária (após fechamento)
45 4 * * * cd /app && python manage.py reconcile_financial_day --require-closing

# Worker de directives (systemd/supervisor, não cron)
# python manage.py process_directives --watch
```

### compute_product_affinity

Recalcula `shop.ProductAffinity` — o que a casa vende junto — a partir das
cestas do último ano: pedidos do Orderman e o histórico externo do B.I.
(`shop/adapters/baskets.py`). É o sinal que substituiu "o item mais popular que
não está na sacola" no adicional do carrinho e do concierge.

```bash
python manage.py compute_product_affinity                      # respeita a cadência
python manage.py compute_product_affinity --force              # recalcula agora
python manage.py compute_product_affinity --dry-run            # mostra o top 10
python manage.py compute_product_affinity --window-days 180 --min-support 3
```

| Flag | Default | O que faz |
|---|---|---|
| `--window-days` | 365 | janela de cestas lidas |
| `--half-life-days` | 120 | aos N dias uma cesta vale metade |
| `--min-support` | 5 | mínimo de cestas em comum para o par virar linha |
| `--min-interval-hours` | 20 | não recalcula se a tabela for mais nova que isto (`0` desliga) |
| `--force` | — | recalcula mesmo com a tabela fresca |

⚠️ **A cadência mora aqui, não no worker.** O `maintenance_worker` roda o ciclo
a cada 5 minutos e não tem noção de "uma vez por noite"; um ano de cestas não
cabe nisso. Quem sabe quanto custa o cálculo é o comando, e o relógio é o
`computed_at` que a própria tabela já tem — sem bookkeeping nova. Por isso ele
pode ficar no ciclo sem custo: 99% das vezes sai na primeira consulta.

Roda no fim do ciclo do `maintenance_worker`, antes do `purge_sign_in_audit`.

### propose_product_attributes

Propõe `natureza`, `sabor` e `temperatura` por SKU a partir da **coleção
primária** do produto, para o gestor revisar. É a carga inicial do registro de
atributos (`shop.AttributeDefinition`).

```bash
python manage.py propose_product_attributes --dry-run
python manage.py propose_product_attributes
python manage.py propose_product_attributes --overwrite-derived
```

⚠️ **Proposta não é curadoria.** Tudo sai com `source="derived"` e
`reviewed=False`; o gestor revisa no Admin. O que ele escreveu à mão
(`source="manual"`) **nunca** é sobrescrito — nem com `--overwrite-derived`,
que só reescreve propostas anteriores.

Mercearia é desempatada por palavra-chave: geleia, mostarda, patê e queijo são
`acompanhamento` (comem-se com o pão); café em grão e chá em lata são `outro`
(saem pela porta). Coleção que não responde a pergunta deixa o atributo em
branco — ausência de dado é ausência de dado, e "combos" não tem natureza
própria: ele herda a dos componentes.

O `seed` chama este comando no fim, depois do catálogo e das coleções. **Num
deployment já no ar, ele precisa ser rodado à mão** — sem ele o registro fica
vazio e os pareamentos de `suggestion.complement` não casam com nada.
