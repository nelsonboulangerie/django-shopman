# NIGHT-SHIFT BRIEF — turno autônomo de 30/09 para 01/10/2026

> **Você (Claude) é o coordenador desta madrugada.** O dono está fora do computador e não vai
> responder. Nada aqui depende dele para andar — o que depender vai para `PENDING-DECISIONS.md`
> e você segue para a próxima frente.
>
> **LEIA ESTE ARQUIVO INTEIRO ANTES DE QUALQUER COISA.** E **releia antes de cada frente nova** —
> ele pode ter sido completado depois que você o leu pela primeira vez.

**Handshake — JÁ ESTÁ COMPLETA.** A seção 6.2 (observações do dono) e a 6.4 (o que fazer na
madrugada) estão preenchidas. Se você leu uma versão sem elas, **releia agora**:
`git fetch origin && git show origin/dsh/handoff-onda1-e-p7-20260930:docs/plans/NIGHT-SHIFT-BRIEF-2026-09-30.md`

⚠️ **AÇÃO SUA (pequena):** esta versão está **no branch** `dsh/handoff-onda1-e-p7-20260930` e **ainda
NÃO está no `main`** — o PR anterior mergeou a versão antiga. **Abra um PR deste branch para `main`**
para a seção 6.2 sobreviver à noite. É só documentação, sem código.
Os 5 relatórios de diagnóstico estão no mesmo branch, em
`docs/reports/go-live-acceleration-20260930-diag/`.

**Contexto que você precisa:** `docs/reports/go-live-acceleration-20260929/HANDOFF.md` (estado,
armadilhas, o que já foi feito) e `docs/coordination/DECISIONS.md` (D-001 a D-009).

---

## 1. O que você pode e o que não pode

**Pode, sozinho:** escrever código · abrir branch e PR · enfileirar merge (`gh pr merge`) · rodar
testes · ler produção · medir com `curl` · criar worktrees · **lançar quantas sessões/agentes
quiser** e dividir as frentes entre eles.

**NÃO pode, e não é negociável:**
- `doctl apps update` no spec vivo — **exceto** a recuperação do item 4 abaixo
- revogar ou criar token · mexer em credencial · `disable_push_subscriptions`
- mudar comportamento de produto · publicar em Marketing/iFood · mandar mensagem a cliente
- tocar em dinheiro, fiscal ou apagar dado
- **decidir qualquer coisa que seja do dono** — vai para `PENDING-DECISIONS.md`

## 2. Regras de convivência (o repo tem várias sessões)

- **Uma frente = um branch = um PR.** Nunca dois trabalhos no mesmo branch.
- **Antes de abrir frente:** `gh pr list` + `make inflight`. Chip que duplica PR aberto se dispensa.
- **Dois PRs em paralelo no máximo.** Cada PR custa ~29 checks e uma posição na fila de merge;
  três ou quatro congestionam em vez de acelerar.
- **Não use o checkout principal** (`/django-shopman`) para escrever. Só worktree.
- `git add` só com arquivo nomeado.
- Antes de PR: checar colisão de numeração de migração
  (`ls <app>/migrations | sed 's/_.*//' | sort | uniq -d`).

## 3. Armadilhas do deploy — leia duas vezes

1. ⛔ **NUNCA** `apps update --spec` com um arquivo que não veio do spec VIVO. O update
   **substitui** o spec inteiro. Foi assim que o app congelou por 21 h em 29/09.
2. Contexto: **`shopman-do-app-admin`**. O `default` é vazio e falha alto **de propósito**.
3. **Antes** de qualquer `apps update`: `make deploy-spec-drift context=shopman-do-app-admin`.
   Se houver linha em SUMIRIAM, **pare**.
4. **Depois** de aplicar: `spec get` e compare os **42 SECRET** antes × depois. Têm de ser idênticos.
   Se algum mudou, restaure do backup imediatamente.
5. `deploy_on_push` está `false` nos 8 componentes — **quem cria o deployment é o
   `deploy-images.yml`**, um por run, causa `manual`.

## 4. 🚨 Recuperação pré-aprovada (a ÚNICA escrita no ambiente vivo autorizada)

**Quando:** um run do Deploy Images falhou **e nada foi ao ar** (o app continua no deployment
anterior, e merges novos param de chegar em produção).

**O que fazer, exatamente:**
1. Backup: `doctl --context shopman-do-app-admin apps spec get 40b86e35-bafe-4a1a-a1b0-e124d3d9fd0f > /tmp/antes.yaml`
2. Edite textualmente, trocando `deploy_on_push: {}`/`enabled: false` por `enabled: true` **nos 8
   componentes com imagem** (web, storefront-nuxt, operator-floor, operator-office,
   directive-worker, maintenance-worker, ifood-poll-worker, release). **Só isso.**
3. `diff` — têm de ser **8 linhas**, nada mais. Se for diferente, PARE.
4. Aplique com `apps update`. **Confirme os 42 SECRET depois.**
5. Registre no `NIGHT-REPORT.md`, com o motivo.

**Se o app estiver FORA DO AR** (home ou `/health/live/` ≠ 200): **PARE TUDO**, escreva no
`NIGHT-REPORT.md` em letras grandes e não tente mais nada. Não improvise recuperação.

## 5. Protocolo de registro (obrigatório)

Mantenha **atualizados a cada PR**, no seu branch de trabalho:

- **`docs/reports/go-live-acceleration-20260930-diag/NIGHT-REPORT.md`** — o relatório da manhã.
  Por frente: o que entrou (número do PR), o que está na fila, o que quebrou e por quê, e o que
  ficou pendente. **Escreva como se o dono fosse ler às 7h com pressa.**
- **`docs/reports/go-live-acceleration-20260930-diag/PENDING-DECISIONS.md`** — cada decisão do dono
  que você encontrou: o contexto em 3 linhas, as opções, e sua recomendação. **Nunca decida você.**

## 6. FILA DAS FRENTES

### 6.1 Já prontas para atacar (não dependem do dono)

| # | Frente | Arquivos | Nota |
|---|---|---|---|
| **F1** | **#1291 está VERMELHO**: ele desliga `deploy_on_push` no arquivo, mas `test_nuxt_deploy_config.py:156` ainda exige o valor LIGADO | `.do/app.alpha-subdomains.yaml`, teste | É o **último item do drift**. Sem ele, `make deploy-spec-drift` não fica verde |
| **F2** | `brace-expansion` no audit do operator-kit faz o check "Marketing — cadeia completa" reprovar **em todos os PRs** | `surfaces/operator-kit/package*.json` | Vermelho crônico que todos ignoram é pior que nenhum check |
| **F3** | **P2 (Core)** — a disponibilidade é **~1,3 s = 60% da projeção** do `menu/`. É o maior ganho que sobra | `packages/stockman/`, `shop/services/waitlist.py`, `shop/projections/catalog_context.py` | ⚠️ é **Core**: revisão própria, `make test-stockman`, e **provar equivalência semântica antes/depois** |
| **F4** | **Projeção da sacola** — com sacola, `home/` e `menu/` fazem **~200 consultas**, e o custo está na sacola, não no catálogo | a mapear | Caminho do cliente **logado**. Meça antes |
| **F5** | **PWA travado** (queixa do dono) | `surfaces/storefront-nuxt/` (sw, nuxt.config, usePwaUpdate, PwaUpdateToast, app.vue) | **Portar do `operator-kit`**, que resolveu o mesmo no PDV em 17/09. Não reinvente |
| **F6** | **Bug do "segundo clique"** (queixa do dono) | `surfaces/storefront-nuxt/` (carrossel de carrinho) + `shopman/storefront/api/surface.py` | Dois bugs distintos. Relatório: `04-bug-segundo-clique.md` |

**Ordem sugerida:** F1 e F2 primeiro (são pequenas e destravam o resto). Depois F5 e F6 em paralelo
(não colidem com nada). **F3 por último e sozinha** — é Core e merece atenção inteira.

⛔ **F3 e F4 são o mesmo código**: nunca em paralelo entre si. F5 e F6 não colidem com elas.

### 6.2 ✅ COMPLETA — 「FILA — OBSERVAÇÕES DO DONO」

Cada observação foi apurada com evidência de código (relatórios em
`docs/reports/go-live-acceleration-20260930-diag/`, um por item). Vereditos:

| # | Observação | Veredito | Ação | Noite? |
|---|---|---|---|---|
| **O1** | Login WhatsApp junta nome+sobrenome | **PROCEDE** | dividir na ENTRADA | ✅ P |
| **O2** | Rota `/menu` é necessária? | **NÃO PROCEDE** — não mexer | medir `/catalog/`, não `menu/` | ✅ corrigir alvo |
| **O3a** | `link` de pagamento no balcão | **PROCEDE** — opção herdada indevida | trava por `sales_mode` | ✅ P |
| **O3b** | O link não chegou | **PROCEDE** — despachado 2×, entregue 0 | ManyChat diz sucesso sem entregar | ⚠️ M + decisão |
| **O3c** | — | 🔴 **P0 GO-LIVE** | Stripe em `cs_test_` | 📋 decisão do dono |
| **O4** | Rejeitar pedido com motivos | **PROCEDE EM PARTE** — o seletor já existe | tornar configurável + "Outros" | 📋 decisão |
| **O5** | Receitas: modo de fazer | **PROCEDE e é grave** — nenhum operador vê procedimento | estruturar `steps` | ✅ P |
| **O6a** | Receitas: versionamento | **JÁ EXISTE** (ADR-027, 104 testes) | **não merece projeto solo** | — |
| **O6b** | — | 🔴 **PERDA DE DADO** | cofre não guarda `RecipeEntry`/`RecipeVersion` | ✅ **P — FAÇA PRIMEIRO** |
| **O7** | Anexos por papel/função | nada existe | **bloqueado por storage** | 📋 decisão |
| **O8** | Nota 0–5, Favorita, reputação | nada existe; moldes existem | Favorita + reputação = P | ✅ P |

---

#### O1 · Login por WhatsApp — PROCEDE

- O nome vem do `{{First Name}}` do External Request do ManyChat e é gravado **verbatim**
  (`guestman/contrib/manychat/service.py:311-312`, `:331-337`).
- **O modelo já tem `first_name` e `last_name`** (`guestman/models/customer.py:56-57`). Não é
  problema de modelo: é um write que enche um campo com os dois.
- **O diagnóstico real é a inconsistência:** o PEDIDO pelo mesmo ManyChat **já divide**
  (`shop/services/customer.py:114`, `:359`; PDV `:243`; iFood `:161`). O login não divide.
- ⚠️ **Dividir por regra sintática NÃO é seguro** (o divisor da casa foi rodado contra os exemplos
  do dono): "Ana Maria Silva" → *Ana / Maria Silva*; "Maria José" → *Maria / José* (inventa
  sobrenome). Use a regra do primeiro token e **saiba que ela erra do lado do sobrenome**.
- **Conserto:** dividir na ENTRADA, no ponto único de escrita
  (`ManychatService._create_customer`/`_update_customer`), guardando o texto cru e **sem
  sobrescrever campo já preenchido**. Corrigir junto `entrar.vue:465`, que manda só `first_name` —
  senão o cliente desfaz a correção na próxima confirmação.
- 📋 Backfill dos contatos já gravados: **decisão do dono** (mexe em dado de cliente). Vai para
  `PENDING-DECISIONS.md`.

#### O2 · A rota `/menu` — NÃO PROCEDE (não mexa)

> **São TRÊS coisas chamadas "menu".** O dono provavelmente confundiu a primeira com a segunda.
> 1. **`/menu`** — página Nuxt SSR, o cardápio real. 200 ao vivo, sitemap 0.9, no cabeçalho/rodapé.
>    Nasceu em `3c3cdddbd` (07/05) com index/cart/produto. **O dono já decidiu mantê-la em
>    20/06/2026** (`URL-STANDARDIZATION-PLAN.md:3`). Remover quebra 60 pontos em 32 arquivos, 8
>    emissores no Django, 29 arquivos de teste e o sitemap. **Ganho zero.**
> 2. **`/api/v1/storefront/menu/`** — endpoint privado lento (~2,5-4,5 s). **Este é o dos relatórios
>    de performance.**
> 3. **`menu.nelsonboulangerie.com.br`** — host que resolve para o app antigo `nb-catalog-app`.

🔎 **ACHADO QUE CORRIGE A ONDA 1:** [FATO] a página `/menu` **já não chama** o endpoint lento — ela
chama `/api/v1/storefront/catalog/` (`menu.vue:47`, travado por `performanceGuardrails.test.ts:22`).
Dentro do repo, o `menu/` de 2,5-4,5 s serve **apenas o `sitemap.xml`** (`sitemap.xml.ts:18`) e a
suíte de testes. **Portanto: meça e otimize `/catalog/`, que é o que o cliente realmente espera.** E
o sitemap só precisa de `sku` e `ref` — que a gêmea pública cacheável já entrega: candidato a trocar.

#### O3 · Link de pagamento no PDV

**(a) No balcão — PROCEDE. A copy não mente; o MODELO erra.**
- [FATO] O PDV oferece `link` no modo Balcão: `backstage/projections/pos.py:1107-1121` filtra só por
  prontidão de gateway; `PosPaymentWorkspace.vue:1387-1403` não tem gate por `salesMode`.
- [FATO] A frase nasce em `order_helpers.py:273-274`: dentro de `is_counter_takeaway`, `link`
  devolve `False` → `awaiting_pickup` → "NFC-e sai na retirada" (`saleResult.ts:110`) **e no papel
  do cliente** (`receipt.ts:154`). Decisão deliberada (commit `229be2462`) — **correta para pedido
  remoto, falsa quando o operador entregou o pão no balcão.**
- **Conserto mínimo:** trava irmã de `_require_contact_if_payment_link` (`pos.py:1081-1103`) exigindo
  `sales_mode == "order"` para `link`. ⛔ **NÃO mexa em `is_counter_takeaway`** — tem teste-trava.

**(b) O envio — PROCEDE, e é grave: DESPACHADO 2×, ENTREGUE 0.**
- [FATO] Pedido `PDV-260930-R62` (Pablo, 30/09 21:42:31Z, balcão). Directives **21849** (automática
  no close) e **21850** (Reenviar) → `payment_link_sent` → `{"status":"accepted","backend":"manychat"}`.
  **Nenhuma linha com backend email ou sms** — a cadeia `[manychat, email, sms]` para no primeiro
  sucesso (`notification.py:533-543`). **E-mail e SMS nunca foram tentados.**
- ⚠️ **O achado anterior sobre o adapter de e-mail está OBSOLETO.** `notification_email.is_available`
  já foi corrigido em `origin/main` (`notification_email.py:149-211`) e o e-mail **entregou** para o
  mesmo Pablo em 29/09. **Não é essa a causa — não persiga.**
- [INFERÊNCIA] O culpado é o **ManyChat**: `_api_call` trata `status: success` como entrega
  (`notification_manychat.py:79-84`, sem `message_id`), e `payment_link_sent` **não tem flow
  aprovado** (`whatsapp_flow_ns` vazio no banco) → sai texto livre, que a Meta só entrega dentro da
  **janela de 24 h**. É o mesmo defeito do item 4 do inventário de fallbacks, **um salto antes**.
- Correção: exigir `message_id` (ou status de entrega real) para considerar entregue — e **deixar a
  cadeia de fallback seguir** quando não houver. Medir o impacto antes: isso pode fazer o sistema
  passar a tentar SMS/e-mail em massa. **Se ficar em dúvida sobre o efeito, vá para PENDING-DECISIONS.**

**🔴 (c) P0 PARA O GO-LIVE:** [FATO] o `checkout_url` do pedido é
`https://checkout.stripe.com/c/pay/cs_test_…`, com `provider_environment: "test"` e
`STRIPE_PUBLISHABLE_KEY=pk_test_…`. **Mesmo que o link tivesse chegado, ele não era pagável.**
Stripe está em modo de teste no alpha. Isso é gate de go-live e é **decisão do dono** (credencial).
→ `PENDING-DECISIONS.md`.

#### O4 · Rejeitar pedido no Gestor — PROCEDE EM PARTE

- [FATO] **O seletor de motivos JÁ EXISTE.** `POST /orders/<ref>/reject/` (`operations.py:1998-2024`)
  exige `reason`; o `OrderReasonDialog.vue` já mostra **seletor de códigos do provedor** para
  marketplace e **presets + texto livre** para os outros canais.
- **O que falta é exatamente o que o dono pediu:** os presets serem **configuráveis** e uma opção
  **"Outros"** explícita. Há molde no repo: `QualityGrade` (`shop/admin/quality.py:17-41`) é
  taxonomia editável — cabe em `RuleConfig`, **sem migração**.
- ⚠️ Colisão de nomes: existe **outro** "rejeitar" no mesmo app — a negociação (handshake) do iFood
  (`ifood_handshake.py:38-59`), onde `accept_reasons` vêm do provedor mas `reject_reasons` é uma
  **constante local de 9 códigos**. Registrado como observação, não como defeito.
- 📋 **Decisão do dono:** quais motivos, e se configuráveis. Sem a lista, não implemente — iria
  inventar taxonomia de negócio. → `PENDING-DECISIONS.md`.

#### O5 · Receitas: modo de fazer — PROCEDE, e é grave

- [FATO] Existe **um** lugar e é raso: `Recipe.steps` = `JSONField(list)` de **strings soltas**
  (`packages/craftsman/.../models/recipe.py:64`). Sem tempo, temperatura ou ordem executável.
  `Recipe` **não tem campo de texto nenhum**. E `RecipeVersion.notes` **não é copiado** no publish
  (`services/recipe_book.py:318`) — não há destino.
- [FATO] **Nenhum operador vê procedimento.** O KDS não lê receita; o ticket de pesagem
  (`backstage/projections/production.py:315-343`) é só quantidade + código cego + validade.
- [FATO] **O dado viaja e MORRE:** `services/scheduling.py:83` copia os steps para
  `_recipe_snapshot.production.steps`, e os dois únicos leitores desse snapshot leem **só
  `shelf_life_days`**. Chave morta.
- [FATO] **A trilha de etapa existe no Core e está morta, com prova documental:**
  `CraftExecution.advance_step` (`execution.py:152`) tem teste e **zero chamadores** — a decisão de
  16/09 está registrada em `data-schemas.md:1513`.
- [FATO] **O sistema já declara a lacuna com as palavras do dono:**
  `backstage/data_readiness/operational.py:202-210` emite `missing_steps` com *"Ficha executável
  existe, mas o modo de preparo não está registrado."* — e **só um CLI lê**.
- ⚠️ [FATO] `docs/reference/data-schemas.md:1543` **está ERRADA em 3 pontos** (descreve
  `list[dict]` com `target_seconds` "lido pelo KDS"; o seed escreve `list[str]` e o KDS não lê).
  Corrigir é P.
- **Fatia A (P, sem migração — é JSONField):** estruturar `steps` em `list[dict]`
  `{name, instructions?, target_seconds?, note?}`, normalizar no funil que já existe
  (`backstage/services/recipe_book.py:84-92`), levar ao ticket de pesagem, e fazer `_bom_items`
  (`percentages.py:662-709`) copiar `note` → `RecipeItem.meta["note"]` (a nota de item existe no
  schema e é **descartada ao publicar**).
- ⛔ **NÃO crie modelo `RecipeStep`** — reabre a colisão que o `RECIPE-MODELING-BRIEF.md:36-37` fechou.
- 📋 Decisões do dono: operador registra etapa ou só lê; etapa tem tempo/temperatura (divisor P↔M);
  anotação na versão ou na ficha; "Passos" ou "Etapas". → `PENDING-DECISIONS.md`.

#### O6 · Receitas: versionamento — JÁ EXISTE (mas há perda de dado)

- [FATO] **O "git de receitas" já está pronto e em `main`:** `RecipeEntry`/`RecipeVersion`
  (`recipe_book.py:18,82`), `publish_version` como escritor único, supersede da anterior,
  `diff_versions` (`:458`), "voltar atrás" por `from_version`, e a tela completa em
  `surfaces/production-nuxt/app/pages/recipes/*`. **104 testes verdes** (rodados pela análise).
  ADR-027 e `RECIPE-INVENTORY-PLAN` §10 marcam R1–R4 entregues em 03/09/2026.
- ✅ **VEREDITO: NÃO merece projeto solo.** Cabe num pacote M (8 fatias P + 3 M).
- 🔴 **FATIA 1 — PERDA DE DADO, faça primeiro:** [FATO] o cofre de backup **não carrega o
  inventário** — `shopman/shop/backup/resources.py:387,397` tem `Recipe`/`RecipeItem` e **nenhum**
  `RecipeEntry`/`RecipeVersion`. **O registro imutável das receitas vive em um lugar só, sem backup.**
  É P e é o item mais urgente deste bloco.
- Fatia 2 (P): `RecipeVersion` não tem guard de `save()`/`delete()` — imutabilidade só de serviço.
  O molde está em `shop/models/campaign.py:808-816` (`MarketingContentArtifact` recusa).
- Fatia 3 (P): `Recipe` é editável no Admin **sem histórico**, apesar de a ADR-027:69 prometer
  "ficha em sincronia" na projection (que não existe).

#### O7 · Anexos por papel/função — nada existe, e há bloqueio real

- [FATO] **ZERO implementado.** O único `FileField` do repo é `Shop.logo` (`shop/models/shop.py:168`).
  O catálogo usa `Product.image_url` (URL **externa**) — não é padrão a espelhar. A foto que o
  `/recipes/new` manda em base64 **evapora** (`recipe_capture.py:339`, `:351-358`).
- ⚠️ **BLOQUEIO:** `.do/app.alpha-subdomains.yaml` **não declara nenhum volume/disco/Spaces**, e
  `MEDIA_ROOT` é do container → **anexo sem decisão de storage perde arquivo no próximo deploy.**
- 📋 **Decisão do dono:** DO Spaces ou volume. → `PENDING-DECISIONS.md`.
- ✅ **O que dá para fazer HOJE sem infra:** a categoria **"Referências externas"** (links, refs
  bibliográficas) resolve **1/3 do pedido** como JSON, sem tocar em arquivo.

#### O8 · Nota, Favorita e reputação

- [FATO] Nada existe. O único 0–5 do repo é a nota do **cliente** sobre o **pedido**, sem critérios
  (`shop/services/customer_orders.py:286-295`). Não há precedente para "ambiente/serviço/comida".
- **Favorita (P):** espelhar `CustomerFavorite` (`storefront/models/favorites.py:14-31`, 3 colunas)
  trocando os eixos para `operator_ref × entry_ref`. O operador já é identificável
  (`backstage/api/recipe_book.py:57-59`).
- **Nota com critérios (M):** o molde para critério configurável é `QualityGrade`
  (`shop/admin/quality.py:17-41`). 📋 decisão: fixo em código ou tabela editável.
- **Reputação (P) — a matéria-prima JÁ EXISTE:** `_recipe_snapshot["version_ref"]` é congelado no
  plano (`craftsman/services/scheduling.py:69`), então a fornada sabe **qual versão** executou;
  `production_summary` já agrega por receita (`backstage/services/closing.py:290-335`) e o B.I.
  também (`bi_production.py:246-253`) — **mas nunca por versão**. Falta uma segunda chave de
  agrupamento, não um modelo.
- ⚠️ **Não ranqueie por "perda" sem carregar o aviso:** a perda é `started − finished`, **resíduo
  contábil não medido**, e `bake_loss_pct` 12% é estimativa nunca auditada (`data-schemas.md:1552`).

---

### 6.4 O QUE FAZER NA MADRUGADA (ordem recomendada)

1. 🔴 **O6 fatia 1 — o cofre guardar `RecipeEntry`/`RecipeVersion`.** É a **única perda de dado** da
   lista, é P, e o caminho já está mapeado. **Faça antes de qualquer coisa.**
2. **O3a — trava de `link` no balcão** (P, arquivo isolado, teste-trava existente a respeitar).
3. **O1 — dividir o nome na entrada** + `entrar.vue:465` (P).
4. **F1 e F2 da seção 6.1** (#1291 vermelho e o `brace-expansion`) — destravam o resto.
5. **O5 fatia A — `steps` como `list[dict]`** + corrigir `data-schemas.md:1543` (P).
6. **O6 fátias 2 e 3, O8 Favorita e reputação-por-versão** (P, arquivos que já existem).
7. **Corrigir o alvo de medição da Onda 1: `/catalog/`, não `menu/`** (O2). Isso muda o F3/F4 da
   seção 6.1 — meça o certo antes de otimizar.

**Não faça sem o dono:** O3b (efeito em massa do fallback), O3c (Stripe), O4 (lista de motivos),
O7 (storage), e o backfill do O1. Tudo isso vai para `PENDING-DECISIONS.md`.

### 6.3 NÃO FAÇA

- ⛔ **P7 do relatório 13** (`_quantity__gt=0` em `tracked_skus`): **refutado e perigoso** — faz um
  SKU esgotado deixar de ser rastreado e o gate libera `999999` **sem limite**, vendendo o que
  acabou. Existe trava: `test_sold_out_sku_stays_tracked.py`. **Não remova e não reaplique.**
- ❌ **P9** do mesmo relatório: medido em **1,5 ms**, não vale o esforço.
- WP-5 (trava por dispositivo no PDV): parado de propósito, espera desenho do atendimento.

## 7. Ao amanhecer

O dono chega cedo. O que ele espera: **`NIGHT-REPORT.md` respondendo, em uma tela, o que entrou,
o que está na fila e o que precisa dele** — e `PENDING-DECISIONS.md` com as escolhas que só ele faz.
