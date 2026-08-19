# ADR-023 — Custo: vivo para precificar, congelado no fato para contar história

**Status:** Proposto (rascunho para decisão do dono, 2026-08-19)
**Data:** 2026-08-19
**Escopo (se aceito):** `shopman/shop` (adapter de custo composto, `OFFERMAN["COST_BACKEND"]`); `packages/craftsman` (snapshot de custo no `finish`); `packages/buyman` (leitura do custo preferencial); `docs/reference/data-schemas.md`
**Não muda nada hoje:** esta ADR **não** vem com implementação. O backend de custo só é escrito **depois** que o dono responder a pergunta do fim.
**Origem:** auditoria do Buyman (2026-08-18), achado B1

---

## Contexto

A cadeia de custo da suíte são três pontas de corda sem meio:

- **Buyman escreve custo que ninguém lê.** `SupplierMaterialCost` guarda
  `cost_q` por par (fornecedor, insumo), com `is_preferred` marcando o canônico
  — e um `grep` no repositório não acha **nenhum leitor** fora do próprio admin
  (`packages/buyman/shopman/buyman/models/cost.py`).
- **Offerman tem o seam, desplugado.** `Product.reference_cost_q` e
  `Product.margin_percent` leem de `OFFERMAN["COST_BACKEND"]`
  (`packages/offerman/shopman/offerman/models/product.py:350`), e
  `config/settings.py:870` traz `"COST_BACKEND": None`. Sem provedor, as duas
  colunas se escondem no Admin — honesto, mas dormente.
- **Craftsman, o dono natural do custeio de receita, não tem uma linha de
  custo.** Nada em models, nada em services.

O `CraftingCostBackend` citado como exemplo em `offerman/conf.py` e em
`offerman/protocols/cost.py` **não existe**; era a promessa, não o código. Este
ADR troca a promessa por uma decisão, e o exemplo por um link para cá.

Escrever o backend é barato (algumas dezenas de linhas). O que **não** é barato
é escrevê-lo antes de responder a pergunta que ele decide sem querer, porque as
duas perguntas do negócio têm respostas opostas:

| Pergunta | Resposta certa |
|---|---|
| "Qual a margem deste produto **hoje**?" | custo **vivo** — custo preferencial atual × receita ativa |
| "Quanto custou a fornada de **12/08**?" (e a margem no B.I.) | custo **congelado no fato** — o que o insumo custava naquele dia |

Um backend só de custo vivo responde a primeira e **mente** na segunda: subiu a
farinha, a margem de agosto muda retroativamente. É exatamente a doença que o
projeto já vacinou uma vez.

**O precedente interno é exato.** `Batch.nonconformity_percent`
(`packages/stockman/shopman/stockman/models/batch.py:113`) é resolvido do grau
**no `finish`** e nunca reescrito por mudança de catálogo — invariante escrita em
[ADR-017 §Invariantes](adr-017-quality-as-production-outcome.md) e no comentário
do próprio campo ("não reescreve os lotes de ontem"). O custo da fornada merece o
mesmo tratamento pelo mesmo motivo: é fato, não configuração.

**O B.I. está no caminho desta decisão, não depois dela.** As Frentes A e B
([BI-DATA-FOUNDATION-PLAN](../plans/BI-DATA-FOUNDATION-PLAN.md), ADR-021)
agregam sobre fatos duráveis; margem por fornada é o próximo pedido natural. Se
o fato nascer sem custo, o B.I. vai reconstruí-lo com o custo de hoje — e o
número vai mudar sozinho a cada compra de farinha.

## Decisão proposta

1. **Dois custos, dois donos, dois nomes.**
   - **Custo vivo** = custo preferencial atual (`SupplierMaterialCost` com
     `is_preferred=True`) × BOM da receita ativa. Responde precificação e
     margem no Admin. É o que `Product.reference_cost_q` já quer.
   - **Custo congelado** = snapshot gravado **no momento da produção**, no fato
     (WorkOrder/lote). Responde história e B.I. Nunca recalculado.
2. **O backend de custo vivo mora no ORQUESTRADOR**, não no Craftsman. Ele
   precisa de receita (Craftsman) **e** de custo de insumo (Buyman) ao mesmo
   tempo, e cores não se importam (ADR-001). O lugar é
   `shopman/shop/adapters/cost.py`, ligado em `OFFERMAN["COST_BACKEND"]` — o
   mesmo desenho já usado pelo validador e pelo catálogo compostos
   (`shopman/shop/adapters/sku_validator.py`,
   `shopman/shop/adapters/catalog_backend.py`) e o que o
   [BUYMAN-PROCUREMENT-PLAN](../plans/BUYMAN-PROCUREMENT-PLAN.md) §Fronteiras já
   previa ("os adapters compostos vivem no ORQUESTRADOR").
3. **O congelamento acontece no `finish` da fornada**, junto da partição de
   qualidade que já congela (ADR-017 §7): cada linha CONSUMPTION carrega o custo
   unitário usado, e a ordem carrega o total. Vai em JSON de fato existente
   (`WorkOrderItem.meta` / `WorkOrder.meta`), sem coluna nova no Core — e a chave
   é registrada em [data-schemas.md](../reference/data-schemas.md) antes de ser
   usada.
4. **Sem custo, sem chute.** Insumo sem custo preferencial faz o custo vivo
   responder `None` (a coluna some, como hoje) e o snapshot registrar a lacuna,
   nunca zero. Zero é um número; ausência não é.
5. **Nada disso é escrito antes da resposta do dono.** Esta ADR é a decisão; o
   código vem depois dela, no plano do Buyman.

## Consequências

**Positivas**

- A tabela de custo do Buyman deixa de ser write-only e ganha o consumidor que
  o docstring prometia.
- Margem no Admin volta a existir sem que a história do B.I. fique refém do
  preço de hoje.
- O eixo de tempo do custo nasce junto com o B.I., não como migração depois.

**Negativas / custos**

- Duas noções de custo é vocabulário novo: "custo vivo" e "custo congelado"
  precisam de nome fixo na UI e nos relatórios, ou viram a mesma confusão que
  esta ADR tenta evitar.
- Snapshot em JSON de fato é barato de escrever e caro de consultar em escala;
  se o B.I. precisar de agregação pesada, a materialização é conversa dele
  (ADR-021), não do Core.
- O custo congelado só existe **de hoje em diante**: fornada antiga não ganha
  custo retroativo (mesma regra do `nonconformity_percent`).

## Alternativas consideradas

- **Só custo vivo** (o mais barato): responde precificação e mente na história.
  É a alternativa B da pergunta abaixo.
- **Só custo congelado**: obriga a inventar uma "produção fictícia" para saber a
  margem de um produto que não foi produzido hoje.
- **Histórico de preço no Buyman** (tabela de vigência por data) em vez de
  snapshot no fato: reconstrói o custo por data corretamente, mas cobra uma
  consulta temporal em todo relatório e ainda erra quando a *receita* muda.
  Snapshot no fato guarda o custo **e** a receita que valeram naquele dia.

## Pergunta ao dono (responda A ou B)

> O custo de uma fornada deve **congelar no dia em que ela foi feita** (A: dois
> custos — vivo para precificar, congelado no WorkOrder para história e B.I.),
> ou o histórico pode ser sempre recalculado com o custo de hoje (B: um custo só,
> vivo — mais simples, e a margem de agosto muda quando a farinha subir)?

## Referências

- Auditoria do Buyman (2026-08-18), achado B1
- [ADR-017](adr-017-quality-as-production-outcome.md) — precedente do dado congelado no fato
- [ADR-021](adr-021-bi-cross-suite-read-layer.md) — agregação é leitura; o fato tem dono
- [ADR-001](adr-001-protocol-adapter.md) — cores não se importam; composição no orquestrador
- [ADR-024](adr-024-material-unit-base-and-purchase.md) — a unidade em que esse custo é expresso
- [BUYMAN-PROCUREMENT-PLAN](../plans/BUYMAN-PROCUREMENT-PLAN.md) — fases e fronteiras
- `packages/offerman/shopman/offerman/protocols/cost.py`, `packages/buyman/shopman/buyman/models/cost.py`
