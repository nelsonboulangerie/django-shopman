# Handoff — implementar a ADR-017 (QC de fornada) localmente

> ✅ **ENTREGUE. Não execute por este documento.** A ADR-017 está Aceita e implementada
> (passos 1 a 8 no PR #143, passo 9 em `feat/qc-kiosk`). O código vive em
> `shopman/shop/admin/quality.py` e a partição do QC já chega ao fechamento do dia.
> Guardado como registro de como o trabalho foi encomendado.

Cole o bloco abaixo como primeira mensagem da sessão de código local.

---

```
Vamos implementar a ADR-017 — controle de qualidade da fornada. Abra branch nova
(`feat/quality-partition`) a partir do HEAD atual.

## Contexto

A decisão arquitetural está fechada e aprovada em
`docs/decisions/adr-017-quality-as-production-outcome.md`, e o desenho de produto em
`docs/plans/QC-FORNADA.md`. Os dois já estão neste repositório. **Leia os dois inteiros antes
de tocar em código** — em especial a seção "Migração" da ADR, que tem os 9 passos na ordem, e
os "Critérios de aceite".

Antes disso, leia a doutrina que governa qualquer mudança aqui: `docs/constitution.md`
(§2.1, §2.5, §2.6, §3.3, §8.3) e as ADRs 001 (fronteiras de package), 004 (string refs, nunca
FK cross-domain), 011 (não crie segundo source of truth), 012/014 (Projection × Presentation)
e 015 (backward-compat pós-produção). E o `CLAUDE.md`.

## O que já está feito

Os **passos 1 e 2** foram implementados num sandbox e vêm como patch:
`qc-passos-1-2.patch`, na raiz do repositório.

Ele contém:

- `craftsman`: `WorkOrderItem` ganha `quality_grade_ref`, `quality_defect_ref` e `batch_ref`
  (+ migration `0010`), e `finish()` passa a repassar `meta` também no ramo de `finished` —
  hoje só `wasted` recebe, e essa assimetria era o que impedia a partição de carregar
  informação. Mais `test_quality_partition.py` (9 testes).
- `shopman/shop`: models `QualityGrade` e `QualityDefect` (+ migrations `0034` e `0035` com
  seed), Admin em Unfold, e `test_quality_catalogs.py` (16 testes).

**Aplique com `git am --3way qc-passos-1-2.patch`.** Se der conflito, não force: o patch veio
de um checkout que pode estar desatualizado em relação a este. Nesse caso, leia o patch como
especificação e reimplemente à mão — o conteúdo importa, o diff não.

Depois de aplicar, rode `make test-craftsman` e
`pytest shopman/shop/tests/test_quality_catalogs.py`. No sandbox davam 252 e 16 passando, com
`make test-migrations` limpo.

## O que falta — passos 3 a 9 da ADR

3. **Rename dos valores de qualidade para inglês.** `excelente→excellent`, `bom→standard`,
   `regular→fair`; `minimal` nasce novo. Data migration cobrindo `WorkOrder.meta["quality"]` e
   `BroadcastRule.trigger_filter["quality_min"]`. Apagar `QUALITY_LEVELS`
   (`shop/models/broadcast.py:45`) e `QUALITY_CHOICES` (`backstage/services/production.py:147`);
   `QualityGrade.rank` passa a ser a hierarquia.
   **Este passo tem janela:** a tag `go-live-v1` não existe (confira com `git tag -l`), então a
   ADR-015 ainda não vigora e o rename é barato. Depois do alpha vira expand-contract com
   janela de alias. Faça-o cedo.
4. **Partição no finish.** `apply_finish` (`backstage/services/production.py:175`) aceita
   grupos; resolve `forces_discard` **antes** de chamar `craft.finish()` (unidades vetadas vão
   para `wasted`, nunca para lote com desconto); `set_quality` é removido.
5. **N lotes.** `_record_batch_traceability` (`production.py:463`) cria um `Batch` por linha de
   OUTPUT, com `batch_ref` próprio, gravando `nonconformity_reason` (label do defeito) e
   `nonconformity_percent` (resolvido do grau) nos grupos com desconto. Hoje a função inteira
   está num `except Exception` que só loga — criando N lotes isso fica caro, então a falha
   passa a emitir `OperatorAlert`.
6. **Broadcast.** O contexto em `shop/handlers/broadcast.py` deriva a qualidade das linhas de
   OUTPUT em vez de ler `meta["quality"]`; `quality_min` compara `rank`; e entra a chave irmã
   `quality_min_share` em `trigger_filter` — unidades em grau ≥ `quality_min` ÷ quantidade
   **prevista**, limitado a 100. **Ausente = 100%** (fornada limpa). Seed em 90.
7. **Ledger.** `WorkOrderEvent.payload` do `finished` passa a carregar a partição.
8. **Leitura.** `report_kind="quality"` em `build_production_reports`
   (`backstage/projections/production.py:1100`), por receita, forno e operador, com os defeitos
   agregados. E consolidação no `DayClosing.data`.
9. **Quiosque** em `surfaces/production-nuxt`: painel de fornadas do dia, escala em coluna ao
   lado do numpad, numpad ancorado, defeitos em bottom sheet. Projection frozen + Presentation
   (ADR-012/014). O protótipo navegável está descrito em `QC-FORNADA.md` §5 com as medidas.

## Regras duras

- **Código só em inglês**: model, campo, value de TextChoices, chave de JSON, setting, codename
  de permission. `verbose_name`, `label`, `help_text` e mensagem de operador em português.
- Um passo por commit, e **cada passo passa `make test` sozinho** antes do próximo.
- O core do `craftsman` **nunca** interpreta `quality_grade_ref` nem `quality_defect_ref`: não
  ordena, não compara, não converte em percentual. Há testes protegendo isso — se você
  precisar afrouxá-los, pare e me pergunte.
- `previsto = soma(OUTPUT) + soma(WASTE)`. Grupos disjuntos por construção.
- Quem define preço é só o grau. `forces_discard` é veto, e só para segurança alimentar.
- `Batch.nonconformity_percent` é escrito no finish e **nunca** reescrito por mudança de
  catálogo.
- Nada de B.I.: sem tabela de agregação, snapshot, warehouse ou gráfico.
- Não crie pacote nem contrib novo. A ADR explica por quê.

## Como me reportar

Ao fim de cada passo: o que mudou, o resultado dos testes, e qualquer ponto onde o código real
divergiu do que a ADR previa. Discorde de mim com argumento e evidência quando eu estiver
errado — as melhores decisões deste projeto vieram de push-back.

Comece lendo a ADR e o plano, aplique o patch, confirme o verde, e me diga o que encontrou
antes de seguir para o passo 3.
```
