# WP-06-agente-d — Compras / Recebimento

**Status:** pronto para implementação · **Autor:** Agente D (revisão do WP-06 do Agente G)
**Superfície:** 'surfaces/purchase-nuxt' + endpoints purchase
**Objetivo:** eliminar duplicação de estoque, spoof de NF/material/custo e divergência de unidade no recebimento, sem escrita silenciosa em dado mestre e preservando uma UX rápida de loja.

## Diferenças vs. WP original (Agente G)

**Mantidos (validados):** P0 recebimento por NF confia no payload do browser ('confirm_receipt' lê supplier/lines do payload — 'purchase.py:112-142'); P0 recebimento não idempotente ('stock.receive' cria Move incondicionalmente); P1 reposição recalculada na UI ('reorderRows' com regra fixa — 'usePurchaseDesk.ts:548-555' vs '_suggested_qty' backend); P1 approved/sent; P1 conversão/custo; permissão única 'backstage.operate_purchase' (na verdade em **8** views, o WP citou 6 — 'api/purchase.py:38,51,68,85,102,136,157,174').

**Recalibrados / agravados:**
- **P0-1 ReceiptDraft** — o WP propôs entidade nova sem reconhecer que **'scan_invoice' já monta um draft** (efêmero, não persistido): valida a chave, resolve fornecedor por CNPJ e lê linhas via adapter ('purchase.py:68-109'). A solução é **persistir o draft existente** e amarrar o 'confirm_receipt' a ele (draft_id + deltas de conferência), não criar fluxo paralelo. Dono dos modelos: declarar (buyman ou backstage) — o WP diz "consumir Buyman" mas propõe modelos no core.
- **P1 conversão/custo** — agravado com achado novo: 'confirm_receipt' **sobrescreve 'cost_q' E 'conversion' in-place** ('_upsert_supplier_cost', ':856-871') — pode **zerar a conversão** de um custo existente (reinterpretando o custo por unidade-base) — e com 'prefer_if_missing=True' **auto-promove o custo a preferido** na primeira entrada: um conferente de balcão vira, silenciosamente, o decisor do custo canônico. 'SupplierCostObservation' **não existe** (ADR-023 reconhece a ausência de trilha).
- **P1 reposição** — agravado: o número que a UI mostra (horizonte fixo) **difere do número que o backend despacha** (lead time) — o operador aprova um número e o fornecedor recebe outro, sem aviso.
- **P1 approved/sent** — 'approveRequest' é **helper morto** (zero call sites); 'approved' existe no tipo e no badge mas é inalcançável pela UI; 'set_purchase_request_status' aceita 'approved' e 'sent' ('services/purchase.py:450-451'). Decisão a tomar: remover o estado ou impor o fluxo.
- **Aceite "sem 'approve_purchase' não envia acima da política"** — inverificável como escrito: 'approve_purchase' **não existe** e "política" de limite também não. Reformulado: ou criar a permissão + a política (feature nova, dono a declarar), ou remover a menção e tratar approved/sent como fluxo interno.

**Novos (achados da verificação):**
- **Escrita silenciosa em dado mestre como efeito colateral do recebimento** (acima) — o mais grave do app.
- **'scan_invoice' cria fornecedor implicitamente** do CNPJ emissor ('purchase.py:91') — escrita em mestre sem gesto de confirmação do operador.
- **'_purchase_request_snapshot' roda 'build_purchase()' inteiro** (todas as materials/costs/moves) dentro do path de escrita ('services/purchase.py:577') — custo desnecessário em mutação.
- Número exibido ≠ número despachado na reposição (acima).

## Fronteira Natural

Compras decide o que comprar, confere o que chegou, registra entrada física e captura custo/conversão observados. Consome Stockman, Producão/receitas e Buyman. **Dono dos modelos novos ('ReceiptDraft'/'PurchaseReceipt'/'SupplierCostObservation'): declarar antes de implementar** — recomendação: entidades de recebimento no backstage (superfície) e 'SupplierCostObservation' em buyman (custo é domínio do core); cada dono assina sua camada. O adapter 'shop/adapters/purchase_invoice_nfe.py' é do orquestrador (shop) — alteração lá é coordenação, não escopo livre.

## Evidências (verificadas)

- 'confirm_receipt' lê supplier/lines do payload: 'shopman/backstage/services/purchase.py:112-142'.
- 'scan_invoice' monta draft efêmero + cria fornecedor: 'purchase.py:68-109' (':91').
- Loop grava via 'stock.receive' sem chave de invoice: 'purchase.py:147-184'; 'packages/stockman/.../movements.py:79'.
- Aprende mapa fiscal no confirm: 'purchase.py:874' ('_learn_invoice_product_map', só 'mode=invoice').
- UI recalcula reposição localmente: 'surfaces/purchase-nuxt/app/composables/usePurchaseDesk.ts:548-555'.
- Backend tem '_suggested_qty' e expõe: 'shopman/backstage/projections/purchase.py:305,257'.
- 8 views com 'backstage.operate_purchase': 'shopman/backstage/api/purchase.py:38,51,68,85,102,136,157,174'.
- Custo sobrescrito in-place: '_upsert_supplier_cost' 'services/purchase.py:856-871'; 'models/cost.py:16' admite ausência de trilha (ADR-023).
- Sem 'SupplierCostObservation': buyman tem 4 modelos (Material, MaterialConversion, Supplier, SupplierMaterialCost).

## Achados Priorizados

### P0 — Recebimento por NF confia no payload do cliente

Proposta:
- Persistir o draft que 'scan_invoice' já constrói: entidade 'ReceiptDraft' servidor-side com 'draft_id', hash/XML/fonte, CNPJ emissor, linhas originais, fornecedor sugerido e decisões do operador.
- 'confirm_receipt' aceita 'draft_id' + deltas de conferência (nunca linhas livres).
- Troca de material/conversão exige override auditado.
- Mapa fiscal só aprende de draft válido (proteger '_learn_invoice_product_map').
- Modo **manual** (sem NF): definir o que é "draft" nesse fluxo (rascunho de conferência do próprio operador) — senão todo recebimento manual fica fora da regra.

Aceite:
- Confirmar linha/material fora do draft falha sem override (teste).
- Mapa fiscal não aprende de payload livre (teste).
- Recebimento manual continua possível com draft de conferência.

### P0 — Recebimento não é idempotente

Proposta:
- Entidade 'PurchaseReceipt' ou chave única 'invoiceAccessKey + supplier + lineId/material/qty'.
- Reenvio idêntico retorna o receipt existente; divergente → 409 com explicação.

Aceite:
- Confirmar mesma NF duas vezes não duplica estoque (teste backend).
- NF mesma chave com linhas diferentes → 409 com diff.

### P1 — Escrita silenciosa em dado mestre (custo/conversão)

Proposta:
- Divergência de conversão **bloqueia** até escolher: manter antiga, aceitar nova (com justificativa), ou cancelar.
- 'SupplierCostObservation' append-only (dono: buyman) registra cada custo recebido.
- Promover custo preferido por regra controlada — **nunca** por efeito colateral do recebimento ('prefer_if_missing' revisado).
- Nunca zerar 'conversion' de custo existente ao receber.

Aceite:
- Custo recebido gera observação histórica (teste).
- Conversão divergente sem justificativa não confirma estoque (depende do draft do P0 — dependência declarada).
- Conferente de balcão não altera custo preferido sem passo explícito.

### P1 — Número exibido ≠ número despachado na reposição

Proposta:
- Projection traz 'suggestedQty', 'suggestedReason', 'replenishAtDays', 'coverageDays' (backend já calcula — '_suggested_qty').
- UI renderiza e ordena pela projection; **remover o recompute local** ('reorderRows').
- O envio usa a MESMA quantidade exibida (teste de paridade UI→envio).

Aceite:
- Teste frontend garante 'reorderRows' não recalcula alvo localmente.
- O número aprovado na tela é o número no 'PurchaseRequest' (paridade).

### P1 — Estado 'approved' existe mas a UI envia direto 'sent'

Proposta (decisão a tomar com o dono):
- Opção A: remover 'approved' (fluxo direto) — menor, se não há requisito de aprovação.
- Opção B: impor 'review → approved → sent' com permissão 'approve_purchase' (feature nova: política de limite + 'setup_groups').
- Escolher UMA; nunca manter estado morto alcançável por badge.

Aceite:
- A UI não expõe path para estado inexistente; se 'approved' fica, 'approveRequest' ganha call site e gate.
- Decisão registrada neste WP antes da implementação.

## Melhorias UX

1. **Recebimento por exceção:** após scan, linhas sem material, conversão divergente, custo ausente e validade faltante no topo.
2. **Comprar por risco de ruptura:** dias até zerar, lead time, produção afetada e sugestão backend.
3. **Scanner real de loja:** bipar SKU/GTIN por linha para confirmar material físico.
4. **Três colunas por item:** Nota, Contagem, Entrada no estoque.
5. **Conferência de nota:** total NF vs conferido, linhas faltantes/extras, CNPJ emissor, validade/lote.
6. **Relógio de ruptura:** entrada cobre X dias e destrava receitas Y/Z (leitura de craftsman — fronteira: só leitura).

## RBAC / setup_groups

Permissões novas **se** a Opção B for escolhida: 'scan', 'receive', 'cost', 'conversion', 'approve', 'send' (nomes a confirmar). **Obrigatório atualizar 'setup_groups.py'** com a matriz de grupos (Caixa não deve receber 'cost'/'conversion'; Gerente decide 'approve'). Hoje: 8 views com 'backstage.operate_purchase' — separar sem destravar o fluxo de recebimento do dia a dia.

## Pré-requisitos

- Bloco "Contrato de actions" do WP-02-agente-d (payloads estritos).
- P0-1 (ReceiptDraft) é pré-requisito do aceite de conversão server-side (declarado).
- Coordenação com o dono do orquestrador para o adapter NF ('shop/adapters/purchase_invoice_nfe.py').

## Testes

- Backend: mesma NF não duplica 'Move'.
- Backend: confirmação por draft não aceita supplier/material/linha fora do draft.
- Backend: conversão divergente bloqueia sem justificativa/permissão.
- Backend: custo gera observação histórica; 'prefer_if_missing' não promove silenciosamente.
- Permissões (se Opção B): scan, receive, cost, conversion, approve, send — matriz + paridade.
- Frontend: usa 'suggestedQty' da projection; paridade UI→envio.
- Contrato: checksum NF-e igual TS/Python ou validação server-side.
- Custo: receber sem sobrescrever 'conversion' de custo existente.

## Fora De Escopo

Preço de venda, emissão/cancelamento fiscal de venda, planejamento de produção, merge amplo de cadastro mestre, inventário cíclico, perdas/ajustes gerais, comunicação com cliente, e **política de limite de gasto** (se surgir, é feature de permissões/backstage, não de Compras).

## Prompt Para Agente Executor

~~~text
Execute WP-06-agente-d (Compras / Recebimento).

Leia:
- docs/plans/backstage-app-audits-2026-08-29/agente_d/WP-06-agente-d-compras.md
- surfaces/purchase-nuxt/app/composables/usePurchaseDesk.ts
- surfaces/purchase-nuxt/app/presentation/purchase.ts
- shopman/backstage/api/purchase.py
- shopman/backstage/services/purchase.py (scan_invoice, confirm_receipt, _upsert_supplier_cost, _learn_invoice_product_map)
- shopman/backstage/projections/purchase.py (_suggested_qty)
- packages/buyman/shopman/buyman/models/*
- packages/stockman/shopman/stockman/services/movements.py
- shopman/shop/adapters/purchase_invoice_nfe.py (coordenacao)
- shopman/shop/management/commands/setup_groups.py (se criar permissoes)

Fases:
1. Persistir ReceiptDraft (a partir do scan_invoice existente) + PurchaseReceipt/idempotencia.
2. Vincular confirmacao ao draft (deltas de conferencia; modo manual definido).
3. Parar escrita silenciosa em custo/conversao (observacao append-only; bloquear divergencia).
4. Remover recalculo local de reposicao; paridade UI→envio.
5. Decidir approved/sent (remover ou impor com permissao + setup_groups).
6. UX de conferencia por excecao.

Este WP tem P0. Nao adicione novas entradas de estoque sem idempotencia. Declare o dono dos modelos novos antes de criar.
~~~

