# Evidências e vínculos locais de catálogo

`CatalogSnapshot` e `CatalogBinding` pertencem ao app `shop`. São genéricos quanto
à identidade do recurso externo; nesta entrega somente o parser iFood foi
implementado, em serviços do App. Não alteram contratos ou modelos do Core.

## CatalogSnapshot

Evidência append-only ligada a `channel` (PROTECT), com `provider`, `account_ref`,
`catalog_ref`, `context`, `captured_at`, `imported_at`, `imported_by` (PROTECT),
`sha256` e `raw_json` TextField original. `source` e `item_count` são resumos
imutáveis derivados na importação. O hash usa os bytes UTF-8 do texto recebido:
a formatação e a precisão dos números permanecem intactas. Não há JSONField que
converta Decimal para float ou números em códigos textuais.

O serviço aceita no máximo 20 MiB, usa parser com Decimal e rejeita chaves
repetidas/números não finitos; depois executa o validador de revisão iFood existente.
O limite HTTP do servidor/proxy pode ser menor. Alteração por `save`, `update` ou
`bulk_update` e remoção pelo ORM são bloqueadas. A interface não oferece exclusão.
Administradores com acesso direto ao banco continuam tecnicamente capazes de
alterar dados; a projeção confere hash e escopo antes de preparar os itens.

`source=api_capture` conserva a declaração do arquivo, não certifica autenticação,
origem, merchant real ou homologação. A escolha do canal local é explícita; seu nome
não demonstra equivalência com a conta remota declarada no snapshot.

## CatalogBinding

Vínculo local para Product (PROTECT), canal (PROTECT), snapshot (PROTECT) e ator
(PROTECT). A chave única de banco é `(provider, account_ref, catalog_ref, context,
resource_id)`. Não inclui Product nem canal: um produto pode representar vários
anúncios, mas um recurso remoto do mesmo escopo não é transferido silenciosamente
entre canais. Campos complementares: `external_product_ref`, `category_ref`,
`item_context_ref`, `confirmed_at` e `revision` inteiro monotônico.

Cada confirmação ou revínculo é decisão explícita sobre um SKU. Sugestões por
código exato nunca preenchem uma escolha ou criam vínculo automaticamente. IDs
remotos não são gerados nem substituídos. A revisão anterior permanece auditada.
Uma nova captura mantém o vínculo atual visível, mas `needs_review=true` até
confirmação sobre aquela captura; reexecutar recibo antigo não confirma a nova.

O serviço adquire locks na ordem Channel → Product → Snapshot → Binding. A
restrição única resolve a corrida entre canais diferentes. `base_revision` é hash
da evidência selecionada e da identidade/versão do vínculo atual. Uma decisão
baseada em vínculo desatualizado retorna 409, preservando a escolha no cliente.

## Intenção, auditoria e efeitos

As APIs exigem `shop.manage_catalog`, `expected_actor_id` inteiro igual à pessoa
identificada e chave de idempotência. `run_idempotent_mutation` persiste a mutação,
a auditoria Django `LogEntry` e o recibo na mesma transação. Os eventos de auditoria
são `catalog.snapshot.import` (canal, snapshot, hash) e `catalog.binding.confirm`
(recurso, canal, SKU/revisão/snapshot anteriores e posteriores). Falha de auditoria
reverte o vínculo e o recibo. Headers e body com chaves divergentes são rejeitados.

- GET `/api/v1/backstage/catalog/channels/<ref>/review/?snapshot_id=<id>` retorna
  histórico, captura selecionada, produtos locais, itens remotos, vínculo atual,
  sugestões, revisão e ações locais. Sem `snapshot_id`, seleciona a captura mais
  recentemente importada; nunca seleciona SKU automaticamente.
- POST `.../snapshots/`: `{raw_json, base_revision, expected_actor_id, idempotency_key}`.
  A revisão da importação é estável para canal/operação/pessoa e vem da ação projetada;
  não obriga reaproveitar revisão de um vínculo ou enfraquecer o protocolo do Gestor.
- POST `.../bindings/`: `{snapshot_id, item_id, sku, base_revision,
  expected_actor_id}` com `Idempotency-Key`.
- GET em cada rota de mutação com `?idempotency_key=<key>` recupera o resultado
  no escopo pessoa/canal/operação. Ausência retorna 202 `unknown` e não autoriza
  trocar a chave ou afirmar que a operação falhou.

Nenhuma dessas operações salva Product/ListingItem, chama record_sync/enqueue,
publica catálogo, envia HTTP, habilita projeção ou altera a loja no iFood. Nem
vínculo local nem captura validada autorizam publicação dos produtos de exemplo.

## Migração coordenada

A migração `0055_catalog_snapshot_binding` depende da
`0054_disable_remote_auto_confirmation` real da PR 680, que sucede
`0053_marketing_delivery_identity` da PR 634. Ela cria somente as tabelas,
índice e restrição de identidade; não importa dados nem habilita integração.
Esta entrega exige as tabelas correspondentes antes de servir os novos endpoints.

## Gestor e validação desta etapa

O acesso fica em Canais, ação **Revisar vínculos**, rota
`/channels/<ref>/catalog`. A projeção `catalog_bindings.py` está registrada na
superfície existente `headless-operator-api` do Unfold Canonical Gate, junto ao
catálogo e aos feeds do Gestor; o registro identifica a API e a página consumidora. A tela importa uma captura completa e oferece seleção
explícita de SKU, prévia e confirmação local. Exibe a evidência externa preservada;
não duplica os editores canônicos de preço, pausa ou cadastro. A identidade futura
pode ser exposta no produto sem criar outro mecanismo de sincronização.

A primeira captura exibida permanece selecionada durante atualizações. Trocar de
captura exige leitura correspondente antes de permitir gravação; rascunhos exigem
confirmação de descarte. Conteúdo externo é texto, inclusive caminho de imagem,
sem requisições implícitas a URLs do arquivo importado.

## Evidências de validação

Validações locais em 15/09/2026, com integrações externas bloqueadas:

- 21 testes backend em PostgreSQL 16 privado com migrações reais. Disputa pelo
  mesmo anúncio produz um sucesso e um 409, sem duplicação; o mesmo SKU pode
  vincular dois anúncios.
- 17 testes da interface, incluindo recibo após resposta perdida, preservação de
  seleção, troca de captura, conteúdo externo e confirmação explícita.
- Verificação de tipos, contrato gerado, Ruff e `make admin` completo aprovados.
- Fluxo de API com autenticação real em SQLite privado: importar, confirmar,
  reler, repetir a mesma intenção e importar uma recaptura simulada. Product,
  ListingItem e Directive permaneceram inalterados.
- Fluxo no navegador interno: busca, escolha explícita de SKU, prévia,
  confirmação local e releitura após recarga. A interface foi conferida em
  desktop e em largura de 390 px. O ensaio usa somente o banco privado de QA.
- Atualização PostgreSQL 16 da 0054 para a 0055 com fixtures preexistentes de
  Product e Channel: os registros foram preservados integralmente, as tabelas
  novas nasceram vazias e a restrição `unique_catalog_remote_resource` foi
  instalada. Esta prova não simula volume ou concorrência de DDL de produção.
- `makemigrations --check --dry-run` não detectou alterações pendentes. A migração
  integral também foi verificada em bancos privados SQLite e PostgreSQL.

As capturas e os dados de ensaio permanecem privados, fora do Git. Nenhum teste
acima constitui homologação iFood ou revisão dos dados comerciais da loja real.
