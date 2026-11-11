# FASE 3 — Specs prontos para aplicar (dual-run, custo, endurecimento)
> 2026-11-10 · Evidência de origin/main 057fe9105 · Documento de SPEC, não mutação

## 3.1 Dual-run do promise_for_sku (elimina a dupla autoridade — gap nº 1)

**Estado atual (medido):**
- Stockman JÁ extraiu a função pura: packages/stockman/.../services/availability.py:299
  `decision_from_availability(...)` e :361 `promise_decision_for_sku(...)` que a chama (:385).
- Shop ainda recomputa: shopman/shop/services/availability.py:686 `_stock_decision(...)`,
  chamado em :554 e :623. É a cópia duplicada que precisa morrer.

**Protocolo (4 passos, cada um verde antes do próximo):**
1. **Caracterização.** Teste que, para um corpus de (sku, qty, info, target_date), roda
   `promise_decision_for_sku` (Stockman) E `_stock_decision` (shop) e serializa ambos. Assert
   de igualdade campo a campo (pausa, demand_ok, datas, qualidade, reason_code).
2. **Shadow opt-in.** No shop/services/availability.py, trocar o corpo de `_stock_decision`
   para delegar ao Stockman, mantendo um switch `SHOPMAN_SHADOW_PROMISE=legacy|kernel` que
   devolve o cálculo antigo. Em staging, ligar shadow e comparar os dois resultados em log.
3. **Cutover.** Após zero divergência no corpus + shadow, trocar os call sites (:554, :623)
   para consumir o Stockman e apagar a cópia antiga.
4. **Remoção.** Apagar `_stock_decision` no commit seguinte (rollback = o switch do passo 2).

**Acceptance:** `grep -r '_stock_decision' shopman/shop` retorna vazio; check_decision_authority
passa; suíte de disponibilidade verde.

## 3.2 Leitor de custo (ADR-023/024 — a corda sem meio)

> **RESOLVIDO (11/11/2026, F3, opção A decidida pelo dono).** O "estado atual" abaixo
> estava defasado: o custo VIVO já existia desde 04/10 (`shop/adapters/cost.py`,
> `RecipeCostBackend`, ligado em `OFFERMAN["COST_BACKEND"]`, lido pela margem do Admin
> do Offerman e pelo "R$ de custo" da sobra no B.I.). A F3 fechou o que faltava:
> revenda (SKU sem ficha, custo do próprio `Material`), lacuna que grita com motivo
> (`CostGapExplainer` → `Product.reference_cost_gap` → selo "Sem custo" no Admin) e o
> custo CONGELADO no `finish` (`WorkOrder.meta["cost_snapshot"]`, receiver
> `shop/handlers/production_cost.py`). Sem migration. Provas:
> `shopman/shop/tests/test_cost_live_and_frozen.py` e `TestCostGap` no Offerman.

**Estado atual (medido):** COST_BACKEND existe em config/settings.py; offerman tem CostBackend
(protocols/cost.py), Product.reference_cost_q e margin_percent; mas NENHUM leitor em runtime
(grep no repo inteiro: só offerman + settings + docs). Buyman grava custo que ninguém lê.

**Spec (2 opções, decisão do dono):**
- **A — ligar:** implementar o leitor mínimo: custo VIVO = custo preferencial atual do Material
  (Buyman) × conversão de unidade (ADR-024) → Product.reference_cost_q via CostBackend; custo
  CONGELADO = snapshot no WorkOrder/Batch no momento da produção (precedente:
  Batch.nonconformity_percent é congelado).
- **B — declarar adiado:** um ADR curto dizendo 'custo fica para a Fase 2 do Buyman' e remove
  as colunas dormant do admin do Offerman (parar de fingir que existe).

**Acceptance:** ou (A) `make test-offerman` prova que reference_cost_q resolve para o Material,
ou (B) a coluna sumiu e a ADR de adiamento está aceita.

## 3.3 Endurecimento dos 3 kernels (Q3 — não negociável)

- **Stockman:** concentrar a SPEC (um módulo dono da promessa); `Quant.batch` → FK se ainda
  for CharField; limpar o sentinela de disponibilidade (is_tracked + available_qty: Decimal|None,
  sem 999999).
- **Offerman:** fechar os contratos públicos (Protocol declara tudo que a impl faz); preço com
  autoridade única (PricingBackend); apagar caminho morto de preço.
- **Doorman:** _link_verified_identifier para a bridge (adapters/customers.py) e parar de
  engolir exceção; desacoplar OTP de reuso interno de AccessLink.

**Acceptance (por kernel, os 4 gates da v6 §2):** autoridade única (busca de símbolo), gate
AST de import, SPEC concentrada, contract tests dos verbos públicos.
