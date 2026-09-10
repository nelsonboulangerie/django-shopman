# UNIT-CONVERSION-PLAN — conversão de unidade como cidadã de primeira classe

> **Status:** 🟢 **Todas as fases (0 a 6) implementadas.**
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
- ✅ Os líquidos (`AGUA-FILTRADA`, `LEITE`, `AZEITE`) passaram a falar `L` na ficha, na
  mesma base `l` do insumo. ⚠️ **Corrigido em 03/09** — eles são PESADOS na bancada, então
  a base honesta é `kg` e não `l`; ver a Calibração no fim deste documento e o
  [WP-BASE-UNIT-LIQUIDS-KG](WP-BASE-UNIT-LIQUIDS-KG.md). O que segue nesta linha é o
  raciocínio da época, e continua valendo para qualquer insumo que a casa **meça em
  volume** de verdade. Destravou porque o perfil ganhou `density_g_per_ml` — a
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

### Fase 2 — `MaterialConversion` no Buyman (a tabela editável) · ✅ concluída

- Campos: `material`, `supplier` (nulo = vale para qualquer fornecedor), `label`
  ("saco 25 kg", "cartela", "ovo"), `to_base_factor` (`Decimal`, > 0), `kind`
  (`conventional` | `approximate`), `is_active`.
- Constraints no banco: fator positivo; `unique(material, supplier, label)`.
- Admin: inline no insumo, no mesmo molde do custo. **Nenhum leitor ainda** — item
  master primeiro, exatamente como foi a Fase 1 do Buyman.
- Testes: fator zero/negativo recusado; duas conversões com o mesmo rótulo recusadas;
  `kind=approximate` nunca é lido como exata.
- **Como ficou:** `packages/buyman/shopman/buyman/models/conversion.py` + migração
  `0004_materialconversion`. A unicidade precisou de **duas** constraints parciais, não
  de uma: `NULL` não colide com `NULL` no banco, então sem a segunda (`supplier IS NULL`
  sobre `material` + `label`) "cartela" sem fornecedor podia entrar duas vezes no mesmo
  insumo e ninguém saberia qual fator valeu.

### Fase 3 — o custo lança pela conversão · ✅ concluída

- `SupplierMaterialCost` ganha `conversion` (FK opcional para `MaterialConversion`);
  `cost_q` passa a ser "centavos por unidade de compra" e o **custo por unidade-base
  vira propriedade derivada** em `Decimal`, arredondada só na ponta.
- O operador digita `saco` · `25` · `R$ 180,00` — três números impressos na nota. A
  divisão é da máquina (regra R2).
- Custo cuja unidade ≠ base **sem conversão declarada**: recusa com mensagem dizendo o
  que cadastrar (regra R4).
- **Ordem que evita migrar dado de custo duas vezes:** existiam **zero** linhas de
  `SupplierMaterialCost` (o seed não cria nenhuma), e é por isso que esta fase entrou
  agora — depois da primeira linha real, seria migração de dado de dinheiro.
- **Como ficou** (e onde o plano divergiu da realidade do código): a linha de custo
  **não redeclara unidade** — quem declara é a FK `conversion`, exatamente como a
  [ADR-024 §3](../decisions/adr-024-material-unit-base-and-purchase.md) pediu ("um
  mecanismo, não dois"). Então não existe estado "unidade ≠ base sem conversão": ou a
  FK aponta para a conversão usada, ou está vazia e a compra foi na própria base.
  A recusa da R4 materializou-se nos três guardas que **podem** acontecer com a FK
  preenchida — conversão de outro insumo, conversão que só vale para outro fornecedor,
  conversão inativa —, cada um com a mensagem dizendo o que cadastrar. A recusa por
  **rótulo não cadastrado** ("cartela" que ninguém declarou) pertence a quem digita
  rótulo, e quem digita rótulo é o recebimento: entra na Fase 5, junto com o emissor.
- Derivados no modelo: `base_factor`, `cost_per_base_unit` (`Decimal`, sem arredondar),
  `cost_per_base_unit_q` (inteiro, arredonda **só aqui**), `purchase_unit_label` e
  `is_approximate`. O Admin mostra os dois números lado a lado — "R$ 180,00 / saco 25 kg"
  e "R$ 7,20 / kg" — e o `≈` aparece quando o segundo veio de ponte aproximada.

### Fase 4 — a anotação de preparo (requisito do dono) · ✅ concluída

- `MiseEnPlaceLineProjection` (`shopman/backstage/projections/production.py`) ganha a
  anotação derivada: `300 g · ≈ 6 ovos`, calculada na hora do fator `approximate` do
  insumo. **Nunca gravada** — corrigir o fator (ovo jumbo, 60 g) atualiza toda lista de
  picking sozinho.
- O `≈` **só** aparece quando o número passou por fator aproximado. Número exato não
  ganha enfeite.
- Depende só da Fase 2.
- **Como ficou:** `MiseEnPlaceLineProjection.annotation` (string vazia quando o insumo
  não tem conversão de contagem declarada), regenerada no contrato da superfície e
  exibida sob a quantidade em `surfaces/production-nuxt/app/pages/mise-en-place.vue`.
  Duas escolhas que o plano não especificava e a bancada resolve:
  - **só conversões sem fornecedor** entram na anotação — na bancada não há fornecedor
    em contexto, e a equivalência física é do insumo, não de quem vende;
  - quando o insumo tem mais de uma, **vence a de menor fator**: quem separa conta ovo
    na mão, não 0,2 cartela.
  Anotação nunca trava a lista: unidade que não alcança a base devolve `""` em vez de
  erro.

### Fase 5 — a entrada carimbada (recebimento) · ✅ concluída

> **O que a destravou:** `Move.Kind.BUY` finalmente ganhou emissor (recebimento do
> Buyman), e a Fase 6 encheu a tabela de conversões de gente de verdade — sem entrada
> convertida, não havia o que carimbar.

- O recebimento grava `Move.metadata["converted_via"] = {"label", "factor",
  "approximate"}` — JSONField que já existia, Core sem mudança de forma. As três chaves
  viajam **num objeto só**: rótulo sem fator não deixa refazer a conta, e fator sem o
  `approximate` não diz se a conta era exata. Entrada na própria unidade-base **não
  carimba nada** — uma chave com `null` fingiria que houve ponte.
- Saldo que passou por aproximação aparece com `≈` na tela
  (`MaterialProjection.stockIsApproximate` → `formatStockOnHand`), e o insumo ganha a
  pendência "Saldo estimado". O custo derivado dali já era marcado desde a Fase 3.
- **A janela erra de propósito para o lado seguro:** saber quando a entrada aproximada
  de fato saiu do estoque exigiria rastrear lote a lote; vale a validade do insumo e,
  sem ela, a janela de consumo da política. O `≈` às vezes fica um pouco mais do que
  precisava — marcar de menos esconderia a incerteza, que é o oposto da regra.
- A recusa por **rótulo não cadastrado** que esta fase devia trazer acabou entrando com
  a Fase 6, e melhor do que o previsto: além de recusar dizendo o que cadastrar, o
  recebimento agora **deixa cadastrar ali mesmo**
  (`POST /api/v1/backstage/purchase/conversions/`, com autor).

### Fase 6 — a NF-e de entrada preenche a tabela sozinha · ✅ concluída

> **O que a destravou:** o QA do dono no alpha (27/08/2026) mostrou o defeito em
> produção — uma nota de fermento fresco Mauri com **10 unidades** entrou na tela como
> **10 kg**. O adapter lia `uCom or uTrib` campo a campo, então conseguia colar a
> quantidade comercial (10) na unidade-base do insumo (kg) sem fator nenhum no meio.
> O dado que responde à pergunta já vinha na nota e estava sendo jogado fora.

- `uCom`/`qCom`/`vUnCom` e `uTrib`/`qTrib`/`vUnTrib` passam a ser lidos como **dois
  eixos inteiros** (`NFeItem`), nunca metade de um com metade do outro. Sem par
  comercial utilizável, o item degrada para o tributável **como bloco**.
- O fator sai da nota: `fator = qTrib ÷ qCom`, com o par tributável levado à
  unidade-base pela física fechada (`shopman.utils.units`). Sinal **secundário**: a
  gramatura embutida no `xProd` ("FERM BIOL FRESCO MAURI 500G"), usada só quando o par
  tributável não decide — texto livre do emissor não é declaração fiscal.
- **Curadoria, como planejado:** nada entra sozinho. A conversão viaja na linha como
  `conversionSuggestion` (rótulo, fator, tipo, procedência e a frase que explica de
  onde saiu), a linha **continua bloqueando a confirmação**, e o operador aceita num
  clique ou declara outra. Mesma língua da sugestão de insumo (PR #354).
- **Ler o par tributável não fere a R4.** A R4 proíbe **inventar** fator; aqui o
  sistema lê o que o emissor declarou. O que continua recusando é a nota que não
  responde: aí a linha para com a mensagem dizendo qual conversão cadastrar.
- **Física deixou de pedir declaração.** Nota em `G` para insumo em `kg` converte
  sozinha (conversão do tipo 1 da ADR-024) em vez de travar pedindo uma
  `MaterialConversion` — exigir que alguém declarasse kg↔g era pedir declaração de
  física.
- **Alerta de ordem de grandeza** (ADR-024, §Consequências): quando a nota discorda da
  conversão já escolhida ("saco 25 kg" declarado, nota dizendo 20), a divergência
  aparece como aviso — não trava, mas não passa calada.
- **O gesto que faltava:** `POST /api/v1/backstage/purchase/conversions/` declara a
  conversão sem sair do recebimento (`declare_conversion`), com autor
  (`MaterialConversion.created_by`, campo novo). Até aqui o operador só podia
  **escolher** entre conversões já cadastradas, e cadastrar era coisa do Admin — uma
  embalagem nova parava a entrada com o entregador esperando.
- **Calibração ainda pendente:** o vocabulário de `uCom` (`PURCHASE_UNIT_WORDS`) e o
  regex de gramatura foram escritos contra a estrutura obrigatória da NF-e e o caso
  real do fermento, não contra as 5–10 notas da [ADR-024
  §Evidência 4](../decisions/adr-024-material-unit-base-and-purchase.md). Elas
  continuam valendo — o que muda com elas é o vocabulário inicial, não o mecanismo.

## Calibração do cadastro (03/09/2026) — os líquidos pesados vão para kg

O mecanismo ficou pronto; o **cadastro da Nelson** ainda tinha água, leite, azeite e
creme de leite em `l`, enquanto a bancada os **pesa**. Pela R1 a base é a do momento da
verdade, então a base estava no eixo errado, e a ponte de densidade caía na produção
diária em vez de no recebimento. A correção é de dado, não de código:
[WP-BASE-UNIT-LIQUIDS-KG](WP-BASE-UNIT-LIQUIDS-KG.md).

Vale como precedente: **a base errada não aparece como erro**, aparece como uma tela que
mostra dois números para a mesma coisa (`3,4 L (3502 g)`). Quando a anotação da Fase 4
precisa existir para o operador entender a linha, a suspeita certa é a unidade-base, não
a anotação.

## Ordem recomendada

```
Fase 0 (dado) ─┬─► Fase 1 (física em utils) ─► Fase 2 (tabela) ─┬─► Fase 3 (custo) ─► Fase 6 (NF-e) ✅
               │                                                └─► Fase 4 (anotação)
               └─────────────────────────────────────────────────► Fase 5 (recebimento, com Buyman F3) ✅
```

Regra de ouro da ordem: **a Fase 3 tem de acontecer antes de existir custo real
cadastrado.** Todo o resto tolera atraso; dinheiro já digitado, não. (Aconteceu: entrou
com a tabela ainda vazia.)

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
| 2 | fator ≤ 0 recusado; rótulo duplicado recusado; aproximada não passa por exata ✅ |
| 3 | custo por base derivado com precisão; conversão incoerente (outro insumo / outro fornecedor / inativa) **recusa** ✅ |
| 4 | anotação derivada muda quando o fator muda, sem tocar na ficha ✅ |
| 5 | `Move` de entrada carrega `converted_via` (as três chaves juntas); entrada na base **não** carimba; saldo que atravessou ponte aproximada volta com `≈` na projection e na tela ✅ |
| 6 | XML com eixos divergentes vira sugestão de conversão **sem gravar nada**; eixos coerentes não sugerem; `qCom` zerado não divide por zero; nota que não decide **recusa dizendo o que cadastrar**; endpoint cria a linha com autor e recusa fator ≤ 0 e rótulo duplicado ✅ |

## Referências

- [ADR-024](../decisions/adr-024-material-unit-base-and-purchase.md) — a decisão (três tipos de conversão, quatro regras)
- [ADR-023](../decisions/adr-023-cost-live-and-frozen.md) — o custo congela; esta frente diz em que unidade
- [BUYMAN-PROCUREMENT-PLAN](BUYMAN-PROCUREMENT-PLAN.md) — Fases 2–4 do Buyman (pedido, recebimento, reposição)
- [ADR-002](../decisions/adr-002-centavos.md) · [ADR-001](../decisions/adr-001-protocol-adapter.md)
