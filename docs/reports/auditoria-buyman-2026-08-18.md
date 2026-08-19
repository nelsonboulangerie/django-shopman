# Auditoria profunda — Buyman

> Série "um app por vez", nº 4 (final) · 2026-08-18 · Base: leitura integral do código (main, pós #215)
> Escopo lido: o pacote inteiro (3 models, 2 adapters, admin, migração, 9 testes), mais tudo que o toca — o `CostBackend` do Offerman (`protocols/cost.py`, `conf.py`, `Product.reference_cost_q`/`margin_percent`), a validação de unidade do `RecipeItem` no Craftsman, os validadores/catálogos compostos do orquestrador, o seed de insumos e saldos de abertura, e o `Move.Kind.BUY` do Stockman.

---

## Veredito em uma frase

O Buyman é o app mais honesto da leva — Fase 1 entrega exatamente o que promete e nada além — mas a auditoria achou algo que o relatório geral não viu: **a cadeia de custo da suite são três pontas de corda sem meio** (Buyman escreve custos que ninguém lê, Craftsman não tem custeio, o seam do Offerman está desplugado), e o campo `Material.unit` serve dois senhores com exigências contraditórias — a receita e o custo — num acoplamento que a Fase 2 vai transformar de incômodo em erro.

---

## Parte I — O que está certo

**1. Os adapters são a peça de valor real, e são finos de propósito.** `MaterialSkuValidator` e `BuymanCatalogBackend` fazem insumo (Material) responder aos protocolos de Stockman e Craftsman como cidadão não-vendável (`is_sellable=False`, `availability_policy="planned_ok"`), compostos no orquestrador com fallback Offerman→Buyman. Foi isso que destravou o guardrail de insumos do Craftsman sem poluir o catálogo de venda com "produtos" que não se vendem — a decisão arquitetural certa, executada com imports lazy conforme ADR-001.

**2. A única constraint sofisticada do pacote é a certa.** `UniqueConstraint(fields=["material"], condition=Q(is_preferred=True))` — **um** preferencial por insumo, garantido pelo banco, não por convenção. É a versão parcial-condicional que a maioria resolve com flag + oração.

**3. Fase 1 é autoconsciente.** O docstring do custo declara "histórico fica para fase futura"; o plano de Fases 2–4 existe; o seed documenta a tabela aprovada de unidades/validades e cria saldos de abertura nomeando o interino. Nenhuma pretensão de ser mais do que item master — a modéstia é deliberada e está escrita.

**4. Admin funcional dos dois lados.** Custo como inline tanto no Insumo quanto no Fornecedor, badges de validade/preferencial, autocomplete. Para master data operado por gente, é o suficiente.

---

## Parte II — Falhas e brechas (por severidade)

### B1 · ALTA — A cadeia de custo são três pontas sem meio (e o quarto fantasma da série)

Segui a corda inteira:

- **Buyman** grava `SupplierMaterialCost` cujo docstring promete: *"é ele que alimenta o custeio (CostBackend) e o custo de receita"*. `grep` no repositório: **nenhum leitor.** Zero consultas fora do próprio admin.
- **Offerman** define o Protocol `CostBackend`, e `Product.reference_cost_q` / `margin_percent` leem dele — mas `conf.py` traz `COST_BACKEND: None` e o `CraftingCostBackend` citado como exemplo no docstring (`shopman.craftsman.adapters.catalog.CraftingCostBackend`) **não existe em lugar nenhum**.
- **Craftsman** — o dono natural do custeio de receita — não tem uma linha de código de custo. Nada em services, nada em models.

Ou seja: o operador que preencher custos hoje alimenta uma tabela write-only; a margem no admin do Offerman fica dormant (ao menos honestamente — as colunas se escondem sem provedor); e a promessa do docstring do Buyman é o **quarto fantasma da série** (WP-7 do Cashman, chargeback do Payman, `delivery` do Fiscalman, agora um modelo inteiro). Isso *corrige* meu relatório geral: eu temia que o custo mutável mudasse o custeio histórico retroativamente — não muda, porque **não existe custeio nenhum**.

Mas a correção não dissolve a questão — ela a antecipa: no dia em que alguém escrever o `CraftingCostBackend` (20 linhas), a semântica precisa já estar decidida, porque as duas perguntas têm respostas opostas:

- *"Qual a margem deste produto hoje?"* → custo **vivo** (preferencial atual × receita ativa). A propriedade do Offerman está certa para isso.
- *"Quanto custou a fornada de 12/08?" / análise de margem do BI* → custo **congelado no fato** (snapshot no WorkOrder/lote no momento da produção). A casa já tem o precedente exato: `Batch.nonconformity_percent` é **congelado** por decisão registrada — o custo da fornada merece o mesmo tratamento pelo mesmo motivo.

**Ação:** decidir e registrar (um ADR curto) *antes* de plugar a corrente: custo vivo para precificação, custo congelado por WorkOrder para história/BI — e só então implementar o backend. Com o BI (Frentes A/B) em andamento, essa decisão está no caminho dele, não depois dele.

### B2 · ALTA — `Material.unit` serve dois senhores, e eles discordam

O mesmo campo alimenta duas mecânicas com pressões opostas:

1. **A receita exige igualdade estrita.** `RecipeItem.clean()` do Craftsman recusa unidade diferente da do catálogo (*"deve coincidir com a unidade do SKU cadastrado"*) — **não há conversão**, por design. Insumo em `kg` obriga toda receita a falar em kg (0,5 kg, não 500 g).
2. **O custo é centavos inteiros por essa mesma unidade.** `cost_q` BigInteger "por unidade do insumo". Insumo em `g` torna custos sub-centavo **irrepresentáveis**: canela a R$ 45/kg = 4,5 centavos/g → arredonda para 4 ou 5, erro de ~11% que se multiplica por cada grama custeado. (O seed já vive o dilema: farinhas em `kg` — custo representável, receitas fracionárias; CANELA e ALECRIM em `g` — receitas ergonômicas, custo condenado ao arredondamento.)

Escolher a unidade fina quebra o custo; escolher a grossa quebra a ficha técnica. E falta o eixo que o item master clássico tem exatamente para isso: **unidade de compra + fator de conversão** — porque ninguém compra grama de farinha; compra-se saco de 25 kg, e é *nesse* nível que o custo do fornecedor existe no mundo real. A Fase 2 (PurchaseOrder/recebimento) vai exigir a unidade de compra de qualquer forma; decidir agora evita migrar dados de custo duas vezes. **Proposta:** `unit` continua sendo a unidade-base da receita/estoque; o custo migra para (unidade de compra, fator → base), e o custo por base vira derivado com precisão decimal — resolvendo os dois senhores de uma vez.

### B3 · MÉDIA — O namespace de SKU não tem porteiro entre as duas tabelas

`Product.sku` e `Material.sku` são únicos **cada um na sua tabela**; o `RefField(ref_type="SKU")` registra para operações de cascade/rename, não impõe unicidade cruzada. Nada impede `CANELA` existir nas duas — e quando existir, todos os caminhos compostos resolvem **Offerman primeiro e sombreiam o insumo em silêncio**: o validador, o catálogo, e a validação de unidade da receita passariam a ler o *produto* homônimo. Sem erro, sem aviso — só respostas sutilmente erradas. Fecho barato: um `clean()` cruzado nos dois models ("SKU já existe como produto/insumo") + um check de sistema que varra colisões existentes. É a mesma classe de porteiro-ausente do F1 do Fiscalman: a porta do admin até avisaria, as outras portas não.

### B4 · MÉDIA — Sem invariantes onde os irmãos têm, e o flip do preferencial dá erro cru

Três ausências que destoam da casa:

- **`cost_q` não tem CheckConstraint de positividade.** Payman (`amount_q > 0` em intent e transação) e Cashman (sinal por tipo) provam que a casa acredita em constraint para dinheiro; aqui, custo **zero ou negativo entra no banco** sem resistência. Um `Q(cost_q__gt=0)` alinha.
- **Trocar o preferencial de A para B** pelo inline do admin (marcar B com A ainda marcado) estoura a constraint parcial como `IntegrityError` cru na tela — exatamente o anti-padrão que o `open_shift` do Cashman faz questão de evitar ("a constraint decide, e a mensagem continua sendo a nossa"). Falta ou um `clean()` que explique, ou um gesto atômico de promoção (demove A, promove B na mesma transação).
- **Nada impede preferencial de insumo/fornecedor inativo** — o custo canônico pode apontar para um par que a loja aposentou.

Nenhum exige service layer completo — um `clean()` caprichado nos três pontos resolve a Fase 1 sem cerimônia. (O service de verdade chega com a Fase 2, onde haverá gestos reais: emitir pedido, receber, emitir BUY.)

### B5 · BAIXA — O literal `SkuInfo` copiado quatro vezes

`get_sku_info`, `get_sku_infos` e `search_skus` repetem a mesma construção de 10 campos a partir de um Material. Um `_to_sku_info(material)` privado elimina três cópias e o dia em que alguém atualizar duas delas e esquecer a terceira.

### B6 · BAIXA — O interino da entrada de estoque não está nomeado onde importa

Conhecido e planejado (Fases 2–4), mas vale registrar o estado exato: `Move.Kind.BUY` existe no Stockman e **nada o emite**; hoje insumo entra por seed e ajuste manual, **sem procedência** — numa suite ledger-first, o estoque que alimenta o guardrail do Craftsman é o único sem história de origem. Uma linha no `status.md` ("entrada de insumo: manual até Fase 2") transforma omissão em decisão registrada — a diferença que a própria casa cultiva em todo o resto.

---

## Parte III — Desconstruir ou não?

**Nada a demolir — mas duas fundações a decidir antes de construir o andar de cima.** O Buyman é pequeno, correto no que faz, e o seu plano de fases é bom. Os riscos não estão no código que existe; estão nas decisões que a Fase 2 e o BI vão *herdar caladas* se não forem tomadas agora:

1. **ADR do custo (B1):** vivo para precificar, congelado no WorkOrder para contar história — decidir antes de escrever o `CraftingCostBackend`, e escrevê-lo só depois. Meia página, precedente interno já existe (`nonconformity_percent`).
2. **ADR da unidade (B2):** unidade-base para receita/estoque + unidade de compra com fator para custo/procurement — decidir antes de a Fase 2 modelar o PurchaseOrder, que vai precisar dela de qualquer jeito.
3. **PR "porteiro e invariantes":** colisão de SKU cruzada (B3) + positividade do custo + promoção atômica do preferencial + veto a preferencial inativo (B4) + `_to_sku_info` (B5) + a linha de interino no status (B6). Uma PR pequena, sem migração de dados.

---

## Fechamento da série

Quatro auditorias, um padrão que atravessou todas: **a suite tem excelência real de construção e um hábito recorrente de deixar a declaração à frente da implementação** — WP-7 citado como guarda existente (Cashman), chargeback somado em relatório sem caminho de criação (Payman), Protocol atrás do próprio contrato (Fiscalman), tabela de custo com consumidor prometido e inexistente (Buyman). Nenhum desses fantasmas é difícil de exorcizar individualmente; o que vale a pena institucionalizar é o anticorpo: *comentário ou docstring que afirma a existência de um guarda, consumidor ou capacidade só entra com o link para o código que o implementa — ou com o tempo verbal no futuro.* É uma frase na constituição do projeto, e teria evitado os quatro.

Prioridade entre os planos de ação, na minha leitura consolidada: **Cashman F1–F3** (dinheiro, corrida, fantasma) → **Fiscalman F1–F2 + contador** (caminho crítico legal com lead time externo) → **Payman P1–P3** (armadilha armada + API) → **Buyman ADRs** (baratos agora, caros depois). Quando quiser, transformo qualquer um deles em plano de execução detalhado.
