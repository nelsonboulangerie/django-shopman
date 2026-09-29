# WP — A unidade-base dos insumos e das fichas é o GRAMA

> Decisão dele em 24/09/2026: *"6 casas acho demais, vai prejudicar muito a leitura.
> Por mais que seja uma mudança grande, ainda estamos em pré go-live, a hora é
> agora… kg estava um pouco superdimensionado mesmo… em algum momento, em
> relatório, pode ser usado, claro. Mas a medida base, é a que trabalhamos na
> balança no dia a dia, é grama."*

## O defeito, medido

Toda quantidade da ficha e da produção é gravada em **kg com três casas**. A menor
quantidade que cabe numa linha é, portanto, **1 g**. O F2 das fichas reais
(`WP-FICHAS-REAIS-DA-CASA`) esbarrou nisso três vezes no mesmo dia:

| insumo | quanto vai | o que a ficha fez |
|---|---|---|
| alecrim na finalização da focaccia | 0,1 g (0,05 g na pequena) | ficou **fora** da ficha |
| louro no recheio de frango | 1 folha = 0,34 g | ficou **fora** |
| baunilha no creme do pain perdu | 2 gotas = 0,125 g | a receita foi **escalada ×8** só para caber |

Arredondar para 1 g não serve. A baixa de estoque não converte unidade, e 0,1 g
gravado como 1 g **desconta dez vezes** o que vai na peça. Nas bebidas, que são por
unidade, isso aparece em toda especiaria, gota e pitada.

## A decisão

**A unidade-base dos insumos pesados e das fichas passa de kg para g, com as mesmas
três casas.** Isso dá resolução de 1 mg (alecrim = `0.100`), e o número gravado é o
que a balança mostra (`280.000` g de massa por baguete). O quilo continua valendo
para leitura em relatório.

Isto **emenda a [ADR-024](../decisions/adr-024-material-unit-base-and-purchase.md)
R1**. A regra continua sendo "a base é a unidade em que a casa mede no momento da
verdade"; o que muda é a resposta, porque a casa mede em grama. A ADR tinha
descartado o grama por **um** motivo: centavo por grama perde precisão (a canela dava
11% de erro). Esse motivo continua existindo e é tratado abaixo.

## O que isso toca (inventário de 24/09 no `main`)

A lógica já converte pela unidade gravada (`shopman.utils.units.convert`), e o
NF-e já converte para a `material.unit`. O que assume kg são **dados** e alguns
pontos de exibição e de custo:

- **Dados:** `recipes_data`, as conversões (ovo 0,050 → 50; saco 25 → 25000; louro
  0,00034 → 0,34; baunilha → 0,063), `material_attrs`, `output_unit` dos
  pré-preparos, `PACOTE_KG`, `PISO_ESPECIARIA_KG`, `PROVISIONAL_CAPACITY_PER_DAY` e
  os alvos de estoque de abertura. O `volume_conversions` usa a densidade como
  kg/l, e em g ela vira densidade × 1000.
- **Defaults:** `RecipeItem.unit="kg"`, `RecipeVersion.yield_unit`,
  `MaterialNeed.unit`, e o rendimento padrão nas telas de receita do
  `production-nuxt`.
- **Exibição:** `mass_factors` da produção, a formatação de peso no
  `production-nuxt` (`weighing.ts`) e a mensagem do balanço de massa.
- **Custo, o ponto crítico:** o banco guarda `cost_q` **por unidade de compra**
  (saco, pacote), e isso não muda. O que quebra é quem arredonda o custo **por
  unidade-base** para centavo inteiro: `cost_per_base_unit_q` (exibido no Admin) e o
  `resale_markup`. Em grama, a farinha a R$ 4/kg vale 0,4 centavo/g e vira **zero**.
  **Regra nova:** nada consome centavo inteiro por grama. O cálculo usa o Decimal,
  e a exibição fala em R$/kg.
- **Fora do escopo, e é regra:** SKU que a casa **revende por peso** (o queijo da
  mercearia) continua em kg. O ledger é por SKU, e compra e venda precisam falar a
  mesma unidade (`units_agree`). A base em grama vale para o que é insumo.

## Fatias (o `main` fica verde entre elas)

1. **Emenda da ADR-024 e neutralização do kg, sem mudar dado.** Custo pelo
   Decimal e exibido em R$/kg; `mass_factors` pelo `units.convert`; mensagem do
   balanço sem "kg" fixo; `weighing.ts` aceitando "g"; um humanizador de massa só
   ("850 g", "1,2 kg"). Com a base ainda em kg, nada muda de comportamento.
2. **Defaults e migrações de estado** (`RecipeItem.unit`, `yield_unit`,
   `MaterialNeed`) e os defaults das telas de receita.
3. **O seed em grama.** Fichas, conversões, pacotes, capacidade e alvos. O
   alecrim, o louro do frango e a baunilha entram na escala real, o que desfaz o ×8
   do creme. Os testes de seed e integração vão junto.
4. **O banco do alpha.** Pré-go-live, o alpha é sintético, e quem o leva à base
   nova é o **reseed**, que pede a palavra dele. Não há migração de dados a
   escrever para ambiente com dado real, porque ainda não existe. O
   `convert_material_base_unit` continua disponível insumo a insumo.

Tamanho estimado: 15 a 20 arquivos de produção, 3 a 5 do front, a ADR e 25 a 35
testes.
