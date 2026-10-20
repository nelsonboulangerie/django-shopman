# ORDEM — 2026-10-19, turno 2: frente 6 (catálogo iFood pela API) — coordenação DSH

> Canal: este arquivo (next-6.md). A sessão executora (Codex) lê inteiro, executa nesta ordem,
> e registra no BOARD e em ROUNDS. Base: origin/main = 4e685c985.
> Antes de começar: git fetch origin, git log --oneline -1 origin/main, gh pr list --state open.

## O que já está em voo (não duplique, não toque)

- **#1900 — Compras no servidor (sessão 1).** Na fila. Não toque em
  shopman/backstage/api/purchase.py, projections/purchase.py nem surfaces/purchase-nuxt/**.
- **#1905 — foto do catálogo iFood (sessão 1).** Aberto e **vermelho**, mexendo em
  shopman/shop/adapters/catalog_projection_ifood.py. **A foto NÃO é desta ordem** e um PR novo
  sobre o mesmo arquivo colide. Esta ordem começa pelo único bloco que não encosta na foto.
- **#1911 — outra coordenação, com shopman/shop/migrations/0101_**. Qualquer migração nova nesta
  frente é 0102+ e só entra depois que a #1911 mergear. Se você precisar de migração, **pare** e
  diga no relatório.
- **Sessão 1 continua com o kit de import/export** (surfaces/operator-kit/** e componentes de
  import/export do orders-nuxt). Não toque.

## Contrato da sessão

1. Uma fatia = um worktree = um branch = um PR.
2. Primeira coisa: copie este arquivo para docs/coordination/ORDERS/2026-10-19-frente6-ifood.md no
   primeiro branch e commite junto. **Não esvazie** o next.md (ele já está vazio; a sessão 1 cuida).
3. Reivindique antes do primeiro edit: empurre o branch e abra PR draft WIP: <id> ….
4. Esteira no mesmo turno: commit → push → PR → gh pr merge <N>. Vermelho: causa lida no log.
5. Ao terminar cada frente: linha no docs/coordination/BOARD.md e registro em
   docs/coordination/ROUNDS/<id>-<slug>.md.
6. Worktree próprio; git add só arquivo nomeado; nunca git stash puro. Scratchpad com nome único.
7. Teste de packages/* com o .venv da raiz e PYTHONPATH/PYTHON explícitos.

## Regras comuns

1. Worktree próprio; add só arquivo nomeado; nunca stash puro.
2. Esteira no mesmo turno.
3. Vermelho: causa lida no log.
4. Baseline visual só a CI regenera.
5. Conjunto mínimo Nuxt UI (md/xl; solid/outline/ghost; primary/neutral/error); :ui mora uma vez no kit.
6. Copy inequívoca, curta, **sem travessão**, vocabulário de docs/reference/suite-vocabulary.md e
   docs/reference/omotenashi-copy.md; **"dispositivo"**, nunca "aparelho". Zero jargão em tela.
7. Desempenho é requisito: medir antes e depois (Server-Timing e contagem de consultas), número no PR.
8. Prévia em navegador de verdade, zero 4xx/5xx, capturas antes/depois claro/escuro, nome único.
9. Faixa de portas própria; matar só os próprios processos.
10. Core (packages/) é sagrado.

## Checklist D1 a D12 (item a item no PR, em toda tela)

D1 cartão de topo outline, cartão dentro de cartão soft sem borda, selo soft · D2 cards sem
cabeçalho/rodapé destacado · D3 botões do conjunto mínimo, conteúdo centrado, sem esticar ·
D4 borda a borda · D5 peças irmãs de altura igual · D6 rótulo completo, depois curto, depois ícone
com aria e tooltip · D7 campo não maior que botão · D8 ação na cor do aviso, aviso acionável e
dispensável · D9 ajuste inline com Aplicar/Cancelar, escolha fora em modal, destruir = confirmar +
Desfazer · D10 copy da casa · D11 Nuxt UI canônico · D12 abrir as próprias capturas.

## Limites duros

- **Nenhuma escrita em loja real.** SHOPMAN_IFOOD_CATALOG_WRITE_POLICY só aceita environment=test +
  merchant na allowlist (docs/reference/ifood-catalog-write-policy.md). Não afrouxe a guarda, não
  crie variável de liberação, não ligue IFOOD_CATALOG_PROJECTION.
- **Nenhuma credencial** em código, teste, doc ou PR. O que faltar vira pergunta no corpo do PR.
- **Nada de HTTP real nos testes.** requests sempre simulado; testes não pedem OAuth nem baixam
  foto de host de verdade (foi o que derrubou o #1905).
- O vínculo (shop/models/catalog_binding.py + backstage/services/catalog_bindings.py) hoje é
  evidência e revisão: não publica, não enfileira, não envia. Nesta frente ele passa a ser **lido**
  pelo envio, nunca escrito pelo adapter.

## Território reservado (NÃO toque)

shopman/shop/services/fiscal.py, shopman/shop/notifications.py,
shopman/backstage/projections/pos.py, shopman/backstage/api/operations.py,
shopman/storefront/api/geocode.py, shopman/shop/services/promotions.py, shopman/shop/modifiers.py,
shopman/shop/services/cart.py, shopman/shop/services/availability.py,
shopman/shop/adapters/stock.py, shopman/shop/notification_copy.py, shopman/shop/config.py,
surfaces/pos-nuxt/**, surfaces/orders-nuxt/**/customers/**, surfaces/production-nuxt/**,
packages/orderman/**, packages/craftsman/**, docs/plans/**.
Precisou? Pare e escreva no relatório ao dono.

---

# Frente A — categorias: criar, renomear e ordenar pela API  [neste turno, primeiro]

**Tamanho:** M. **Branch:** codex/ifood-categorias.

**Medido hoje:** o adapter só tem o mapa catalog_category_map + catalog_default_category
(_resolve_category_id, catalog_projection_ifood.py:119) e não lista, cria nem edita categoria.
Contrato confirmado na doc em docs/plans/IFOOD-CATALOG-READINESS-2026-09-13.md:
POST .../categories (obrigatórios name, status, template; opcionais id, externalCode, index) e
PATCH .../categories/{categoryId} (opcionais name, externalCode, status, index; resposta 200).
Nome duplicado pode dar 409 e **não autoriza criar outra** — reconcilie a identidade existente.
Ordenação usa index, não sequence.

**Tarefa:**
1. Listar categorias (com includeItems), criar, renomear, reordenar e mudar status. Cada intenção
   com **corpo mínimo**: renomear envia só name; reordenar só index; status só status.
2. Trocar o mapa estático por configuração administrável, mantendo leitura compatível de
   catalog_category_map / catalog_default_category: coleção interna aponta para a categoria remota
   escolhida; categoria remota é reconciliada por id, nunca recriada por nome.
3. Guarda: toda operação passa por ensure_catalog_write_allowed **antes** de OAuth/HTTP, como o
   upsert. 429 preserva a intenção; 409 vira pendência legível; nada de retry cego.
4. **Não encoste em _item_payload** (é o #1905 e a frente B). Se precisar, pare e diga no relatório.
5. Fora de escopo: a tela (frente D) e o ensaio ao vivo (frente E).

**Prova:** testes simulados de criar/renomear/reordenar (corpo mínimo por intenção, sem campo a
mais), 409 sem segunda criação, 429 preserva a intenção, guarda nega antes do HTTP, e mapa vazio
não cria categoria sozinho.

**Pronto quando:** PR verde na fila e o contrato de categorias coberto por teste.

---

# Frente B — o vínculo dirige o envio (resolvedor único)

**Tamanho:** M. **Branch:** codex/ifood-vinculo-resolvedor.
**Depende do #1905 mergeado** (mesmo arquivo). Antes de abrir o PR: git merge origin/main e mantenha
as duas mudanças (imagePath do #1905 e os ids do vínculo). Se o #1905 ainda estiver aberto, faça a
frente C antes desta.

**Medido hoje:** _item_payload deriva item e product por uuid5(merchant, sku)
(_item_uuid/_product_uuid) e ignora o CatalogBinding. Resultado: um SKU reconciliado por vínculo é
enviado para outro item, criando anúncio paralelo. O vínculo tem a identidade remota:
(provider, account_ref, catalog_ref, context, resource_id) único no banco, mais
external_product_ref, category_ref, item_context_ref, revision, snapshot
(docs/reference/catalog-bindings.md). _set_item_status usa o mesmo uuid derivado.

**Tarefa:**
1. Um resolvedor único, em módulo novo do shop (por exemplo shopman/shop/services/catalog_identity.py):
   para (sku, channel) devolve item_id, product_id, category_ref e a origem ("binding" | "derived").
   - binding vigente cujo provider/account_ref/catalog_ref/context batem com o SHOPMAN_IFOOD
     configurado → resource_id / external_product_ref;
   - sem binding, ou binding de outro escopo → uuid5 como hoje.
2. O adapter usa o resolvedor em _item_payload e em _set_item_status. **Não** cria, altera ou apaga
   binding; não enfileira nada.
3. category_ref do vínculo é o ponto de partida da categoria quando não há exceção local.
4. Testes: com vínculo → payload e PATCH usam o id remoto, nunca uuid derivado; sem vínculo → uuid
   derivado; binding de outro merchant/account → ignorado com aviso, não erro fatal; dois SKUs com o
   mesmo resource_id → erro explícito, nunca escolha silenciosa.

**Prova:** testes com transporte simulado nos quatro casos; suíte
shopman/storefront/tests/test_catalog_projection_ifood.py e a de catálogo do backstage verdes.

**Pronto quando:** PR verde na fila e o resolvedor é o único lugar que decide identidade remota.

---

# Frente C — preço e pausa por PATCH específico

**Tamanho:** M. **Branch:** codex/ifood-preco-pausa-patch.

**Medido hoje:** preço e status sobem no **PUT completo** do item (FullItemDto), que reescreve
categoryId, index, shifts e o produto inteiro. A doc do módulo Catalog tem PATCH específico de
preço e de status, global ou por contexto; alteração pontual deve preservar imagem, complementos,
horários e contextos alheios (docs/plans/CATALOG-INTEGRATIONS-2026-09-14.md, critérios).

**Tarefa:**
1. Separar a intenção: quando o que mudou é só preço ou só disponibilidade, sair por PATCH
   específico com os ids resolvidos (frente B ou uuid derivado); o PUT completo fica para criação e
   para mudança de texto/estrutura.
2. Preservar sempre: imagePath vigente, categoria, index, shifts e contexto não pretendido.
3. Duas mudanças rápidas convergem na última intenção (o handler já serializa por SKU/canal; não
   invente outro mutex).
4. Leitura de confirmação: depois do PATCH, ler o item e registrar o estado remoto confirmado; falha
   de leitura não vira falso sucesso.

**Prova:** testes simulados: PATCH de preço não envia name/description/category/shifts nem apaga
imagePath; pausa e retomada usam status; pausa durante envio em trânsito termina em UNAVAILABLE;
erro 429 preserva a intenção e o retry lê o estado atual.

**Pronto quando:** PR verde na fila e o PR diz, em uma linha, qual caminho cada intenção usa.

---

# Frente D — a tela de categorias em Canais

**Tamanho:** M. **Branch:** codex/ifood-categorias-tela.
**Depende da frente A.**

Na página do canal (surfaces/orders-nuxt/app/pages/channels/[ref]/catalog.vue e os composables de
binding), o operador mapeia a coleção interna para a categoria remota, **renomeia** e **ordena**
arrastando ou por campo, com pendência e erro legíveis, sem ID na cara e sem JSON. Estado remoto
confirmado vem da mesma projeção da matriz; nenhuma segunda implementação de edição. D1 a D12,
capturas claro/escuro e o teste de componente.

---

# Frente E — ensaio na loja de TESTE (bloqueada)

**Tamanho:** S. **Branch:** codex/ifood-ensaio.
Roteiro dos passos 4 e 5 de docs/plans/CATALOG-INTEGRATIONS-2026-09-14.md: pausar, retomar, mudar
preço, mudar descrição, mover de categoria e subir foto **num item de teste**, conferindo leitura
remota e restaurando. **Sem credencial não se executa**: abra PR draft com o roteiro escrito e a
pergunta no corpo. Não use loja real, não invente ensaio.

**Pergunta que vai no PR:** para rodar o ensaio, o dono precisa (1) confirmar o UUID do merchant de
teste que entra em SHOPMAN_IFOOD_CATALOG_WRITE_POLICY.merchant_allowlist, (2) digitar client_id e
client_secret no ambiente isolado do ensaio, e (3) liberar 1 item de teste e 1 categoria de teste.
