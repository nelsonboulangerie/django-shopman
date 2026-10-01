# 06 — Receitas: ciclo de vida (edição/versionamento, anexos, avaliação, reputação)

**Data:** 2026-09-30 · **Autor:** agente de análise (DSH) · **Árvore:** `.dsh-worktrees/go-live-acceleration`
(branch `dsh/handoff-onda1-e-p7-20260930`, 3 commits à frente de `origin/main`)
**Método:** leitura de código em `origin/main` (verificado com `git cat-file -e origin/main:<path>`), testes executados
na worktree com `PYTHONPATH` explícito. Nenhum comando git mutante. Nada foi editado além deste relatório.

---

## 0. Veredito em cinco linhas

| Pergunta do dono | Estado hoje | Tamanho |
|---|---|---|
| **(a)** Edição versionada com registro imutável e "voltar atrás" | **JÁ EXISTE E ESTÁ NO `main`** — inventário, versão congelada, comparar, publicar | Faltam **3 lacunas de blindagem** = **P** |
| **(b)** Anexos visuais por papel (produção / original / referências) | **NÃO EXISTE NADA.** Zero model de mídia, zero upload no repo inteiro | **M** (+ 1 decisão de infra) |
| **(c)** Avaliação 0–5 com critérios + "Favorita" por operador | **NÃO EXISTE.** Existe o molde de favorito do CLIENTE e o molde de taxonomia configurável | **P** (favorita) + **M** (nota com critérios) |
| **(d)** "Reputação" a partir do uso real | **A MATÉRIA-PRIMA EXISTE** (o carimbo de versão já é gravado na fornada). Falta só a agregação por versão | **P–M** |

> **Isto NÃO merece projeto solo.** A pergunta (a) — que é 60% do que o dono enxerga como
> "quase um git de receitas" — já está construída, testada e mergeada. O bloco inteiro
> (a)+(c)+(d) cabe em **um pacote M**, fatiado; só (b) tem uma decisão de infraestrutura
> de verdade (onde os bytes moram), e essa decisão é de uma tarde, não de um projeto.

---

## 1. (a) Versionamento — o que JÁ EXISTE

**[FATO] O inventário de receitas com versionamento imutável está no `origin/main`.**
Verificado por comando:

```
$ git cat-file -e origin/main:packages/craftsman/shopman/craftsman/models/recipe_book.py  && echo SIM
SIM
$ git cat-file -e origin/main:shopman/backstage/api/recipe_book.py && echo SIM
SIM
$ git cat-file -e origin/main:surfaces/production-nuxt/app/pages/recipes/index.vue && echo SIM
SIM
```

Introduzido em **2026-09-03** por `1ac9152c5 feat(craftsman): RecipeEntry e RecipeVersion, o inventário de receitas (migração 0007)`
e `9fa4fd094 feat(backstage): projections, API e contrato do inventário de receitas (WP-R3)`.

### 1.1 O que ele é, em código

- **`RecipeEntry`** — a receita no inventário, com `kind`, `output_sku` opcional, `is_archived`,
  `current_version` (FK para a última publicada). `packages/craftsman/shopman/craftsman/models/recipe_book.py:18-79`
- **`RecipeVersion`** — a fórmula congelada, com `status` `draft → published → superseded`
  (`recipe_book.py:85-88`), `number` por entry com `UniqueConstraint(entry, number)`
  (`recipe_book.py:156`), `label` ("o que mudou"), `created_by`, `published_at`.
- **`origin`** — JSON declarado **imutável** por contrato, guardando "a receita como chegou
  (quantidades, unidades, texto)". `recipe_book.py:131-136`.
  → É o "registro imutável de mudanças" que o dono pediu, e ele **já grava o dado bruto**.
- **`source`** — `{kind: manual|note|photo|ficha|import, text?, language?, image_name?, model?}`
  (`recipe_book.py:137-142`). **`image_name`** existe como string — é o único vestígio de
  anexo no modelo hoje (ver §3).
- **`version_ref`** = `"<ref>@<n>"` (`recipe_book.py:163-166`) — o carimbo que viaja para a
  ficha e para o snapshot da fornada.

### 1.2 Ciclo de vida, em serviços

| Operação | Onde | Regra |
|---|---|---|
| criar rascunho | `services/recipe_book.py:153` | `number = último + 1`, `status=draft` |
| editar rascunho | `services/recipe_book.py:186` | **recusa se não for draft** (`:192 VERSION_NOT_DRAFT`) — publicado é imutável |
| publicar | `services/recipe_book.py:211` | upsert da `Recipe`, **supersede a anterior** (`:252`), carimba `Recipe.meta["version_ref"]` |
| comparar | `services/recipe_book.py:458 diff_versions` | linhas + métricas, lado a lado |
| "voltar atrás" | `services/recipe_book.py:546 bootstrap_entry_from_recipe` + `from_version` | **copiar-para-frente**: cria rascunho novo a partir de qualquer versão antiga |

**[FATO] "Voltar atrás" existe, mas como copiar-para-frente, não como re-publicar.**
`publish_version` exige `status == DRAFT` (`services/recipe_book.py:227`), então uma versão
`superseded` **não** pode voltar a ser a atual. O caminho é `from_version`:
`shopman/backstage/services/recipe_book.py:240-246` copia a origem para um rascunho novo.
Na tela, é o botão **"Nova versão"** de `surfaces/production-nuxt/app/pages/recipes/[ref]/index.vue:68-81,358`.

> Julgamento: **está certo assim.** É append-only, que é o que torna o registro confiável.
> Mas o nome na tela ("Nova versão") **não diz ao operador que é o caminho de volta** —
> a lacuna aqui é de copy, não de motor.

### 1.3 O que o operador vê hoje

**[FATO] A superfície está construída**, em `surfaces/production-nuxt` (2.130 linhas de página):

- `app/pages/recipes/index.vue` (229) — inventário
- `app/pages/recipes/new.vue` (516) — três portas: anotação / foto / manual
- `app/pages/recipes/[ref]/index.vue` (570) — lente, **linha do tempo das versões** (`:393-420`),
  publicar com o diff (`:92-119`), comparar (`:366`)
- `app/pages/recipes/[ref]/edit.vue` (630) — editor com prévia
- `app/pages/recipes/compare.vue` (185)
- Rail "Receitas" em `app/app.vue:14,77-80`, atrás de `useRecipeBookAccess`

**Gates:** ler = `backstage.operate_production` ou `craftsman.view_recipe`; escrever =
`shop.manage_production` ou `craftsman.change_recipe`. `shopman/backstage/projections/recipe_book.py:1038-1050`.

### 1.4 Provas de execução (rodadas nesta worktree)

```
$ PYTHONPATH=<worktree+packages+root> .venv/bin/python -m pytest \
    packages/craftsman/shopman/craftsman/tests/test_recipe_book.py -q
35 passed in 0.57s

$ PYTHONPATH=<...> .venv/bin/python -m pytest \
    shopman/backstage/tests/test_api_recipe_book.py \
    shopman/backstage/tests/test_recipe_book_projections.py -q
69 passed in 27.01s
```

→ **104 testes verdes.** Não é protótipo; é feature em produção.

### 1.5 Existe PADRÃO de versionamento imutável no repo? Sim, e são DOIS

**[FATO] Padrão A — congelar + publicar (o do inventário de receitas).** Versionado por
número, histórico append-only, e um único escritor na execução. É o mais forte dos dois.

**[FATO] Padrão B — `django-simple-history`.** A dependência está instalada e usada:
- `packages/offerman/shopman/offerman/models/product.py:190` (`Product`)
- `packages/offerman/shopman/offerman/models/listing.py:123` (`Listing`)
- `shopman/shop/models/rules.py:48` (`RuleConfig`)
- `shopman/shop/models/faq.py:54`, `shopman/shop/models/omotenashi_copy.py:44`
- middleware em `config/settings.py:388`

⚠️ **`simple_history` NÃO está em nada do Craftsman.** `Recipe`, `RecipeItem`,
`RecipeEntry` e `RecipeVersion` não têm `history = HistoricalRecords()` — confirmado por
`grep -rn "HistoricalRecords" packages/ shopman/ config/` (12 arquivos, nenhum do craftsman).

**[FATO] Procurei `revision` em `packages/orderman/` e não existe.** `grep -rn "revision" --include=*.py packages/orderman/`
retorna **vazio**. Onde `revision` aparece é:
- **optimistic-concurrency de sacola/pedido** (não versionamento de conteúdo):
  `shopman/storefront/api/serializers.py:62 expected_revision`, `shopman/shop/projections/cart.py:319`,
  `shopman/storefront/presentation/cart.py:209`
- **`shop/services/courier.py:265 dispatch_revision`** — etiqueta de concorrência
- **`shop/models/catalog_binding.py:63 revision = PositiveIntegerField(default=1)`** — ponteiro

→ **`revision` no repo significa "detecte conflito de escrita concorrente", nunca "histórico".**
Não confundir com o que o dono pediu.

**[FATO] Padrão C — append-only com trava no `save()`.** `shopman/shop/models/campaign.py:27-35`
(`_AppendOnlyMarketingQuerySet` bloqueando `update()`/`delete()`) e o guard duro em
`MarketingContentArtifact.save()` (`campaign.py:808-810`: *"Artefatos de Marketing são imutáveis"*,
com `raise ValidationError`) e `delete()` (`:816`).
**É exatamente o guard que falta no `RecipeVersion`** (ver §2.2).

---

## 2. (a) Versionamento — as lacunas MEDIDAS

### 2.1 ⚠️ O cofre NÃO carrega o inventário — risco real

**[FATO]** `shopman/shop/backup/resources.py:387` registra `("recipes", RecipeResource, 1)` e
`:397` `("recipe_items", RecipeItemResource, 2)`. O `grep` por `RecipeEntry|RecipeVersion` em
`shopman/shop/backup/` retorna **vazio**.

→ **O registro imutável de mudanças — a coisa que o dono quer que seja confiável — não é
exportado pelo backup.** Se o banco vivo cair, as versões somem; a `Recipe` (última publicada)
sobrevive, e o histórico vira pó. Já estava previsto como pendência em
`docs/plans/RECIPE-INVENTORY-PLAN.md:291` ("Cofre ainda não carrega `RecipeEntry`/`RecipeVersion`").
**Esta é a lacuna mais grave das quatro perguntas.**

### 2.2 ⚠️ A imutabilidade é só de serviço, não de banco

**[FATO]** `RecipeVersion` não tem `save()` guard nem `delete()` guard — o modelo
(`recipe_book.py:82-181`) tem apenas `clean()` (`:168`, valida `yield_quantity` e `steps`).
A trava mora **exclusivamente** em `update_draft` (`services/recipe_book.py:186-192`).

→ Um `RecipeVersion.objects.filter(...).update(formula=...)` no shell, um script de seed ou
uma futura tela de Admin reescrevem uma versão publicada **em silêncio**.
Contraste com `MarketingContentArtifact` (`campaign.py:808-810`), que recusa.
**Correção: P** — copiar o padrão do Marketing para `RecipeVersion`.

### 2.3 ⚠️ A ficha de execução ainda pode ser editada por fora

**[FATO]** `Recipe` é registrada no Admin com inline de itens:
`packages/craftsman/shopman/craftsman/contrib/admin_unfold/admin.py:376-401` (`RecipeAdmin`,
`inlines = [RecipeItemInline]`). Como `Recipe` **não tem histórico** (§1.5), uma edição pelo
Admin **não deixa rastro** e faz a ficha divergir da versão publicada. O único denunciante é o
`version_ref` (`Recipe.meta["version_ref"]`, `docs/reference/data-schemas.md:1550`), que é
**comparação exata** — mas hoje a projection não expõe um campo "ficha fora de sincronia"
(o `grep` por `in_sync`/`is_versioned` em `shopman/backstage/projections/recipe_book.py` retorna vazio).

→ A ADR-027 (`docs/decisions/adr-027-recipe-book-authoring-vs-execution.md:69`) prometeu que
"a projection expõe se a ficha está em sincronia" — **não cumprido**.
**Correção: P** — um booleano na projection do detalhe.

### 2.4 O que **não** é lacuna (é decisão, e está certa)

- Não existe "restaurar versão excluída": `RecipeVersion` não tem delete pela UI. Correto.
- Não existe edição de versão publicada pela UI: correto.
- Não existe merge de duas versões. Não precisa.

---

## 3. (b) Anexos visuais por papel — **NADA EXISTE**

### 3.1 Resposta direta: não há como anexar arquivo hoje

**[FATO]** Varredura no repo inteiro por model de mídia:

```
$ grep -rn "models.FileField|models.ImageField" --include=*.py packages/ shopman/ config/
shopman/shop/migrations/0001_initial.py:108:  ('logo', models.FileField(... upload_to='branding/' ...))
shopman/shop/models/shop.py:168:              logo = models.FileField(... upload_to="branding/" ...)
```

→ **Dois resultados, e são o mesmo campo.** O único `FileField` do sistema é o logotipo da loja.
**Não existe nenhum model de mídia, anexo, arquivo ou imagem.**

**[FATO] Não existe endpoint de upload.** `grep -rn "MultiPartParser|request.FILES|files\[" --include=*.py shopman/`
retorna vazio; `grep -rn "FormData|multipart" surfaces/*/app` retorna vazio.

### 3.2 Como o catálogo resolve foto hoje: **URL externa, não upload**

**[FATO]** `packages/offerman/shopman/offerman/models/product.py:164-168`:

```python
image_url = models.URLField(_("URL da imagem"), ...)
help_text=_("URL da imagem principal do produto (ex: Unsplash, Cloudinary, S3)"),
```

→ O catálogo **não guarda bytes**. Guarda um link. Não há galeria, não há miniatura, não há
model de imagem secundária. **Não é um padrão a espelhar para anexos de receita** — é a
negação do problema.

### 3.3 A foto que entra hoje entra e **evapora**

**[FATO]** `/recipes/new` aceita foto, mas ela só serve para o modelo de IA transcrever:

- `shopman/backstage/services/recipe_capture.py:46` `ACCEPTED_IMAGE_MEDIA_TYPES = ("image/jpeg", "image/png", "image/webp", "image/gif")`
- `recipe_capture.py:351-358 _build_content` — a imagem vai **base64 para o provedor**
- `recipe_capture.py:339 _clean_image` — valida e devolve, **não persiste**

O que sobra da imagem é **o nome do arquivo**, na string `source["image_name"]`
(`recipe_book.py:137-142`, `docs/reference/data-schemas.md:1575`).
→ **O "Original" (foto, rascunho, manuscrito), que é literalmente o papel nº 2 que o dono
pediu, é hoje descartado no fim do request.**

### 3.4 A infraestrutura está pela metade

**[FATO]** Configurado e servido, mas sem uso:
- `config/settings.py:573-575` `STORAGES` com `FileSystemStorage`
- `config/settings.py:586-587` `MEDIA_ROOT = os.path.join(BASE_DIR, "media")`, `MEDIA_URL = "/media/"`
- `config/urls.py:190` `urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)`
- `Dockerfile:95` `RUN mkdir -p /app/staticfiles /app/media`

**[FATO] O deploy não declara NENHUM volume, disco ou Spaces:**
`grep -n "volume|disk|spaces|s3" .do/app.alpha-subdomains.yaml` → **vazio**.
Os serviços sobem com `instance_count: 1` (`.do/app.alpha-subdomains.yaml:838 web`, `:1064 operator-floor`, `:1155 operator-office`).

**[INFERÊNCIA]** Com `FileSystemStorage` sobre `/app/media` e sem volume declarado, os anexos
vivem **dentro do container `web`**. Sobrevivem a restart, morrem em redeploy, e não escalam
para `instance_count: 2` nem para um segundo ambiente. **Não verifiquei o comportamento real
do App Platform** (não tenho acesso ao ambiente) — mas a ausência de volume no spec é fato.

→ **Esta é a única decisão de verdade em (b):** onde os bytes moram (DO Spaces/S3 + URL assinada,
ou volume persistente). Sem essa decisão, anexo de receita é feature que perde dado no próximo deploy.

### 3.5 O que falta para (b)

1. **Decisão de storage** (a de cima) — bloqueia tudo.
2. **Model de anexo** com o eixo **papel/função**. O repo já tem o molde do que é uma
   "taxonomia declarada e editável" em `QualityGrade`/`QualityDefect`
   (`shopman/shop/admin/quality.py:17-75`: `ref` + `label` + `is_active` + `position`, editável
   no Admin, com `ref` `readonly` quando já existe — `:39-41`). **É este o padrão a copiar**
   para os três papéis ("Auxílio à produção", "Original", "Referências externas"), em vez de
   `TextChoices` no código: os três papéis do dono são o começo da lista, não o fim.
3. **Anexo × versão.** Decidir se o anexo pertence à `RecipeEntry` (a receita, atravessa versões)
   ou à `RecipeVersion` (congelado com a fórmula). Minha leitura: **os dois** — "Original" é
   da versão (o manuscrito que originou *aquela* fórmula); "Auxílio à produção" é da entry
   (o esquema de modelagem não muda quando a hidratação muda).
4. **Volume e formato.** Foto de celular não pode entrar crua. Já existe precedente de
   redimensionamento no browser em `/recipes/new` (`RECIPE-INVENTORY-PLAN.md:258`, "redimensionada
   no navegador para ≤1600 px antes de enviar").
5. **"Referências externas" pode ser mais barato que anexo**: link + bibliografia não precisa
   de storage nenhum. Um campo JSON `links: [{url, title, note}]` na entry resolve 1/3 do
   pedido **hoje, sem infraestrutura**. Só "Original" e "Auxílio" (arquivo de verdade) precisam dos bytes.

---

## 4. (c) Avaliação 0–5 + "Favorita"

### 4.1 Nota por estrelas — **não existe no sistema**

**[FATO] O único 0–5 do repo é a nota do CLIENTE sobre o PEDIDO**, e é nota única, sem critérios:

```
shopman/shop/services/customer_orders.py:286-295
  data["customer_rating"] = {"rating": rating, "comment": comment[:500],
                             "submitted_at": ..., "source": "storefront_nuxt"}
```

Gravada em `Order.data["customer_rating"]` (JSON, padrão da casa). Lida em
`packages/orderman/shopman/orderman/admin.py:651-685` (estrelas ★☆ + comentário + data).
API: `POST /api/v1/orders/{ref}/rate/` — aparece em `shopman/storefront/tests/security/test_idor_sweep.py:36`.

→ **Não há critérios, não há múltiplos eixos, não há agregação.** O molde de restaurante
("ambiente, serviço, comida") que o dono descreveu **não tem precedente no repo** — seria o
primeiro. E note: a nota do cliente é sobre o **pedido**, não sobre a receita; são eixos diferentes.

**[FATO] O molde do que "critério configurável" significa neste repo é `QualityGrade`:**

```
shopman/shop/admin/quality.py:17-41   QualityGradeAdmin
  list_display: ("label","ref","rank","markdown_display","is_default","is_active")
  fieldsets: "Identificação" (ref,label,is_active) | "Política comercial" (rank, markdown_percent, is_default)
  get_readonly_fields: return ("ref",) if obj else ()    # o código é fixo, o rótulo edita
```

É uma tabela de referência **dirigida por dados, editável no Admin, já exportada no cofre**
(`shopman/shop/backup/resources.py:374 ("quality_grades", QualityGradeResource, 0)`).
O outro molde de configurabilidade é `RuleConfig` (`shopman/shop/models/rules.py:24-48`, com
`params` JSON e `history = HistoricalRecords()`).

→ **Decisão a tomar com o dono:** os critérios são **fixos em código** (3 eixos, tipo
restaurante) ou **tabela editável** (`RatingCriterion` com `ref/label/position/is_active`, no
molde do `QualityGrade`)? Fixo = **P**. Editável = **M** (mais Admin, mais migração, mais
agregação por critério). Recomendo **editável**, porque "ambiente, serviço, comida" para
panificação provavelmente vira "sabor, textura, aparência, dificuldade" — e o dono vai querer
mexer sem deploy.

### 4.2 "Favorita" por operador — **não existe, mas o molde é trivial**

**[FATO] O favorito de hoje é do CLIENTE e é sobre SKU:**

```
shopman/storefront/models/favorites.py:14-31
class CustomerFavorite(models.Model):
    customer_ref = models.CharField(max_length=64, db_index=True)
    sku          = RefField(ref_type="SKU", max_length=64)
    created_at   = models.DateTimeField(auto_now_add=True)
    constraints: UniqueConstraint(("customer_ref","sku"), name="uniq_customer_favorite")
```

API: `shopman/storefront/api/urls.py:204-205` (`account/favorites/`, `account/favorites/<sku>/`).

→ **Espelhar é copiar a forma de 3 colunas trocando os eixos:** `operator_ref` × `entry_ref`
(em vez de `customer_ref` × `sku`). **Não existe** favorito de operador no repo: o
`favoriteRefs` do PDV (`surfaces/pos-nuxt/app/components/PosProductGrid.vue:14`) é coleção
**derivada de venda**, não escolha do operador — vem do histórico de compra do cliente
(`shopman/backstage/projections/pos.py:2835-2883 favorite_product/favorite_item`,
`POSCheckoutOptionProjection(ref="favorite_item", label="Adicionar favorito")`).

**[FATO] A identidade do operador existe e é estável:**

```
shopman/backstage/api/recipe_book.py:57-59
def _actor(request) -> str:
    user = getattr(request, "user", None)
    return getattr(user, "username", None) or "operator"
```

`RecipeVersion.created_by` já é preenchido com isso (`packages/craftsman/.../recipe_book.py:145`).
→ "as receitas dele" é expressável hoje, **sem modelo de operador novo**.

**Tamanho: P.** Model de 3 colunas + 2 endpoints (`POST/DELETE favorites/<ref>/`) + filtro na
`RecipeBookListProjection` (`shopman/backstage/projections/recipe_book.py:160-165`) + chip na
`recipes/index.vue`.

---

## 5. (d) "Reputação" pelo uso real — a matéria-prima existe

### 5.1 O que já liga fornada → receita → VERSÃO

**[FATO] O carimbo de versão já é congelado no plano da fornada.**

```
packages/craftsman/shopman/craftsman/services/scheduling.py:54-76  build_recipe_snapshot()
    return {
        "batch_size": str(recipe.batch_size),
        "version_ref": (recipe.meta or {}).get("version_ref", ""),   # ← linha 69
        "items": [...],
        "production": {...},
    }
```

Vai para `WorkOrder.meta["_recipe_snapshot"]` e é **gerido pelo Core, nunca editado**
(`docs/reference/data-schemas.md:1518`). Confirmado pelos testes:
`packages/craftsman/shopman/craftsman/tests/test_recipe_book.py:525-532`.

→ **Este é o alicerce de (d), e ele está pronto e no `main`.** Sem ele, "reputação por versão"
seria impossível. Com ele, é uma consulta.

### 5.2 O ledger de produção já existe, com qualidade

**[FATO]** `packages/craftsman/shopman/craftsman/models/work_order_item.py:30-35`:

```python
class Kind(models.TextChoices):
    REQUIREMENT  = "requirement",  _("Requisito")
    CONSUMPTION  = "consumption",  _("Consumo")
    OUTPUT       = "output",       _("Saída")
    WASTE        = "waste",        _("Perda")
```

Com `quality_grade_ref` (`:85`) e `quality_defect_ref` (`:91`), **indexados**
(`:114-115`). E o consumo de insumo é derivado da ficha × coeficiente e escrito no ledger do
Stockman como `Move.Kind.MAKE` (`contrib/stockman/handlers.py:283,327,398,558`).

### 5.3 Agregação: existe por RECEITA, **não por versão**

**[FATO] `production_summary` fecha o dia por receita:**

```
shopman/backstage/services/closing.py:290-335
  summary[recipe_ref] = {"recipe_ref","output_sku","planned","finished","loss","quality":{grade: qty}}
```

Uma fonte, dois leitores (fechamento + pré-fechamento), persistido em `DayClosing.data`
(`docs/reference/data-schemas.md:1601`). Agrupado por `wo.recipe.ref` — **não por
`_recipe_snapshot["version_ref"]`** (`closing.py:302`).

**[FATO] O B.I. também agrupa por receita, e só por receita:**

```
shopman/backstage/projections/bi_production.py:67-72   BIProductionReport.oven_time_by_recipe
shopman/backstage/projections/bi_production.py:246-253 _oven_rows(..., group="recipe") → key = (wo.recipe.ref, wo.recipe.name)
```

`grep -rn "recipe_ref|version_ref" --include=*.py shopman/backstage/projections/bi_*.py` → **vazio**
nas projections `bi_*` (só aparece em `bi_production.py` via `wo.recipe.ref`).

→ **A pergunta "a v3 rende mais que a v2?" é respondível hoje, e ninguém a responde.**
O dado está no `meta` da fornada; falta a leitura.

### 5.4 Três avisos que qualquer "reputação" precisa carregar

1. ⚠️ **[FATO] A perda é resíduo contábil, não medida.** `production_summary` calcula
   `loss = (started_qty or quantity) − finished` (`closing.py:317-318`). O próprio briefing do
   dono já sabe disso: *"perda real (massa na bacia, aparas) infla o número... É resíduo
   contábil, não medido"* (`.claude/worktrees/receitas-paes-producao-26a519/docs/plans/RECIPE-MODELING-BRIEF.md:110`).
   **Uma "reputação" que ordene receitas por perda vai ordenar por quem anota melhor.**
2. ⚠️ **[FATO] A perda de forno é estimativa nunca auditada.** `Recipe.meta["bake_loss_pct"]`
   ausente cai no padrão `12` da casa, rotulado `house_default`
   (`docs/reference/data-schemas.md:1552`: *"estimativa nunca auditada: o número de 12% nunca
   passou pela balança"*).
3. ⚠️ **[FATO] Ficha nunca publicada pelo inventário tem `version_ref = ""`** e a defasagem é
   **indetectável** (`docs/reference/data-schemas.md:1418`, `shopman/shop/services/derived_provenance.py`).
   As 90 fichas do seed e o bootstrap de 67 entradas (`RECIPE-INVENTORY-PLAN.md:279`) precisam
   ser conferidas antes de qualquer ranking por versão.

### 5.5 O que falta para (d)

**Fatia 1 (P):** ler `WorkOrder.meta["_recipe_snapshot"]["version_ref"]` e agrupar o
`production_summary` por versão. Já responde: fornadas por versão, massa planejada ×
produzida, perda média, mix de grade de qualidade. Sem tabela nova, sem migração — é uma
segunda chave de agrupamento em `closing.py:290-335`.

**Fatia 2 (P/M):** expor essa leitura na linha do tempo da versão
(`surfaces/production-nuxt/app/pages/recipes/[ref]/index.vue:393-420`), ao lado de cada versão:
"executada em N fornadas; rendimento médio X; perda Y". Isto **é** a resposta ao pedido do dono,
e é onde (d) encontra (a).

**Fatia 3 (M, opcional):** série histórica consultável. Hoje a agregação do dia cai em
`DayClosing.data` (JSON) — não há tabela indexada por receita/versão/dia. Se "reputação" virar
número que o dono olha toda semana, aí sim precisa de materialização. **Não fazer antes de a
Fatia 1 provar que alguém olha.**

---

## 6. Veredito: **merece projeto solo? NÃO**

### 6.1 Por quê

O dono imagina que "edição com versionamento, registro imutável e voltar atrás" é trabalho a
fazer. **É trabalho feito.** `RecipeEntry`/`RecipeVersion`, a matemática base-first, a
publicação como único escritor, a tela com linha do tempo, o comparador, 104 testes — tudo
mergeado em 03/09/2026 e presente em `origin/main`. Um "projeto solo de versionamento"
começaria **reescrevendo o que existe**, que é o pior resultado possível.

### 6.2 Tamanho por fatia

| # | Fatia | Tamanho | Bloqueio? |
|---|---|---|---|
| 1 | Cofre carrega `RecipeEntry`/`RecipeVersion` (§2.1) | **P** | **SIM — é perda de dado.** Fazer primeiro |
| 2 | Guard de imutabilidade no `save()`/`delete()` do `RecipeVersion` (§2.2) | **P** | não |
| 3 | Booleano "ficha fora de sincronia" na projection (§2.3) | **P** | não |
| 4 | Copy do botão de volta ("Nova versão" → dizer que é a volta) (§1.2) | **P** | não |
| 5 | "Favorita" por operador (§4.2) | **P** | não |
| 6 | Reputação por versão, leitura (§5.5 fatia 1) | **P** | não |
| 7 | Reputação na linha do tempo (§5.5 fatia 2) | **P** | depende de 6 |
| 8 | "Referências externas" como links (JSON, sem bytes) (§3.5 item 5) | **P** | não |
| 9 | Nota 0–5 com critérios, taxonomia editável (§4.1) | **M** | decisão do dono: fixo ou configurável |
| 10 | Anexos por papel (§3) | **M** | **SIM — decisão de storage (§3.4)** |
| 11 | Série histórica materializada (§5.5 fatia 3) | **M** | não — e provavelmente desnecessária |

**Total: 8 fatias P + 3 fatias M.** Não é G. Não é projeto solo: é **um pacote M**, um
`RECIPE-LIFECYCLE` com fatias independentes, entregáveis uma por PR.

### 6.3 O que fazer sem projeto solo, em ordem

**Agora (antes de qualquer coisa nova):** fatia 1 — o cofre. É a única do conjunto que é
**perda de dado**, e é pequena. Um recurso de `ModelResource` em `shopman/shop/backup/resources.py`
no molde do `RecipeResource` que já está lá (`:387`).

**Depois, na mesma semana:** 2, 3, 4, 5, 6 — todas P, todas tocam arquivos que já existem
(`recipe_book.py` models/services, `projections/recipe_book.py`, `recipes/index.vue`).

**Quando o dono decidir a infra:** fatia 10 (anexos). **Anexo sem decisão de storage é
feature que perde arquivo no próximo deploy.** Levar a pergunta a ele, não decidir sozinho:
DO Spaces (URL assinada, escala, custa) ou volume no App Platform (mais barato, prende ao
container, complica o segundo ambiente).

**Só se ele pedir:** 9 e 11.

---

## 7. Onde procurei e não achei (para não repetir a busca)

| Procurei | Onde | Resultado |
|---|---|---|
| `revision` em orderman | `grep -rn "revision" --include=*.py packages/orderman/` | **vazio** |
| histórico no Craftsman | `grep -rn "HistoricalRecords" packages/ shopman/ config/` | 12 arquivos, **nenhum do craftsman** |
| model de mídia | `grep -rn "models.FileField\|models.ImageField"` em todo o repo | **só `Shop.logo`** |
| endpoint de upload | `grep "MultiPartParser\|request.FILES\|FormData\|multipart"` em `shopman/` e `surfaces/` | **vazio** |
| avaliação interna | `grep -rni "rating\|estrela\|stars\|avalia"` | só `Order.data["customer_rating"]` |
| favorito de operador | `grep -rni "favorit" surfaces/` + `projections/pos.py` | só favorito **do cliente**, derivado de venda |
| reputação por versão | `grep "recipe_ref\|version_ref" shopman/backstage/projections/bi_*.py` | **vazio** |
| volume no deploy | `grep "volume\|disk\|spaces\|s3" .do/app.alpha-subdomains.yaml` | **vazio** |
| inventário no cofre | `grep "RecipeEntry\|RecipeVersion" shopman/shop/backup/` | **vazio** |
| botão "voltar atrás" | `grep -rni "revert\|rollback\|restaurar"` em craftsman/backstage | só rollback **transacional** de teste |

## 8. Não verificado

- **[NÃO VERIFICADO]** Comportamento real de `MEDIA_ROOT` no App Platform da DigitalOcean entre
  redeploys (não tenho acesso ao ambiente). O que **é** fato é a ausência de volume/disco/Spaces
  no spec (`grep` vazio em `.do/app.alpha-subdomains.yaml`).
- **[NÃO VERIFICADO]** Se o inventário de receitas está **em uso** na operação viva (quantas
  `RecipeEntry`/`RecipeVersion` existem no banco do alpha, e se alguma foi publicada por
  humano). Não consultei o banco vivo.
- **[NÃO VERIFICADO]** O estado exato de `origin/main` para a **superfície** `recipes/` — o
  `git cat-file -e` provou a existência de `index.vue` em `origin/main`, mas não comparei
  byte a byte com a worktree.
- **[NÃO VERIFICADO]** Os 90 registros de `recipes_data` do seed
  (`config/management/commands/seed.py`, ~`:2818`) quanto a terem virado `RecipeEntry` — o
  `RECIPE-INVENTORY-PLAN.md:279` fala em bootstrap de 67 fichas; a diferença não foi explicada.
- `bootstrap_recipe_book` está em `packages/craftsman/shopman/craftsman/management/commands/bootstrap_recipe_book.py`
  e é chamado ao fim de `_seed_recipes` (`config/management/commands/seed.py:5125-5131`).

---

## 9. Referências

- `docs/decisions/adr-027-recipe-book-authoring-vs-execution.md` — a decisão de arquitetura (autoria × execução)
- `docs/plans/RECIPE-INVENTORY-PLAN.md` — o plano, com a tabela de WPs entregues (§10)
- `.claude/worktrees/receitas-paes-producao-26a519/docs/plans/RECIPE-MODELING-BRIEF.md` — o briefing do dono (05/09/2026), 138 linhas, ainda válido
- `docs/reference/data-schemas.md:1518,1550,1562-1575,1601` — `_recipe_snapshot`, `version_ref`, `source`, `production_summary`
