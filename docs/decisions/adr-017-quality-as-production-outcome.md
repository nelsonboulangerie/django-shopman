# ADR-017 - Qualidade e o resultado da producao: nao e dominio novo

**Status:** Proposto
**Data:** 2026-08-07
**Escopo:** `craftsman` core, `craftsman.contrib.stockman`, `shopman/shop` (politica), `stockman` (nenhuma mudanca)
**Supersede parcialmente:** o §6.2 e o §9 de `docs/plans/QC-FORNADA.md`, que recomendavam uma FK `WorkOrder -> Batch`

---

## Contexto

A padaria precisa declarar, ao fechar a fornada, que **parte** dela saiu fora do padrao,
com que severidade e por que. O desenho de produto esta fechado em
`docs/plans/QC-FORNADA.md`. Falta a decisao arquitetural: **onde isso mora**.

A pergunta que originou este ADR foi se "Quality" deveria ser pacote, addon ou contrib.

Tres fatos do codigo delimitam a resposta.

**Primeiro: o fato do lote ja esta modelado e decidido.** A Onda 14 (`ea429d14`) entregou
`Batch.nonconformity_reason` + `nonconformity_percent`, com tres consequencias amarradas a um
unico fato — preco (`lot_pricing.percent_for_lot`), destino (`_write_off_nonconforming`) e
visibilidade (`ChannelConfig.stock.sells_nonconforming`). Nada disso precisa mudar.

**Segundo: o fato da fornada esta escondido num JSONField.** `WorkOrder.meta["quality"]`
guarda uma string de tres valores, sem coluna, sem historico, sobrescrita a cada finish. O
proprio codigo se declara atalho (`backstage/services/production.py:151`, *"sem migracao"*), e
o literal esta duplicado entre `broadcast.QUALITY_LEVELS` e `production.QUALITY_CHOICES`. A
constituicao ja julgou esse padrao (§2.5): *"Se um pacote usa `JSONField` para esconder seu
contrato real, ele ainda nao terminou sua semantica."*

**Terceiro: `WorkOrder.finished` e um escalar onde o dominio tem uma particao.** Uma fornada de
40 nao produz "38". Produz *32 a preco cheio, 8 com desconto, 3 de perda*. O escalar e a soma
de uma particao que o `finish()` ja sabe receber — `execution.py:197-220` aceita
`finished=[{item_ref, quantity, unit}]` — mas que a superficie nunca usou, e que perde o
`meta` no caminho (o ramo de `wasted` passa `meta`, o de `finished` nao).

---

## Decisao

### 1. Nao existe pacote `quality`, nem contrib `quality`

Aplicando a constituicao §8.3 ("isto e core do dominio? plugin do dominio? conveniencia de
framework?"), a resposta e **os tres, em camadas diferentes** — e nenhuma delas e um dominio
novo.

Um pacote `quality` precisaria depender de `craftsman` **e** de `stockman` para existir, o que
`test_kernel_packages_do_not_import_host_layers` e a ADR-001 barram. E criaria um **terceiro
dono** para um fato que ja tem dois — exatamente o erro que a ADR-011 nomeou ao recusar
`FormulaPlan`: *"introduziria um segundo source of truth para o mesmo fato operacional."*

Um contrib `craftsman.contrib.quality` **com models** poria a escala de uma padaria dentro de
um pacote core, contra a constituicao §2.6: *"Nenhum pacote core pode nascer semanticamente
dependente de uma instancia especifica."*

Qualidade nao e uma pergunta canonica propria. E **metade da resposta a uma pergunta que o
`craftsman` ja faz**: *"o que deve ser produzido... e com qual resultado real?"* (constituicao
§4.3). O `craftsman` ja responde a quantidade do resultado. Falta responder a natureza dele.

### 2. Craftsman core ganha tres colunas opacas em `WorkOrderItem`

```python
quality_grade_ref  = models.CharField(max_length=32,  blank=True, db_index=True)
quality_defect_ref = models.CharField(max_length=32,  blank=True, db_index=True)
batch_ref          = models.CharField(max_length=100, blank=True, db_index=True)
```

Os dois primeiros levam o prefixo `quality_` de proposito: sao um **par**, respondem a mesma
pergunta em dois eixos (*quanto* desviou e *por que*), e `grep quality_` acha a feature
inteira. `batch_ref` **nao** leva o prefixo porque nao e qualidade — e rastreabilidade, e
existe mesmo em fornada perfeita. A assimetria e informacao, nao descuido.

`grade` (grau) e o termo canonico de QC em manufatura e alimentos, e traduz 1:1 o "grau" que a
operacao ja fala. Sozinho seria ambiguo — *grau de que?* — dai o prefixo. `defect` e mais
preciso que `reason` para o que esta sendo catalogado: um **tipo nomeado de falha**, com veto
proprio. "Motivo" e a pergunta; o defeito e a resposta. O label do defeito e o que alimenta o
`Batch.nonconformity_reason`, que nao muda.

**O core nunca interpreta esses valores.** Nao sabe que `minimal` vale menos que `standard`,
nao sabe que `contaminated` obriga descarte, nao conhece percentual. Sao ponteiros string no formato
da ADR-004, validados na borda pelo framework. Um torrefador de cafe instala o mesmo
`craftsman` com outra escala.

Sao colunas e nao chaves de `meta` porque passam os quatro criterios do ADR-006 arquivado —
historico, auditoria, query indexada e cardinalidade > 1. O relatorio precisa de
`GROUP BY quality_grade_ref` e `GROUP BY quality_defect_ref` por forno, receita e operador; chave de JSON nao
tem indice.

`finish()` passa a repassar `meta` tambem no ramo de `finished` — hoje so `wasted` recebe.
E uma linha, e e a assimetria que impedia a particao de carregar informacao.

### 3. `WorkOrder.meta["quality"]` e removido, nao promovido

A qualidade da fornada passa a ser **derivada** das linhas de OUTPUT, nao armazenada. Nao ha
campo novo em `WorkOrder`. Isso mata o segundo source of truth em vez de institucionaliza-lo,
e o `on_production_changed` roda em `transaction.on_commit`, depois das linhas gravadas —
logo o contexto do broadcast pode ler os itens.

### 4. `stockman` nao muda. A particao de lote nao e mecanismo novo

Duas linhas de OUTPUT com `batch_ref` diferente sao dois `Batch`. O split de lote e
**consequencia** de `finish()` receber uma lista, nao uma capacidade a construir. O trabalho
esta em `craftsman/contrib/stockman/handlers.py`, o contrib que **ja existe** — nenhum contrib
novo.

### 5. Nao existe FK `WorkOrder -> Batch`. O elo e `batch_ref` na linha certa

**Esta decisao corrige o §6.2 de `QC-FORNADA.md`, que estava errado.** A ADR-004 e explicita:
ponteiros cross-domain sao `CharField` indexado, *nunca* FK nem `GenericForeignKey`.
`WorkOrder` e craftsman, `Batch` e stockman: FK ali violaria a fronteira que
`test_import_boundaries` protege, e faria `craftsman` deixar de instalar sozinho.

O problema real nunca foi a ausencia de FK. Era que o `batch_ref` e **derivado por formula de
string** (`f"{sku}-{date}-{wo.pk}"`, `production.py:481`) e guardado em `WorkOrder.meta` — no
agregado, nao na linha que corresponde ao lote. Formula derivada so admite um lote por ordem;
por isso a particao parecia impossivel. Guardando `batch_ref` na linha de OUTPUT, N grupos
viram N lotes sem inventar nada.

### 6. A politica mora no framework, em dois catalogos pequenos

Em `shopman/shop/models/quality.py`, editaveis no Admin:

```python
class QualityGrade(models.Model):
    ref              = CharField(unique=True)   # excellent | standard | fair | minimal
    label            = CharField()              # "Otima" | "Normal" | "Razoavel" | "Minima"
    rank             = IntegerField(unique=True)  # maior = melhor
    markdown_percent = PositiveSmallIntegerField(default=0)
    is_default       = BooleanField(default=False)   # unique parcial

class QualityDefect(models.Model):
    ref             = CharField(unique=True)    # underbaked | overbaked | misshapen | ...
    label           = CharField()               # "Palido / cru" | "Escuro / queimado" | ...
    hint            = CharField(blank=True)     # "pequeno, denso, rasgou" — o sintoma
    forces_discard  = BooleanField(default=False)
    position        = IntegerField(default=0)
    is_active       = BooleanField(default=True)
```

O catalogo inicial, com um par que prova a regra do eixo unico:

| Rotulo | `ref` | Veto |
|---|---|---|
| Fermentou pouco | `underproofed` | |
| Fermentou demais | `overproofed` | |
| Assou pouco | `underbaked` | |
| Assou demais | `overbaked` | |
| Deformado | `misshapen` | |
| Marcas de forno | `scorch_marks` | |
| Contaminado | `contaminated` | **sim** |

Um **2x2 mais tres**: dois processos (fermentacao e forno), cada um com dois sentidos. Nenhum
dos quatro carrega severidade — "escuro" e "queimado" sao o mesmo defeito em graus diferentes:
`overbaked` em Razoavel e escuro, `overbaked` em Minima e queimado. A palavra nao muda quando a
severidade muda. E a demonstracao de que o eixo unico funciona.

O catalogo nomeia **causa**, nao sintoma: "pequeno" nao ensina nada num relatorio, e a causa
quase sempre e fermentacao — que pode ter faltado ou sobrado. O custo e uma inferencia a mais
para o operador, pago com uma segunda linha de dica no botao (`hint`), que devolve o sintoma:
`underproofed` -> *"pequeno, denso, rasgou"*. Por isso `QualityDefect` ganha um campo `hint`.

`QualityGrade.rank` **substitui** `QUALITY_LEVELS`, encerrando o literal duplicado.
`BroadcastRule.trigger_filter.quality_min` passa a comparar `rank` — a producao continua
emitindo e o marketing continua decidindo (ADR-001: efeito fire-and-forget e signal).

Fornada otima **com** unidades fora dispara, com piso: `trigger_filter` ganha a chave irma
`quality_min_share` (inteiro 0-100). A conta e *unidades em grau >= `quality_min` dividido pela
quantidade prevista*, limitada a 100 — o previsto e o denominador de proposito, para que a
perda pese. **Ausente significa 100%**, isto e, fornada limpa: o default falha para o lado
seguro, e afrouxar e decisao consciente do marketing. Zero model novo, zero migration: o campo
ja e JSONField anunciando condicoes extras. Valor inicial no seed: **90**.

`forces_discard` e **veto, nao preco**. Defeito com essa marca manda as unidades para
`wasted`, nunca para um lote com desconto. Preserva o eixo unico: quem define preco e so o grau.

**O veto e so para o que torna o alimento inseguro, nunca para o que o torna feio.** Sujeira de
forno, fuligem e marcas sao defeitos **cosmeticos**: vendem com desconto. Tentar limpa-los pode
danificar o produto, e essa e uma decisao de quem esta com o pao na mao — o sistema nao pode
tomar por ele. So contaminacao real (materia estranha, qualquer coisa que torne o pao
incomivel) carrega o veto. Isso torna `forces_discard` raro e inequivoco, em vez de uma
categoria com a qual o operador discute.

### 7. O grau e o input; o percentual e o fato — e ele congela no lote

Isto reconcilia a tensao entre `business-rules.md` (*"Nao ha constante de percentual em lugar
nenhum. O valor e do LOTE, escrito por quem inspecionou"*) e `QC-FORNADA.md` (*"o grau define
o desconto"*).

No finish, o framework resolve `QualityGrade.markdown_percent` e **grava o numero resolvido**
em `Batch.nonconformity_percent`. A partir dai o lote carrega o proprio percentual. Mudar a
tabela amanha nao reescreve os lotes de ontem.

Nao ha constante em codigo (virou config) e o lote continua dono do numero (virou snapshot,
constituicao §3.3). `percent_for_lot` nao muda em uma linha: continua arbitrando
`max(automatic, declared)`.

### 8. Os numeros nao vao para um B.I.

Confirmando o que ja estava decidido em `BACKSTAGE-EXCELLENCE-HARDENING-PLAN.md` §9 e nos
commits de 2026-07-17: nao ha app de B.I., tabela de agregacao, snapshot ou grafico. O fato
vai para o ledger imutavel (`WorkOrderEvent.payload` ganha a particao), a consolidacao do dia
para `DayClosing.data`, e a leitura para um `report_kind` novo em `build_production_reports`.
Um app de B.I. permanece frente separada.

---

## Consequencias

### Positivas

- Nenhum pacote novo, nenhum contrib novo, nenhum model no core.
- Craftsman fica **mais** agnostico: passa a expressar particao de resultado, capacidade
  generica de manufatura que faltava (constituicao §4.3 lista "falta uma linguagem oficial para
  perdas, rendimento" como desalinhamento atual).
- Some um source of truth (`meta["quality"]`) e some um literal duplicado (`QUALITY_LEVELS`).
- O split de lote deixa de ser feature e vira consequencia de uma chamada.
- A escala fica editavel no Admin sem tocar codigo, como o dono pediu.
- `stockman`, `lot_pricing`, `closing` e o gate de canais remotos: zero mudanca.

### Negativas

- Tres colunas novas em `WorkOrderItem` e uma migration em pacote core.
- Renomear `regular|bom|excelente` para ingles exige data migration em `WorkOrder.meta` e em
  `BroadcastRule.trigger_filter`.
- Derivar a qualidade da fornada custa uma query a mais no handler de broadcast.
- `_record_batch_traceability` e best-effort (`except Exception` que so loga). Se passar a
  criar N lotes, a falha silenciosa fica mais cara — precisa virar alerta de operador.

### Mitigacoes

- A janela e agora: **`go-live-v1` nao existe** (`git tag -l`; o mais avancado e
  `v0.1.0-alpha`). A ADR-015 so entra em vigor na tag, entao o rename ainda e barato. Depois do
  alpha, o mesmo rename exige expand-contract com janela de alias.
- `finish()` mantem o ramo escalar: `finish(finished=38)` continua valido e grava uma linha
  sem `grade_ref`. Nenhum chamador atual quebra.
- Falha em `_record_batch_traceability` passa a emitir `OperatorAlert`, nao so log.

---

## Invariantes

- Nao existe pacote `quality`, nem contrib `quality`.
- Nao existe FK entre `WorkOrder` e `Batch`. O elo e `WorkOrderItem.batch_ref`.
- O core do `craftsman` nunca interpreta `quality_grade_ref` nem `quality_defect_ref`: nao
  ordena, nao compara, nao converte em percentual.
- `forces_discard` marca apenas seguranca alimentar. Defeito cosmetico nunca leva veto.
- Nao existe campo de qualidade em `WorkOrder`. A qualidade da fornada e derivada das linhas.
- `previsto = soma(OUTPUT) + soma(WASTE)`. Os grupos sao disjuntos por construcao.
- Quem define preco e so o grau. `forces_discard` e veto, nunca percentual.
- `Batch.nonconformity_percent` e escrito no finish e nunca reescrito por mudanca de catalogo.
- Motivo vazio em `Batch` continua significando lote conforme — ter motivo e ser.
- Percentual de grau vive em `QualityGrade`, nunca em constante de codigo.

---

## Migracao

Ordem obrigatoria; cada passo entrega valor sozinho e passa `make test`.

1. **Colunas + `meta` no OUTPUT.** Migration em `craftsman` com os tres `CharField` e a linha
   que repassa `meta` no ramo `finished`. Nada consome ainda.
2. **Catalogos.** `QualityGrade` e `QualityDefect` em `shopman/shop`, com data migration de
   seed nos quatro graus e nos sete defeitos, e Admin.
3. **Rename para ingles.** `excelente -> excellent`, `bom -> standard`, `regular -> fair`;
   `minimal` nasce novo. Data migration cobrindo `WorkOrder.meta["quality"]` e
   `BroadcastRule.trigger_filter["quality_min"]`. `QUALITY_LEVELS` e `QUALITY_CHOICES` sao
   apagados; `rank` passa a ser a hierarquia. (`regular` vira `fair`, o degrau menos punitivo,
   para nao aprofundar desconto retroativo.)
4. **Particao no finish.** `apply_finish` aceita grupos; resolve `forces_discard` antes de
   chamar `craft.finish()` (unidades vetadas viram `wasted`); `set_quality` e removido.
5. **N lotes.** `_record_batch_traceability` cria um `Batch` por linha de OUTPUT com
   `batch_ref` proprio, gravando `nonconformity_reason` (label do motivo) e
   `nonconformity_percent` (resolvido do grau) nos grupos com desconto. Falha vira
   `OperatorAlert`.
6. **Broadcast.** Contexto deriva a qualidade das linhas; `quality_min` compara `rank`.
7. **Ledger.** `WorkOrderEvent.payload` do `finished` passa a carregar a particao.
8. **Leitura.** `report_kind="quality"` em `build_production_reports` e consolidacao no
   `DayClosing.data`.
9. **Superficie.** Quiosque em `production-nuxt` consumindo Projection frozen (ADR-012/014):
   `label` e copy ficam em `presentation/`, a Projection carrega `ref` e `rank`.

---

## Criterios de aceite

- `pip install shopman-craftsman` em venv limpo + `make test-craftsman` passa sem
  `shopman.shop` instalado.
- `test_import_boundaries` e `test_architecture` verdes sem excecao nova.
- `make test-migrations` verde: schema limpo do zero e grafo consistente.
- Nenhum `grep` em `packages/craftsman` retorna `percent`, `discard` ou nome de grau/defeito.
- `grep -r "QUALITY_LEVELS\|QUALITY_CHOICES\|meta\[.quality.\]"` retorna vazio.
- Fornada de 40 com 32 padrao + 8 minima + 3 perda gera 2 `Batch`, 3 `WorkOrderItem`
  (2 OUTPUT + 1 WASTE) e um `WorkOrderEvent` com a particao no payload.
- Defeito com `forces_discard` nunca produz `Batch` com `nonconformity_percent > 0`.
- `quality_min_share` ausente se comporta como 100: fornada com qualquer unidade fora nao
  dispara ate alguem afrouxar explicitamente.
- Alterar `markdown_percent` de um grau nao muda `nonconformity_percent` de lote ja gravado.
- Lote com desconto nao aparece em canal remoto nem sobrevive ao fechamento.

---

## Alternativas descartadas

**Pacote `shopman-quality`.** Dependeria de dois cores; barrado pela ADR-001 e pelo teste de
fronteira. Terceiro dono de um fato que ja tem dois (ADR-011).

**Contrib `craftsman.contrib.quality` com models.** Poe politica de instancia dentro de pacote
core (constituicao §2.6). E as superficies nao podem importar `contrib.<x>` diretamente
(`test_import_boundaries:152`), entao exigiria reexport de nivel de pacote so para escapar da
propria fronteira — sinal de que a camada esta no lugar errado.

**Campo `quality` em `WorkOrder`.** Promove o JSONField a coluna sem resolver o problema: a
qualidade e por grupo, nao por ordem. Uma coluna no agregado obrigaria a escolher qual grupo
representa a fornada, e a escolha teria que ser reimplementada em todo consumidor.

**Escala de graus como `RuleConfig`.** Tentador — reusa Admin e o parser de textarea pt-BR. Mas
o percentual do grau nao participa da resolucao de preco na venda: ele e resolvido **uma vez**,
no finish, e congela no lote. Nao e regra de pricing, e tabela de politica de QC. Poe-la no
motor de regras faria `percent_for_lot` parecer ter duas fontes quando tem uma.

**Defeito com percentual proprio.** Recusado pelo dono e mantido: o defeito teria que ser
decidido junto com um preco toda vez que a padaria inventasse uma palavra nova. Um eixo so.
`underbaked`/`overbaked` mostram por que: o mesmo defeito vale −20% ou −50% conforme o grau.

**`grade_ref` e `reason_ref` sem prefixo.** Mais curtos, mas `grade` sozinho nao diz *grau de
que*, e `reason` nao diz que ha um catalogo curado por tras. O prefixo `quality_` custa oito
caracteres e faz `grep quality_` devolver a feature inteira.

**"Aceitavel" para o degrau de −20%.** Descartado por sobreposicao: "aceitavel" nomeia a
**fronteira inferior** do que se aceita — que e exatamente o que "Minima" ja e. Usa-lo no
degrau do meio faria dois nomes disputarem o mesmo lugar da escala, e o degrau de baixo
tambem e aceitavel (ele e vendido). "Razoavel" nomeia um **meio**, nao uma fronteira.
"Plausivel" e "viavel" foram descartados por categoria: qualificam proposicoes e planos, nao
objetos. "Admissivel" ordena bem, mas e registro de engenharia para uma tela de 5h da manha.

---

## Referencias

- [Constituicao Semantica](../constitution.md) — §2.1, §2.5, §2.6, §3.3, §8.3
- [ADR-001 - Protocol/Adapter e fronteiras de core](adr-001-protocol-adapter.md)
- [ADR-004 - String refs para identificadores cross-domain](adr-004-string-refs.md)
- [ADR-011 - Formula sem FormulaPlan](adr-011-formula-and-cashshift.md)
- [ADR-012 - Contrato headless de superficie](adr-012-headless-surface-contract.md)
- [ADR-015 - Backward-compat pos-producao](adr-015-backward-compat-policy-post-prod.md)
- [QC da fornada - desenho de produto](../plans/QC-FORNADA.md)
- [Regras de negocio - a fornada nao conforme](../business-rules.md)
