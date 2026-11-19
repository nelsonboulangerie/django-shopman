# Stockman — Estoque e Reservas

## Visão Geral

O app `shopman.stockman` é um ledger imutável de estoque com coordenadas espaço-tempo, sistema de holds (reservas) e planejamento de produção. A interface pública unificada é a classe `StockService` (exposta como `stock`).

**Conceito central:** Estoque existe numa coordenada `(position, target_date, batch)`. `target_date=None` significa estoque físico (agora); datas futuras representam produção planejada.

```python
from shopman.stockman import stock, StockError
```

## Conceitos

### Coordenadas Espaço-Tempo
Todo estoque vive numa coordenada tridimensional:
- **Posição** (`Position`) — Onde: vitrine, depósito, forno
- **Data-alvo** (`target_date`) — Quando: None=agora, futuro=planejado
- **Lote** (`batch`) — Rastreabilidade: "CRO-20260319-M"

### Quant
Cache de quantidade numa coordenada. O campo `_quantity` é O(1) — atualizado atomicamente por cada Move.

### Move (Imutável)
Registro de alteração de quantidade. **Nunca** se atualiza ou deleta um Move. Correções são novos Moves com delta inverso.

### Hold (Reserva)
Reserva de quantidade com ciclo de vida: `PENDING → CONFIRMED → FULFILLED` ou `RELEASED`.

Dois modos:
- **Reserva** (`quant != None`) — estoque existe, quantidade reservada
- **Demanda** (`quant == None`) — estoque não existe, pré-encomenda aceita

### Política de Disponibilidade
Definida no Product (`shopman.offerman`), respeitada pelo Stockman:
- `stock_only` — só estoque físico
- `planned_ok` — aceita produção planejada
- `demand_ok` — aceita holds sem estoque (demanda)

### Validade e margem
O saldo conta para uma data-alvo enquanto estiver válido nela. A validade tem duas fontes, e as duas valem juntas (a mais restritiva ganha):
- **Lote datado** — `Batch.expiry_date`.
- **Saldo sem lote** — validade implícita: dia de produção + `shelf_life_days` do produto. É o caso de toda fornada planejada (`Quant.target_date` preenchido) e do que está em produção.

`expiry_margin_days` (parâmetro de `quants_eligible_for`, das leituras de disponibilidade e do `hold`) pede que o saldo ainda tenha N dias de validade DEPOIS da data-alvo, e alcança as duas fontes. A fornada planejada para a própria data-alvo sempre conta, com qualquer validade. Margem 0 (o default) é "válido na data basta".

O "dia de produção" de um saldo físico é o do lote dele (`Batch.production_date`), quando o lote o declara; o `created_at` do saldo é só o dia em que ele entrou no estoque. Com margem, o saldo físico de um lote é julgado pela data de produção do lote, pela mesma régua da fornada planejada: o lote de sexta fechado na quinta à noite conta para sexta, e o lote de quinta não. A janela histórica sobre o `created_at` (sem margem) continua valendo para ele. Lote nomeado sem `Batch`, ou com `Batch` sem data de produção, não declara nada: a margem cai sobre o `created_at`. A consulta do escopo passa os lotes ao `filter_valid_quants(lots=...)`; a leitura em lote passa `lot_production_date` ao `is_valid_for_date`, sem consulta a mais.

`availability_for_skus_on_dates` aceita `expiry_margin_days_by_date` para quem lê, numa varredura só, datas que pedem margens diferentes. O orquestrador usa isso para a regra da casa: sobra de hoje não lastreia encomenda (`shopman/shop/policies/promise_expiry_margin.py`).

## Modelos

### Position

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `ref` | SlugField(unique) | Identificador ("vitrine", "deposito") |
| `name` | CharField(100) | Nome legível |
| `kind` | CharField(choices) | PHYSICAL, PROCESS, VIRTUAL |
| `is_saleable` | BooleanField | Estoque aqui pode ser vendido? |
| `is_default` | BooleanField | Posição padrão |
| `metadata` | JSONField | Dados customizados |

**PositionKind:**
- `PHYSICAL` — Local real (Vitrine, Depósito)
- `PROCESS` — Etapa de produção (Forno, Fermentação)
- `VIRTUAL` — Conceito contábil (Perdas, Ajustes)

### Quant

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `sku` | CharField(100) | SKU do produto |
| `position` | FK(Position, null, PROTECT) | Onde |
| `target_date` | DateField(null) | Quando (null=físico) |
| `batch` | CharField(50) | Referência de lote |
| `_quantity` | DecimalField(12,3) | Cache de quantidade (O(1)) |
| `metadata` | JSONField | Dados customizados |

**Constraint único:** `(sku, position, target_date, batch)`

**Propriedades:**
- `quantity` — Retorna `_quantity`
- `held` — Soma de holds ativos (não expirados)
- `available` — `quantity - held`
- `is_future` — `target_date > today`

**Manager:**
- `Quant.objects.for_sku(sku)` — Filtra por SKU
- `Quant.objects.physical()` — Só estoque físico
- `Quant.objects.planned()` — Só planejado (futuro)
- `Quant.objects.at_position(position)` — Filtra por posição

### Move (Imutável)

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `quant` | FK(Quant, PROTECT) | Coordenada alterada |
| `delta` | DecimalField(12,3) | +n=entrada, -n=saída |
| `reason` | CharField(255) | Motivo obrigatório |
| `metadata` | JSONField | Dados extras |
| `timestamp` | DateTimeField | Quando |
| `user` | FK(User, SET_NULL, null) | Quem |

**Imutabilidade:** `save()` rejeita update (pk existente), `delete()` sempre rejeita.

### Hold

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `sku` | CharField(100) | SKU do produto |
| `quant` | FK(Quant, PROTECT, null) | Estoque vinculado (None=demanda) |
| `quantity` | DecimalField(12,3) | Quantidade reservada |
| `target_date` | DateField | Data desejada |
| `status` | CharField(choices) | PENDING, CONFIRMED, FULFILLED, RELEASED |
| `expires_at` | DateTimeField(null) | Expiração opcional |
| `resolved_at` | DateTimeField(null) | Quando resolvido |
| `metadata` | JSONField | Dados extras |

**Propriedades:** `is_demand`, `is_reservation`, `is_active`, `is_expired`, `hold_id` ("hold:{pk}")

### Batch

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `ref` | CharField(50, unique) | Identificador do lote |
| `sku` | CharField(100) | SKU do produto |
| `production_date` | DateField(null) | Data de produção |
| `expiry_date` | DateField(null) | Data de validade |
| `supplier` | CharField(200) | Fornecedor |
| `notes` | TextField | Observações |

**Lote, sem lote e o marcador de produção.** `Quant.batch` é uma referência textual, e três coisas diferentes moram nela:

- vazio: saldo sem lote (o planejado, por exemplo);
- o ref de um `Batch`: lote de verdade, com validade e grau de qualidade;
- `"started"` num saldo com `target_date`: o MARCADOR do que já entrou em produção (`services.scope.STARTED_BATCH`, escrito pela ponte do Craftsman). Não é lote e não existe `Batch` com esse ref.

O canal que lê com lista de graus (`allowed_quality_grade_refs`) só aceita lote de verdade com grau permitido: lote nomeado sem `Batch`, ou com `Batch` sem grau, fica de fora, na leitura, na reserva e na baixa. O marcador de produção passa como o saldo sem lote (`scope.is_in_production`), porque ainda não foi inspecionado; no fechamento, o `realize` só leva a reserva para o pão cujo grau a lista dela aceita.

### StockAlert

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `sku` | CharField(100) | SKU do produto |
| `position` | FK(Position, null) | Posição (null=todas) |
| `min_quantity` | DecimalField(12,3) | Limite mínimo |
| `is_active` | BooleanField | Ativo |
| `last_triggered_at` | DateTimeField(null) | Último disparo |

## Serviços

A classe `StockService` combina 4 mixins: `StockQueries`, `StockMovements`, `StockHolds`, `StockPlanning`.

### Consultas (StockQueries)

```python
from shopman.stockman import stock

# Quantidade disponível (física)
disponivel = stock.available("CROISSANT")

# Disponível numa posição e data
disponivel = stock.available("CROISSANT", target_date=date.today(), position=vitrine)

# Demanda pendente (holds sem estoque)
demanda = stock.demand("CROISSANT", target_date=date.today())

# Quantidade comprometida (holds ativos)
comprometido = stock.committed("CROISSANT")

# Buscar quant específico
quant = stock.get_quant("CROISSANT", position=vitrine)

# Listar quants
quants = stock.list_quants(sku="CROISSANT", include_future=True)
```

### Movimentações (StockMovements)

```python
# Entrada de estoque
quant = stock.receive(
    quantity=Decimal("100"),
    sku="CROISSANT",
    position=vitrine,
    reason="Produção manhã",
    user=usuario,
)

# Saída de estoque
move = stock.issue(
    quantity=Decimal("5"),
    quant=quant,
    reason="Venda #123",
    user=usuario,
)

# Entrada num quant já localizado (espelho do issue; devolve o Move):
# a devolução no mesmo saldo de onde a venda saiu, o lote versionado do QC
move = stock.receive_into(
    quantity=Decimal("2"),
    quant=quant,
    reason="Cancelamento antes do preparo",
    kind=Move.Kind.RETURN,
)

# Ajuste de inventário (contagem física)
move = stock.adjust(
    quant=quant,
    new_quantity=Decimal("93"),
    reason="Contagem física",
    user=usuario,
)
```

### Holds (StockHolds)

```python
# Criar hold (reserva ou demanda)
hold_id = stock.hold(
    quantity=Decimal("5"),
    product=croissant,  # Product com availability_policy
    target_date=date.today(),
    expires_at=timezone.now() + timedelta(minutes=30),
)
# → "hold:42"

# Confirmar (PENDING → CONFIRMED)
hold = stock.confirm(hold_id)

# Efetivar (CONFIRMED → FULFILLED, cria Move negativo)
move = stock.fulfill(hold_id, user=usuario)

# Liberar (PENDING|CONFIRMED → RELEASED)
hold = stock.release(hold_id, reason="Pedido cancelado")

# Liberar todos expirados (batch processing)
liberados = stock.release_expired()
```

**Entrega antes de o lote fechar.** `fulfill` baixa do quant em que a reserva está, e ele pode ainda ser saldo de produção (planejado, ou `batch="started"`): o balcão entrega pão de um lote aberto, o operador aceita um pedido já pago. A baixa sai na hora, e a entrega segue o lote: quando a contribuição dele muda de saldo, a entrega muda junto, num par de `Move` que soma zero, no `kind` da entrega, e a reserva `fulfilled` passa a apontar para o saldo que a pagou. Quem faz isso é o `realize`, do saldo de produção para o lote, e `StockPlanning.carry_deliveries(from_quant, to_quant, limit=...)`, que a ponte do Craftsman chama no início do lote (do planejado para o que está em produção). **A conta da entrega é chaveada em `Move.metadata`**, nunca no `reason`: `{"delivery": {"hold_id": "hold:N", "entry": "fulfilled" | "carried_out" | "carried_in" | "returned"}}` (`services/holds.py::delivery_entry`; inventário em `docs/reference/data-schemas.md`). O que cada saldo ainda deve é o líquido dessa conta, por reserva, lido do ledger, sem contador; a frase do `Move` (`Entrega hold:N`, `Entrega hold:N segue com o lote`) é texto para gente e pode ser reescrita sem mudar o estoque. `Move` sem a chave não é entrega conhecida, tenha a frase que tiver. Resultado: lote de 10 com 4 já entregues fecha com `+10` de produção e `-4` de venda no lote, 6 para vender. As pernas `MAKE` não mudam, e a venda continua contada uma vez só. Entrega maior que o realizado abate até zerar o lote, e o resto continua devido ao saldo de produção: nunca vira saldo negativo; a ponte, em modo `fail_closed`, recusa o fechamento (#2724).

### Planejamento (StockPlanning)

```python
amanha = date.today() + timedelta(days=1)

# Planejar produção futura
quant = stock.plan(
    quantity=Decimal("100"),
    product=croissant,
    target_date=amanha,
    reason="Produção planejada",
)

# Replanejar (ajustar quantidade)
quant = stock.replan(
    quantity=Decimal("110"),
    product=croissant,
    target_date=amanha,
    reason="Demanda aumentou",
)

# Realizar produção (planejado → físico)
quant_fisico = stock.realize(
    product=croissant,
    target_date=amanha,
    actual_quantity=Decimal("93"),
    to_position=vitrine,
    reason="Produção realizada",
)
# → Transfere holds FIFO do planejado para o físico
# → Emite sinal holds_materialized

# Reassentar reservas entre saldos planejados irmãos (mesmo SKU e data)
movidas = stock.settle_holds([quant_em_producao, quant_planejado])
```

`realize` só materializa as reservas ancoradas no quant de onde o lote sai (mais a demanda sem saldo da data). Por isso, quando a QUANTIDADE do plano muda de quant (o lote entra em produção e vai para o quant `batch="started"`, um lote é cancelado, o plano encolhe), a reserva tem de mudar junto: é o que `settle_holds` faz. Os quants vêm na ordem em que são servidos (o lote aberto primeiro); as reservas ativas são percorridas na ordem de atendimento do `realize` (`metadata.priority`, depois FIFO) e cada uma vai, inteira, para o primeiro quant em que cabe. A que não cabe em nenhum fica onde está, sem lastro. Não muda quantidade, prazo nem estado. Quem chama é a ponte do Craftsman (`craftsman/contrib/stockman`), no início, no ajuste e no cancelamento do lote.

### Alertas

```python
from shopman.stockman.services.alerts import check_alerts

# Verificar alertas (todos os SKUs)
alertas = check_alerts()

# Verificar alertas de um SKU
alertas = check_alerts(sku="CROISSANT")
```

## Protocols

### SkuValidator

Interface para validar SKUs contra catálogo externo (ex: Offerman).

```python
class SkuValidator(Protocol):
    def validate_sku(self, sku: str) -> SkuValidationResult: ...
    def validate_skus(self, skus: list[str]) -> dict[str, SkuValidationResult]: ...
    def get_sku_info(self, sku: str) -> SkuInfo | None: ...
    def search_skus(self, query: str, limit=20) -> list[SkuInfo]: ...
```

### ProductionBackend

Interface para solicitar produção ao Craftsman.

```python
class ProductionBackend(Protocol):
    def request_production(self, request: ProductionRequest) -> ProductionResult: ...
    def check_status(self, request_id: str) -> ProductionStatus | None: ...
    def cancel_request(self, request_id: str, reason: str) -> ProductionResult: ...
    def list_pending(self, sku: str | None = None) -> list[ProductionStatus]: ...
```

## Configuração

Chave Django settings: `STOCKMAN`

| Setting | Default | Descrição |
|---------|---------|-----------|
| `SKU_VALIDATOR` | `""` | Dotted path para validador de SKU |
| `HOLD_TTL_MINUTES` | `0` | TTL padrão de holds (0=sem expiração) |
| `EXPIRED_BATCH_SIZE` | `200` | Batch para release_expired |
| `VALIDATE_INPUT_SKUS` | `True` | Validar SKUs antes de operações |

## Integridade de `_quantity`

### Por que é cache

`Quant._quantity` é um campo **denormalizado** — ele armazena o resultado de
`Σ(moves.delta)` para que consultas de disponibilidade sejam O(1) em vez de
O(N moves). Performance essencial em catálogos com muitos produtos.

### Por que pode divergir

Três vetores conhecidos de divergência silenciosa:

| Vetor | Exemplo | Risco |
|-------|---------|-------|
| Queryset bypass | `Quant.objects.filter(...).update(_quantity=X)` | Alto — skipa Move ledger completamente |
| Seed/fixture direto | `Quant.objects.create(_quantity=50)` sem Moves | Médio — inofensivo em teste, perigoso em seed prod |
| SQL direto | `UPDATE stockman_quant SET _quantity=X` via psql/migração | Baixo — requer acesso ao banco |

### Como detectar

```bash
# Dry-run: lista divergências sem corrigir (exit 1 se há divergência)
python manage.py recompute_quant_quantities --dry-run

# Filtrar por SKU
python manage.py recompute_quant_quantities --dry-run --sku croissant
```

Output (quando há divergência):
```
      pk  sku                             position      current      computed        delta
--------  ----------------------------  ------------  -----------  -----------  -----------
      42  croissant                     1                   50.000      100.000      +50.000
```

### Como corrigir

```bash
# Aplica recalculate() nos divergentes — Move ledger ganha
python manage.py recompute_quant_quantities --apply
```

`recalculate()` logga `ERROR quant.quantity_mismatch` com detalhes estruturados
(pickável por Sentry/SIEM):

```json
{"pk": 42, "sku": "croissant", "position": "1", "current": 50.0, "computed": 100.0, "delta": 50.0}
```

### Política: nunca bypassar o Move ledger

**REGRA**: `Quant._quantity` é escrito apenas por `Move.save()`. Qualquer outro
código que precise "ajustar" estoque deve criar um `Move`.

```python
# ❌ NUNCA — bypassa Move ledger, quebra invariante
Quant.objects.filter(sku='croissant').update(_quantity=100)

# ✅ SEMPRE — cria Move, atualiza cache atomicamente
stock.adjust('croissant', vitrine, Decimal('100'), reason='Ajuste de inventário')
```

A tentativa de uso direto de `.update(_quantity=...)` levanta `ValueError`
explicativo. O escape hatch `_allow_quantity_update=True` existe apenas para
`Move.save()` e `recompute_quant_quantities --apply` (internos do sistema).

### Cron recomendado

```cron
0 3 * * * /app/manage.py recompute_quant_quantities --dry-run >> /var/log/shopman/quant-audit.log 2>&1
```

Se houver divergência: corrigir com `--apply` e investigar a causa raiz.

---

## Exceções

`StockError` com códigos estruturados:
- `INSUFFICIENT_AVAILABLE` — Quantidade indisponível
- `INSUFFICIENT_QUANTITY` — Estoque insuficiente para saída
- `INVALID_HOLD` — Hold não encontrado
- `INVALID_STATUS` — Transição de status inválida
- `INVALID_QUANTITY` — Quantidade ≤ 0
- `HOLD_IS_DEMAND` — Não pode fulfill hold de demanda
- `HOLD_EXPIRED` — Hold expirado
- `REASON_REQUIRED` — Motivo obrigatório
- `QUANT_NOT_FOUND` — Quant não encontrado

