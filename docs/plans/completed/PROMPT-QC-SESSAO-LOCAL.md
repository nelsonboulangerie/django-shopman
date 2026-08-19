# Prompt — QC de fornada (sessão local)

> ✅ **ENTREGUE. Não execute por este documento.** A ADR-017 está Aceita e implementada
> (passos 1 a 8 no PR #143, passo 9 em `feat/qc-kiosk`). O código vive em
> `shopman/shop/admin/quality.py` e a partição do QC já chega ao fechamento do dia.
> Guardado como registro de como o trabalho foi encomendado.

Vamos implementar o controle de qualidade da fornada (QC) no Django Shopman. A decisão
arquitetural já está tomada e aprovada; sua tarefa é executá-la. Abra branch nova
(`feat/quality-partition`) a partir do HEAD atual.

---

# 1. Onde está tudo

Neste repositório, já commitado:

- `docs/decisions/adr-017-quality-as-production-outcome.md` — **a decisão**. Status: aprovada
  pelo dono. A seção "Migração" tem os 9 passos na ordem; a seção "Criterios de aceite" é o
  seu checklist final; a seção "Invariantes" é o que você não pode quebrar.
- `docs/plans/QC-FORNADA.md` — **o desenho de produto**: a escala, os defeitos, a aritmética,
  o layout do quiosque, e o porquê de cada nome ter sido escolhido e os outros rejeitados.
- `qc-passos-1-2.patch` (na raiz) — os passos 1 e 2 já implementados.

Leia a ADR e o plano **inteiros** antes de tocar em código. Eles têm o raciocínio; este prompt
tem só o resumo.

---

# 2. Antes de propor qualquer coisa: a doutrina

Esta suite tem lei escrita, e ela venceu discussões neste próprio trabalho — inclusive
derrubou uma recomendação minha. Leia:

1. `docs/constitution.md` — canônica. §2.1 (o core deve ser pequeno), §2.2 e §5.2 (nomes de
   compromisso, não de implementação), §2.5 (estado × evento × snapshot × metadata; *"se um
   pacote usa JSONField para esconder seu contrato real, ele ainda não terminou sua
   semântica"*), §2.6 (default de instância não contamina o core), §3.3, §8.3 (as três
   perguntas que toda extensão precisa responder).
2. `docs/decisions/` — ADRs obrigatórias aqui: **001** (fronteiras de package; signal ×
   protocol; quando nasce contrib), **004** (ponteiro cross-domain é `CharField` indexado,
   **nunca** FK nem `GenericForeignKey`), **006 arquivada** (quando um fato merece tabela em
   vez de JSON: histórico, auditoria, query indexada, cardinalidade > 1), **011** (não crie
   segundo source of truth; e o playbook de rename), **012/014** (Projection carrega dado e
   semântica; Presentation carrega copy e formatação), **015** (backward-compat pós-produção).
3. `CLAUDE.md` — convenções ativas, "Core é Sagrado", "O Que NÃO Fazer".
4. `docs/business-rules.md` §6.3 — a fornada não conforme, já implementada na Onda 14.

---

# 3. O que já está decidido (não reabra sem argumento novo)

## A tese central

**Qualidade não é domínio novo.** Não existe pacote `quality`, não existe contrib `quality`.
Um pacote precisaria depender de `craftsman` **e** de `stockman`, o que a ADR-001 e o
`test_import_boundaries` barram; e criaria um terceiro dono para um fato que já tem dois.

Qualidade é a metade que falta de uma pergunta que o `craftsman` já faz: *"o que deve ser
produzido… e com qual resultado real?"*. Ele já responde a quantidade; falta a natureza.

**`WorkOrder.finished` é um escalar onde o domínio tem uma partição.** Uma fornada de 40 não
produz "38" — produz *32 a preço cheio, 8 com desconto, 3 de perda*. E `craft.finish()` **já
aceita lista** (`packages/craftsman/shopman/craftsman/services/execution.py:197-220`); a
superfície nunca usou. O split de lote não é feature a construir: é consequência de uma
chamada.

## A escala (4 graus)

| Rótulo (Admin, editável) | `ref` (fixo) | Preço | Dia seguinte | Broadcast |
|---|---|---|---|---|
| Ótima | `excellent` | cheio | vai | **dispara** |
| Normal *(padrão)* | `standard` | cheio | vai | não |
| Razoável | `fair` | −20% | **não vai** | não |
| Mínima | `minimal` | −50% | **não vai** | não |

"Mínima" é o piso: abaixo dela não existe grau, existe descarte. Rejeitados e por quê está no
plano §2 — não reabra "Aceitável" para o degrau do meio (ele nomeia a fronteira inferior, que
é o que "Mínima" já é).

## Os defeitos (2×2 + três)

| Rótulo | Sintoma (`hint`) | `ref` | Veto |
|---|---|---|---|
| Fermentou pouco | pequeno, denso, rasgou | `underproofed` | |
| Fermentou demais | murchou, achatou | `overproofed` | |
| Assou pouco | pálido, cru | `underbaked` | |
| Assou demais | escuro, queimado | `overbaked` | |
| Deformado | torto, colado, fora de tamanho | `misshapen` | |
| Marcas de forno | fuligem, manchas | `scorch_marks` | |
| Contaminado | matéria estranha | `contaminated` | **sim** |

Dois processos, dois sentidos cada. **Nenhum carrega severidade**: `overbaked` em Razoável é
escuro, `overbaked` em Mínima é queimado — a palavra não muda quando a severidade muda. Por
isso não existe defeito `burnt`.

O `hint` é a segunda linha do botão no quiosque. Ele existe porque nomear pela causa cobra uma
inferência que nomear pelo sintoma não cobra — sem ele, quem não distinguir vai chutar, e
chute vira o ruído que o QC existe para evitar.

## As duas regras que não se misturam

- **Quem define preço é só o grau.** Defeito não tem percentual, de propósito: se tivesse,
  cada palavra nova que o fournil inventasse viraria decisão de precificação.
- **`forces_discard` é veto, não preço** — e **só para o que torna o alimento inseguro, nunca
  para o que o torna feio**. Marcas e fuligem vendem com desconto; tentar limpar às vezes
  danifica o produto, e essa decisão é de quem está com o pão na mão.

## A aritmética

```
previsto = a preço cheio + com desconto + perda
```

Três grupos **disjuntos por construção**. O campo principal da tela do operador é "a preço
cheio", não "saíram do forno" — com o rótulo errado o modelo conta o mesmo pão duas vezes
(plano §4). O que não sai do forno é **perda**, e perda pede motivo: o rendimento da massa já
foi resolvido em etapas anteriores, então o previsto que chega ao forno é quente.

## O grau é input; o percentual é fato, e congela

No finish, o framework resolve `QualityGrade.markdown_percent` e **grava o número** em
`Batch.nonconformity_percent`. Mudar a tabela amanhã **não** reescreve os lotes de ontem.
Isso reconcilia `business-rules.md` (*"não há constante de percentual em lugar nenhum"*) com a
tabela de graus: a constante virou config, e o lote continua dono do número.

## O elo `WorkOrder ↔ Batch` **não** é FK

A ADR-004 proíbe. O elo é `WorkOrderItem.batch_ref` (string ref, na linha que corresponde ao
lote). O problema nunca foi a ausência de FK: era o `batch_ref` ser derivado por fórmula de
string (`f"{sku}-{data}-{wo.pk}"`) e guardado em `WorkOrder.meta`, no agregado. Fórmula
derivada só admite **um** lote por ordem — era isso que fazia a partição parecer impossível.

## Broadcast

`BroadcastRule.trigger` já tem `production_finished` e `trigger_filter` já aceita
`quality_min` — a arquitetura está certa, a produção **emite** e o marketing **decide**. Falta
a fornada informar o grau de verdade, e a escala ir de três para quatro níveis.

Fornada Ótima **com** unidades fora dispara, com piso: chave irmã `quality_min_share` no
`trigger_filter`. Conta = unidades em grau ≥ `quality_min` ÷ quantidade **prevista**, limitado
a 100. **Ausente = 100%** (fornada limpa) — o default falha para o lado seguro. Seed em 90.

## B.I. não existe, e é intencional

Nenhuma tabela de agregação, snapshot, warehouse ou gráfico. Decisão reafirmada e registrada.
Fato vai para ledger imutável (`WorkOrderEvent`, `Move`), consolidação para `DayClosing.data`,
leitura vira `report_kind` numa projection existente. Se você achar que BI é necessário, trate
como frente separada e diga isso — não construa.

---

# 4. Passos 1 e 2 — já feitos, vêm como patch

`qc-passos-1-2.patch` na raiz contém:

**`craftsman`** — `WorkOrderItem` ganha `quality_grade_ref` (32), `quality_defect_ref` (32) e
`batch_ref` (100), todos `blank=True, db_index=True`, mais dois índices compostos com
`recorded_at` (+ migration `0010`). E `finish()` passa a repassar `meta` também no ramo de
`finished` — hoje só `wasted` recebe, e essa assimetria era o que impedia a partição de
carregar informação. Helper `_group_fields()`. Mais `test_quality_partition.py` (9 testes).

**`shopman/shop`** — models `QualityGrade` e `QualityDefect` em `models/quality.py`, Admin em
Unfold (`admin/quality.py`), migrations `0034` (schema) e `0035` (seed dos 4 graus e 7
defeitos), e `test_quality_catalogs.py` (16 testes).

**Aplique com `git am --3way qc-passos-1-2.patch`.**

**Se der conflito, NÃO force.** O patch veio de um checkout que pode estar defasado deste.
Leia o patch como **especificação** e reimplemente à mão — o conteúdo importa, o diff não.

Depois: `make test-craftsman` (esperado 252 passed) e
`pytest shopman/shop/tests/test_quality_catalogs.py` (16 passed), mais `make test-migrations`.

Duas escolhas minhas nesse patch que você pode questionar: `QualityDefect.clean()` recusa
desativar um defeito com veto (evita que "Contaminado" vire silenciosamente defeito comum), e
`QualityGrade.is_default` tem constraint parcial única (trocar o padrão exige tirar o antigo
primeiro — chato de propósito, porque dois padrões seria pior).

---

# 5. Passos 3 a 9 — o que falta

### 3. Rename dos valores de qualidade para inglês — **faça cedo, tem janela**

`excelente→excellent`, `bom→standard`, `regular→fair`; `minimal` nasce novo. Data migration
cobrindo `WorkOrder.meta["quality"]` e `BroadcastRule.trigger_filter["quality_min"]`. Apagar
`QUALITY_LEVELS` (`shopman/shop/models/broadcast.py:45`) e `QUALITY_CHOICES` +
`DEFAULT_QUALITY` (`shopman/backstage/services/production.py:147`) — o literal está duplicado
entre os dois. `QualityGrade.rank` passa a ser a única hierarquia.

**A janela:** confira `git tag -l`. Se `go-live-v1` não existir, a ADR-015 ainda não vigora e
o rename é barato. Depois do alpha vira expand-contract com janela de alias, para sempre.
(`regular` vira `fair`, o degrau menos punitivo, para não aprofundar desconto retroativo.)

### 4. Partição no finish

`apply_finish` (`shopman/backstage/services/production.py:175`) passa a aceitar grupos.
Resolve `forces_discard` **antes** de chamar `craft.finish()`: unidades com defeito vetado vão
para `wasted`, nunca para lote com desconto. `set_quality` (`:151`) é **removido** — a
qualidade da fornada passa a ser derivada das linhas de OUTPUT, não armazenada. Não crie campo
novo em `WorkOrder`.

### 5. N lotes

`_record_batch_traceability` (`production.py:463`) cria um `Batch` por linha de OUTPUT, com
`batch_ref` próprio, gravando `nonconformity_reason` (o label do defeito) e
`nonconformity_percent` (resolvido do grau) nos grupos com desconto. Hoje a função inteira está
num `except Exception` que só loga; criando N lotes isso fica caro, então a falha passa a
emitir `OperatorAlert`.

### 6. Broadcast

`shopman/shop/handlers/broadcast.py` deriva a qualidade das linhas em vez de ler
`meta["quality"]`; `_quality_at_least` (`shop/services/broadcast.py:143`) passa a comparar
`rank`; entra `quality_min_share` conforme §3 acima.

### 7. Ledger

`WorkOrderEvent.payload` do `finished` passa a carregar a partição (hoje leva
`finished_qty`, `planned_qty`, `started_qty`, `loss_qty`). É daqui que o relatório é
reconstruível.

### 8. Leitura

`report_kind="quality"` em `build_production_reports`
(`shopman/backstage/projections/production.py:1100`) — por receita, por forno e por operador,
com os defeitos agregados. E consolidação no `DayClosing.data`.

⚠️ Dois bugs conhecidos e adjacentes, conserte se estiver por perto: `production_summary` no
`DayClosing.data` usa `int(...)` e **trunca fracionários**; e `capacity_utilization` em
`_recipe_waste_rows` (`projections/production.py:1489`) é **sempre string vazia**.

### 9. Quiosque em `surfaces/production-nuxt`

O layout está descrito com medições em `QC-FORNADA.md` §5. O essencial:

- **Duas telas.** Painel de ordens do dia (não catálogo de SKU — a ordem já traz forno,
  horário e previsto, e é o previsto que faz a fornada normal fechar em poucos toques), e a
  tela de QC.
- **O numpad é âncora.** Da barra do topo até o `⌫`, altura fixa em todos os estados. O painel
  de defeitos abrindo no meio da tela empurrava o numpad no primeiro dígito de um número de
  dois dígitos — o operador erra e não sabe por quê.
- **Dois campos numéricos lado a lado** ("a preço cheio" / "quantas assim"), sempre visíveis; o
  da direita apagado enquanto o grau for Ótima/Normal.
- **A escala é coluna à direita do numpad**, como a coluna de operadores de uma calculadora.
  Faixa de cor contínua na borda esquerda. Vão maior entre numpad e coluna do que entre teclas.
- **Defeitos em bottom sheet**, não banner. `Confirmar` fica sempre ativo e significa "fechar a
  fornada": se falta um motivo, ele pergunta, um de cada vez, e fecha na resposta — assim o
  sheet não custa toque nenhum.
- Reaproveite o `PosNumpad` do PDV. Projection frozen + Presentation, ADR-012/014: a Projection
  carrega `ref` e `rank`, os labels e a copy ficam em `presentation/`.

---

# 6. Regras duras

- **Código só em inglês**: nome de model, campo, value de `TextChoices`, chave de JSON,
  setting, codename de permission. `verbose_name`, `label`, `help_text` e mensagem de operador
  **em português**. Violar isso invalida a entrega.
- **Um passo por commit**, e cada passo passa `make test` sozinho antes do próximo.
- **O core do `craftsman` nunca interpreta** `quality_grade_ref` nem `quality_defect_ref`: não
  ordena, não compara, não converte em percentual, não conhece percentual. Há testes
  protegendo isso. Se precisar afrouxá-los, **pare e pergunte**.
- `previsto = soma(OUTPUT) + soma(WASTE)`.
- `Batch.nonconformity_percent` é escrito no finish e **nunca** reescrito por mudança de
  catálogo.
- Motivo vazio em `Batch` continua significando lote conforme — **ter motivo é ser**.
- Não crie pacote novo, contrib novo, nem model no core. Não crie FK cross-domain.
- Cite **arquivo:linha** para toda afirmação sobre o código. Nada de "provavelmente".
- Tudo deve ser **simples, robusto e elegante**. Semântica antes de conveniência.

---

# 7. Como trabalhar comigo

- Rode o **raio de impacto** durante a implementação (produção, broadcast, fechamento,
  qualidade — leva menos de um minuto) e deixe a bateria completa para uma passada no fim. Não
  rode a suíte inteira a cada passo.
- Nunca rode dois `pytest` ao mesmo tempo: eles brigam pelo mesmo banco de teste e o resultado
  vira lixo.
- Ao fim de cada passo, me diga em poucas linhas: o que mudou, o resultado dos testes, e
  **qualquer ponto onde o código real divergiu do que a ADR previa**. Esse último item é o mais
  valioso.
- Me pergunte quando a decisão for minha. **Discorde de mim com argumento e evidência quando eu
  estiver errado** — as melhores decisões deste projeto vieram de push-back, inclusive a
  correção de uma recomendação errada que já estava escrita na primeira versão da ADR.

---

# 8. Ainda em aberto

- **`hint` do defeito**: a lista de sintomas foi proposta por mim, não pela equipe. Se o
  pessoal do fournil descrever diferente, o texto muda — é campo de Admin.
- **Fuligem × marcas**: hoje são o mesmo defeito (`scorch_marks`). Se a equipe distinguir na
  prática, separar é um registro no Admin.
- **`quality_min_share` = 90** é o valor inicial. Numa fornada de 40 são 4 unidades de folga;
  numa de 24, só 2 — percentual é mais duro em fornada pequena. Se incomodar na prática, me
  avise em vez de trocar por contagem absoluta (que não escala entre receitas).

---

Comece lendo a ADR-017 e o `QC-FORNADA.md`, aplique o patch, confirme o verde, e me diga o que
encontrou antes de seguir para o passo 3.
