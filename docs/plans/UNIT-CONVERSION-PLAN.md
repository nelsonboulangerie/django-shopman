# UNIT-CONVERSION-PLAN — conversão de unidade como cidadã de primeira classe

> **Status:** 🟢 Fases 0 a 4 **implementadas**; Fases 5 e 6 seguem abertas (dependem,
> respectivamente, do recebimento do Buyman e dos XMLs de NF-e do dono).
> Decisão que o rege:
> [ADR-024](../decisions/adr-024-material-unit-base-and-purchase.md) (Aceita na
> direção, dono, 19/08/2026) e [ADR-023](../decisions/adr-023-cost-live-and-frozen.md)
> (o custo congela).
> **Pedido do dono (19/08):** *"o processo de conversão de unidades … deve ser um
> cidadão de primeiríssima classe … super simples, super robusto, super elegante!
> Flexível, mas à prova de falhas, sem gambiarra."*

## O problema em uma frase

A padaria fala três vocabulários ao mesmo tempo — o que ela **compra** (saco, caixa,
fardo, cartela), o que ela **conta fácil** (ovo, limão, pacote) e o que ela **mede na
verdade** (kg, l, un) — e hoje o sistema finge que existe uma unidade só, por insumo,
servindo à ficha técnica, ao estoque e ao dinheiro ao mesmo tempo.

**A física já está triplicada no código**, o que prova que o assunto não tem dono:

| Onde | Vocabulário |
|---|---|
| `packages/buyman/…/models/material.py` (`Material.Unit`) | `un`, `kg`, `g`, `l`, `ml` |
| `packages/craftsman/…/models/recipe.py` (`RecipeItem.Unit` + `RECIPE_ITEM_UNIT_ALIASES`) | `un`, `kg`, `g`, `mg`, `L`, `ml` (+ 11 apelidos) |
| `shopman/shop/services/nutrition_from_recipe.py` (`MASS_UNIT_TO_GRAMS`, `VOLUME_UNIT_TO_ML`) | `kg`/`g`/`mg`, `L`/`ml` |
| `packages/offerman/…/models/product.py` (`Product.unit`) | texto livre, `help_text="un, kg, lt, etc."` |

Três tabelas de conversão e um campo livre para a mesma pergunta.

## Fronteiras — quem é dono de quê

| Pacote | Papel nesta frente |
|---|---|
| **`shopman-utils`** | **A física.** Tabela fechada em código (kg↔g↔mg, l↔ml, dz↔un) + `convert()`. Sem banco, sem tela. Todos os cores já importam `shopman.utils`. |
| **`buyman`** | **O item master.** `Material.unit` é a unidade-**base**; a tabela editável de conversões (convencionada e aproximada) é dele; o custo lança pela conversão. |
| **`craftsman`** | **A ficha.** Continua exigindo igualdade estrita com a base (`RecipeItem.clean` não muda). Ganha a **anotação derivada** para o preparo. |
| **`stockman`** | **O livro.** Conta na base, e só nela. Ganha o **carimbo** de aproximação no `Move.metadata` (JSONField que já existe — sem migração no Core). |
| **`backstage`** | **A tela.** `MiseEnPlaceLineProjection` mostra `300 g · ≈ 6 ovos`; o `≈` some quando o número é exato. |
| **orquestrador** | Nada novo: já compõe catálogo e validador. A tabela é do Buyman porque o insumo é dele. |

## Fases

Cada fase é útil sozinha e nenhuma exige a seguinte.

### Fase 0 — a base fica honesta (dado, sem código) · ✅ concluída

- ✅ `OVOS`, `LIMAO`, `CANELA` e `ALECRIM` em base `kg` — todos são **pesados**, que é o
  que a R1 pergunta. `0.300` de ovo significa 300 g, como o dono confirmou. O seed passa
  `unit` **explícito** na criação do `RecipeItem` em vez de cair no default, e o teste do
  seed prova que toda ficha de insumo pesado bate com a base (`full_clean()` em cada
  linha).
- ✅ Os líquidos (`AGUA-FILTRADA`, `LEITE`, `AZEITE`) passam a falar `L` na ficha, na
  mesma base `l` do insumo. Destravou porque o perfil ganhou `density_g_per_ml` — a
  ponte volume→massa que a nutrição precisa
  (`nutrition_from_recipe.py::_item_quantity_grams`). Sem a densidade o item continua
  ficando **de fora** da soma, que é o comportamento certo: melhor rótulo incompleto do
  que rótulo inventado.

### Fase 1 — a física, num lugar só (`shopman.utils.units`) · ✅ concluída

- Tabela **fechada em código**: massa (kg/g/mg), volume (l/ml), contagem (dz/un).
  Não é editável, não tem tela, não tem migração — constante de física não é
  configuração (ADR-024 §1).
- `convert(quantity, from_unit, to_unit) -> Decimal` que **levanta** quando não existe
  caminho exato (regra R4: recusa, não adivinha), e `normalize(unit)` com os apelidos
  que hoje vivem no Craftsman.
- **Consumidores imediatos** (é o que tira as cópias de circulação):
  `nutrition_from_recipe` passa a usar a tabela; `RECIPE_ITEM_UNIT_ALIASES` passa a
  delegar; a densidade dos líquidos entra no perfil do insumo e fecha a Fase 0.
- Testes: ida e volta sem perda, precisão decimal, e **recusa** de par sem caminho
  (kg→un levanta; nunca devolve palpite).
- **Como ficou:** `packages/utils/shopman/utils/units.py` — `normalize`, `is_known`,
  `dimension`, `same_dimension`, `convert` e `UnitError` (códigos `unknown_unit`,
  `incompatible_units`, `invalid_quantity`). Fatores são **inteiros na menor unidade da
  dimensão** (mg, ml, un), então toda conversão é divisão exata de inteiros em `Decimal`.
  O Craftsman guarda o litro como `"L"` (valor da choice, e o que está no banco) e a
  física fala `"l"`: sobrou uma linha de **grafia** em `recipe.py`, não uma segunda
  tabela. `RECIPE_ITEM_UNIT_ALIASES` foi apagada; `MASS_UNIT_TO_GRAMS`/`VOLUME_UNIT_TO_ML`
  também.

### Fase 2 — `MaterialConversion` no Buyman (a tabela editável)

- Campos: `material`, `supplier` (nulo = vale para qualquer fornecedor), `label`
  ("saco 25 kg", "cartela", "ovo"), `to_base_factor` (`Decimal`, > 0), `kind`
  (`conventional` | `approximate`), `is_active`.
- Constraints no banco: fator positivo; `unique(material, supplier, label)`.
- Admin: inline no insumo, no mesmo molde do custo. **Nenhum leitor ainda** — item
  master primeiro, exatamente como foi a Fase 1 do Buyman.
- Testes: fator zero/negativo recusado; duas conversões com o mesmo rótulo recusadas;
  `kind=approximate` nunca é lido como exata.

### Fase 3 — o custo lança pela conversão · **é esta que não pode atrasar**

- `SupplierMaterialCost` ganha `conversion` (FK opcional para `MaterialConversion`);
  `cost_q` passa a ser "centavos por unidade de compra" e o **custo por unidade-base
  vira propriedade derivada** em `Decimal`, arredondada só na ponta.
- O operador digita `saco` · `25` · `R$ 180,00` — três números impressos na nota. A
  divisão é da máquina (regra R2).
- Custo cuja unidade ≠ base **sem conversão declarada**: recusa com mensagem dizendo o
  que cadastrar (regra R4).
- **Ordem que evita migrar dado de custo duas vezes:** hoje existem **zero** linhas de
  `SupplierMaterialCost` (o seed não cria nenhuma). Esta fase tem de entrar **antes da
  primeira linha de custo real ser digitada** — depois dela, é migração de dado de
  dinheiro.

### Fase 4 — a anotação de preparo (requisito do dono)

- `MiseEnPlaceLineProjection` (`shopman/backstage/projections/production.py`) ganha a
  anotação derivada: `300 g · ≈ 6 ovos`, calculada na hora do fator `approximate` do
  insumo. **Nunca gravada** — corrigir o fator (ovo jumbo, 60 g) atualiza toda lista de
  picking sozinho.
- O `≈` **só** aparece quando o número passou por fator aproximado. Número exato não
  ganha enfeite.
- Depende só da Fase 2.

### Fase 5 — a entrada carimbada (recebimento)

- O recebimento converte para a base pela conversão declarada e grava
  `Move.metadata["converted_via"] = {"label", "factor", "approximate"}` — o JSONField já
  existe, o Core não muda de forma.
- Saldo que passou por aproximação aparece como `≈` na tela; o custo derivado dali é
  **estimado** e nunca vira custo congelado sem o rótulo (ADR-023).
- Casa com a **Fase 3 do BUYMAN-PROCUREMENT-PLAN** (recebimento → `stock.receive` com
  `kind=BUY`), que é quando `Move.Kind.BUY` finalmente ganha um emissor.

### Fase 6 — a NF-e de entrada preenche a tabela sozinha

- Ingestão de XML **por arquivo** (dado externo entra por arquivo — convenção da casa):
  `uCom`/`qCom`/`vUnCom` + `uTrib`/`qTrib`/`vUnTrib` viram, respectivamente, a linha de
  conversão (`fator = qTrib ÷ qCom`) e o custo por unidade-base (`vUnTrib`).
- **Curadoria do dono**: nada entra sem revisão; a nota **sugere**, o dono confirma.
- Depende das Fases 2 e 3 e do experimento das 5–10 notas descrito na
  [ADR-024 §Evidência 4](../decisions/adr-024-material-unit-base-and-purchase.md).

## Ordem recomendada

```
Fase 0 (dado) ─┬─► Fase 1 (física em utils) ─► Fase 2 (tabela) ─┬─► Fase 3 (custo) ─► Fase 6 (NF-e)
               │                                                └─► Fase 4 (anotação)
               └─────────────────────────────────────────────────► Fase 5 (recebimento, com Buyman F3)
```

Regra de ouro da ordem: **a Fase 3 tem de acontecer antes de existir custo real
cadastrado.** Todo o resto tolera atraso; dinheiro já digitado, não.

## Não-objetivos (para não virar projeto grande)

- **Não** converter unidade dentro da receita: o Craftsman continua estrito, por design.
- **Não** guardar duas unidades no estoque: um insumo, uma base, um saldo.
- **Não** deduzir fator por heurística: sem declaração, o gesto para (R4).
- **Não** mexer em `Product.unit` do Offerman nesta frente: produto vendável é outro
  domínio, e a arrumação do campo livre é faxina separada.

## Testes que cada fase deve trazer

| Fase | O teste que prova |
|---|---|
| 0 | ficha de insumo pesado bate com a base; líquido em `L` com densidade no perfil; `full_clean()` em cada linha do seed ✅ |
| 1 | ida e volta sem perda; par sem caminho **levanta** ✅ |
| 2 | fator ≤ 0 recusado; rótulo duplicado recusado; aproximada não passa por exata |
| 3 | custo por base derivado com precisão; unidade ≠ base sem conversão **recusa** |
| 4 | anotação derivada muda quando o fator muda, sem tocar na ficha |
| 5 | `Move` de entrada carrega `converted_via`; saldo aproximado sinalizado |
| 6 | XML de exemplo vira sugestão de conversão + custo, sem gravar sozinho |

## Referências

- [ADR-024](../decisions/adr-024-material-unit-base-and-purchase.md) — a decisão (três tipos de conversão, quatro regras)
- [ADR-023](../decisions/adr-023-cost-live-and-frozen.md) — o custo congela; esta frente diz em que unidade
- [BUYMAN-PROCUREMENT-PLAN](BUYMAN-PROCUREMENT-PLAN.md) — Fases 2–4 do Buyman (pedido, recebimento, reposição)
- [ADR-002](../decisions/adr-002-centavos.md) · [ADR-001](../decisions/adr-001-protocol-adapter.md)
