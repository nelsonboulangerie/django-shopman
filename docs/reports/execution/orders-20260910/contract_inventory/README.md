# Matriz de contratos, escritas e consumidores

Fonte **8318b9b03**. `build.py` lê AST sem inicializar Django ou banco. `routes.csv`
inventaria as **39 rotas** literais de Pedidos/Catálogo/Feeds, classe, métodos
herdados, localização, hash de fonte e chamadas de facade diretamente observadas.
`consumers.csv` registra **47 ocorrências diretas** de IdempotencyKey/merge_order_data.
Não confundir ocorrência com execução: chamadas indiretas, aliases e autoridade
operacional não são demonstradas por AST. Esta matriz complementa o inventário
histórico `../writer-inventory.md`, cujas linhas não são referências atuais.

## Cada família de escrita

Os testes abaixo são arquivos sob `shopman/backstage/tests`, salvo indicação.
As rodadas efetivamente executadas estão no diário e em CURRENT-STATUS; esta
matriz não conta coleta/leitura de teste como nova execução. Fixtures são
sintéticas dos próprios testes; dados reais/H08 não foram consultados.

| Rotas/família | Fonte canônica, facade e política | Escrita/efeito e proteção | Fixture/prova | Dono e rollback |
| --- | --- | --- | --- | --- |
| advance, confirm | Order/OrderEvent; operator_orders; manage_orders + guards canônicos | Transição e fases/Directive, revisão observada, intenção por pessoa; Payman antes da transição | test_order_confirm_intention; shop/tests/test_orders_intention_concurrency; H03 | shop; servidor seguro permanece, suspender capacidade incompatível |
| reject, cancel | cancellation + operator_orders; motivos do canal e aprovação gerencial vigente | Reavalia estado/pagamento/autoridade; retorno/estorno são serviços existentes | test_cancel_reject_intentions; shop/tests/test_cancellation_fresh_state; test_h03_confirmation_barriers | shop/Operações; G02/G03 para procedimento, não editar status/livro |
| settle-delivery-cash, equipment-back | Order + Shift/Entry + Payman; operator_orders/cash | Shift→Order, revisão de custódia, caixa aberto/autorizado, recibo e devolução canônicos | test_cash_settlement_intentions; test_equipment_comment_intentions; shop/tests/test_cod_custody_concurrency | shop/Financeiro; conservar Entry/Transaction/recibos, G02 pendente |
| notes, assign, unassign, comment | Order.data e OrderEvent; operator_orders; manage_orders | Campo/base próprios, JSON fresco sob lock, comentário com intenção; texto não vai para labels | shop/tests/test_orders_intention_concurrency; test_equipment_comment_intentions; integrações notas | shop; rollback de cliente não pode reintroduzir writer de JSON obsoleto |
| courier-quote/dispatch/cancel | Order.data.courier + Directive/receipts; courier facade | Rede fora do lock, revisão fresca para aplicar; started/unknown não reenviados cegamente; confirmação física separada | test_courier_dispatch_intentions; famílias courier do diário | integração; manter fence de unknown, G03 para lookup/retry homologado |
| requeue-fiscal | FiscalReceipt/Directive; serviço fiscal e resolver existente | Consulta/recuperação canônica; autorizado não vira nova emissão; metadado Action controla UI | família fiscal; h03-final-matrix; fiscal_evidence/ | fiscal/shop; conservar chave/autorização, não reemitir por rollback |
| resend-payment-link | Directive e provedor existente; notification_service | Aceite externo monotônico, started antes da rede, unknown sem fallback/reenvio | notification_unknown/; crash real de processo com fake | integração; worker antigo demonstrado inseguro, G03 |
| catalog cell | Product/Listing/ListingItem ou Channel.config.display; set_cell; manage_catalog | Somente campo editado; locks da superfície/produto/célula e revisão; feed sem preço próprio | test_catalog_cell_concurrency; test_catalog_price_intentions | catálogo; preservar preço e chaves; rollback não reaplica delta |
| catalog bulk, bulk-price | Mesmas entidades e regras individuais; preview/apply do catálogo | Prévia exata, conjunto/revisões congelados; invalidez final recusa integralmente; sync separado | test_catalog_publication_intentions; test_catalog_price_intentions | catálogo; manter recibo e gate fiscal; G05 sensível |
| product, product/SKU, social | Product/config canônicos; update_product_detail | Patch validado integralmente; versão por campo; resposta de A não hidrata B; intenção estável | test_catalog_product_intentions; test_catalog_social_intentions; integração SKU/resposta perdida | catálogo; nenhum dado fiscal/nutricional inventado, G05 |
| reorder-collections, reorder-items | Collection/CollectionItem; facades de reorder | Conjunto/base conferidos, ordem persistida é a lida; coleção smart não amplia intenção | test_catalog_order_intentions; integração curadoria/teclado | catálogo; preservar ordem/seleção conhecida, sem lista paralela |
| resync | CatalogSyncState/Directive; apply_resync_intention | Adota trabalho queued/running, não reaplica preço nem chama queued de publicado | test_catalog_resync_intentions; integrações de resync | integração; retomar destino faltante pelo recuperador, G03 |
| feeds active, collections, rotation | Channel.config.display; feed_service; manage_catalog | Revisão por campo + lock de config + intenção; coleções são refs canônicas | test_feed_intentions; feed-writers-final; integração feed/SSE | catálogo; conservar config/recibos; não criar preço do feed |
| catalog ai-assist | Sugestão do adaptador; Product só muda após aplicação explícita | Não é publicação; resposta amarrada a recurso/campo, sem inferir ingredientes | testes de catálogo/AI e componente CatalogAiSuggest | catálogo; desligar sugestão sem mudar Product; G05 |

## Leituras com efeitos e entradas adjacentes

`GET orders/<ref>/` conserva a reconciliação de pagamento já existente e throttled
(`_reconcile_payment_if_due`), ao contrário da fila sem chamadas por pedido ao
fornecedor. Abrir detalhe real não é um ensaio readonly autorizado por este mandato:
no laboratório os adaptadores externos estão isolados. `cancellation-reasons`
pode consultar fornecedor; não inventa lista vazia nem aplica cancelamento.

Tickets individuais/lotes HTML e ESC/POS usam o caminho de impressão existente,
incluindo carimbo de primeira impressão. Ler/gerar bytes não demonstra impressão
física. Counteragent passou96 testes/1 skip exclusivo de Linux; não se ligou
periférico. Estas rotas não foram convertidas em nova superfície de dispatch.

Queue, matriz, promise, sync-status e board de feeds permanecem projeções das
fontes acima. SSE notifica invalidação; não é uma segunda fonte de estado nem
prova de frescor sem leitura bem-sucedida. GET de recibo reautoriza pessoa e
escopo; ausência durante transação não prova ausência de efeito.

## Writers e consumidores compartilhados

| Grupo observado | Compatibilidade e fonte | Prova/limite |
| --- | --- | --- |
| Courier callback, gateway throttle, lifecycle | merge_order_data relê Order sob select_for_update, mescla somente campos/bloco do writer | test_orders_intention_concurrency parametriza os3 writers e preserva nota/captured_at; corrida de nota/atribuição usa conexões PG independentes |
| Waitlist, payment capture/refund, stock, production sync, return | Conservam seus serviços, transações e locks; não são substituídos pelo frontend | famílias H03, lifecycle/return/production no diário e suíte ampla; um save textual não prova ordem global de locks |
| CommitService/checkout/reorder | Escopos existentes de IdempotencyKey continuam separados do envelope local-mutation-v1 | core orderman291 testes na rodada canônica; checkout/reorder na suíte ampla; não se alterou regra de CommitService |
| remote_mutations legado | fingerprint=None conserva contrato legado/expiração24h; novo contrato usa envelope + fingerprint e retenção conservadora | shop/tests/test_remote_mutations; expirado/in_progress não é licença para apagar recibo novo; G08 |
| Webhooks Stripe/Efi/iFood/Machine | webhook_idempotency e stable_webhook_key conservam namespace/claim/done próprios | famílias webhook e courier, sem webhook real; callbacks antigos/repetidos não repetem efeito local conhecido |
| Produção/quick finish, compra, POS/caixa e alertas | Receipts existentes nos próprios escopos; chamadas indiretas ao helper continuam consumidores | suites canônicas12 cores2646/21 skips/2 subtests; suite shopman8718/68 skips; cada rodada tem SHA e limites próprios |
| Diretivas/reaper, Admin e cleanup_idempotency_keys | Leem status/recibo existente; nenhum novo formato de tabela | restore140 tabelas/129 sequências; chaves permanentes não apagadas; Admin/cleanup não foram executados para alterar dados reais |
| Browser antigo e worker antigo | Leitura antiga tolerada, mutação sem contrato recusada; worker antigo pode repetir unknown | legacy_browser/ e restore_lab/: servidor seguro/fence deve permanecer no rollback |

## Rastreabilidade normativa

| Achados/gates | Contratos | WPs | Evidência vinculada |
| --- | --- | --- | --- |
| D01/D02/D17 | C02/C03/C07 | 00/02/06/09 | remote_mutations, concorrência PG, receipt após resposta perdida e reason_discard |
| D03/H02/H03, G02 | C03/C04/C05 | 03/04/09 | H03, cancellation_fresh_state, custódia/Payman/retorno |
| D04/D18/D19/H01, G03 | C05/C08 | 04/08/09 | courier, notification_unknown, PROCESS-CRASH e runbook |
| D05/D06/D07/D12/H05, G05 | C06 | 05/09 | preço/patch/publicação/reorder/resync/feed intentions |
| D08/D10/D11/H07/H09, G01 | C01/C08 | 01/06/08 | schema/quantidade, Actions/personas, courier_actions; política ampliada pendente |
| D09/D13/D14/D15/H06, G05/G08 | C06/C07/C08 | 05/06/09 | integrações de leitura/SKU/sessão, confirmed_note, reason_discard |
| D16/D20/H04, G04/G06 | C08 + budgets §6 | 07/09 | clock, Hold batch, HTTP/SSE; 500/10 ainda fora do budget; som preservado |
| H08, G07/G08 | §8/§10/DoD | 00/09/10/11/12 | restore/versões locais; inventário real, piloto/rollout/contração pendentes |

Sem migração ou mudança de runtime neste inventário. Regerar o CSV em outro SHA
atualiza proveniência; não reclassifica automaticamente hipótese ou gate humano.
