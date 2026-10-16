# Mapa semântico dos pacotes

**Status:** referência canônica

**Escopo:** todos os diretórios físicos de `packages/`

**Lei relacionada:** [Constituição C5](../constitution.md#c5-uma-decisão-tem-um-dono)

Este mapa preserva o vocabulário operacional que saiu da Constituição quando ela foi
reduzida às cláusulas pétreas. Ele diz qual pergunta cada pacote possui e quais palavras
devem nomear suas decisões. Não transforma todos os verbos e eventos abaixo em APIs ou
signals já implementados: quando o código ainda não publica evento, isso é dito
explicitamente. A topologia e as setas físicas continuam em
[`docs/architecture.md`](../architecture.md).

## offerman

**Diretório físico:** `packages/offerman/`

- **Pergunta canônica:** O que é vendável e qual é seu preço de lista ou faixa de oferta?
- **Verbos:** `define_offer`, `publish_offer`, `unpublish_offer`, `list_offer`,
  `price_offer`, `compose_offer`, `retire_offer`.
- **Estados e sinais:** produto `published/unpublished` e `sellable/unsellable`;
  listagem `active/inactive` e `published/unpublished`. Elegibilidade comercial nunca
  substitui promessa operacional; preço contextual cross-domain é do orquestrador.
- **Eventos:** `product_created`, `product_updated`, `price_changed`,
  `availability_changed`.
- **Evidência:** [`Product`, `Listing` e `Collection`](../../packages/offerman/shopman/offerman/models/)
  e [signals públicos](../../packages/offerman/shopman/offerman/signals/__init__.py).

## stockman

**Diretório físico:** `packages/stockman/`

- **Pergunta canônica:** O que pode ser prometido, para quando e em qual quantidade?
- **Verbos:** `assess_promise`, `hold`, `confirm_hold`, `release_hold`, `fulfill_hold`,
  `project_supply`, `reconcile_stock`.
- **Estados e sinais:** hold `pending`, `confirmed`, `fulfilled`, `released`; uma decisão
  de promessa distingue saldo disponível, esperado, planejado, pausa e motivo da recusa.
- **Eventos:** `holds_materialized`; movimentos e mudanças de holds permanecem fatos do
  ledger mesmo quando não são publicados como signals Django.
- **Evidência:** [`PromiseDecision`](../../packages/stockman/shopman/stockman/protocols/sku.py),
  [`HoldStatus`](../../packages/stockman/shopman/stockman/models/enums.py) e
  [signals](../../packages/stockman/shopman/stockman/signals.py).

## craftsman

**Diretório físico:** `packages/craftsman/`

- **Pergunta canônica:** O que deve ser produzido e qual foi o resultado?
- **Verbos:** `plan_work`, `adjust_work`, `assign_work`, `start_work`, `finish_work`,
  `void_work`, `publish_output`.
- **Estados e sinais:** work order `planned`, `started`, `finished`, `void`; seus eventos
  registram planejamento, ajuste, início, conclusão e anulação.
- **Eventos:** `production_changed`, `production_stock_shortfall` e o ledger
  `WorkOrderEvent`.
- **Evidência:** [`WorkOrder`](../../packages/craftsman/shopman/craftsman/models/work_order.py),
  [`WorkOrderEvent`](../../packages/craftsman/shopman/craftsman/models/work_order_event.py)
  e [signals](../../packages/craftsman/shopman/craftsman/signals/__init__.py).

## orderman

**Diretório físico:** `packages/orderman/`

- **Pergunta canônica:** Qual compromisso comercial foi assumido e qual é seu progresso?
- **Verbos:** `quote_order`, `place_order`, `confirm_order`, `prepare_order`,
  `ready_order`, `dispatch_order`, `deliver_order`, `complete_order`, `cancel_order`,
  `return_order`.
- **Estados e sinais:** `new`, `confirmed`, `preparing`, `ready`, `dispatched`,
  `delivered`, `completed`, `cancelled`, `returned`; `preparing` é execução do pedido,
  não produção em lote.
- **Eventos:** `order_changed` e `OrderEvent` preservam a transição observada.
- **Evidência:** [`Order.Status`](../../packages/orderman/shopman/orderman/models/order.py),
  [ADR-006](../decisions/adr-006-order-status-semantics.md) e
  [signal](../../packages/orderman/shopman/orderman/signals.py).

## payman

**Diretório físico:** `packages/payman/`

- **Pergunta canônica:** Qual obrigação financeira existe e o que aconteceu com ela?
- **Verbos:** `create_intent`, `authorize_payment`, `capture_payment`, `cancel_payment`,
  `fail_payment`, `refund_payment`, `reconcile_payment`.
- **Estados e sinais:** `pending`, `authorized`, `captured`, `failed`, `cancelled`,
  `refunded`; estado do gateway não substitui estado financeiro canônico.
- **Eventos:** `payment_authorized`, `payment_captured`, `payment_failed`,
  `payment_cancelled`, `payment_refunded`.
- **Evidência:** [`PaymentIntent.Status`](../../packages/payman/shopman/payman/models/intent.py)
  e [signals](../../packages/payman/shopman/payman/signals/__init__.py).

## guestman

**Diretório físico:** `packages/guestman/`

- **Pergunta canônica:** Quem é o cliente e quais são seus contatos e vínculos comerciais?
- **Verbos:** `identify_customer`, `merge_customer`, `attach_contact`, `verify_contact`,
  `set_primary_contact`, `segment_customer`, `remember_customer`.
- **Estados e sinais:** cliente `active/inactive`; contato `verified/unverified` e
  `primary/non_primary`; tipos `whatsapp`, `phone`, `email`, `instagram`.
- **Eventos:** `customer_created`, `customer_updated`. Eventos mais específicos de contato
  não são signals públicos do pacote hoje.
- **Evidência:** [`Customer`](../../packages/guestman/shopman/guestman/models/customer.py),
  [`ContactPoint`](../../packages/guestman/shopman/guestman/models/contact_point.py) e
  [signals](../../packages/guestman/shopman/guestman/signals/__init__.py).

## doorman

**Diretório físico:** `packages/doorman/`

- **Pergunta canônica:** Como autenticar o sujeito e estabelecer confiança para o contexto?
- **Verbos:** `challenge_identity`, `verify_handle`, `issue_access_link`,
  `exchange_access_link`, `trust_device`, `link_identity_provider`, `resume_session`.
- **Estados e sinais:** código de verificação `pending`, `sent`, `verified`, `expired`,
  `failed`; link de acesso `valid`, `used`, `expired` como projeção de validade; confiança
  é vinculada ao tipo e ao identificador do sujeito.
- **Eventos:** `customer_authenticated`, `access_link_created`,
  `verification_code_sent`, `verification_code_verified`, `device_trusted`.
- **Evidência:** [`VerificationCode`](../../packages/doorman/shopman/doorman/models/verification_code.py),
  [`TrustedDevice`](../../packages/doorman/shopman/doorman/models/device_trust.py) e
  [signals](../../packages/doorman/shopman/doorman/signals.py).

## buyman

**Diretório físico:** `packages/buyman/`

- **Pergunta canônica:** Como comprar e receber insumos de fornecedores? O recorte hoje
  implementado responde cadastro comprável, fornecedor, contato, custo e conversão.
- **Verbos:** cadastrar, ativar ou desativar material e fornecedor; vincular contato;
  declarar ou calibrar conversão; registrar custo por fornecedor; promover um custo a
  preferencial. São ações dos models/Admin e do comando `calibrate_conversions`, não nomes
  de uma API pública inexistente.
- **Estados e sinais:** material, fornecedor e conversão `active/inactive`; conversão
  `conventional/approximate`, com origem `invoice/owner/house_scale/estimate`; custo
  preferencial é único por material.
- **Eventos:** o pacote não publica signals de domínio hoje; mudanças são fatos persistidos
  nos cadastros de material, fornecedor, conversão e custo.
- **Evidência:** [`Material`](../../packages/buyman/shopman/buyman/models/material.py),
  [`Supplier`](../../packages/buyman/shopman/buyman/models/supplier.py),
  [`MaterialConversion`](../../packages/buyman/shopman/buyman/models/conversion.py) e
  [`SupplierMaterialCost`](../../packages/buyman/shopman/buyman/models/cost.py).

## fiscalman

**Diretório físico:** `packages/fiscalman/`

- **Pergunta canônica:** Como classificar o item fiscalmente e contratar emissão ou
  cancelamento sem deixar o gateway definir o domínio?
- **Verbos:** `from_metadata`, `validate_for_emission`, `resolve_fiscal_item`; no porto do
  provedor, `emit`, `query_status`, `cancel`.
- **Estados e sinais:** perfis `standard/tax_substitution`; documento `pending`,
  `authorized`, `denied`, `cancelled`; classificação inválida produz erros e avisos
  explícitos, não fallback silencioso.
- **Eventos:** o pacote não publica signals de domínio hoje; emissão e cancelamento retornam
  `FiscalDocumentResult` e `FiscalCancellationResult` pelo porto.
- **Evidência:** [classificação](../../packages/fiscalman/shopman/fiscalman/classification.py)
  e [`FiscalBackend`](../../packages/fiscalman/shopman/fiscalman/contracts.py).

## cashman

**Diretório físico:** `packages/cashman/`

- **Pergunta canônica:** Quem responde pela gaveta e quais fatos alteraram seu saldo?
- **Verbos:** `open_shift`, `record_entry`, `close_shift`, `correct_count`, `timeline`,
  `balance`, `difference`.
- **Estados e sinais:** turno `open/closed`; lançamentos append-only tipam entrada, saída,
  contagem, correção e fatos sem dinheiro. Correção é novo lançamento com `parent`.
- **Eventos:** `shift_opened`, `shift_closed`, `entry_recorded`.
- **Evidência:** [`Shift`](../../packages/cashman/shopman/cashman/models/shift.py),
  [`Entry`](../../packages/cashman/shopman/cashman/models/entry.py),
  [services](../../packages/cashman/shopman/cashman/services/) e
  [signals](../../packages/cashman/shopman/cashman/signals.py).

## refs

**Diretório físico:** `packages/refs/`

- **Pergunta canônica:** Que identidade operacional tipada nomeia este alvo, neste escopo,
  sem acoplar kernels?
- **Verbos:** `attach`, `resolve`, `resolve_partial`, `resolve_object`, `deactivate`,
  `transfer`, `rename`, `refs_for`, `generate_value`.
- **Estados e sinais:** ref `active/inactive`; tipo, valor e escopo definem resolução;
  sequências são monotônicas por nome e hash de escopo.
- **Eventos:** `ref_attached`, `ref_deactivated`, `ref_renamed`, `ref_transferred`.
- **Evidência:** [`Ref`](../../packages/refs/shopman/refs/models.py),
  [services](../../packages/refs/shopman/refs/services.py) e
  [signals](../../packages/refs/shopman/refs/signals.py).

## watchman

**Diretório físico:** `packages/watchman/`

- **Pergunta canônica:** Qual é a saúde operacional observada, sem tomar posse nem alterar
  o domínio observado?
- **Verbos:** `build_registry`, `Registry.for_profile`, `run_profile`, `assess_deadline`,
  `BudgetRecorder.record`, `BudgetRecorder.snapshot`.
- **Estados e sinais:** resultado `pass/warn/fail/unknown/skipped`; escopos
  `liveness/readiness/diagnostic/security/performance`; exceção do observador vira
  `unknown`, nunca reinicia ou muta o observado.
- **Eventos:** não há signal de domínio; `CheckResult`, `Report` e `BudgetEvent` são os fatos
  de observação versionados e serializáveis.
- **Evidência:** [contratos](../../packages/watchman/shopman/watchman/contracts.py),
  [runner](../../packages/watchman/shopman/watchman/runner.py) e
  [performance](../../packages/watchman/shopman/watchman/performance.py).

## utils

**Diretório físico:** `packages/utils/`

- **Pergunta canônica:** Quais primitivas estritamente transversais evitam duplicação sem
  ganhar regra de negócio?
- **Verbos:** não possui verbos de domínio; oferece operações puras de dinheiro, unidades,
  telefone, nomes, documentos, formatação, planilhas e contexto de dispositivo.
- **Estados e sinais:** não possui estado canônico de domínio. Qualquer módulo que passe a
  carregar lifecycle ou vocabulário de produto deve sair deste pacote.
- **Eventos:** não publica eventos de domínio.
- **Evidência:** [módulos públicos](../../packages/utils/shopman/utils/) e
  [Constituição C5](../constitution.md#c5-uma-decisão-tem-um-dono).

## Regra de manutenção

Todo novo diretório físico diretamente sob `packages/` entra neste mapa no mesmo PR. Remover
um pacote remove sua seção. O gate documental compara os dois conjuntos e também recusa uma
seção que aponte para diretório inexistente.
