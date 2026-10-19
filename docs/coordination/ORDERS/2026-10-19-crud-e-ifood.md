# ORDEM — 2026-10-19, turno do CRUD turbo + catálogo iFood (coordenação DSH)

> Canal vivo: este arquivo. A sessão executora (Codex) lê inteiro, executa tudo, e registra
> no BOARD e em ROUNDS. Base de referência: origin/main = 4e685c985. Confira antes de começar:
> git fetch origin && git log --oneline -1 origin/main, e gh pr list --state open.
> Se alguma frente abaixo já tiver PR aberto, NÃO duplique: registre e pegue a próxima.

## Contrato da sessão

1. **Uma fatia = um worktree = um branch = um PR.** Três frentes abaixo, três PRs separados,
   que mergeiam sozinhos.
2. **Primeira coisa:** no primeiro branch, copie este arquivo para
   docs/coordination/ORDERS/2026-10-19-crud-e-ifood.md e commite junto. Quando o terceiro PR
   estiver aberto, **esvazie** o docs/coordination/ORDERS/next.md do checkout principal.
3. **Reivindique antes do primeiro edit de código:** empurre o branch e abra PR draft
   WIP: <id> …. A reivindicação que vale é o PR draft, não a linha do BOARD.
4. **Esteira no mesmo turno:** commit → push → PR → gh pr merge <N>. PR draft só sai de draft
   completo e verde. Vermelho: nomeie a causa lendo o log, nunca reenfileire às cegas.
5. **Ao terminar cada frente:** linha no docs/coordination/BOARD.md (estado, branch/PR) e
   registro em docs/coordination/ROUNDS/<id>-<slug>.md.
6. Worktree próprio; git add só arquivo nomeado; **nunca** git stash puro. Scratchpad com nome
   único por frente (pr<n>-*.md), nunca pr.md.
7. Migração: antes do PR, ls <app>/migrations | sed 's/_.*//' | sort | uniq -d (numeração colide
   em silêncio entre branches).
8. Teste de packages/* só com o .venv da raiz e PYTHONPATH/PYTHON explícitos (worktree não testa
   Core sozinha).

## Regras comuns (valem para toda frente)

1. Worktree próprio; add só arquivo nomeado; nunca stash puro.
2. Esteira no mesmo turno (acima).
3. Vermelho: causa lida no log. "Marketing — cadeia completa" é flake conhecido.
4. Baseline visual só a CI regenera (docs/reference/operator-visual-baselines.md).
5. Conjunto mínimo Nuxt UI (md/xl; solid/outline/ghost; primary/neutral/error); :ui mora uma vez
   no kit.
6. Copy inequívoca, curta, **sem travessão**, vocabulário de docs/reference/suite-vocabulary.md e
   docs/reference/omotenashi-copy.md; **"dispositivo"**, nunca "aparelho" (fora do Storefront).
   Zero jargão ("N+1", "payload", "endpoint", "server-side") em texto de tela.
7. Desempenho é requisito: **medir antes e depois** com Server-Timing e contagem de consultas
   (padrão de shopman/backstage/tests/test_catalog_server_list.py e test_pos_projecao_consultas.py)
   e **pôr o número no corpo do PR**.
8. Prévia testada em navegador de verdade, zero 4xx/5xx, capturas antes/depois claro/escuro com
   nome único da frente.
9. Faixa de portas própria por agente; matar só os próprios processos.
10. Core (packages/) é sagrado: mudança só com necessidade medida; chave nova de JSONField entra
    antes em docs/reference/data-schemas.md.

## Checklist de design do dono (D1 a D12 — relatar item a item no PR)

- D1. Cartão de topo outline; cartão dentro de cartão soft sem borda. Selo sempre soft.
- D2. Cards sem cabeçalho/rodapé destacado salvo necessidade real.
- D3. Botões só do conjunto mínimo; conteúdo centrado; botão não estica além do necessário.
- D4. Alinhamento borda a borda dentro do bloco.
- D5. Peças irmãs de tamanho fixo com a mesma altura (2 linhas reservadas + reticências, ou todas 1 linha).
- D6. Rótulo: completo, depois curto escrito à mão, depois só ícone (aria + tooltip).
- D7. Campos não maiores que botões, salvo obrigação.
- D8. Ação dentro de aviso na cor do aviso; avisos acionáveis e dispensáveis.
- D9. Um padrão por gesto: ajuste na tela = inline com Aplicar/Cancelar; escolher algo fora = modal; destruir = confirmar + Desfazer.
- D10. Copy da casa, sem travessão, sem jargão técnico, sem repetir o mesmo dado.
- D11. Tudo Nuxt UI canônico (primitiva > classe copiada).
- D12. Abrir as próprias capturas e caçar desalinhamento, borda indevida, altura desigual, corte, aperto.

## Território reservado (NÃO toque)

Outra coordenação tem agentes vivos nestes arquivos:
shopman/shop/services/fiscal.py, shopman/shop/notifications.py,
shopman/backstage/projections/pos.py, shopman/backstage/api/operations.py,
shopman/storefront/api/geocode.py, shopman/shop/services/promotions.py,
shopman/shop/modifiers.py, shopman/shop/services/cart.py,
shopman/shop/services/availability.py, shopman/shop/adapters/stock.py,
shopman/shop/notification_copy.py, shopman/shop/config.py, surfaces/pos-nuxt/**,
surfaces/orders-nuxt/**/customers/**, surfaces/production-nuxt/**,
packages/orderman/**, packages/craftsman/**, docs/plans/**.
Precisou de um deles? **Pare** e escreva no relatório ao dono.

---

# Frente 1 — §7.2-kit: import/export genérico nasce UMA vez no operator-kit

**Tamanho:** M. **Depende de:** nada. **Branch:** codex/kit-import-export.

**Medido hoje (19/10, origin/main 4e685c98):**
- A prévia de import mora presa no app: surfaces/orders-nuxt/app/components/CatalogImportCsv.vue
  (168 linhas) + surfaces/orders-nuxt/app/composables/useCatalogMatrix.ts:909 (previewImport /
  applyImport) chamando POST /api/v1/backstage/catalog/product/import/ com {csv, preview: true}.
- O export mora numa função de app: surfaces/orders-nuxt/app/presentation/customers.ts:110
  (customersCsv). Os helpers puros de leitura de CSV já existem no kit
  (operator-kit/app/presentation/readingChart.ts: readingCsvText / readingCsvMoney).
- O kit **não** tem peça de import nem de export.

**Tarefa:**
1. Nascer no kit, uma vez, em surfaces/operator-kit/app/components/: a peça de importação
   (escolher arquivo, prévia do que muda com totais novo/atualiza/sem mudança, **erro por linha**
   com número da linha e motivo, confirmação que leva a revisão da prévia) e a de exportação
   (baixar a lista corrente).
2. A regra de CSV pt-BR mora em operator-kit/app/presentation/ puro e testado com vitest:
   **vírgula decimal** (padrão do #1670), separador ponto e vírgula, cabeçalho em português, BOM
   quando for para Excel, e leitura tolerante a decimal com ponto. Nada de domínio dentro do kit:
   ele recebe colunas, linhas e um preview(csv) / apply(revision).
3. Migrar o catálogo para a peça do kit e **apagar** CatalogImportCsv.vue. O comportamento do
   catálogo não muda: mesmas rotas, mesma revisão de prévia, mesmos erros.
4. Exportar a lista de clientes pelo mesmo caminho, apagando customersCsv do app (mantendo o
   texto do arquivo idêntico, byte a byte — teste de paridade).
5. **Fora de escopo desta fatia:** ligar import/export a insumo, fornecedor, receita e grupo
   (fatias seguintes) e prévia em segundo plano com progresso (frente própria).

**Prova:**
- Testes do kit (vitest) para CSV pt-BR: 1.234,56 → 123456 centavos; 12.50 → 1250; vírgula vs
  ponto; cabeçalho escapado; linha com campo a mais vira erro daquela linha.
- Teste de componente: prévia mostra contagens e erros por linha; confirmar envia a revisão.
- Suíte do orders-nuxt verde e o alvo de testes das surfaces verde.
- Capturas antes/depois claro/escuro do diálogo de importação (nome único da frente) + D1 a D12.

**Pronto quando:** PR verde na fila, CatalogImportCsv.vue e customersCsv não existem mais, e o PR
mostra que o kit é o único lugar com a regra.

---

# Frente 2 — §7.2-compras: insumos e fornecedores paginando, filtrando e ordenando NO SERVIDOR

**Tamanho:** M. **Depende de:** nada. **Branch:** codex/compras-lista-no-servidor.

**Medido hoje:**
- shopman/backstage/api/purchase.py:108 (PurchaseBoardView, já com ServerTimingMixin) serve
  GET /api/v1/backstage/purchase/ com build_purchase() (projections/purchase.py:297) devolvendo
  **tudo**: materials, suppliers, conversions, costs.
- Não há page, page_size, q nem order em purchase.py (grep: nenhum). O recorte, a busca e a
  ordenação acontecem no cliente (surfaces/purchase-nuxt/app/composables/usePurchaseDesk.ts).
- **O caminho já existe e é o modelo:** o catálogo do Gestor virou lista de servidor em
  CatalogMatrixView (api/catalog.py:48-78: q, order, page, page_size, filtros) com o teste
  shopman/backstage/tests/test_catalog_server_list.py provando que a contagem de consultas **não
  cresce com o número de linhas**. Espelhe esse padrão, não invente outro.

**Tarefa:**
1. GET /purchase/ passa a aceitar page, page_size, q, order e os filtros que a tela já tem
   (situação/atenção, fornecedor, cobertura) e devolve, por lista, items + total + has_next +
   page. Paginação e ordenação são do **banco** (order_by traduzido de uma allowlist, nunca
   order_by(param) cru).
2. As facetas que hoje a tela calcula (cobertura, custo base, situação) saem em **lote**: uma
   leitura por faceta, não uma por linha.
3. usePurchaseDesk passa a pedir a página ao servidor; tabela, filtro, busca e ordenação mantêm o
   comportamento visível. O "‹ 3 de 18 ›" e a URL continuam funcionando (recorte e ordem da pessoa).
4. **Fora de escopo:** ações em lote e tabelão (frentes seguintes).

**Prova (desempenho é requisito do dono):**
- Teste novo no padrão de test_catalog_server_list.py: CaptureQueriesContext com 5 e com 500
  insumos, mesma page_size → **mesma contagem de consultas**; reprova se crescer.
- Server-Timing na resposta e o número antes/depois no corpo do PR (consultas e ms com 500 linhas,
  medidos localmente).
- Teste de contrato da resposta paginada (total/has_next coerentes, page fora da faixa).
- Capturas antes/depois claro/escuro da lista e do filtro + D1 a D12.

**Pronto quando:** PR verde na fila, número de consultas constante no teste, e nenhum recorte
feito no cliente.

---

# Frente 3 — §6-foto: a foto do produto sobe para o iFood (imagePath)

**Tamanho:** M. **Depende de:** nada. **Branch:** codex/ifood-foto.

**Medido hoje:**
- shopman/shop/adapters/catalog_projection_ifood.py:138 (_item_payload) monta o FullItemDto
  **sem imagem**; o comentário em :167-169 diz "no inline image … separate upload flow
  (imagePath), out of scope". URL inline dá **500** no iFood (verificado ao vivo 01/07); o caminho
  é **upload base64 → imagePath** (docs/plans/CATALOG-FIELD-AUDIT-2026-09-14.md: JPG/JPEG/PNG até
  5 MB, imagePath reutilizável).
- ProjectedItem.image_url **já existe** (packages/offerman/.../protocols/projection.py:34) e já é
  preenchido: não mexa no Core.
- A casa já tem o fluxo de foto do produto no Gestor: POST
  /api/v1/backstage/catalog/product/photo/upload/ → backstage/services/catalog.py:1616
  store_product_photo grava no storage default e devolve URL; em produção o host é
  img.nelsonboulangerie.com.br/products/<arquivo> (ingress reescreve para /img/ do storefront,
  cache de 1 ano, arquivo imutável).
- Escrita no iFood é **negada por padrão**: SHOPMAN_IFOOD_CATALOG_WRITE_POLICY só aceita
  environment=test + merchant na allowlist (docs/reference/ifood-catalog-write-policy.md).
  Trabalhe com transporte **simulado**; nada de credencial.

**Tarefa:**
1. No adapter, antes do upsert: se o item tem image_url, obter os bytes (do storage local quando a
   URL é a nossa, senão HTTP GET com timeout) e enviar no endpoint de upload de imagem do
   catálogo; guardar o imagePath devolvido e mandá-lo no produto do FullItemDto.
2. **Um upload por imagem, não por envio:** cache sha256(bytes) → imagePath (em memória por
   execução e num registro durável simples, fora do Core) para reenvio não subir de novo a mesma
   foto.
3. **Falha não destrói:** upload que falha não apaga a foto remota, não altera status e não marca
   sincronização bem-sucedida; a pendência sai com motivo legível no resultado da projeção. Sem
   image_url no item, o envio segue como hoje e **não** remove a imagem existente.
4. Formatos/tamanho: só JPG/JPEG/PNG até 5 MB; o resto vira pendência com motivo, nunca erro
   silencioso.
5. **Fora de escopo:** categorias (frente própria), preço/status por PATCH específico (frente
   própria), ensaio ao vivo (bloqueado por credencial do dono).

**Prova:**
- Testes com transporte simulado: item com foto → payload com imagePath; imagem acima de 5 MB →
  pendência e item intocado; dois envios do mesmo SKU → **um** upload; upload falhando → sem
  imagePath e sem apagar imagem remota.
- Nenhuma chamada HTTP real nos testes (requests mockado); a guarda de escrita continua negando
  antes de OAuth/HTTP.
- python -m pytest shopman/storefront/tests/test_catalog_projection_ifood.py e os testes do
  backstage que tocam catálogo, verdes.

**Pronto quando:** PR verde na fila, e o corpo do PR diz, em uma linha, o que **ainda** não foi
provado (o ensaio ao vivo na loja de teste, que depende da credencial do dono).

---

# Depois deste turno (não faça agora)

Ondas seguintes, já fatiadas e na ordem: catálogo pela API do iFood (resolvedor do vínculo →
preço/pausa por PATCH específico → categorias criar/renomear/ordenar → tela em Canais → ensaio);
Compras (lote com Desfazer, tabelão de insumos); produto (listings, coleções, componentes de
combo, vigência de preço, apagar em lote); import/export ligado às cinco entidades.

# Pergunta aberta ao dono (não bloqueia este turno)

"Apagar em lote" no catálogo: **1** = Arquivar (recomendado: sai do catálogo e dos canais,
histórico preservado, Desfazer) ou **2** = apagar de verdade só quando não há pedido, ficha nem
compra. A fatia do "apagar em lote" espera essa resposta.
