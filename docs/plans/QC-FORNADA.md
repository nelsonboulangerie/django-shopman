# QC de fornada — desenho, decisões e onde os números vão parar

> Status: **desenho de produto fechado. Decisão arquitetural em [ADR-017](../decisions/adr-017-quality-as-production-outcome.md).**
> Protótipo navegável: `qa/proto/qc-fornada.html` (fora do repo, entregue por chat).
> Continuação do POS-ALPHA-REMEDIATION-PLAN (ondas 8–14, modelo de lote/validade).
> ⚠️ **Esse plano NUNCA foi commitado** — viveu fora do repo, e com ele se perdeu a
> discussão que decidiu a superação do D-1 pelo modelo de validade (o caso do
> queijo: produto com validade de dias não cabe num balde binário "ontem").
> A decisão sobrevive aqui e no ADR-017; o link morto fica como lição de
> [plan-in-repo](../../docs/README.md).
>
> ⚠️ **Correção (2026-08-07):** os §6.2 e §9 deste documento recomendavam uma FK
> `WorkOrder → Batch`. **Estava errado** — a ADR-004 proíbe FK cross-domain. O elo correto é
> `WorkOrderItem.batch_ref` (string ref). Ver ADR-017 §5. Os códigos de grau e o marcador de
> descarte também estavam em português, contra a convenção; os valores canônicos são
> `excellent · standard · fair · minimal` e `forces_discard`. E o grau de −20% deixou de se
> chamar "Aceitável" (ver §2), assim como "sujo" deixou de ser veto (ver §3).

---

## 1. O problema

O padeiro precisa declarar, ao fechar a fornada, que **parte** dela saiu fora do padrão — e
com que severidade. Hoje isso não existe como fluxo: a não conformidade marca o `Batch`
inteiro, e a qualidade da fornada é uma string solta em JSON.

Restrições dadas pelo dono da operação:

- Chão de fábrica: **menos toques possíveis**, tela touch, às 5h da manhã.
- **Fornada não conforme NÃO vai para o dia seguinte**, mesmo em SKU que normalmente vai.
- Estoque não conforme **não é oferecido aos canais remotos**.
- Fornada de qualidade máxima **dispara divulgação**; fornada normal não.
- **O grau (severidade) define o desconto — nunca o motivo.** Motivos como "queimado" não são
  binários; têm grau. Isso mantém a tabela de preço com **um eixo só**: acrescentar um motivo
  novo nunca exige uma decisão de precificação.
- A quantidade prevista que chega ao forno é **quente**: o rendimento da massa já foi tratado
  em etapas anteriores da produção. Portanto **o que não sair do forno é perda**, e perda é
  não conformidade que pede motivo.

---

## 2. A escala de qualidade

Quatro graus, **substantivos** (graus de *uma coisa só*: a qualidade). Adjetivo julga o pão e,
de tabela, o padeiro; substantivo nomeia uma faixa.

| Rótulo (Admin, editável) | Código (fixo) | Preço | Vai p/ dia seguinte | Broadcast |
|---|---|---|---|---|
| Ótima      | `excellent`  | cheio | sim | **dispara** |
| Normal *(padrão)* | `standard` | cheio | sim | não |
| Razoável   | `fair`       | −20%  | **não** | não |
| Mínima     | `minimal`    | −50%  | **não** | não |

Notas de projeto:

- **"Mínima" é o piso.** Abaixo dela não existe grau, existe descarte — que é exatamente a
  regra da casa. O nome ensina a política.
- Rejeitado **"Máxima"** para o topo: `máxima` e `mínima` diferem em duas letras, começam com M
  e terminam em `-ima`, e são os **dois extremos**. Confundi-los é o pior erro possível
  (preço cheio + divulgação × metade do preço).
- Rejeitado **"Regular"** (o valor que existe hoje no código), **"Desvio leve/grande"**
  (quebra a forma gramatical dos outros dois), **"Fraco/Ruim"** (quase-sinônimos: a ordem
  não é óbvia num relance), **"Primeira/Segunda/Terceira"** ("segunda" numa padaria é dia da
  semana) e **"Desconto/Metade"** (amarra o rótulo ao preço, que é editável).
- Critério duro que gerou as rejeições: **a ordem tem que ser óbvia num relance.** Se o padeiro
  hesitar "qual é pior?", o dado sai errado — e esse dado é justamente o que vai dizer se o
  forno 2 está queimando.
- **"Aceitável" foi descartado para o degrau de −20%** por sobreposição: ele nomeia a
  *fronteira inferior* do que se aceita, que é exatamente o que **Mínima** já é. Dois nomes
  disputando o mesmo lugar da escala — e o degrau de baixo também é aceitável, tanto que é
  vendido. **Razoável** nomeia um *meio*, não uma fronteira, e é fala corrente ("foi só
  razoável" nunca é elogio), o que importa às 5h da manhã.
- Descartados por categoria gramatical: **plausível** e **viável** qualificam proposições e
  planos, não objetos — "pão plausível" não significa nada. **Admissível** ordena bem, mas é
  registro de engenharia para uma tela de chão de fábrica.

### Impacto no código existente

`shopman/shop/models/broadcast.py:44` tem hoje três níveis:

```python
QUALITY_LEVELS = ("regular", "bom", "excelente")
```

Precisa virar quatro. Os quatro valores canônicos são `excellent`, `standard`, `fair` e
`minimal`, e a hierarquia deixa de ser uma tupla literal: passa a ser `QualityGrade.rank`
(ADR-017 §6).
`shopman/backstage/services/production.py:147` tem o espelho:

```python
QUALITY_CHOICES = ("regular", "bom", "excelente")
DEFAULT_QUALITY = "bom"
```

Os dois têm que sair do literal duplicado e virar uma fonte só.

---

## 3. Defeitos

Catálogo editável no Admin, **sem percentual** (quem define preço é o grau). O que está sendo
catalogado não é "um motivo" — é um **tipo nomeado de falha**, e por isso o modelo se chama
`QualityDefect`. "Motivo" é a pergunta que o lote faz (`Batch.nonconformity_reason`, que não
muda); o defeito é a resposta. Nas palavras da equipe:

| Rótulo (Admin) | Dica na tela | Código (fixo) | Veto |
|---|---|---|---|
| Fermentou pouco | pequeno, denso, rasgou | `underproofed` | |
| Fermentou demais | murchou, achatou | `overproofed` | |
| Assou pouco | pálido, cru | `underbaked` | |
| Assou demais | escuro, queimado | `overbaked` | |
| Deformado | torto, colado | `misshapen` | |
| Marcas de forno | fuligem, manchas | `scorch_marks` | |
| Contaminado | matéria estranha | `contaminated` | **`forces_discard`** |

**O catálogo é um 2×2 mais três.** Dois processos — fermentação e forno — cada um com dois
sentidos. O operador lê uma grade, não uma lista, e um padeiro novo aprende em um minuto.

**"Pequeno" saiu, e a razão é boa.** Pequeno é sintoma, não defeito: o relatório dizer "12
pequenos esta semana" não ensina nada. A causa quase sempre é fermentação — que pode ter
faltado **ou sobrado**. Trocando o sintoma pela causa, o relatório passa a dizer *o que
ajustar*.

**Nenhum dos quatro carrega severidade.** "Escuro" e "queimado" são o mesmo defeito em graus
diferentes: `overbaked` em Razoável é escuro; `overbaked` em Mínima é queimado. A palavra não
muda quando a severidade muda — é a demonstração de que o eixo único funciona. Por isso não
existe um defeito `burnt` separado.

**A dica na tela é o que torna isso viável às 5h.** Nomear pela causa custa uma inferência que
nomear pelo sintoma não custa: o padeiro *vê* pálido, ele *deduz* que assou pouco. A segunda
linha do botão carrega o sintoma, então a escolha volta a ser reconhecimento, não diagnóstico.
Sem ela, quem não souber distinguir vai chutar — e chute vira ruído no relatório, que é
exatamente o que o QC existe para evitar.

**Fuligem e marcas são a mesma coisa** (`scorch_marks`), confirmado com a operação. Se a
equipe passar a distinguir na prática, separar é um registro no Admin.

**Pão fora de tamanho por peso/divisão errada cai em `misshapen`** — decidido com a operação.
Não ganha código próprio: a causa é de uma etapa anterior à do forno, e o QC da fornada não é
o lugar de diagnosticá-la. Se o relatório mostrar `misshapen` crescendo sem explicação, aí
sim vale separar.

### O marcador `forces_discard`

Um defeito pode ganhar no Admin um marcador booleano. Se escolhido, aquelas unidades **não
viram lote com desconto** — viram perda, e não há tela em que o operador possa contrariar.

Isso **não** desmonta a regra do eixo único: quem define **preço** continua sendo só o grau.
O marcador não é preço, é **veto** — outra dimensão.

**A regra do veto: só o que torna o alimento inseguro, nunca o que o torna feio.**

A primeira versão marcava "sujo" como veto, e estava errada — "sujo" é grosso demais para ser
uma coisa só. Sujeira de forno, fuligem e marcas são defeitos **cosméticos**: vendem com
desconto como qualquer outro. E há a nuance que o dono levantou: *tentar limpar às vezes
danifica o produto* — decisão de quem está com o pão na mão, que o sistema não pode tomar por
ele. Um veto ali empurraria o operador a destruir pão vendável, ou a mentir no motivo para
salvá-lo. As duas saídas são piores que o problema.

Sobra o caso que é veto de verdade: **contaminação** — matéria estranha, qualquer coisa que
torne o pão incomível. Aí não há grau, não há desconto, não há discussão. `forces_discard`
fica raro e inequívoco, em vez de virar uma categoria com a qual o operador negocia.

---

## 4. A aritmética (a parte que estava errada)

O campo principal da tela **não é "saíram do forno"** — é **"a preço cheio"**. A troca não é
cosmética; sem ela o modelo conta o mesmo pão duas vezes.

O bug: com o rótulo "saíram do forno", digitar 38 num previsto de 40 significa "2 se perderam".
Se o operador então toca num grau menor e o sistema preenche 2 em "quantas assim", essas 2 já
estavam contadas como perda — total 42 num previsto de 40.

Com o rótulo corrigido, os três grupos são **disjuntos por construção**:

```
previsto = a preço cheio + com desconto + perda
```

E o modelo fica **subtrativo**, que é como se conta na boca do forno: a tela nasce com tudo a
preço cheio e cada exceção é retirada dali.

Daí sai, sem ramo especial, a regra do padrão de "quantas assim":

> ao tocar num grau menor, **"quantas assim" recebe o que ainda não foi contado**
> (`previsto − a_preço_cheio`); se o operador não mexeu em nada, o não contado é zero,
> e aí o padrão vira a fornada inteira.

Um enunciado, dois comportamentos.

---

## 5. A UI (quiosque do fournil)

Duas telas.

**Tela 1 — painel.** Lista de **ordens de produção do dia**, não catálogo de SKU: a ordem já
carrega forno, horário e **previsto**, e é o previsto que faz a fornada normal fechar em um
toque. Ordenadas por horário, a próxima a vencer com moldura; as fechadas ficam visíveis e
esmaecidas; contador "N de M fechadas" no topo. Botão discreto **"fornada fora do plano"**
abre a lista de SKU e nasce sem previsto (honesto: não havia expectativa).
Sem campo de busca — são 5–15 fornadas/dia, e busca em quiosque significa teclado alfabético
na tela.

**Tela 2 — QC.** Regras de layout, todas verificadas por medição no protótipo:

- **O numpad é âncora.** Da barra do topo até a tecla `⌫`, a tela é estática — medido em
  `y = 412,19px` em todos os estados (idle, grau escolhido, primeiro dígito, segundo dígito,
  perda, descarte, sheet aberto, troca de escala). O motivo de existir essa regra: o painel de
  motivos abria no meio da tela e empurrava o numpad no primeiro dígito de um número de dois
  dígitos — o operador erra e não sabe por quê.
- **Dois campos numéricos lado a lado** ("a preço cheio" / "quantas assim"), sempre visíveis;
  o da direita apagado enquanto o grau for Ótima/Normal, acende sozinho nos outros.
- **A escala é coluna à direita do numpad**, como a coluna de operadores de uma calculadora.
  Economiza ~180px de altura (num painel de parede é a diferença entre caber e rolar), e
  empilhada vira uma faixa de cor contínua na borda esquerda — lê-se como escala antes de se
  ler como palavra. Vão maior entre numpad e coluna do que entre as teclas: errar o `9` e
  acertar "Razoável" seria erro de categoria, não de número.
- **Motivos em bottom sheet**, não banner. Custam zero espaço enquanto não são necessários e
  não deslocam nada. Ficam representados por dois cartões de uma linha abaixo do numpad,
  alinhados com os dois campos numéricos: coluna esquerda é a fornada e o que se perdeu dela,
  coluna direita é o sublote com desconto.
- **`Confirmar` está sempre ativo** e significa "fechar a fornada": se falta um motivo, ele
  pergunta — uma coisa de cada vez — e fecha na resposta. Isso faz o sheet **não custar toque
  nenhum**, e elimina o botão desabilitado sem explicação.
- **Navegação:** tocar num campo move o numpad para ele (a legenda acima do numpad diz em qual
  campo se está); tocar num motivo já respondido reabre o sheet; `trocar` no topo volta ao
  painel. Teclado físico: dígitos, `Backspace`, `Tab` alterna campos, `Esc` fecha o sheet —
  numpad USB funciona sem mudança.

### Toques até confirmar

| Caso | Toques |
|---|---|
| Fornada normal, saíram os 40 | 2 |
| Fornada ótima (e o broadcast sai) | 3 |
| 38 boas, 2 se perderam | 5 |
| 38 boas + 2 na mínima | 6 |
| A fornada toda na mínima | 4 |

Sem a regra do padrão de "quantas assim", o caso "38 + 2 na mínima" custaria 7.

---

## 6. Levantamento: onde o QC mora hoje

### 6.1 Três lugares que não se conhecem

| Onde | O quê | Qualidade da modelagem |
|---|---|---|
| `craftsman.WorkOrder.meta["quality"]` | string, 3 valores, default `"bom"` | ⚠️ JSON, sem coluna, **sem histórico** — sobrescrito a cada finish. O próprio código diz *"sem migração"*: é atalho assumido (`shopman/backstage/services/production.py:147-172`) |
| `stockman.Batch.nonconformity_reason` / `_percent` | motivo + percentual do lote | ✅ primeira classe, com `clean()`, queryset `.nonconforming()`, filtro no Admin e migration `0009` |
| `DayClosing.data["nonconformity_writeoffs"]` | `[{sku, batch, qty, reason}]` | ✅ persistido no fechamento |

### 6.2 O elo está no lugar errado — e **não** é uma FK

> ⚠️ Esta seção foi reescrita. A versão anterior pedia uma FK `WorkOrder → Batch`, o que a
> ADR-004 proíbe: ponteiros cross-domain são `CharField` indexado, nunca FK nem `GenericFK`.
> `WorkOrder` é craftsman e `Batch` é stockman; uma FK ali faria o craftsman deixar de
> instalar sozinho e quebraria `test_import_boundaries`.

O problema real é outro. O `batch_ref` é **derivado por fórmula de string** em
`shopman/backstage/services/production.py:481` (`_record_batch_traceability`):

```python
batch_ref = f"{work_order.output_sku}-{production_date:%Y%m%d}-{work_order.pk}"
```

…e guardado em `WorkOrder.meta`, ou seja **no agregado, não na linha que corresponde ao lote**.
Fórmula derivada só admite **um lote por ordem** — é por isso que a partição parecia
impossível.

A correção é guardar `batch_ref` na linha de OUTPUT (`WorkOrderItem`). N grupos viram N lotes
sem inventar mecanismo nenhum. Ver [ADR-017](../decisions/adr-017-quality-as-production-outcome.md) §5.

### 6.3 O que já existe e serve (mais do que se supunha)

`packages/craftsman/shopman/craftsman/models/`:

- **`WorkOrder`** — `quantity` (previsto), `finished` (realizado, imutável após o finish),
  `started_qty` (derivado do evento), e as propriedades `loss` e `yield_rate`.
- **`WorkOrderEvent`** — ledger imutável por WO, com `seq` (unique com a WO) e
  `idempotency_key`. O payload do `finished` já leva `finished_qty`, `planned_qty`,
  `started_qty`, **`loss_qty`**, `output_sku`, `operator_ref`.
- **`WorkOrderItem`** — ledger de materiais com `Kind.WASTE`.

`packages/stockman/`:

- **`Move`** — ledger de estoque imutável por guard (`update()`/`delete()` levantam
  `ValueError`), com `Kind.WASTE`.

**A tela nova não inventa entidade nenhuma.** Ela preenche campos que já existem, e acrescenta
a partição do lote.

### 6.4 Fechamento do dia

`shopman/backstage/services/closing.py` grava em **duas tabelas e só duas**:

1. `stockman.Move`, com razões carimbadas: `fechamento:<data>`, `d1:<data>`, `perda:<data>`,
   `perda_vencido:<data>`, **`perda_nao_conformidade:<data>`** (`Kind.WASTE`).
2. `backstage.DayClosing.data` (JSONField, `unique(date)`, append-only na prática — o Admin
   bloqueia add/change/delete), com seis chaves, das quais interessam:
   - `nonconformity_writeoffs` — já é um mini-relatório de QC por lote
   - `production_summary` — `{recipe_ref, output_sku, planned, finished, loss}` por receita
     ⚠️ usa `int(...)`: **trunca fracionários**

`classify_leftover` está em `shopman/backstage/projections/closing.py:28` (não no services).

---

## 7. B.I.: **não existe**

Nenhum app, package ou módulo de BI/analytics/reporting. Sem `ledgerman`, sem `olap`, sem
warehouse. **Sem Celery** (só dois comentários no código; nenhuma dependência real).
**Nenhuma tabela de agregação ou snapshot** — os únicos "snapshots" persistidos são JSONFields
dentro de tabelas transacionais (`DayClosing.data`, `WorkOrder.meta`,
`BroadcastPost.trigger_context`, `Move.metadata`).

O que existe é relatório **calculado na hora**:

- `shopman/backstage/projections/production.py` — `build_production_dashboard()` e
  `build_production_reports()`, com três `report_kind`: `history` (`WorkOrderReportRow`, com
  `qty_loss` e `yield_rate`), `operator_productivity`, `recipe_waste` (`RecipeWasteRow`, com
  `loss_total` — e `capacity_utilization` **sempre string vazia**, `projections/production.py:1489`).
- `GET /api/backstage/production/reports/` — permissão própria
  `backstage.view_production_reports`; CSV via `export_reports_csv`
  (`backstage/services/production.py:243`).
- `shopman/backstage/projections/dashboard.py` + `admin/dashboard.py` + template
  `admin/dashboard.html` — o dashboard do Admin.
- **Sem gráficos, por decisão explícita.** `surfaces/production-nuxt/app/pages/reports.vue`
  traz, no topo do `<script setup>`:
  `// Sem gráficos: tabelas caladas e números pré-formatados pelas projections.`

Único modelo com cheiro de agregação: `packages/guestman/.../contrib/insights/models.py` →
`CustomerInsight` (RFM de clientes). É CRM, não produção.

**Consequência para o QC:** não há para onde "mandar" os números além do que já existe. O
caminho é (a) gravar o fato no ledger que já é imutável (`WorkOrderEvent`), (b) materializar o
lote não conforme em `Batch`, (c) deixar o fechamento consolidar em `DayClosing.data`, e
(d) acrescentar um `report_kind` novo em `build_production_reports`. Um app de BI é uma
conversa separada — e, dado o volume de uma padaria, provavelmente prematura.

---

## 8. Eventos: como o Broadcast escuta (e está certo)

Confirmado: **a produção emite, o marketing decide.** Nada a corrigir na arquitetura.

- Sinal: `packages/craftsman/shopman/craftsman/signals/__init__.py:19` →
  `production_changed = Signal()`, disparado em `services/execution.py:296` (finished).
- Receiver: `shopman/shop/handlers/broadcast.py` → `on_production_changed` monta o contexto
  com `"quality": meta.get("quality", "bom")` e chama `_evaluate_later`, que faz
  `transaction.on_commit(...)` e engole exceção (*"Marketing não pode quebrar a operação"*).
- Regra: `shopman/shop/models/broadcast.py:26` já tem
  `PRODUCTION_FINISHED = "production_finished", "fornada concluída"`, e `trigger_filter` aceita
  `{"quality_min": "bom"}`, filtrado por `_quality_at_least`
  (`shopman/shop/services/broadcast.py:143`). Testado em `shop/tests/test_broadcast.py:106-146`.
- Outbox real, se precisar de assincronia: `packages/orderman/.../models/directive.py` →
  `Directive` (at-least-once, `dedupe_key`, consumida por `process_directives` /
  `maintenance_worker`, sem broker).

Falta apenas a fornada **informar** o grau de verdade (hoje o default `"bom"` é o que sai
quase sempre) e a escala ir de três para quatro níveis.

### Fornada ótima com unidades fora: dispara, com piso

Decidido: **dispara**, desde que a maior parte da fornada esteja no grau exigido. Isso vira uma
chave nova ao lado da que já existe em `BroadcastRule.trigger_filter` — zero model novo, zero
migration, porque o campo já é JSONField com `help_text` anunciando condições extras:

```json
{"quality_min": "excellent", "quality_min_share": 90}
```

- **A conta:** unidades em grau ≥ `quality_min` ÷ **quantidade prevista**, limitado a 100%.
- **O previsto é o denominador de propósito.** Fornada que perdeu 3 no forno não saiu 100%
  ótima, e a perda tem que pesar. Um denominador só, sem caso especial.
- **Ausente = 100%**, ou seja fornada limpa. O default falha para o lado seguro: afrouxar é
  decisão consciente do marketing, não herança de omissão.
- **Valor inicial no seed: 90.** Numa fornada de 40 são 4 unidades de folga — flexível o
  bastante para não perder a divulgação por um pão torto, apertado o bastante para não
  anunciar fornada meia-boca.
- **Atenção ao tamanho da fornada:** 90% numa fornada de 40 dá 4 unidades de folga; numa de 24
  dá 2. O percentual é mais duro em fornada pequena — é consequência real de usar percentual, e
  a alternativa (contagem absoluta) não escala entre receitas.

A produção continua só emitindo. Quem decide o piso é a `BroadcastRule`, no Admin do marketing.

---

## 9. Ordem de implementação

> A ordem canônica agora vive na
> [ADR-017 § Migração](../decisions/adr-017-quality-as-production-outcome.md), em 9 passos.
> Resumo:

1. **Colunas opacas em `WorkOrderItem`** (`quality_grade_ref`, `quality_defect_ref`, `batch_ref`) e o repasse
   de `meta` no ramo `finished` de `craft.finish()` — hoje só `wasted` recebe `meta`.
2. **Catálogos no framework**: `QualityGrade` e `QualityDefect` em `shopman/shop`, com Admin.
3. **Rename para inglês** dos valores de qualidade, com data migration. Barato agora,
   caro depois do go-live (ADR-015).
4. **Partição no finish** — `apply_finish` aceita grupos; `set_quality` é removido.
5. **N lotes** em `_record_batch_traceability`, um por linha de OUTPUT.
6. **Broadcast** deriva a qualidade das linhas; `quality_min` compara `rank`.
7. **Ledger**: a partição entra no `WorkOrderEvent.payload`.
8. **Leitura**: `report_kind="quality"` + consolidação no `DayClosing.data`.
9. **Superfície**: quiosque em `production-nuxt` sobre Projection frozen.

O **split de lote deixou de ser o buraco**: ele não é mecanismo novo, é consequência de
`finish()` receber uma lista — capacidade que o core **já tem** (`execution.py:197-220`).

---

## 10. Pendências com o dono da operação

- [x] Rótulos: **Ótima · Normal · Razoável · Mínima** (§2).
- [x] O veto é só de segurança alimentar; cosmético nunca veta (§3).
- [x] Fuligem e marcas são a mesma coisa: `scorch_marks`.
- [x] Fornada Ótima com unidades fora **dispara**, com piso `quality_min_share` (§8).
- [x] Fora de tamanho por peso/divisão cai em `misshapen`; sem código próprio.
- [x] Piso inicial de `quality_min_share`: **90**.
- [x] Fornada **Ótima com unidades fora** dispara broadcast ou exige fornada limpa?
      Decidido: dispara, com piso `quality_min_share` (ver §8 e ADR-017 §6);
      ausente = 100% (fornada limpa), seed em 90.
