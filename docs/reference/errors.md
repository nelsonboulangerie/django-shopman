# Referência de Exceções e Códigos de Erro

> Gerado a partir dos arquivos `exceptions.py` do código atual.

---

## Dialeto HTTP de erro (superfícies headless)

Toda resposta de erro JSON das APIs (`/api/v1/` e `/api/v1/backstage/`) fala o
mesmo dialeto, que os fronts Nuxt leem via `httpError.ts`:

```json
{
  "detail": "Escolha a data.",
  "field": "delivery_date",
  "errors": {"delivery_date": ["Escolha a data."]}
}
```

| Chave | Presença | Uso |
|-------|----------|-----|
| `detail` | **Sempre** | Mensagem humana principal (pt-br). É o que as superfícies exibem (`errorDetail`/`httpErrorMessage`). |
| `field` | Erros de campo | Roteia o erro para o passo/campo dono (ex.: `finalizar.vue` reabre o passo do checkout). Campos aninhados usam caminho pontuado (`delivery_address_structured.cep`, `items.0.sku`). |
| `errors` | Erros de validação | Mapa completo `campo → [mensagens]` para render inline. |

Implementação:

- **Erros de negócio** são construídos manualmente nas views já nesse shape.
- **Falha de serializer DRF** é convertida pelo `EXCEPTION_HANDLER` custom
  (`shopman/shop/api_errors.py`, registrado em `config/settings.py`): o shape
  DRF cru `{"phone": ["..."]}` nunca chega ao front. Mensagens dos validators
  chegam em pt-br via i18n (`LANGUAGE_CODE = "pt-br"` + locale `pt_BR` do DRF).
- **Não encontrado mapeia por TIPO de exceção**, nunca por string: `PosRecentSaleNotFound`,
  `KDSTicketNotFound`, `KDSOrderNotFound` → 404; conflito de estado
  (`OrderConflict`/`OrderStateConflict`) → 409.

### Superset do PDV (deliberado)

O POS fala um dialeto **rico** por cima do canônico — `detail` continua
obrigatório; `error` agrega metadados estáveis de recuperação
(`shopman/shop/services/pos_intent.py`):

```json
{
  "detail": "CPF/CNPJ inválido: confira os dígitos.",
  "error": {
    "code": "invalid_customer_tax_id",
    "message": "CPF/CNPJ inválido: confira os dígitos.",
    "field": "customer_tax_id",
    "focus": "customer_tax_id",
    "recovery": "Corrija o documento ou remova para emitir sem CPF."
  }
}
```

Um front que só entende o dialeto canônico continua funcionando (lê `detail`);
o operator-kit usa `error.{code,focus,recovery}` para foco e ação de 1 clique.

### Recusa de negócio nomeada: reenvio do link de pagamento (409)

`POST /api/v1/backstage/pos/orders/<ref>/resend-payment-link/` (PDV) e
`POST /api/v1/backstage/orders/<ref>/resend-payment-link/` (gestor) recusam no
canônico mais `error.code` — `detail` é o que a tela mostra no toast; o código
é para a tela distinguir "venceu" de "cedo demais" sem casar a frase
(`shopman/shop/services/notification.py::resend_payment_link`):

| `error.code` | O que aconteceu | O que resolve |
|---|---|---|
| `payment_link_unavailable` | O pedido não é de `link`, ou a cobrança não nasceu (sem `checkout_url`) | Nada a reenviar; refazer a venda se o gateway falhou |
| `payment_link_order_cancelled` | Pedido cancelado (o vencimento cancela sozinho) | Refazer a venda |
| `payment_link_already_paid` | Payman mostra captura cobrindo o total | Nada — o cliente pagou |
| `payment_link_expired` | `payment.expires_at` no passado | Refazer a venda; não existe regenerar o link |
| `payment_link_send_pending` | O envio anterior ainda está `queued`/`running` | Aguardar; o worker retenta com backoff |
| `payment_link_resend_too_soon` | Último envio há menos de 60 s | Aguardar o que o `detail` diz |

Todos saem **409**. O 200 devolve `{ok, ref, detail, payment_link_notice}` — a
prova de envio ("Enviando o link ao cliente…") que o detalhe do gestor também
carrega em `payment_link_notice`.

### Recusa nomeada: `error.code` em 403

Nem toda recusa é igual, e o status HTTP sozinho não separa as três que o operador
enfrenta. `shopman/shop/api_errors.py` publica o código da recusa em `error.code`
quando ela tem nome:

| `error.code` | O que aconteceu | O que resolve |
|---|---|---|
| `not_authenticated` | A sessão do operador caiu (ou nunca existiu) | Login |
| `station_locked` | O operador ativo saiu; a estação está travada | O PIN, ali mesmo |
| *(ausente)* | Falta de permissão comum | Nada que a tela possa oferecer |

⚠️ **O backstage nunca devolve 401.** `DEFAULT_AUTHENTICATION_CLASSES` tem uma
classe só (`SessionAuthentication`), que não implementa `authenticate_header()` —
e sem header de desafio o DRF rebaixa o `NotAuthenticated` para **403**. Por isso a
sessão expirada chega às superfícies como 403, e a única forma de distingui-la de
uma recusa de permissão é o `error.code`.

O front decide pelo **código**, nunca pelo status solto: `isUnauthenticatedError`
aceita 401 **ou** 403 com `not_authenticated`; `isStationLockedError` exige 403 com
`station_locked` (`surfaces/operator-kit/app/utils/httpError.ts`). Afrouxar isso
para "todo 403" transformaria toda negativa de permissão em "sessão expirada" e
mandaria o operador digitar senha para um problema que senha não resolve.

**Recusa de permissão comum continua sem `error`** — o handler ignora
`code == "permission_denied"` de propósito. É a ausência que diz "não há nada a
oferecer aqui".

⚠️ **Gate de operador recusa LEVANTANDO, nunca devolvendo `False`.** Um
`BasePermission` que devolve `False` entrega ao DRF a escolha da exceção, e ele
escolhe pelo estado da **autenticação**, não pelo que a recusa é: sem authenticator
bem-sucedido, vira `NotAuthenticated`. A estação autônoma (o totem) opera sem sessão
— então a recusa por falta de permissão dela saía como credencial ausente, com a
mensagem certa montada e descartada. `HasBackstagePermission` levanta as duas
recusas (`station_locked` e falta de permissão) por isso.

### Superset do storefront (deliberado)

Respostas de **recuperação** e **rate-limit** do storefront agregam metadados de
UI por cima do canônico — `detail` continua obrigatório. São consumidos pelo app
Nuxt (`useCartState`, lógica de retry); um front que só lê `detail` ignora o
resto sem quebrar:

```json
{
  "detail": "Atualize a quantidade: temos menos em estoque.",
  "error_code": "insufficient_stock",
  "title": "Revise este item",
  "actions": [ ... ],
  "retry_after_seconds": 60
}
```

| Chave | Presença | Uso |
|-------|----------|-----|
| `error_code` | Erros com recuperação | Roteia a UI para a ação certa (`mutation_in_progress`, `rate_limited`, `insufficient_stock`, `order_not_cancellable`…). |
| `title` | Alertas ricos (carrinho) | Título curto do alerta quando a tela não deriva o próprio (o 404 NÃO carrega `title` — a tela gera pelo status). |
| `actions` / `retry_after_seconds` | Rate-limit e conflitos | Ações de 1 clique e cadência de retry (`Retry-After` também vai no header). |
| `payment_status` | 409 `order_not_cancellable` | Enum **cru** do pagamento (`pending`/`authorized`/`captured`) que explica *por que* o cancelamento foi recusado. É o único ponto onde `payment_status` aparece — o payload de tracking usa `payment_status_label` (rótulo humano), sem colisão de nome. |

**Regra:** respostas simples — em especial **todo 404** — falam só o canônico
`{detail, field, errors}`. O superset só aparece onde há semântica de recuperação
real que o front consome; nunca é decoração de um erro comum.

---

## Hierarquia

```
Exception
├── BaseError (utils)                    # Base com code + message + data
│   ├── CatalogError (offerman)
│   ├── StockError (stockman)
│   ├── CraftError (craftsman)
│   │   └── StaleRevision
│   ├── CustomerError (guestman)
│   └── AuthError (doorman)
│       └── GateError
│
├── PaymentError (payman)                # Base independente com code + context
│
├── OrderError (orderman)                # Base independente com code + context
│   ├── ValidationError
│   ├── SessionError
│   ├── CommitError
│   ├── DirectiveError
│   ├── IssueResolveError
│   ├── IdempotencyError
│   ├── IdempotencyCacheHit
│   └── InvalidTransition
│
└── RefError (orderman/refs)
    ├── RefTypeNotFound
    ├── RefScopeInvalid
    └── RefConflict
```

---

## BaseError (Utils)

**Arquivo:** `packages/utils/shopman/utils/exceptions.py`

Classe base que todas as exceções de domínio dos core apps herdam. Oferece serialização via `as_dict()`.

```python
raise BaseError(code="SOME_CODE", message="descrição", extra_key="valor")
# .as_dict() → {"code": "SOME_CODE", "message": "descrição", "extra_key": "valor"}
```

---

## CatalogError (Offerman)

**Arquivo:** `packages/offerman/shopman/offerman/exceptions.py`
**Base:** `BaseError`
**Propriedade:** `.sku` — extrai SKU dos dados

| Código | Quando ocorre |
|--------|--------------|
| `SKU_NOT_FOUND` | SKU não encontrado no catálogo |
| `SKU_INACTIVE` | Produto existe mas está inativo |
| `NOT_A_BUNDLE` | Tentativa de expandir produto que não é bundle |
| `INVALID_PRICE_LIST` | Listing referenciado não existe |
| `PRICE_LIST_EXPIRED` | Listing expirou |
| `INVALID_QUANTITY` | Quantidade inválida (≤ 0) |
| `CIRCULAR_COMPONENT` | Ciclo detectado na árvore de componentes do bundle |

**Guia:** [offerman.md](../guides/offerman.md)

---

## StockError (Stockman)

**Arquivo:** `packages/stockman/shopman/stockman/exceptions.py`
**Base:** `BaseError`
**Propriedades:** `.available`, `.requested` — quantidades para erros de insuficiência

| Código | Quando ocorre |
|--------|--------------|
| `INSUFFICIENT_AVAILABLE` | Quantidade disponível insuficiente para hold/move |
| `INSUFFICIENT_QUANTITY` | Quantidade insuficiente para operação genérica |
| `INVALID_HOLD` | Hold não encontrado ou em estado inválido |
| `INVALID_STATUS` | Transição de status inválida |
| `INVALID_QUANTITY` | Quantidade ≤ 0 |
| `HOLD_IS_DEMAND` | Tentativa de operação inválida em hold de demanda |
| `HOLD_EXPIRED` | Hold expirou antes da operação |
| `REASON_REQUIRED` | Motivo obrigatório para ajuste de estoque |
| `QUANT_NOT_FOUND` | Quant não encontrado na posição/SKU |
| `CONCURRENT_MODIFICATION` | Conflito de concorrência (optimistic locking) |

**Guia:** [stockman.md](../guides/stockman.md)

---

## CraftError (Craftsman)

**Arquivo:** `packages/craftsman/shopman/craftsman/exceptions.py`
**Base:** `BaseError`

| Código | Quando ocorre |
|--------|--------------|
| `INVALID_QUANTITY` | Quantidade ≤ 0 para work order |
| `TERMINAL_STATUS` | Work order já em estado terminal (DONE/VOID) |
| `VOID_FROM_DONE` | Tentativa de anular work order já concluída |
| `STALE_REVISION` | Conflito de concorrência — revisão esperada não bate |
| `BOM_CYCLE` | Ciclo detectado na árvore BOM de receita |
| `RECIPE_NOT_FOUND` | Receita não encontrada |
| `WORK_ORDER_NOT_FOUND` | Work order não encontrada |

**Subclasse:** `StaleRevision(CraftError)` — levantada com `code="STALE_REVISION"` automaticamente, recebe `(order, expected_rev)`.

**Subclasse:** `RecipeBookError(CraftError)` — inventário de receitas (`RecipeEntry`/`RecipeVersion`, [RECIPE-INVENTORY-PLAN](../plans/RECIPE-INVENTORY-PLAN.md) §5). `data["field"]` carrega o caminho do campo ofensor na fórmula (`items[2].sku`, `parts[0]`).

| Código | Quando ocorre | Na API do backstage (`/api/v1/backstage/recipes/*`) |
|--------|--------------|------|
| `FORMULA_INVALID` | Fórmula fora do schema, rendimento/unidade inválidos, ou a ficha recusou uma linha ao publicar (unidade do cadastro) | 400 com `field` |
| `ITEM_WITHOUT_SKU` | Ingrediente ou parte sem insumo associado ao publicar | 400 com `field` |
| `ENTRY_WITHOUT_SKU` | Receita sem SKU de saída ao publicar | 400 com `field=output_sku` |
| `PART_WITHOUT_FORMULA` | Parte cuja receita não tem versão publicada | 400 com `field` |
| `PART_EXCEEDS_BASE` | Parte leva mais de um ingrediente do que a base declara | 400 com `field` |
| `ANCHOR_EMPTY` | Âncora soma zero; não há como padronizar | 400 com `field=anchor` |
| `VERSION_NOT_DRAFT` | Editar ou publicar versão que não é rascunho | 409 com `error.code=version_not_draft` |
| `ENTRY_ARCHIVED` | Criar versão ou publicar em receita arquivada | 409 com `error.code=entry_archived` |

A tradução vive em `shopman/backstage/services/recipe_book.py` (`RecipeBookServiceError`). Receita ou versão inexistente é 404; leitura por IA sem credencial é 503 e provedor em falha é 502 (o mesmo mapeamento do assist do catálogo).

**Guia:** [craftsman.md](../guides/craftsman.md)

---

## CustomerError (Guestman)

**Arquivo:** `packages/guestman/shopman/guestman/exceptions.py`
**Base:** `BaseError`

| Código | Quando ocorre |
|--------|--------------|
| `CUSTOMER_NOT_FOUND` | Cliente não encontrado pelo ref |
| `ADDRESS_NOT_FOUND` | Endereço não encontrado para o cliente |
| `DUPLICATE_CONTACT` | Contato (telefone/email) já associado a outro cliente |
| `INVALID_PHONE` | Telefone não passou na validação (formato E.164) |
| `MERGE_DENIED` | Merge de clientes negado (requer validação prévia) |
| `CONSENT_NOT_FOUND` | Registro de consentimento não encontrado |
| `LOYALTY_NOT_ENROLLED` | Cliente não está inscrito no programa de fidelidade |
| `LOYALTY_INSUFFICIENT_POINTS` | Pontos insuficientes para resgate |

**Guia:** [guestman.md](../guides/guestman.md)

---

## AuthError (Doorman)

**Arquivo:** `packages/doorman/shopman/doorman/exceptions.py`
**Base:** `BaseError`

| Código | Quando ocorre |
|--------|--------------|
| `TOKEN_INVALID` | Bridge token inválido, expirado ou já usado |
| `CODE_INVALID` | Código de verificação incorreto ou expirado |
| `RATE_LIMIT` | Limite de taxa excedido (muitos códigos/tentativas) |
| `GATE_FAILED` | Gate genérico falhou (via `GateError`) |

**Subclasse:** `GateError(AuthError)` — levantada com `gate_name` e `code="GATE_FAILED"`. Usada pelos gates individuais.

**Guia:** [doorman.md](../guides/doorman.md)

---

## PaymentError (Payman)

**Arquivo:** `packages/payman/shopman/payman/exceptions.py`
**Base:** `Exception` (independente de `BaseError`)
**Construtor:** `__init__(code, message, context=None)`
**Serialização:** `.as_dict()` → `{"code": "...", "message": "...", "context": {...}}`

| Código | Quando ocorre |
|--------|--------------|
| `INTENT_NOT_FOUND` | Intent não encontrado pelo ref |
| `INVALID_TRANSITION` | Transição de status não permitida |
| `ALREADY_CAPTURED` | Intent já foi capturado |
| `ALREADY_REFUNDED` | Intent já foi totalmente reembolsado |
| `AMOUNT_EXCEEDS_CAPTURED` | Refund maior que o capturado |
| `CAPTURE_EXCEEDS_AUTHORIZED` | Capture maior que o autorizado |
| `INTENT_EXPIRED` | Intent expirado |

---

## OrderError (Orderman)

**Arquivo:** `packages/orderman/shopman/orderman/exceptions.py`
**Base:** `Exception` (independente de `BaseError`)
**Construtor:** `__init__(code, message, context=None)`

### ValidationError

| Código | Quando ocorre |
|--------|--------------|
| `missing_sku` | SKU ausente no item |
| `invalid_qty` | Quantidade inválida |
| `unsupported_op` | Operação não suportada pelo canal |

### SessionError

| Código | Quando ocorre |
|--------|--------------|
| `not_found` | Sessão não encontrada |
| `already_committed` | Sessão já foi commitada |
| `already_abandoned` | Sessão já foi abandonada |
| `locked` | Sessão está travada para edição |

### CommitError

| Código | Quando ocorre |
|--------|--------------|
| `blocking_issues` | Issues bloqueantes não resolvidas |
| `stale_checks` | Checks de pré-commit desatualizados |
| `missing_check` | Check obrigatório não executado |
| `hold_expired` | Hold de estoque expirou durante commit |
| `already_committed` | Sessão já commitada |

### DirectiveError

| Código | Quando ocorre |
|--------|--------------|
| `no_handler` | Nenhum handler registrado para o tópico |
| `handler_failed` | Handler falhou durante execução |

### IssueResolveError

| Código | Quando ocorre |
|--------|--------------|
| `issue_not_found` | Issue não encontrada na sessão |
| `no_resolver` | Nenhum resolver registrado para o tipo |
| `action_not_found` | Ação de resolução não encontrada |
| `stale_action` | Ação de resolução desatualizada |
| `resolver_error` | Erro durante resolução |

### IdempotencyError

| Código | Quando ocorre |
|--------|--------------|
| `in_progress` | Operação idempotente já em execução |
| `conflict` | Conflito de chave de idempotência |

### IdempotencyCacheHit

Não é erro — controle de fluxo. Contém `cached_response` com resultado anterior.

### InvalidTransition

| Código | Quando ocorre |
|--------|--------------|
| `invalid_transition` | Transição de status não permitida |
| `terminal_status` | Pedido em status terminal, não aceita transições |

**Guia:** [orderman.md](../guides/orderman.md)

---

## RefError (Ordering — Refs)

**Arquivo:** `packages/orderman/shopman/ordering/contrib/refs/exceptions.py`
**Base:** `Exception`

| Exceção | Quando ocorre |
|---------|--------------|
| `RefTypeNotFound(slug)` | Tipo de referência não registrado |
| `RefScopeInvalid(missing_keys, ref_type_slug)` | Chaves de escopo ausentes na referência |
| `RefConflict(ref_type_slug, value, existing_target_kind, existing_target_id)` | Referência já aponta para outro alvo |

---

## Padrão de Uso

```python
from shopman.stockman.exceptions import StockError

try:
    stock.hold(sku="PAO-FR", qty=10)
except StockError as e:
    if e.code == "INSUFFICIENT_AVAILABLE":
        print(f"Disponível: {e.available}, Pedido: {e.requested}")
    print(e.as_dict())
    # {"code": "INSUFFICIENT_AVAILABLE", "message": "...", "available": 5, "requested": 10}
```
