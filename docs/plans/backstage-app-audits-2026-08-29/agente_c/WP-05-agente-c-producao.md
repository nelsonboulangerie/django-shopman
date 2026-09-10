# WP-05-agente-c — Produção / Fornadas

**Status:** pronto para implementação · **Autor:** Agente C (terceira leitura, 2026-08-29)
**Superfície:** `surfaces/production-nuxt` (kiosk Solari) + `shopman/backstage/{api,projections,services}/production*`
**Objetivo:** a fornada que o padeiro fecha é a fornada que o sistema credita, com o peso da ficha que ele planejou, e ninguém escreve no estoque por acidente de permissão, de relógio ou de duplo toque.

## Diferenças vs. WP-05 (Agente G) e WP-05-agente-d

**Mantidos, verificados:** as mutações de produção passam só pelo gate grosso e nunca consultam a permissão
por coluna; a concorrência otimista existe no core e é descartada na borda; o `force` não pede motivo;
seleção implícita quando há duas fornadas do mesmo SKU.

**Refutados (não entram):**
- **"~11 permissões novas" (G).** As 10 permissões por coluna já existem, são concedidas e têm teste de
  paridade. O Agente D acertou ao apontar isso. O buraco de autorização não é falta de permissão — é que as
  oito mutações nunca consultam as que existem.
- **"Separar reports/management/blind-map" e "bancada cega verdadeira" (G).** Já feito. Nesse eixo o problema
  é o oposto do que G descreve — ver o achado novo N1.
- **"`check_finish_materials` faz fail-open" (G).** Refutado: ele levanta com `CRAFTSMAN_MODE=strict`. O
  comportamento gracioso sem backend de inventário é o que permite o craftsman rodar standalone, e está
  documentado na própria docstring.
- **"Race no board: `void` entre `queue()` e `get()` derruba o kiosk" (D).** Refutado: `void` não apaga a
  linha e `ref` é único, então não há `DoesNotExist`. O que sobra é um N+1 (N5), que é outro problema.
- **"A terceira conexão do `resolve_production_access` no eventstream" (D).** É um comentário, não uma chamada.
- **"Pesagem deve usar `started_qty`" (G e D).** Descartar como escrito: quebra a estabilidade da etiqueta
  cega, que é fixada por teste ("reimpressão às 10h bate com a etiqueta das 6h, sempre") e ancorada em
  `OPERATION-DOMAIN-PLAN.md:138-146`. Uma reimpressão passaria a discordar da etiqueta já colada no pote.
  Sobra a metade legítima da proposta do Agente D: **mostrar** planejado e iniciado quando divergem. O bug
  real da pesagem é o N3, e é outro.
- **"`can_finish` sempre True é capability enganosa" (D).** Rebaixado a nota de rodapé: nenhum arquivo de
  `surfaces/production-nuxt/app` lê `can_finish`. Corrige-se junto com o P2-2, numa linha.

**Novos (verificados nesta leitura), e valem mais que metade do WP original:** os relatórios de produção são
inalcançáveis para toda persona não-superusuário; o guardrail de cobertura de encomendas nunca dispara no
caminho real da tela; a pesagem mistura ficha congelada com rendimento vivo.

**Já resolvido, não reabrir:** duplo toque no finalizar **não** credita a vitrine em dobro. `_leg_lock`,
os marcadores `stock_consumed_at`/`stock_realized_at`, a `_finish_idempotency_key` e o 409 de
`a88ecabf5` cobrem o caso. É a suspeita natural de quem lê a superfície, e a resposta já está no código.

## Pré-requisitos

- **WP-00 Bloco B** (parser de entrada canônico): o `force` estrito do P2-4 consome o helper de lá.
- **WP-00 Bloco D**: este WP toca `shopman/backstage/api/operations.py` e
  `shopman/shop/services/production.py`. Vai na **onda 2**, em branch único com WP-02 e WP-03.
- **Resposta à pergunta 1** (de quem são os relatórios de produção): bloqueia o fix de uma linha do P1-1.

## Fronteira natural

A Produção decide o que se fabrica e credita a vitrine quando a fornada fecha. Não decide venda, preço,
pagamento nem comanda. Escreve no ledger de estoque por uma perna única e já existente
(`craftsman/contrib/stockman`, `kind=MAKE`) — **este WP não toca essa perna**. O core do craftsman já resolve
concorrência, snapshot de ficha e idempotência de fechamento: o trabalho é a borda usar o que o core oferece,
não o core mudar.

## Achados priorizados

### P1-1 — Os relatórios de produção estão inalcançáveis para toda persona não-superusuário

Uma tela publicada e morta, e a rede de segurança documenta o oposto do que o código faz.

**Mecanismo, do clique ao efeito.** As três views de relatório declaram
`required_permission = "backstage.view_production_reports"` (`api/operations.py:853,881,903`), avaliada
literalmente. O `setup_groups.py` **não concede essa permissão a grupo nenhum** — a única ocorrência do nome
no arquivo é um comentário explicando por que ela não deve ser varrida por prefixo. Logo: Cozinha 403,
Gerente 403, Caixa 403; só superusuário abre. E `useReportsAccess.ts` sonda o endpoint e esconde a navegação
no 403 — então o gestor **nem vê** que existe uma tela de relatórios de produção.

Ao mesmo tempo, `admin/navigation.py:141-146` mostra o item "Relatórios" com um predicado **diferente**, que
aceita `shop.manage_production` **ou** `backstage.view_production_reports`. A Cozinha tem `manage_production`
→ o padeiro vê o link no Admin, clica e leva 403. O Gerente não tem nenhum dos dois → não vê o link e também
não teria acesso.

E `test_group_permission_parity.py:111-114` isenta a permissão com a justificativa *"alternativa OR em
`can_view_production_reports`; coberta por `shop.manage_production` em Cozinha/Gerente"*. A premissa é falsa
para a API, que não usa o predicado, e falsa para o Gerente, que não tem `manage_production` — o próprio
comentário do `setup_groups` diz isso. **A suíte fica verde por causa da isenção.**

**Fix mínimo — uma linha:** `shop_dclo("view_production_reports"),` no bloco "Gerente" do `setup_groups.py`,
e remover a isenção do teste de paridade. Corolário barato, no mesmo PR: alinhar o item de navegação do Admin
ao mesmo gate da API, senão a Cozinha continua vendo um link que responde 403.

⚠️ Depende da pergunta 1: pode ser que a decisão certa seja um grupo "Dono", não o Gerente.

### P1-2 — O guardrail de cobertura de encomendas nunca dispara no caminho real da tela

Dá para reduzir o planejado abaixo do que já foi vendido, em silêncio. É encomenda de cliente que não vai
existir.

**Mecanismo.** O filtro do guardrail e o filtro de quem escreve não casam, em três eixos:

| Eixo | Guardrail (`services/production.py:623-632`) | Escritor (`shop/services/production.py:226-241`) |
|---|---|---|
| `position_ref` | `position_ref or ""` | `str(position_ref or "").strip() or _default_position_ref()` |
| `operator_ref` | filtra por operador | **não filtra** |
| data | string crua | `_target_date_or_today(...)` |

A primeira divergência é fatal no uso normal: `ProductionStageGrid.vue:241` envia
`position_ref: board.selected_position_ref || undefined` — ou seja, **nada**, que é o estado padrão do board
(sem filtro de posição). O guardrail procura `position_ref=""`; o escritor procura `_default_position_ref()`,
que no seed vivo é `"massa"`. O guardrail não acha nada, retorna cedo, e o planejado é reduzido sem checagem.

A terceira é insidiosa: o escritor **cai silenciosamente para hoje** em qualquer string não-ISO, e o
guardrail é engolido por um `except Exception`. Data malformada = guardrail cego e planejamento no dia errado.

**Por que ninguém viu.** O único teste do assunto faz `monkeypatch` do `apply_planned` inteiro e passa
`position_ref` explícito. Ele testa o envelope de erro, nunca a lógica. A cobertura real do guardrail é zero.

**Fix mínimo:** o guardrail para de refazer a busca e recebe a ordem de quem escreve. Na versão de uma linha,
replica exatamente a régua do escritor — mesma normalização de posição, sem `operator_ref`, mesma
normalização de data. E o `except Exception` vira fail-closed com `CRAFTSMAN_MODE=strict`, como o Agente D
propôs.

### P1-3 — A pesagem mistura ficha congelada com rendimento vivo

Peso errado de insumo na balança, silencioso — e é exatamente o hazard que o plano de domínio nomeia.

**Mecanismo.** Em `build_production_weighing` (`projections/production.py:790-791`), os **itens** vêm do
snapshot da ficha, congelado no planejamento, e o **coeficiente** é calculado com o `batch_size` da receita
**viva**. Se alguém editar o rendimento da ficha entre o planejamento e a pesagem — a mesma manhã basta — o
ticket usa quantidades congeladas divididas por um rendimento novo. Um `batch_size` que vai de 10 para 20
corta todos os pesos pela metade, e a etiqueta cega não dá pista nenhuma: o padeiro pesa 300 g onde a ficha
manda 600 g.

**Prova de que é lapso, não decisão:** os outros dois consumidores do snapshot leem `snapshot["batch_size"]`
corretamente (`services/production.py:715-720` e `execution.py:127-133`). A pesagem é a única que mistura. E
`OPERATION-DOMAIN-PLAN.md:148-150` manda literalmente preferir o snapshot "evitando que uma edição posterior
da receita altere silenciosamente a pesagem".

**Fix mínimo — duas linhas:** extrair o `batch_size` junto com os itens em `_work_order_recipe_items` e usar
o do snapshot no coeficiente. `build_production_mise_en_place` tem a mesma origem de erro (usa
`recipe.batch_size` com itens vivos — internamente coerente, mas ignora o snapshot): mesmo tratamento, mesmo PR.

### P1-4 — A escrita da produção não consulta a permissão por coluna

**Mecanismo.** O operador toca "Planejar" → `_ProductionActionBase` (`api/operations.py:1605-1609`) confere
só `backstage.operate_production` → `apply_planned` → `set_planned_quantity` → `CraftPlanning` → sinal
`production_changed` → o handler do stockman cria o Quant planejado. Nenhum ponto da cadeia pergunta por
`shop.edit_production_planned`. O mesmo vale para start e para finish — e finish é a escrita `kind=MAKE` no
ledger.

**Risco×esforço:** o resolvedor já existe e já é testado. P1 e não P0 porque os dois grupos que hoje recebem
`operate_production` também recebem as colunas: o buraco é de **arquitetura de gate**, não de exposição ativa
no alpha de hoje. Mas é o mesmo padrão do P1-1 do WP-01 — o dia em que alguém fizer um grant customizado, ele
morde.

**Fix mínimo:** `_ProductionActionBase` resolve `resolve_production_access(request.user)` uma vez e cada view
declara a coluna que exige; 403 nomeando a permissão faltante. **Sem permissão nova.**

### P1-5 — Concorrência otimista existe no core e é descartada na borda

**Mecanismo.** `WorkOrder.rev` existe e `_check_rev` faz compare-and-swap atômico; `adjust`, `start`, `finish`
e `void` todos aceitam `expected_rev`. **Nenhum caller do backstage passa** — o parâmetro nem está nas
assinaturas de `shop/services/production.py` e `backstage/services/production.py`. Resultado: a bancada A
ajusta o planejado para 40 enquanto a bancada B ajusta para 25 sobre um board de 60 segundos de idade; o
último POST vence, sem 409 e sem aviso.

**Fix:** o card ganha `rev` (regerar `productionContract.ts` — o drift test já cobre); `expected_rev` opcional
atravessa backstage → shop → core; o cliente envia o `rev` do card. **Não** tornar obrigatório no craftsman:
o core documenta last-write-wins como aceitável para uso standalone.

⚠️ Atravessa quatro camadas e o contrato TS. É o item mais caro deste WP — e o único que justifica o custo,
porque duas bancadas na mesma fornada é o dia normal da padaria.

### P2-1 — Board, KDS e QC nascem com acesso total de leitura

As três views chamam o builder sem `access`, que cai em `_full_access()`, e a projection devolve tudo `True`.
`build_qc_kiosk` nem aceita o parâmetro. Consequência isolada é *ver demais*, não *escrever demais* — por isso
P2, e por isso o P1-4 é a metade que importa. **Fix:** passar `access` nas três; `build_qc_kiosk` ganha o
kwarg com o mesmo default. O painel de forecast fica de fora: é painel público de salão.

### P2-2 — `force` sem motivo, sem aprovador, sem parser estrito

Shortage → diálogo → um único botão → mesmo POST com `force: true` → o `raise` é pulado e só se cria um
alerta. Quem forçou fica registrado; **o porquê não existe em lugar nenhum**. E `bool("false") is True`
(WP-00 Bloco B): um cliente que serialize query-string em vez de JSON força sem querer.

**Fix:** parser estrito nas três linhas e `override_reason` não-vazio obrigatório quando `force` for
verdadeiro, gravado no evento/alerta. O PIN de gerente é decisão de produto — pergunta 2.

### P2-3 — Seleção implícita quando há várias fornadas do mesmo SKU

`startableWorkOrder` devolve `planned_orders[0]` e `confirmVoid` usa `started_orders[0]`. Com dois lotes do
mesmo pão no dia, o operador estorna um lote e o sistema estorna outro — sem tela que mostre qual.
**Fix:** quando houver mais de um, abrir seletor com ref, horário e posição em vez de agir.

### P2-4 — Estado inexistente chega ao kiosk como 500 cru

`apply_finish` e `apply_advance_step` buscam a ordem sem `try`; `WorkOrder.DoesNotExist` não é convertido pelo
handler de erro e vira 500 num kiosk sem teclado. **Prova de que é lapso:** os dois endpoints de forno tratam
o caso explicitamente e devolvem "Ordem de produção não encontrada." Os quatro que escrevem estado, não.
**Fix:** mover o `try/except` para dentro do helper de busca.

### P2-5 — A data do planejamento vem do relógio do cliente

`defaultPlanningDate(now = new Date())` decide "hoje ou amanhã" pelo horário **local do kiosk**, e esse valor
viaja como `target_date`. O servidor usa `timezone.localdate()` para todo o resto, e a normalização não reclama
de nada que seja ISO válido. Kiosk com fuso ou relógio errado planeja no dia errado. É a armadilha "uma âncora
só de relógio" que a casa já pagou uma vez.
**Fix:** o default do cliente sai de um campo do servidor (`board.suggested_planning_date`), não de `new Date()`.

### P2-6 — Sem teto de plausibilidade no servidor para a quantidade fechada

O servidor repassa a quantidade sem validar; o core só exige `> 0`, e não há comparação com o iniciado. A
defesa contra o dígito a mais é **inteiramente do cliente**. Qualquer POST direto credita a vitrine com o
número que mandar, via `kind=MAKE`. **Fix:** 400 quando a soma exceder o iniciado além de um limite, sem
`override_reason` — mesma régua do P2-2, aplicada à quantidade. O limite é a pergunta 3.

### P2-7 — O board faz uma query por item da fila

Para cada item da fila roda um `get(ref=...)`, quando os cards já foram construídos logo acima. Trinta
fornadas = 30 queries extras, num board que refaz o fetch a cada 60 s em kiosk. **Fix:** indexar por `ref` e
reaproveitar.

## RBAC / `setup_groups`

**Uma linha, e talvez zero permissões novas.**

Estado verificado: `backstage.operate_production` vai para Cozinha e Gerente; `shop.manage_production` só para
Cozinha; das 10 colunas, Cozinha recebe 6 e Gerente recebe 10. `backstage.view_production_reports` **não vai
para ninguém** — é o P1-1.

- P1-4, P1-5 e P2-1 **não exigem permissão nova**: o resolvedor e as colunas já existem.
- P1-1 exige **uma linha** (destino pendente da pergunta 1) e a remoção da isenção no teste de paridade.
- `shop.override_production` só se a pergunta 2 for respondida no sentido de separar force/void de
  `edit_production_finished`. Começar sem.

⚠️ Esta mudança vai no **PR único de permissões da onda 4** (WP-00 Bloco D3), porque `setup_groups` usa `set`
e o último branch a mergear revoga o que os outros concederam.

## Testes

| # | Aceite | Prova |
|---|---|---|
| 1 | Quem tem `view_production_planned` + `operate_production` e **não** tem `edit_production_planned` recebe 403 no plan. | Backend, um por mutação (6 asserts). |
| 2 | Quem tem `edit_production_planned` planeja (200) e **não** inicia (403). | Backend — prova que as colunas são independentes. |
| 3 | Board de quem não tem `view_production_started` devolve `can_view_started == false` e fila vazia. | Assert-negativo de payload. |
| 4 | `build_qc_kiosk` aceita `access` e a view o passa. | Projection + assinatura. |
| 5 | Grupo "Gerente" recém-criado por `setup_groups` abre os relatórios com 200. | Backend usando o próprio `setup_groups`. |
| 6 | Nenhuma permissão de produção fica isenta na paridade com justificativa falsa. | O próprio teste de paridade, sem a isenção. |
| 7 | Plano que reduz abaixo de encomendas comprometidas devolve 409 **sem** enviar `position_ref`. | Backend end-to-end no `apply_planned` real, **sem monkeypatch**. É o teste que hoje não existe. |
| 8 | Falha do backend de estoque com `CRAFTSMAN_MODE=strict` bloqueia o plan, não só o finish. | Backend com backend que levanta. |
| 9 | Sem `INVENTORY_BACKEND`, o finish continua permitido. | Teste existente deve continuar verde (não regredir o standalone). |
| 10 | Ticket de pesagem usa o `batch_size` do snapshot mesmo após a ficha mudar. | Projection: planeja, altera o rendimento, assere o peso. |
| 11 | `force="false"` (string) devolve 400, nos três endpoints. | Backend. |
| 12 | `force=true` sem `override_reason` devolve 400; com motivo, o motivo aparece no evento/alerta. | Backend. |
| 13 | O card expõe `rev` e o contrato TS bate. | `test_production_schema_export.py` (drift test já existe). |
| 14 | Segundo start/finish/void com `expected_rev` defasado devolve 409. | Backend simulando duas bancadas. |
| 15 | Mutação sobre ordem inexistente devolve 400 com mensagem, nunca 500. | Backend, quatro endpoints. |
| 16 | Board com N fornadas executa número constante de queries. | `django_assert_num_queries`. |
| 17 | Linha com duas fornadas iniciadas exige seleção antes de estornar. | Vitest da função pura + e2e. |
| 18 | Fechar acima do iniciado sem `override_reason` devolve 400. | Backend. |

Nenhum depende de infra inexistente.

## Arquivos tocados (para a matriz de colisão)

| Arquivo | Dono | Colisão |
|---|---|---|
| `shopman/backstage/api/operations.py` (712-919, 1605-1849) | backstage | **ALTA — WP-02 e WP-03. Onda 2, branch único.** |
| `shopman/shop/services/production.py` (208, 300, 328, 494) | **shop** | P1-5 e P1-2 caem no mesmo arquivo. **Um PR só.** |
| `shopman/backstage/projections/production.py` | backstage | — |
| `shopman/backstage/services/production.py` | backstage | — |
| `shopman/shop/management/commands/setup_groups.py` | **shop** | **PR único de permissões, onda 4.** |
| `shopman/shop/tests/test_group_permission_parity.py` | shop | idem |
| `shopman/backstage/admin/navigation.py` (141-146) | backstage | WP-09 |
| `surfaces/production-nuxt/**` + `generated/productionContract.ts` (regerado) | production-nuxt | — |

**Não tocar:** `packages/craftsman/**`. O core já faz tudo o que é preciso — `_check_rev`, snapshot,
idempotência de fechamento. Nenhuma mudança de core neste WP. E não tocar a perna do ledger em
`craftsman/contrib/stockman`: está correta, e a proteção de duplo toque é recente e cara.

## Fora de escopo

Venda, preço, pagamento, comanda, fechamento de caixa. Mudança de core no craftsman ou no stockman.
Substituir o planejado pelo iniciado na etiqueta cega. Reabrir a idempotência do fechamento.

## Perguntas para o dono do produto

1. **Os relatórios de produção são do Gerente ou do Dono?** A tela existe, está gateada, e ninguém tem a
   permissão. O guia de personas sugere que é fluxo do gestor; a docstring do teste sugere que a exclusão da
   Cozinha é deliberada. Concedo ao Gerente, crio grupo próprio, ou é intencional que seja superusuário?
   **Esta pergunta bloqueia um fix de uma linha.**
2. **Forçar o fechamento com insumo faltando exige aprovação de gerente, ou só motivo escrito?** O PDV já tem
   o padrão de PIN de segunda assinatura. Motivo obrigatório se implementa lendo código; PIN muda o fluxo do
   kiosk — o padeiro está com as mãos na massa.
3. **Qual é o teto de plausibilidade do fechamento?** Hoje o servidor aceita qualquer número positivo e a
   única defesa é o cliente. Aceitar quanto acima do iniciado sem override? Preciso do número para o assert.

## Prompt para agente executor

~~~text
Execute WP-05-agente-c (Producao).

⚠️ ONDA 2: este WP toca shopman/backstage/api/operations.py, compartilhado com WP-02 e
WP-03. Branch UNICO com eles. Ver WP-00 Bloco D.
⚠️ A mudanca de setup_groups.py NAO vai neste branch — vai no PR unico de permissoes da
onda 4 (WP-00 Bloco D3).

Bloqueio: a pergunta 1 (de quem sao os relatorios) precisa de resposta antes do P1-1.

Leia:
- docs/plans/backstage-app-audits-2026-08-29/agente_c/WP-05-agente-c-producao.md
- docs/plans/backstage-app-audits-2026-08-29/agente_c/WP-00-agente-c-transversal.md (Blocos B e D)
- docs/plans/OPERATION-DOMAIN-PLAN.md:126-150 (as 10 perms canonicas + a regra do snapshot)
- shopman/backstage/api/operations.py:712-919 e 1605-1849
- shopman/backstage/services/production.py:386-434, 605-649, 715-720, 822-826
- shopman/backstage/projections/production.py:620, 655-668, 745-833, 867-905, 2314-2322
- shopman/shop/services/production.py:175-330, 494-498
- packages/craftsman/**/scheduling.py (_check_rev) e execution.py:127-133 — LER, nao alterar
- shopman/shop/management/commands/setup_groups.py + tests/test_group_permission_parity.py:111-114

Fases:
1. P1-3 (pesagem, 2 linhas) e P2-4 (500 -> 400) — isolados, sem dependencia. Comece por eles.
2. P1-2: alinhar o guardrail a regua do escritor + o teste 7, que NAO existe hoje.
   Escreva o teste ANTES; ele deve falhar sem position_ref.
3. P1-4 + P2-1: access por coluna na escrita e na leitura. Sem permissao nova.
4. P2-2 (force com motivo + parser estrito do WP-00) e P2-6 (teto), depois das respostas 2 e 3.
5. P1-5 (expected_rev): 4 camadas + regerar productionContract.ts. O item mais caro; faca por ultimo.
6. P2-3, P2-5, P2-7.

NAO crie permissao nova. NAO toque packages/craftsman. NAO troque o planejado pelo
iniciado na etiqueta cega. NAO reabra a idempotencia do fechamento — ja esta resolvida.
~~~
