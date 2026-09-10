# Verificação WP-06 — Compras

Base: worktree `coordenar-sessoes-deploys-b9cdac`, HEAD `9469c92a2` (descendente de `origin/main`, 2026-08-29). Todos os `arquivo:linha` abaixo foram abertos e lidos nesta árvore.

## A. Superfície real (o que existe hoje)

**Backend (Django)**

| Arquivo | O que é |
|---|---|
| `shopman/backstage/api/purchase.py` (223 linhas) | 10 views DRF. 8 com `required_permission = "backstage.operate_purchase"` (linhas 44, 57, 74, 91, 108, 142, 193, 210) e 2 com a tupla `PURCHASE_COUNT_PERMISSIONS` (linhas 163, 176), que o gate exige **todas** (`api/permissions.py:129-133`, `_required_codes`). |
| `shopman/backstage/api/urls.py:226-264` | As 10 rotas: `purchase/`, `receipts/scan-invoice/`, `receipts/confirm/`, `receipts/reject/`, `costs/`, `conversions/`, `count/`, `count/confirm/`, `requests/<sku>/approve/`, `requests/<sku>/send/`. |
| `shopman/backstage/services/purchase.py` (1182 linhas) | Write-side: `scan_invoice`, `confirm_receipt`, `reject_receipt`, `upsert_cost`, `declare_conversion`, `set_purchase_request_status`, e os helpers de fornecedor/lote/chave NF-e. |
| `shopman/backstage/services/purchase_count.py` (166 linhas) | **Não citado por G nem por D.** Contagem física → `stock.adjust`/`stock.receive` com `kind=ADJUST`. |
| `shopman/backstage/projections/purchase.py` (609 linhas) | Read model: materiais, fornecedores, conversões, custos, `purchaseRequestStatuses`, `activeReceipt`. |
| `shopman/backstage/projections/purchase_count.py` (84 linhas) | **Não citado por G nem por D.** |
| `shopman/shop/purchase_policy.py` (86 linhas) | **Não citado por G; D disse que "política não existe".** `PurchasePolicy` dataclass + `resolve_purchase_policy()` sobre `Shop.defaults["purchase"]` (PR #357). É política de **reposição**, não de limite de gasto. |
| `shopman/shop/adapters/purchase_invoice_nfe.py` (1198 linhas) | Leitor NF-e (download SEFAZ/XML local) → draft de recebimento; fuzzy de insumo; sugestão de conversão pelos dois eixos. |
| `packages/buyman/shopman/buyman/models/` | 4 modelos: `Material`, `MaterialConversion`, `Supplier`, `SupplierMaterialCost`. Nenhum modelo de recebimento. |
| `packages/stockman/.../services/movements.py:22-98` | `StockMovements.receive` — único caminho de escrita usado pelo recebimento. |
| `shopman/shop/management/commands/setup_groups.py:159, :233` | `operate_purchase` → só **Gerente**; `audit_stock` → só **Dono**. |

**Superfície (Nuxt)** — `surfaces/purchase-nuxt` existe e **não está listada no CLAUDE.md** (que fala em "7 apps Nuxt"; hoje há 9 diretórios de app + `operator-kit`). `bi-nuxt` também está fora da lista.

| Arquivo | O que é |
|---|---|
| `app/composables/usePurchaseDesk.ts` (1208) | Estado + gestos. Guarda de duplo clique em `runBackendAction` (`:718-720`). |
| `app/composables/usePurchaseApi.ts` (128) | Cliente HTTP; `approveRequest` (`:71-77`) exportado e **sem nenhum call site**. |
| `app/presentation/purchase.ts` (551) | Projeções puras: `parseMoneyInput` (`:38`), `parseInvoiceAccessKey` (`:135`), `parseQtyInput` (`:457`), `receiptLineWarnings`, `enrichMaterial`. |
| `app/pages/index.vue` (~950) | Tela única com 4 abas (`panel`/`buy`/`receive`/`base`). |
| `tests/purchase.test.ts` (744) | 30 testes de presentation. Nenhum sobre `reorderRows`, nenhum sobre `parseMoneyInput`. |

**Testes backend existentes:** `shopman/backstage/tests/test_api_purchase_surface.py` (1214 linhas, 31 testes), `test_purchase_replenishment.py` (107), `test_api_purchase_count.py` (236). **Não há nenhum teste de idempotência de recebimento.**

**ADRs/documentação relevantes:** ADR-023 (custo vivo × congelado), ADR-024 (unidade-base e conversões, R1-R4), `docs/reference/data-schemas.md:1423-1456` (contrato do `invoice_product_map`), `docs/plans/BUYMAN-PROCUREMENT-PLAN.md:72-75` (Fase 3: `PurchaseReceipt` **append-only** no buyman), `docs/plans/UNIT-CONVERSION-PLAN.md:3` (fases 0-6 ✅ concluídas).

---

## B. Evidências dos WPs, veredito uma a uma

| # | Afirmação (de quem) | Arquivo:linha ATUAL | Veredito | Nota |
|---|---|---|---|---|
| 1 | `confirm_receipt` confia no payload do browser (G, D) | `services/purchase.py:112-142` | **CONFIRMADO** | `mode` (:119), `invoiceAccessKey` (:123), `supplierRef` (:131), `lines` (:138) vêm todos de `payload`. Nada liga esses dados ao que o scan leu. Linhas de G (`:112, :123, :131, :138`) estão exatas. |
| 2 | Loop grava estoque via `stock.receive` (G, D) | `services/purchase.py:163-184`; `movements.py:79` | **CONFIRMADO** (linha corrigida) | G citou `:147`, que hoje é o `with transaction.atomic():`. A chamada real é `:163`. `Move.objects.create` incondicional em `movements.py:79`. |
| 3 | Recebimento não é idempotente (G, D) | `services/purchase.py:147-195`; `movements.py:70-86` | **CONFIRMADO** | Nenhuma chave única, nenhum `get_or_create` de recibo. Só o `Batch` deduplica (`:152`), e Batch não é o Move. |
| 4 | Aprende mapa fiscal no confirm (G, D) | `services/purchase.py:194-195` (chamada), `:874-921` (função) | **CONFIRMADO, mas documentado** | G/D citaram `:874`, que é a `def` — a **chamada** é `:195`, dentro da transação. O comportamento (inclusive o overwrite com `logger.warning`) está especificado em `docs/reference/data-schemas.md:1437-1451` e coberto por 3 testes (`test_api_purchase_surface.py:363, :434, :498`). Ver §E. |
| 5 | UI recalcula reposição localmente (G, D) | `usePurchaseDesk.ts:562-575` | **CONFIRMADO** (linha corrigida) | G/D citaram `:548`/`:548-555`; hoje é `:562-575`. `target = Math.max(minStock*2, dailyUse*7)`, filtro `coverageDays <= 5`. |
| 6 | Backend tem `_suggested_qty` e expõe (G, D) | `projections/purchase.py:305-323` (função), `:257` (campo), `:42` (dataclass) | **CONFIRMADO** | Linhas de G e D exatas. `replenish_at = leadTime + review + safety` (`:232`). |
| 7 | "Todas as views usam `operate_purchase`" — **6** views (G) | `api/purchase.py:44,57,74,91,108,142,193,210` | **PARCIAL** | São **8**, não 6; e as linhas de G (`36,49,66,100,117,155`) não batem com nada hoje. Além disso há 2 views com permissão diferente (`:163, :176`), que G ignorou. |
| 8 | São **8** views com `operate_purchase`, linhas `38,51,68,85,102,136,157,174` (D) | `api/purchase.py:44,57,74,91,108,142,193,210` | **PARCIAL** | Contagem certa (8), linhas erradas — nenhuma das 8 de D existe hoje. |
| 9 | `scan_invoice` já monta um draft efêmero (D) | `services/purchase.py:68-109` | **CONFIRMADO** | Linhas de D exatas: valida chave (:75), resolve fornecedor (:83-91), monta `active_receipt` (:94-100), devolve via `build_purchase(active_receipt=...)` (:109). Nada persistido. |
| 10 | `scan_invoice` cria fornecedor implicitamente (D) | `services/purchase.py:91` → `:1036-1072` (`Supplier.objects.create` em `:1064`) | **CONFIRMADO E SUBESTIMADO** | D só viu a criação. Há um segundo caminho de escrita: `_adopt_supplier_by_name` (`:996-1033`) **grava CNPJ e telefone num fornecedor já existente** (`supplier.save`, `:1029`). Ambos rodam no scan, fora de transação, antes de qualquer confirmação. |
| 11 | `_upsert_supplier_cost` sobrescreve `cost_q` E `conversion` in-place (D) | `services/purchase.py:856-871` | **CONFIRMADO** | Linhas de D exatas. `:863-864` são atribuições cegas; `:865-866` preserva `is_preferred`. |
| 12 | Pode **zerar** a conversão de um custo existente (D) | `services/purchase.py:863` + `:189` | **CONFIRMADO** | `_upsert_supplier_cost(conversion=line.conversion)` com `line.conversion is None` (compra na unidade-base) grava `cost.conversion = None` numa linha que tinha "saco 25 kg". Mecanismo concreto: nota com duas linhas do mesmo insumo, uma por caixa e uma a granel — a última linha do loop vence. |
| 13 | `prefer_if_missing=True` auto-promove o custo a preferido (D) | `services/purchase.py:193` + `:858-859` | **CONFIRMADO, e mais grave do que D disse** | D chamou de "decisor do custo canônico". É mais: `is_preferred` decide **qual fornecedor recebe o pedido** (`_queue_supplier_purchase_request`, `:479-483`) e o **lead time** do insumo (`projections/purchase.py:447-452`). O docstring do modelo (`packages/buyman/.../models/cost.py:12-15`) afirma "hoje esta tabela não tem leitor no repositório" — está **desatualizado**, e ADR-023 repete o mesmo erro. |
| 14 | `SupplierCostObservation` não existe (D) | `packages/buyman/shopman/buyman/models/` | **CONFIRMADO** | 4 modelos: `material.py`, `conversion.py`, `supplier.py`, `cost.py`. Nenhuma trilha de custo. |
| 15 | `approveRequest` é helper morto, zero call sites (D) | `usePurchaseApi.ts:71-77`, `:121` | **CONFIRMADO** | `grep` em `surfaces/purchase-nuxt/app` acha só a definição e o export. `sendPurchaseRequest` (`usePurchaseDesk.ts:1073-1076`) chama `sendRequest` direto. |
| 16 | `set_purchase_request_status` aceita `approved` e `sent` — `services/purchase.py:450-451` (D) | `services/purchase.py:448-451` | **CONFIRMADO** | Linha de D exata (`:450` é o `if status not in {...}`). |
| 17 | "`approve_purchase` não existe" (D) | `grep` em `shopman/`, `packages/`, `config/` | **CONFIRMADO** | Só existem `backstage.operate_purchase` e `backstage.audit_stock` (`backstage/models/closing.py:35-36`). |
| 18 | "'política' de limite também não existe" (D) | `shopman/shop/purchase_policy.py` | **PARCIAL** | Existe uma `PurchasePolicy` (PR #357), mas é de **reposição** (janelas, lead time, segurança) — não há limite de gasto nem gate de aprovação. A conclusão de D está certa; a afirmação, imprecisa. |
| 19 | `_purchase_request_snapshot` roda `build_purchase()` inteiro no path de escrita (D) | `services/purchase.py:576-577` | **CONFIRMADO** | Linha de D exata. Roda a projeção completa (todos os materiais, custos, moves, receitas, mediana de lead time) para ler **um** `suggestedQty`. |
| 20 | "Número exibido ≠ número despachado na reposição" (D) | `usePurchaseDesk.ts:562-575` vs `services/purchase.py:576-592` | **CONFIRMADO, com um efeito pior que D descreveu** | Não é só divergência silenciosa: quando o backend calcula `suggestedQty <= 0` (o caso comum quando a UI conta com `dailyUse*7` e o backend com `dailyUse*replenish_at`), o envio **falha** com "Este insumo não tem reposição sugerida agora" (`:581-586`) — sobre um item que a tela acabou de listar como urgente. |
| 21 | "Aceite `sem approve_purchase não envia acima da política`" é inverificável (D) | — | **CONFIRMADO** | Nem a permissão nem o limite existem; o aceite de G (`WP-06-compras.md:76`) não pode ser escrito como teste. |
| 22 | Permissão única gateia coisas de risco diferente (G, D) | `api/purchase.py` + `setup_groups.py:159, :233` | **PARCIAL — gravidade menor do que os dois sugerem** | É verdade que 8 gestos compartilham `operate_purchase`. Mas `setup_groups.py` concede `operate_purchase` **só ao Gerente** e `audit_stock` **só ao Dono**: não há hoje uma persona "conferente de balcão" com acesso a Compras. Separar permissões é preparação para uma persona que ainda não existe. Ver §E. |
| 23 | `models/cost.py:16` "admite ausência de trilha (ADR-023)" (D) | `packages/buyman/.../models/cost.py:12-16` | **CONFIRMADO** | O texto está em `:12-16`. |
| 24 | Fronteira "modelos novos: recebimento no backstage, custo no buyman" (D) | `docs/plans/BUYMAN-PROCUREMENT-PLAN.md:72-75` e `:23` | **REFUTADO** | O plano do repositório já declara o dono: **Fase 3 — Recebimento (ledger-first): `PurchaseReceipt` append-only** em **buyman**, com `receipt_created` → `buyman/contrib/stockman`. E `:23` diz "Buyman é dono de … (fases) Pedido de Compra, Recebimento, Reposição". A recomendação de D contraria um plano existente. |

---

## C. Achados confirmados, com gravidade recalibrada

### C1 — Nada no sistema sabe se uma NF já entrou (P0)

**Gravidade P0.** Risco: estoque e custo duplicados sem sinal nenhum. Esforço: baixo (uma tabela de 5 colunas + uma constraint + um `get_or_create`).

**Mecanismo, do clique ao efeito.** O operador escaneia a NF, confere as linhas, clica "Confirmar entrada". `confirm_receipt` abre a transação (`services/purchase.py:147`) e, por linha, chama `stock.receive` (`:163`), que faz `Move.objects.create` incondicional (`movements.py:79`). Não há chave de recibo em lugar nenhum: nem no `Move.metadata` (que carrega `purchase_invoice_access_key` mas ninguém consulta), nem numa tabela própria. Se a resposta se perder (504 no proxy, aba fechada, tablet sem rede na volta), o operador clica de novo e o estoque dobra. E mais provável no chão: **três horas depois, ninguém consegue responder "essa nota já entrou?"** — a projection não expõe nenhuma lista de recebimentos (`PurchaseProjection`, `projections/purchase.py:133-141`), e `_last_delivery_map` (`:539-558`) só devolve a data da última entrada por fornecedor. Reescanear a mesma NF é o gesto natural de quem está em dúvida, e ele duplica tudo em silêncio.

A guarda que existe é só de tela: `runBackendAction` bloqueia o segundo clique enquanto o primeiro está em voo (`usePurchaseDesk.ts:718-720`) e o sucesso limpa as linhas. Nenhuma delas sobrevive a um retry ou a um segundo dispositivo.

Ironia útil como prova: `reject_receipt` **é** idempotente — usa `create_deduped` com chave derivada de `(source_ref, supplier, reason, lines)` (`services/purchase.py:254-263`). Recusar a nota duas vezes não duplica nada; recebê-la duas vezes duplica o estoque.

**Fix mínimo.** `PurchaseReceipt` append-only em `packages/buyman` (dono já declarado — BUYMAN-PROCUREMENT-PLAN Fase 3), com `UniqueConstraint(fields=["invoice_access_key"], condition=Q(invoice_access_key__gt=""))`; `confirm_receipt` cria o recibo **antes** do loop de `stock.receive`, dentro da mesma transação; `IntegrityError` vira `PurchaseError(code="receipt_already_registered", status_code=409)` com a data e o operador da primeira entrada. Modo manual usa um `source_ref` estável (hoje `_manual_source_ref`, `:1149-1152`, mistura `timezone.now()` e portanto é diferente a cada chamada — trocar por hash de `supplier+lines+note+data`).

### C2 — O recebimento reescreve o custo mestre sem gesto e sem trilha (P0)

**Gravidade P0** (D disse P1; subo por causa da consequência que D não viu). Esforço: baixo para o fix mínimo.

**Mecanismo.** Ao confirmar, para cada linha com custo > 0, `_upsert_supplier_cost(..., prefer_if_missing=True)` (`services/purchase.py:185-193`). A função (`:856-871`) faz três coisas cegas:

1. `cost.conversion = conversion` (`:863`) — sobrescreve a unidade de compra do custo existente, inclusive para `None`;
2. `cost.cost_q = cost_q` (`:864`) — reprecifica o custo canônico do par (fornecedor, insumo);
3. `should_prefer = make_preferred or (prefer_if_missing and not preferred_exists)` (`:859`) — se nenhum custo preferido existe para o insumo, **esta entrada vira o custo preferido**.

E `is_preferred` **não é inerte**: decide qual fornecedor recebe o pedido de reposição (`:479-483`) e de onde sai o lead time do insumo (`projections/purchase.py:447-452`). O docstring do modelo (`packages/buyman/.../models/cost.py:12-15`) e a ADR-023 ainda afirmam que a tabela não tem leitor — o código andou, a documentação não.

Resultado prático: uma compra de emergência num fornecedor caro, feita às cinco da manhã, silenciosamente (a) reprecifica o insumo, (b) apaga a unidade de compra anterior e (c) pode eleger aquele fornecedor como o canônico. Nada aparece na tela, nada fica no histórico — `SupplierMaterialCost` não tem trilha, e o único `logger.info` de custo está em `upsert_cost` (`:301-309`), o caminho **manual**, não neste.

**Fix mínimo (duas linhas + um teste).** Trocar `prefer_if_missing=True` por `prefer_if_missing=False` em `services/purchase.py:192` — a promoção a custo canônico volta a ser um gesto explícito (`setPreferredCost`, que já existe em `usePurchaseDesk.ts:1078-1092`). E, em `_upsert_supplier_cost:863`, não apagar conversão existente quando a linha não declara uma:
```python
if conversion is not None or cost.pk is None:
    cost.conversion = conversion
```
A trilha append-only (`SupplierCostObservation`) é o fix **correto**, mas é maior; as duas linhas acima param a promoção e o apagamento hoje.

### C3 — O número que a tela sugere não é o número que o servidor despacha (P1)

**Gravidade P1.** Risco: pedido errado ao fornecedor, ou envio que falha sobre um item que a tela chamou de urgente. Esforço: baixo (apagar um `computed` e ler a projection).

**Mecanismo.** A aba "Comprar" monta `reorderRows` (`usePurchaseDesk.ts:562-575`) com regra própria: filtro `stockOnHand < minStock || coverageDays <= 5`, alvo `Math.max(minStock*2, dailyUse*7)`. O backend calcula `target = max(min_stock, daily_use * replenish_at)` com `replenish_at = leadTime + review_period + safety` da política do Admin (`projections/purchase.py:232, 305-323`) e expõe o resultado em `suggestedQty` (`:257`) — que a UI **recebe** (o tipo `Material.suggestedQty?` existe em `app/types/purchase.ts:31`) e **nunca lê**.

No envio, `_purchase_request_snapshot` (`services/purchase.py:576-606`) usa o `suggestedQty` do backend. Duas consequências: o fornecedor recebe uma quantidade diferente da que o operador aprovou; e quando o backend chega a zero, o clique morre com `"Este insumo não tem reposição sugerida agora"` (`:581-586`) — mensagem que contradiz a própria tela.

Há um terceiro número na mesma tela: `materialIssues` (`presentation/purchase.ts:415-417`) usa `coverageDays <= replenishAtDays(material)`, que **é** o valor do servidor. Ou seja, a lista de alertas e a lista de compra usam réguas diferentes, e nenhuma das duas usa a do envio.

**Fix mínimo.** Em `usePurchaseDesk.ts:562-575`, trocar o cálculo por `suggestedQty: material.suggestedQty ?? 0` e o filtro por `(material.suggestedQty ?? 0) > 0`, mantendo a ordenação por `coverageDays`. O `estimatedCostQ` continua sendo `preferredBaseCostQ * suggestedQty`.

### C4 — `scan_invoice` escreve em cadastro mestre antes de qualquer confirmação (P1)

**Gravidade P1.** Risco: lixo de cadastro e CNPJ gravado em fornecedor errado. Esforço: médio (o comportamento é intencional e útil; o fix é torná-lo reversível/visível, não removê-lo).

**Mecanismo.** `scan_invoice:91` chama `_register_supplier_from_issuer`, que ou **cria** um `Supplier` (`:1064`) ou, via `_adopt_supplier_by_name` (`:996-1033`), **grava CNPJ e telefone num fornecedor existente** (`:1021-1029`). Nada disso está em transação, e nada exige confirmação: basta bipar o QR. Escanear a nota errada, ou bipar por engano, deixa cadastro atrás. A adoção por nome tem guardas boas (só documento vazio, só um candidato — `:1016-1019`) e é decisão documentada no docstring (PR #364), mas continua sendo escrita de mestre num gesto que o operador entende como "ler".

**Fix mínimo.** Não criar/adotar no scan. Devolver o emissor no draft (`issuer` já viaja, `adapters/purchase_invoice_nfe.py:186-192`) e criar/adotar dentro de `confirm_receipt`, na transação que já existe — o fornecedor passa a nascer junto com a entrada que o justifica. Se o gesto precisar ficar no scan, expor `supplierCreated`/`supplierAdopted` na projection para a tela poder dizer "cadastrei este fornecedor da nota" com um desfazer.

### C5 — `approved` é estado inalcançável com endpoint vivo (P2)

**Gravidade P2** (G e D disseram P1). Risco: baixo — a rota existe e funciona, mas ninguém a chama e o estado não bloqueia nada. Esforço: baixo se a decisão for remover.

**Mecanismo.** `PurchaseRequestApproveView` (`api/purchase.py:191-205`) e `set_purchase_request_status(..., "approved")` (`services/purchase.py:448-473`) funcionam; `approveRequest` (`usePurchaseApi.ts:71-77`) existe e não é chamado de lugar nenhum; o badge "Pronto" (`index.vue:126, :132`) só apareceria se alguém setasse o estado por fora. `sendPurchaseRequest` (`usePurchaseDesk.ts:1073-1076`) vai direto de `review` para `sent` sem consultar `approved`.

Baixo por dois motivos: a rota exige a mesma permissão do resto (não é escalada), e o efeito de `approved` é só um carimbo em `Material.metadata`. É dívida de coerência, não de risco.

**Fix mínimo.** Escolher: apagar a view, a rota, o helper `approveRequest`, o valor `"approved"` de `REQUEST_STATUSES` (`projections/purchase.py:25`), do tipo TS (`types/purchase.ts:6`) e do badge; **ou** dar call site ao `approveRequest` e fazer `sendPurchaseRequest` recusar `status !== "approved"`. Não recomendo criar `approve_purchase` + limite de gasto agora: é feature nova (§H).

---

## D. Achados NOVOS (que G e D perderam)

### D1 — O total em dinheiro que a tela mostra pode ser 100× o que o servidor grava (P1)

**Gravidade P1.** Risco: dinheiro; falha silenciosa dos dois lados. Esforço: 3 linhas, com precedente pronto no mesmo arquivo.

**Mecanismo.** Há dois parsers de dinheiro e eles discordam.

- TS (`presentation/purchase.ts:38-47`): remove **todos** os pontos, depois troca a primeira vírgula por ponto.
- Python (`services/purchase.py:685-702`): se há vírgula, trata ponto como milhar; **senão**, `raw.count(".") == 1 and len(decimais) <= 2` faz o ponto valer como decimal.

O operador digita `12.50` no campo de custo da linha (input livre, `inputmode="decimal"`, `index.vue:831`):

| | resultado |
|---|---|
| TS → `receiptTotalCostQ` (`usePurchaseDesk.ts:512-513`), exibido em `index.vue:907` | **R$ 1.250,00** |
| Python → `total_cost_q`, gravado no `Move` e no `SupplierMaterialCost` | **R$ 12,50** |

Com `12.5` a divergência é 10×. Nenhum dos dois lados avisa, e nenhum teste cobre `parseMoneyInput` (`tests/purchase.test.ts` tem 30 testes, zero sobre dinheiro digitado). O caminho pré-preenchido pela NF está a salvo (`_money_text` usa vírgula, `adapters/purchase_invoice_nfe.py:1113-1116`; `centsInput` também, `usePurchaseDesk.ts:356-358`) — o buraco é só na digitação, que é exatamente o modo manual "sem NF".

Pior: um custo **impossível de parsear** vira `0` em silêncio nos dois lados (`parse_money_input` retorna `0` em `InvalidOperation`, `:698-699`), e `confirm_receipt` simplesmente pula o custo (`if line.total_cost_q > 0`, `:185`). Digitar `12,50 (com frete)` grava a entrada com custo zero e não diz nada. Isso é falhar-aberto em dinheiro.

**Fix mínimo.** Alinhar o TS ao Python — a regra "vírgula decide a notação" já está implementada três funções abaixo, em `parseQtyInput` (`presentation/purchase.ts:457-465`):
```ts
const normalized = value.trim().replace(/[R$\s]/g, "");
const parsed = Number(normalized.includes(",") ? normalized.replace(/\./g, "").replace(",", ".") : normalized);
```
E, no servidor, `parse_money_input` deve distinguir "vazio" de "não entendi": levantar `PurchaseError(code="cost_unparseable", field=f"lines.{index}.costInput")` quando o texto não é vazio e não parseia, em vez de devolver `0`.

### D2 — Nada confere que o fornecedor escolhido é o emissor da NF (P1)

**Gravidade P1.** Risco: estoque, custo e de-para fiscal atribuídos ao fornecedor errado. Esforço: **uma linha** — a verificação já existe no arquivo, aplicada a outro caso.

**Mecanismo.** `confirm_receipt` valida a chave de acesso (`:124`) e valida que o fornecedor existe e está ativo (`:131-136`) — mas **nunca cruza os dois**. Os 14 dígitos do CNPJ do emitente estão dentro da própria chave, e o código já sabe disso: `_supplier_ref_from_invoice_key` faz `issuer_cnpj = access_key[6:20]` (`:1075-1081`).

No chão: o scan preenche o fornecedor certo, mas o `supplierRef` que volta no confirm é o do dropdown da tela (`usePurchaseDesk.ts:934`), que o operador pode ter trocado sem perceber ao navegar entre abas — `normalizeSelections`/`applyProjection` mexem em seleções (`:668-682`). O resultado: `Move.metadata.purchase_supplier_ref` errado, `SupplierMaterialCost` do fornecedor errado, e — o pior — `_learn_invoice_product_map` (`:195`) ensina o de-para `cProd → insumo` **no fornecedor errado**, envenenando o scan de todas as notas futuras daquele fornecedor. O overwrite loga um `warning` (`:904-912`), mas o aprendizado inicial no fornecedor errado não loga nada.

Isto é o núcleo defensável do "P0 de payload" que G e D descreveram — e ele não precisa de `ReceiptDraft` para ser fechado.

**Fix mínimo**, em `services/purchase.py`, logo depois de `:136`:
```python
if mode == "invoice" and re.sub(r"\D", "", supplier.document or "") != invoice_key[6:20]:
    raise PurchaseError("O fornecedor escolhido não é o emitente desta NF.", code="supplier_not_issuer", field="supplierRef")
```

### D3 — A validação da chave NF-e diverge entre tela e servidor (P2)

**Gravidade P2.** Risco: erro tardio e confuso; nenhum dano de dado. Esforço: baixo.

**Mecanismo.** O servidor confere o dígito verificador módulo-11 (`_valid_invoice_key`, `:1095-1106`). A tela só procura 44 dígitos (`parseInvoiceAccessKey`, `presentation/purchase.ts:135-139`) e chama isso de `valid` (`invoiceProbe`, `:141-147`). O gate de confirmação usa a validação fraca (`receiptDocumentBlockers`, `usePurchaseDesk.ts:508-510`): com uma chave digitada com um dígito trocado, a tela libera "Confirmar", o servidor recusa, e a linha só volta a ser digitável depois do erro. O teste de TS que existe (`tests/purchase.test.ts:181-187`) só testa a extração, não o dígito.

**Fix mínimo.** Portar o cálculo de `_valid_invoice_key` para `presentation/purchase.ts` (é determinístico, ~8 linhas, sem risco de "segunda tabela" — não é regra de negócio, é aritmética do documento) e usá-lo em `invoiceProbe`. Alternativa mais barata: mover o bloqueio para depois do scan (só liberar confirmação se `readInvoice` tiver respondido `ok` para esta chave), que resolve o mesmo problema sem duplicar código.

### D4 — Payload frouxo vira 500 na cara do operador (P2)

**Gravidade P2.** Risco: baixo pela via da UI (o front nunca produz esses valores); real pela via de qualquer requisição fora dela. Esforço: baixo.

**Mecanismo.** `_error_response` (`api/purchase.py:30-39`) só trata `PurchaseError`. O `EXCEPTION_HANDLER` da casa (`shopman/shop/api_errors.py:49-62`) delega ao handler do DRF, que devolve `None` para exceções não-DRF — ou seja, **500 cru**. Três valores chegam lá (verificado executando os parsers):

- `{"lines":[{"purchaseQty":"NaN"}]}` → `_decimal` (`:1178-1182`) devolve `Decimal('NaN')`; a comparação `purchase_qty <= 0` (`:725`) levanta `InvalidOperation` → 500.
- `{"costInput":"Infinity"}` → `Decimal("Infinity")` passa da construção, e `.quantize()` (`:702`) levanta `InvalidOperation` → 500.
- `{"purchaseQty":"Infinity"}` → passa do gate `> 0`, vira `base_qty = Infinity`, e `stock.receive` (`movements.py:21`) também deixa passar → o erro estoura no `Move.objects.create` como exceção de banco.

Mesma classe em `purchase_count._parse_qty` (`services/purchase_count.py:154-166`): `"NaN"` levanta na comparação `value < 0`.

E há uma terceira convenção decimal na mesma frente: `_decimal` (`services/purchase.py:1178`) só troca `,` por `.`, então o fator de conversão `"1.250"` (mil duzentos e cinquenta escrito à brasileira) vira `1,25` em silêncio, num número que multiplica estoque e dinheiro.

**Fix mínimo.** Em `_decimal` e `parse_money_input`, recusar não-finitos:
```python
value = Decimal(str(raw).replace(",", "."))
return value if value.is_finite() else Decimal("0")
```
E envolver o corpo das views de escrita num `except Exception` que devolve o dialeto canônico `{detail, error.code}` com 500 legível — hoje o operador vê a página de erro do DRF.

### D5 — O contrato tem campos que ninguém lê, e a UI tem números que ninguém envia (P2)

**Gravidade P2.** Dívida de contrato, não de dado.

- `MaterialProjection.replenishAtDays` (`projections/purchase.py:41`) e `suggestedQty` (`:42`) chegam ao TS (`types/purchase.ts:30-31`) — `replenishAtDays` é lido por `materialIssues`, `suggestedQty` **não é lido por nada**. É o campo que fecharia C3.
- `coverageDays` é calculado só no cliente (`presentation/purchase.ts:71-74`) e é o eixo de ordenação e de filtro da aba "Comprar", sem contraparte no servidor.
- `PurchaseProjection` não expõe **nada** sobre recebimentos realizados — o que é a raiz de C1 pelo lado da tela.
- `ReceiptLineProjection.suggestionScore` (`:104`) é `int` no servidor e `number` no TS, mas `receiptLineSuggestion` faz `Math.round(line.suggestionScore ?? 0)` (`presentation/purchase.ts:164`), arredondando um inteiro. Inofensivo; sinal de contrato não conferido.

### D6 — A contagem de insumos ficou fora dos dois WPs (P2, informativo)

`shopman/backstage/services/purchase_count.py`, `projections/purchase_count.py` e as views `PurchaseCountView`/`PurchaseCountConfirmView` (`api/purchase.py:161-188`) são parte da mesma superfície (aba `base/count`) e nenhum dos dois WPs os menciona. A boa notícia: **esse serviço está melhor construído que o recebimento** — é idempotente por construção (converge ao contado; um segundo envio dá delta zero e não lança nada, `services/purchase_count.py:104-107`), recusa SKU duplicado (`:67-73`), exige motivo para divergência e reconfere a divergência **no momento de aplicar**, não no de carregar (`:110-117`), e escreve sempre pelo caminho canônico do Stockman. Vale como referência do padrão que C1/C2 deveriam seguir.

Uma nota de fronteira: ele importa `_default_receive_position` — um privado de `services/purchase.py` (`purchase_count.py:24`). Acoplamento pequeno, mas o WP que mexer em `purchase.py` precisa saber.

**Nada novo encontrado** sobre: autorização real (a matriz de `setup_groups.py` é coerente com o que as views exigem), escrita concorrente no `SupplierMaterialCost` (o `save()` do modelo já resolve a promoção atomicamente, `models/cost.py:139-160`), ou segundo escritor de `Move.kind=BUY` (só existe `confirm_receipt`).

---

## E. Achados a DESCARTAR (de G ou D)

1. **"Mapa fiscal aprende do payload" como P0 isolado** (G `:16`/`:25`, D "proteger `_learn_invoice_product_map`"). O comportamento é **decisão documentada**: `docs/reference/data-schemas.md:1423-1451` especifica o contrato, quem escreve, quem lê, o tratamento de aliases legados e a política de overwrite com `warning` estruturado; e há 3 testes cobrindo aprendizado, substituição divergente e não-aprendizado sem contexto de NF (`test_api_purchase_surface.py:363, :434, :498`). É uma decisão **correta** para o caso que ela resolve. O que sobra de risco real é o vetor de D2 (fornecedor ≠ emitente), que é um achado diferente e tem fix de uma linha. Não vale um WP próprio.

2. **`ReceiptDraft` como entidade nova (G) / draft persistido (D) como pré-requisito de tudo.** Não descartar a ideia, descartar a **prioridade**. Persistir o draft é uma peça grande (modelo, ciclo de vida, expiração, modo manual, deltas de conferência, migração), e as três consequências concretas que G e D usaram para justificá-la se fecham mais barato: a duplicação por C1 (`PurchaseReceipt` + constraint), o fornecedor errado por D2 (uma linha), e o mapa fiscal envenenado também por D2. O que o draft ainda resolveria — "confirmar linha que não veio da nota" — é, hoje, o gesto **legítimo** de um app cujo único usuário é o Gerente e que precisa aceitar entrada sem NF (`mode="manual"`, `:120`). Proponho o draft como fase posterior, não como P0.

3. **"Separar permissões scan/receive/cost/conversion/approve/send" agora** (G `:108`, D `:112`). `setup_groups.py:159` concede `operate_purchase` só ao Gerente; `:233` concede `audit_stock` só ao Dono. Não existe hoje uma persona de conferente de balcão com acesso a Compras — a granularidade seria preparação para um usuário que não existe, e custaria migração de permissão + revisão de grupos + testes de paridade. Além disso, `PurchaseConversionView` (`api/purchase.py:123-142`) tem **20 linhas de docstring** justificando por que declarar conversão é permissão de operador de compras e não de gestor; é uma decisão explícita e, na minha leitura, correta (a conversão transcreve o que a nota declara e guarda `created_by`). Reabrir isso exige o gesto do dono (§H), não uma auditoria.

4. **"Conversão divergente bloqueia até justificar"** (G `:84`, D `:69`). Já existe o aviso de ordem de grandeza, com tolerância relativa igual nos dois lados (`presentation/purchase.ts:187-198`, `_same_factor` em `adapters/purchase_invoice_nfe.py:527`), e a R4 da ADR-024 já **recusa** entrada sem fator declarado (`services/purchase.py:738-743`). Transformar "watch" em "block" é decisão de produto (trava a entrada com o entregador esperando — exatamente o impasse que `declare_conversion` foi criada para desfazer, ver o docstring em `:317-328`), não correção de bug. Vai para §H.

5. **Aceite "usuário sem `approve_purchase` não consegue enviar compra acima da política"** (G `:76`). Inescrevível: nem a permissão nem o limite existem. D já apontou; confirmo e mantenho fora.

6. **`_purchase_request_snapshot` roda `build_purchase()` inteiro** (D). Confirmado (`:577`) e é de fato desperdício, mas: acontece uma vez por clique de "enviar pedido", num app de um usuário, num catálogo de dezenas de insumos. Custo desproporcional ao risco enquanto não houver medição. Manter como nota, não como achado.

---

## F. Aceites verificáveis

Todos checáveis contra o código/teste de hoje. Nenhum depende de infra inexistente.

| # | Aceite | Como se prova |
|---|---|---|
| F1 | Confirmar a mesma NF duas vezes não cria um segundo `Move` | Teste em `shopman/backstage/tests/test_api_purchase_surface.py`: POST em `receipts/confirm/` duas vezes com o mesmo payload; segundo responde 409 com `error.code == "receipt_already_registered"`; `Move.objects.filter(kind="buy").count() == 1`. |
| F2 | Recebimento em modo `manual` também é idempotente | Mesmo teste sem `invoiceAccessKey`; a chave de recibo deve ser derivada de `(supplier, lines, note, data)` — hoje `_manual_source_ref` (`services/purchase.py:1149-1152`) usa `timezone.now()` e falharia. |
| F3 | Fornecedor escolhido é o emitente da NF | Teste: confirmar com `supplierRef` de um fornecedor cujo `document` ≠ `invoice_key[6:20]` → 400, `field == "supplierRef"`, `code == "supplier_not_issuer"`; e nenhum `Move` criado. |
| F4 | Confirmação não promove custo a preferido | Teste: insumo sem custo preferido; confirmar entrada com custo → `SupplierMaterialCost.objects.filter(material=..., is_preferred=True).exists() is False`. Contra-prova: `setPreferredCost` via `costs/` com `makePreferred=true` continua promovendo. |
| F5 | Confirmação não apaga a conversão de um custo existente | Teste: criar `SupplierMaterialCost` com `conversion` = "saco 25 kg"; confirmar uma entrada do mesmo par sem `conversionId` → `cost.conversion_id` inalterado. |
| F6 | A quantidade sugerida na tela é a do servidor | Teste vitest em `surfaces/purchase-nuxt/tests/purchase.test.ts`: `reorderRows` (ou a função pura extraída dele) com `suggestedQty: 7` e `minStock`/`dailyUse` que produziriam outro número → resultado é 7. Complementar: `grep -n "Math.ceil(target" surfaces/purchase-nuxt/app/composables/usePurchaseDesk.ts` não retorna nada. |
| F7 | O número aprovado na tela é o número no pedido | Teste backend: com `suggestedQty` conhecido, `POST requests/<sku>/send/` → o `Directive` criado tem `payload.context.base_qty_display` correspondente àquele `suggestedQty`. |
| F8 | Os dois parsers de dinheiro concordam | Tabela de casos idêntica nos dois lados: `"12,50"→1250`, `"12.50"→1250`, `"1.234,56"→123456`, `"1.234"→123400`, `"R$ 12,50"→1250`. Um teste em `tests/purchase.test.ts` e um em `test_api_purchase_surface.py`, com a **mesma** tabela literal. |
| F9 | Custo ilegível não vira zero silencioso | Teste: `costInput: "12,50 (com frete)"` → 400 com `field == "lines.0.costInput"`; nenhum `Move` criado. |
| F10 | Payload não-finito não vira 500 | Teste: `purchaseQty: "NaN"`, `purchaseQty: "Infinity"`, `costInput: "Infinity"` → cada um responde 400 com `detail` e `field`, nunca 500. |
| F11 | A tela só libera "Confirmar" para chave que o servidor aceitaria | Teste vitest com uma chave de 44 dígitos e dígito verificador errado → `invoiceProbe(...).valid === false`. |
| F12 | Escanear não cria nem altera fornecedor | Teste: `POST receipts/scan-invoice/` com XML de emitente desconhecido → `Supplier.objects.count()` inalterado; a criação acontece só no confirm. (Se o dono preferir manter a criação no scan, o aceite vira: a resposta traz `supplierCreated: true` e a tela o exibe.) |
| F13 | Se `approved` for removido: não sobra resíduo | `grep -rn "approved\|approveRequest" shopman/backstage/{api,services,projections}/purchase.py surfaces/purchase-nuxt/app` retorna vazio. Se for mantido: teste de que `POST requests/<sku>/send/` com status `review` responde 409. |

---

## G. Fronteiras e colisões

**Arquivos que este WP precisa tocar** (lista exata, para a matriz de colisão):

*Backend*
- `shopman/backstage/services/purchase.py` — C1 (recibo + idempotência), C2 (`:192`, `:863`), C4 (`:91`), D2 (`:136`), D4 (`:685-702`, `:1178-1182`)
- `shopman/backstage/api/purchase.py` — 409 no confirm; `except Exception` legível; possível remoção de `PurchaseRequestApproveView`
- `shopman/backstage/api/urls.py:256-259` — só se `approved` for removido
- `shopman/backstage/projections/purchase.py` — `REQUEST_STATUSES` (`:25`) se `approved` sair; opcional: expor recibos recentes
- `shopman/backstage/tests/test_api_purchase_surface.py` — F1-F5, F7, F9, F10, F12
- `packages/buyman/shopman/buyman/models/__init__.py` + `models/receipt.py` (novo) + migração `0007_*` — C1
- `packages/buyman/shopman/buyman/models/cost.py:12-15` — docstring desatualizado ("não tem leitor")
- `docs/decisions/adr-023-cost-live-and-frozen.md` — mesma correção; a tabela **tem** leitores hoje
- `docs/reference/data-schemas.md` — se o `Move.metadata` do recebimento ganhar `purchase_receipt_ref`

*Superfície*
- `surfaces/purchase-nuxt/app/composables/usePurchaseDesk.ts` — C3 (`:562-575`)
- `surfaces/purchase-nuxt/app/presentation/purchase.ts` — D1 (`:38-47`), D3 (`:135-147`)
- `surfaces/purchase-nuxt/app/composables/usePurchaseApi.ts:71-77, :121` — só se `approved` sair
- `surfaces/purchase-nuxt/app/pages/index.vue:124-133` — idem (badge)
- `surfaces/purchase-nuxt/app/types/purchase.ts:6` — idem
- `surfaces/purchase-nuxt/tests/purchase.test.ts` — F6, F8, F11

*Não tocar* (leitura apenas): `shopman/shop/adapters/purchase_invoice_nfe.py` (dono é o orquestrador; nada aqui exige mudança), `packages/stockman/.../services/movements.py` (a idempotência é do chamador, não do ledger — `receive` é primitiva genérica e outros apps dependem dela), `shopman/shop/purchase_policy.py`.

*Colisão provável:* `shopman/backstage/services/purchase.py` também é importado por `services/purchase_count.py:24` (`_default_receive_position`). Qualquer WP que mexa em contagem de insumos colide aqui.

**Permissões novas e `setup_groups.py`.** **Recomendo nenhuma.** Ver §E item 3: `operate_purchase` hoje só existe no grupo "Gerente" (`shopman/shop/management/commands/setup_groups.py:159`) e `audit_stock` só no "Dono" (`:233`); não há persona intermediária para separar. Se o dono decidir criar a persona "conferente" (§H-1), então: `setup_groups.py` ganha um grupo novo com `operate_purchase` **sem** `costs/`/`conversions/`, e as views `PurchaseCostView` (`:106`) e `PurchaseConversionView` (`:123`) trocam para uma permissão própria — e aí é obrigatório um teste de paridade grupo↔view, porque o modo silencioso de errar é conceder uma permissão que nenhuma view exige (ou o contrário, que trava o app).

**Modelos novos — de quem é o dono.** Não é pergunta aberta: o repositório já respondeu.

- **`PurchaseReceipt` → `packages/buyman`.** `docs/plans/BUYMAN-PROCUREMENT-PLAN.md:72-75` especifica "Fase 3 — Recebimento (ledger-first): `PurchaseReceipt` **append-only** (correção = nova receipt, nunca edição) + `ReceiptService` que emite `receipt_created` → handler em `buyman/contrib/stockman` chama `stock.receive`", e `:23` declara Buyman dono de "Pedido de Compra, Recebimento, Reposição". Isso também é o idioma que o CLAUDE.md manda usar (anunciar evento sem esperar retorno → signal + ponte `<core>/contrib/<alvo>/`, como `craftsman/contrib/stockman` já faz). **A recomendação de D (recebimento no backstage) contraria esse plano.** Nota honesta: adotar a ponte por signal é uma mudança maior que a constraint de idempotência; é legítimo entregar o `PurchaseReceipt` no buyman **sem** o signal numa primeira volta, com `confirm_receipt` criando o recibo e chamando `stock.receive` como hoje, e declarar a ponte como fase seguinte.
- **`SupplierCostObservation` → `packages/buyman`.** Mesmo plano, `:40-45`: "Ledger-first … Aplicar ao **recebimento** (append-only) e ao **histórico de custo** (futuro)". Custo de compra é domínio declarado do Buyman (`:23`).
- **`ReceiptDraft` → não criar agora** (§E item 2). Se vier, é do **backstage**: é estado de uma conferência de tela, não fato de domínio — e a regra de dependência do CLAUDE.md permite backstage → packages, nunca o inverso.

---

## H. Pergunta aberta para o dono do produto

1. **Existe, ou vai existir, alguém que recebe mercadoria e não é o Gerente?** Hoje `operate_purchase` está só no grupo Gerente. Se a resposta for não, separar permissões (scan/receive/cost/conversion) sai do WP e a discussão de `approve_purchase` morre junto. Se for sim, muda a arquitetura de permissões e o `setup_groups.py`.

2. **Quando a NF discorda da conversão cadastrada (o saco declarado de 25 kg vem como 20 na nota), a entrada deve PARAR até alguém decidir, ou seguir com o aviso que já existe?** Hoje é aviso. Parar protege custo e estoque contra um erro de 20%; parar também trava a entrada com o entregador na porta, que é o impasse que a rota de declarar conversão foi criada para desfazer. É decisão de negócio, não de código.

3. **Quando o mesmo insumo é recebido de um fornecedor novo, o custo daquela nota deve virar o custo canônico da casa?** Hoje vira, sozinho, se ainda não houver um preferido — e esse custo preferido decide para quem o próximo pedido de reposição é enviado. Proponho parar de promover automaticamente (C2); confirme se isso não quebra o fluxo que você espera no início de vida de um insumo novo.
