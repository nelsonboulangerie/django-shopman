# WP-00-agente-c — Transversal: honrar os contratos que o backstage já declara

**Status:** pronto para implementação · **Autor:** Agente C (terceira leitura, 2026-08-29)
**Superfície:** `shopman/backstage/api/*`, `shopman/backstage/projections/*`, `shopman/shop/projections/types.py`, `surfaces/*-nuxt`
**Objetivo:** fechar, de uma vez, cinco classes de falha que aparecem repetidas nos nove WPs — e que **não se resolvem app a app**, porque a causa é uma só em cada caso.

> **Por que este WP não existe nas versões do Agente G nem do Agente D.**
> Ambos auditaram por app. Cinco dos achados mais caros do backstage só ficam visíveis
> quando se olha os nove juntos: o mesmo bug de parsing em nove arquivos, a mesma
> declaração de idempotência mentindo em oito ações, os dois apps sem contrato gerado
> sendo exatamente os dois com mais divergência FE↔BE, e três WPs escrevendo no mesmo
> arquivo de 113 KB. O Agente D chegou perto ao propor um "manifest de actions" como
> infra nova — mas o manifest **já existe e está em produção**. O trabalho não é criar;
> é honrar.

---

## Bloco A — Idempotência: o contrato já existe e diz `"none"` em todo o dinheiro

### A tese

O backstage **já declara** idempotência por ação. `shopman/shop/projections/types.py:79` define:

```python
@dataclass(frozen=True)
class Action:
    ref: str
    kind: str
    label: str
    priority: str = "secondary"
    enabled: bool = True
    reason: str = ""
    href: str = ""
    method: str = ""
    payload_schema: dict[str, Any] = field(default_factory=dict)
    idempotency: str = "none"          # ← o default
    confirmation: dict[str, Any] = field(default_factory=dict)
```

E o servidor **já sabe honrar** a chave: `shopman/shop/services/pos.py:273-524` faz claim,
replay por `client_request_id`, e faz a ponte para o `idempotency_key` do orderman
(`:516`). É maduro, comentado, com teste. A máquina existe e é boa.

Ela só não foi ligada no caixa.

### A prova

Manifest de ações do PDV (`shopman/backstage/projections/pos.py:938-1240`), extraído
mecanicamente — 25 ações, com o valor declarado de idempotência:

| Ação | Método | `idempotency` | Rota |
|---|---|---|---|
| `close_sale` | POST | **required** | `/pos/sale/close/` |
| `customer_resolve` | POST | **required** | `/pos/customer/resolve/` |
| `fire_tab` | POST | **client_request_id** | `/pos/tabs/fire/` |
| `open_cash_shift` | POST | `none` | `/pos/cash/open/` |
| `close_cash_shift` | POST | `none` | `/pos/cash/close/` |
| `cash_movement` | POST | `none` | `/pos/cash/movement/` |
| `refund_cash` | POST | `none` | `/pos/cash/refund/{order_ref}/` |
| `settle_account` | POST | `none` | `/pos/accounts/{customer_ref}/settle/` |
| `request_change` | POST | `none` | `/pos/cash/change-request/` |
| `serve_change_request` | POST | `none` | `.../{request_ref}/serve/` |
| `cancel_change_request` | POST | `none` | `.../{request_ref}/cancel/` |
| `drawer_open` / `drawer_unlock` | POST | `none` | `/pos/cash/drawer-*/` |
| `cancel_recent_sale` | POST | **ausente → `none` por default** | `/pos/sale/recent/cancel/` |
| `clear_tab` | DELETE | **ausente → `none`** | `/pos/tabs/{session_key}/clear/` |
| `rename_tab`, `move_tab_lines`, `unfire_tab`, `open_tab`, `save_tab` | POST | **ausente → `none`** | — |
| `create_tab`, `review_sale`, `customer_lookup`, `customer_search`, `reverse_geocode` | — | `none` | — |

**Leitura:** a venda está protegida. **Todas as oito mutações de dinheiro do caixa
declaram `none`** — sangria, suprimento, abertura, fechamento, estorno, acerto de
conta, troco. E sete ações **nem declaram o campo**: herdam `none` do default do
dataclass, ou seja, ninguém decidiu — o silêncio decidiu.

Isso viola frontalmente a régua já escrita da casa (`feedback_falhar_fechado_ou_falhar_gritando`):
em dinheiro, auth e fiscal, **omissão tem que ser restritiva**. Um campo de idempotência
cujo default é "não precisa" é um default invertido.

E não é régua só de memória: `docs/plans/fallbacks-perigosos-go-live.md` (PR #393) inventaria **17
fallbacks** que degradam para o permissivo em silêncio, abrindo com o princípio *"a omissão configura o
comportamento restritivo… falhar fechado, ou falhar aberto e gritando. Nunca falhar aberto e calado."*
Aquele documento olhou adapters e settings; **este bloco é o item 18**, no contrato de ações do backstage.

E há uma diferença de grau que vale nomear, na formulação da sessão que escreveu o inventário: **os 17 itens
dela são fallbacks de _configuração_** — alguém esquece uma env e o sistema degrada. **Este é permissivo por
_default de dataclass_**, o que é pior: toda ação nova nasce insegura sem ninguém decidir nada, e sete ações
já nem declaram o campo. A versão dura do princípio, portanto:

> **O default de um campo de segurança tem que ser o valor restritivo, senão a omissão vira política.**

É exatamente o que o P0-A1 propõe — inverter o default para `"required"` e obrigar quem não precisa de chave a
declarar `"none"`. A partir daí o CI trabalha a favor: cada ação nova sem decisão aparece sozinha.

**Tarefa de acoplamento:** quando o [PR #393](https://github.com/nelsonboulangerie/django-shopman/pull/393)
mergear, `docs/plans/fallbacks-perigosos-go-live.md` estará no `main` — **acrescentar este bloco como item 18
naquele documento**, no PR deste WP. Combinado com a sessão dona do inventário: o achado fica aqui, e a
entrada lá é feita por nós depois do merge (commitar nela agora expulsaria o #393 da fila, e ele carrega um
bloqueador de go-live).

### Mecanismo da falha, do balcão até o efeito

O operador lança uma sangria de R$ 200. A rede do salão oscila (é a mesma rede do
kiosk e do KDS). O botão não responde. Ele toca de novo. Duas linhas de sangria de
R$ 200 no livro-caixa imutável — que é imutável de propósito (`packages/cashman`), então
o conserto não é apagar: é um ajuste, com o gerente, no fechamento, com o dono
perguntando por que faltam R$ 200. O mesmo caminho vale para estorno, acerto de conta
e troco.

### Achados

#### P0-A1 — `Action.idempotency` tem default invertido
**Fix mínimo:** `shopman/shop/projections/types.py:91` → `idempotency: str = "required"`.
Fazer o contrário do que o campo faz hoje: quem não precisa de chave **declara**
`"none"` explicitamente. A mudança é de uma linha e faz o CI listar, sozinho, todas as
ações que ninguém pensou.
**Risco×esforço:** 1 linha + acerto das ações que legitimamente são `none` (leitura,
`create_tab`, `review_sale`). Alto retorno, esforço baixo.

#### P0-A2 — Oito mutações de dinheiro sem chave de idempotência
**Fix mínimo:** `client_request_id` no `payload_schema` de `open_cash_shift`,
`close_cash_shift`, `cash_movement`, `refund_cash`, `settle_account`,
`request_change`, `serve_change_request`, `cancel_change_request`; declaração
`idempotency="client_request_id"`; e, no servidor, a mesma travessia já usada na venda
(`shop/services/pos.py:412-430`) aplicada em `shopman/backstage/api/operations.py`
(`POSCashOpenView:1850`, `POSCashCloseView:1895`, `POSMovementView:1932`,
`POSChangeRequestView:2091`).
**Não inventar infra:** reusar `_payload_client_request_id` e o claim existente.

#### P1-A3 — Ausência do campo não é decisão
**Fix:** declarar `idempotency` explicitamente nas 7 ações que hoje herdam o default,
inclusive `cancel_recent_sale` (cancelamento de venda) e `clear_tab` (DELETE).

### Aceites (verificáveis hoje)
- Teste de contrato: nenhuma ação com `method` em `POST/DELETE/PUT/PATCH` sai da
  projection com `idempotency="none"` sem uma linha de justificativa numa allowlist
  nomeada no próprio teste. Prova: varre `_pos_actions()` e as demais projections de ação.
- Teste de backend por ação de dinheiro: dois POSTs com o mesmo `client_request_id`
  produzem **um** lançamento no livro-caixa; com chaves diferentes, dois. Prova:
  `shopman/backstage/tests/test_pos_cash_service.py` estendido.
- Teste de regressão do default: `Action().idempotency == "required"`.

---

## Bloco B — Entrada: a casa tem dialeto de erro e não tem dialeto de entrada

### A tese

`shopman/shop/api_errors.py` é exemplar: dialeto canônico `{detail, field, errors}`,
documentado em `docs/reference/errors.md`, citado no CLAUDE.md, com `EXCEPTION_HANDLER`
DRF ligado e supersets deliberados do PDV e do storefront. **A saída é disciplinada.**

A entrada não tem dono. Três dialetos convivem:

1. **`bool(...)` cru** — `bool("false") is True`. Ocorre em, no mínimo:
   - `shopman/backstage/api/kds.py:88` — `checked` do item da cozinha (achado de G e D);
   - `shopman/backstage/api/operations.py:1639`, `:1701`, `:1768` — **a flag `force`
     das mutações de WorkOrder**. É a mesma falha, na flag de *forçar produção*, e
     nenhum dos dois WPs a listou como bug de parsing;
   - `shopman/backstage/api/operations.py:2467` — `close_source_when_empty`;
   - `shopman/backstage/api/bi.py:329`, `shopman/backstage/api/marketing.py:657,659,704,706`,
     `shopman/backstage/services/catalog.py:510,613`, `shopman/backstage/services/purchase.py:296`.
2. **`_as_bool`** (`shopman/backstage/api/marketing.py:783`) — correto para strings, e
   usado em **um** call site (`:172`, `publish_now`). É o parser certo, esquecido num arquivo.
3. **`_as_int` duplicado** — `marketing.py:790` e `catalog.py:403`, ambos engolindo
   `TypeError/ValueError` e devolvendo `None`. Lixo entra, vira `None`, e o `None` segue
   viagem sem 400.

### Mecanismo da falha

Nenhum destes é explorável por um operador de boa-fé com a UI de hoje — a UI manda
boolean JSON real. Todos são explotáveis por qualquer um que fale com a API direto, e
todos viram bug real no dia em que alguém trocar um `fetch` por um form-data, um
`URLSearchParams`, ou um cliente iFood/integração. É dívida de superfície de ataque,
não bug de tela — e é por isso que a gravidade certa é P1 de higiene, não P0 de
incêndio (o Agente D promoveu o do KDS a P0; discordo do rótulo, concordo com a pressa:
o fix custa uma tarde para os 20 call sites, não uma linha em um).

### Achados

#### P1-B1 — Não existe parser de entrada canônico
**Fix:** `shopman/backstage/api/_parse.py` com `as_bool`, `as_int`, `as_decimal`,
`as_ref`, `as_choice` — todos levantando `rest_framework.exceptions.ValidationError`
com `field`, para cair no dialeto de erro que já existe. Falha fechado e falha gritando,
que é a régua da casa.
**Migrar** os ~20 call sites acima; deletar os dois `_as_int` duplicados (zero-residuals).

#### P1-B2 — `force` de produção aceita `"false"` como verdadeiro
Caso específico e o mais caro do conjunto: `force` contorna a checagem de insumos.
**Fix:** parser estrito nos três call sites de `operations.py`.

### Aceites
- Teste de API por endpoint migrado: `"false"`, `"0"`, `null`, `"abc"` e ausência
  retornam 400 com `{detail, field}`; boolean JSON real continua passando.
- Grep de gate no CI: zero ocorrências de `bool(request.` / `bool(payload.` /
  `bool(data.get(` em `shopman/backstage/api/` e `shopman/backstage/services/`.
- `_as_int` existe em um lugar só.

---

## Bloco C — Contrato gerado: os dois apps sem export são os dois com mais divergência

### A prova

| App Nuxt | Testes | Contrato gerado | Comando de export |
|---|---|---|---|
| pos-nuxt | 32 | `posContract.ts` | `export_pos_schema` |
| production-nuxt | 20 | `productionContract.ts` | `export_production_schema` |
| orders-nuxt | 12 | `ordersContract.ts` | `export_orders_schema` |
| kds-nuxt | 5 | `kdsContract.ts` | `export_kds_schema` |
| — | — | (B.I.) | `export_bi_schema` |
| **marketing-nuxt** | **5** | **nenhum** | **não existe** |
| **hub-nuxt** | **2** | **nenhum** | **não existe** |

Os achados de divergência FE↔BE que G e D levantam se concentram exatamente nos dois
sem contrato: no Hub, tiles/hrefs stale; no Marketing, o formulário descartando chaves
de audiência e a flag `publish_now` sem emissor no frontend. Não é coincidência: os
outros quatro apps têm um teste de export (`test_*_schema_export.py`) que quebra quando
o backend e o `.ts` divergem. Hub e Marketing não têm esse guarda.

### Achado

#### P1-C1 — `export_marketing_schema` e `export_hub_schema` não existem
**Fix:** replicar o padrão de `shopman/backstage/management/commands/export_kds_schema.py`
sobre a infra já compartilhada em `shopman/backstage/contracts.py`, com o
`test_*_schema_export.py` correspondente.
**Retorno:** fecha, por construção, uma classe inteira de achados dos WP-01 e WP-08 —
e impede que ela volte.

### Aceites
- `surfaces/marketing-nuxt/app/generated/marketingContract.ts` e
  `surfaces/hub-nuxt/app/generated/hubContract.ts` existem e são gerados por comando.
- `test_marketing_schema_export.py` e `test_hub_schema_export.py` quebram quando o
  backend muda e o `.ts` não é regerado (mesma prova dos quatro existentes).

---

## Bloco D — Execução: o plano de nove frentes paralelas não sobrevive a este repositório

Este bloco não tem achado de código. Tem duas medições que mudam o **plano**, e ambas
foram feitas neste repositório, hoje.

### D1 — Três WPs escrevem no mesmo arquivo de 113 KB

`shopman/backstage/api/operations.py` tem 113.491 bytes e ~97 símbolos de topo. Ele
contém, no mesmo arquivo:

- POS e Caixa (`POSView:297`, `POSCashOpenView:1850`, `POSCashCloseView:1895`, `POSMovementView:1932`, `POSCashReceiptView:1972`, `POSCashDrawerOpenView:2023`, `POSChangeRequestView:2091`) → **WP-02**
- Pedidos e courier (`_OrderActionBase:1026` e 18 subclasses, `:1046`–`:1605`) → **WP-03**
- Produção (`_ProductionActionBase:1605` e 9 subclasses, `:1619`–`:1850`) → **WP-05**
- Operador e estação (`OperatorLoginView:432`, `StationProvisionView:610`, `OperatorPinResetView:668`) → **WP-01 / WP-09**

O CLAUDE.md abre dizendo que este repositório roda **várias sessões ao mesmo tempo**, e
a memória do projeto registra que *criss-cross derruba a fila de merge* — dois PRs com
bases diferentes chegam a `UNMERGEABLE` mostrando `CLEAN`. Quatro branches editando este
arquivo em paralelo é a receita documentada do problema que já custou trabalho aqui.

**Prescrição:** o eixo de paralelização **não pode ser o app**. Ou as mudanças em
`operations.py` vão todas num único branch (onda 2 abaixo), ou não vão.

**Não** dividir o arquivo agora: rename/split em massa é hostil a merge (régua da casa),
e faria exatamente o que se quer evitar. Split é WP próprio, depois das ondas.

### D2 — Nove WPs de testes estouram o CI do backstage por tempo, antes de qualquer bug

`shopman/backstage/tests/` tem 163 arquivos e **1.628 funções de teste**, e a suíte
`test-backstage` já rodou em **20min04s** — o próprio `.github/workflows/runtime-gate.yml:160-165`
documenta o episódio: naquele dia o step tinha teto de 20 min, a suíte passou verde, o
job caiu vermelho e a fila de merge expulsou um PR inocente (#361). Hoje o step tem 30
min e o job 35: ~10 minutos de folga.

A média é ~0,74 s por teste. Os nove WPs, somados, adicionam algo entre 200 e 300 testes
de backend ao mesmo alvo — **+2,5 a +4 minutos**, mais o custo dos testes de integração
que são mais lentos que a média. A folga acaba no meio das ondas, e o modo de falha não
é "teste vermelho": é "suíte verde, check vermelho, PR inocente expulso" — o mais caro
de diagnosticar, porque parece flake.

**Prescrição:** dividir a matriz `test-backstage` em dois shards **antes da onda 2**.
É mudança de CI, isolada, sem colisão com nenhum WP, e cabe na onda 0.

⚠️ **Achado ao medir (29/08): a suíte do `shop` não é segura em paralelo.** O alvo do Makefile roda serial
(`pytest shopman/shop/tests -x -q`) e passa — 2.593 testes. Com `-n auto`, **dois** falham por interferência
entre workers: `test_operator_order_contract.py::test_cancel_does_not_mutate_orders_that_cannot_transition_to_cancelled`
e `test_mark_paid.py::test_operator_hot_path_surfaces_do_not_expose_mark_paid_action` — os dois passam
isolados. Não é regressão; é acoplamento pré-existente que o serial esconde.

Consequência para este bloco: **shardar não é só dividir a matriz.** Se o shard levar paralelismo para dentro
do alvo, ele acorda esse acoplamento e o sintoma será "flake" — o diagnóstico mais caro. O shard seguro é por
**arquivo entre jobs**, com cada job continuando serial por dentro. E os dois testes acima merecem isolamento
próprio antes de qualquer aumento de paralelismo.

### Ondas propostas

| Onda | Conteúdo | Paralelizável? | Por quê |
|---|---|---|---|
| **0** | Shard do `test-backstage` (D2) · default de `Action.idempotency` (P0-A1) · `_parse.py` criado (sem migrar call sites) | sim, 3 branches | arquivos disjuntos, nenhum toca `operations.py` |
| **1** | P0 de arquivos disjuntos: KDS (`api/kds.py`), Compras (`api/purchase.py` + `services/purchase.py`), Admin (`admin/*`), B.I. (`bi/*`) | sim, 4 branches | um arquivo-raiz por frente |
| **2** | **Tudo que toca `operations.py`**: idempotência do caixa (P0-A2), pedidos, produção, `force` estrito (P1-B2) | **não — branch único** | D1 |
| **3** | Contratos gerados de Hub e Marketing (C1) + os achados FE↔BE que eles destravam | sim, 2 branches | arquivos novos |
| **4** | Permissões finas + `setup_groups` (um PR só, ver abaixo) | **não — branch único** | `setup_groups.py` é dono único e usa `set` |
| **5** | UX de excelência | sim | depende de 0-4 |

### D3 — `setup_groups` usa `set`, então permissão nova é operação de arquivo único

`shopman/shop/management/commands/setup_groups.py` é dono único e o loop final faz
`group.permissions.set(perms)` — **o que sai da lista sai do banco**. Seis dos nove WPs
criam permissão. Se forem seis PRs, o último a mergear ganha e os cinco anteriores
revogam em silêncio no próximo deploy, porque cada branch tem sua versão da lista.

O Agente D acertou ao exigir uma seção `setup_groups` em cada WP. Faltou a consequência:
**as seis mudanças de permissão são um PR só, na onda 4**, com o teste de paridade
(`tests/test_group_permission_parity.py`) rodando uma vez sobre o conjunto.

Duas leituras do arquivo que valem para todos os WPs de permissão:

- O grupo **Gerente** recebe `*_ver("backstage")` — o app **inteiro**, e o comentário
  celebra isso ("escopo novo de configuração nasce alcançável"). Consequência não
  declarada em nenhum WP: **todo model novo do backstage nasce visível para o Gerente**.
  Isso interage diretamente com o achado de Admin sobre actions sem `allowed_permissions`
  — se `view_*` basta para executar uma action, o auto-grant amplia o alcance a cada
  model novo, sem ninguém decidir. (Ver WP-09.)
- O grupo **Dono** é o único com `*_ver("payman")`, e **Gerente não tem dinheiro** por
  decisão explícita e comentada. Todo WP que propõe permissão de dinheiro precisa dizer
  se vai para "Dono" (portão) ou "Gerente" (persona) — são coisas diferentes aqui.

---

## Bloco E — O backstage nunca devolve 401, e por isso metade das receitas dos WPs não roda

### A tese

`config/settings.py:826-828` configura **uma só** classe de autenticação DRF:
`SessionAuthentication`. Ela não sobrescreve `authenticate_header()`, e o DRF rebaixa
`NotAuthenticated` (401) para **403** sempre que nenhum authenticator devolve um header
de desafio. Consequência medida: **nenhum endpoint de operador emite 401** — requisição
anônima a `/api/v1/backstage/hub/` volta 403 com `{"detail": "As credenciais de
autenticação não foram fornecidas."}` e **sem** `error.code`.

E `shopman/shop/api_errors.py:59` só anexa `error.code` para `PermissionDenied`:

```python
    elif isinstance(exc, exceptions.PermissionDenied):
        _attach_permission_code(response, exc)
```

`NotAuthenticated` passa reto. O front recebe um 403 mudo e não tem como distinguir
"sua sessão caiu" de "você não tem permissão" de "a estação está travada" sem casar a
mensagem em português — que é exatamente o que o `STATION_LOCKED_CODE` foi criado para
evitar.

### O que isso invalida

`isUnauthenticatedError` (`operator-kit/app/utils/httpError.ts`) testa `status === 401`.
Na zona de operador esse ramo é **inalcançável**. No `hub-nuxt`, `sessionExpired` é
constante `false` e o bloco "Sua sessão expirou" é código morto. Em todo o `surfaces/`
há **um único** chamador de `flagIfUnauthenticated` — `pos-nuxt/app/composables/usePosAction.ts`.

Vários WPs (do Agente G e do Agente D) prescrevem "401 → re-gate de sessão" como
correção de UX. **Implementadas como estão escritas, essas correções produzem um `if`
que nunca entra**, e o 403 continua caindo no ramo genérico — o operador continua vendo
formulário de senha quando a API caiu.

### Achado

#### P1-E1 — `NotAuthenticated` não carrega código de erro
**Fix mínimo (uma linha), `shopman/shop/api_errors.py:59`:**

```python
    elif isinstance(exc, (exceptions.PermissionDenied, exceptions.NotAuthenticated)):
```

`_attach_permission_code` já ignora `code == "permission_denied"`, e
`NotAuthenticated().detail.code` é `"not_authenticated"` — então passa e o payload ganha
`{"error": {"code": "not_authenticated"}}`, sem mudar status nem `detail`.

**Alcance:** as sete superfícies. É pré-requisito de todo aceite de UX de erro nos
WP-01 a WP-08, e por isso mora aqui e não em nenhum WP de app.

⚠️ **Não** "consertar" `isUnauthenticatedError` para aceitar 403 no front. Afrouxar o
narrowing no cliente transforma toda negativa de permissão em "sessão expirada" e manda
o operador digitar senha para um problema que senha não resolve. A correção é no
servidor.

### Aceite
- Requisição anônima a um endpoint de backstage devolve 403 **com**
  `error.code == "not_authenticated"`. Prova: assert de payload; hoje falha.
- Um 403 de permissão comum continua **sem** `error.code` (nada foi alargado).
  Prova: assert-negativo.

---

## Fora de escopo deste WP

Achados específicos de cada app (ficam nos WP-01..09), split de `operations.py`,
migração do gate canônico do Admin, e qualquer mudança de UX. Este WP é infraestrutura
de contrato e plano de execução — deliberadamente pequeno e mergeável cedo.

## Prompt para agente executor

~~~text
Execute WP-00-agente-c (transversal do backstage).

Leia:
- docs/plans/backstage-app-audits-2026-08-29/agente_c/WP-00-agente-c-transversal.md
- shopman/shop/projections/types.py (dataclass Action)
- shopman/backstage/projections/pos.py (_pos_actions)
- shopman/shop/services/pos.py:270-530 (claim/replay de client_request_id — o padrão a reusar)
- shopman/shop/api_errors.py + docs/reference/errors.md
- shopman/backstage/management/commands/export_kds_schema.py + shopman/backstage/contracts.py
- shopman/shop/management/commands/setup_groups.py
- .github/workflows/runtime-gate.yml (job `tests`)

Ordem obrigatória (as fases NAO sao paralelizaveis entre si):
1. Onda 0: shard do test-backstage; Action.idempotency default "required"; criar
   shopman/backstage/api/_parse.py (sem migrar call sites ainda).
2. Bloco B: migrar os ~20 call sites de bool()/int() crus para _parse; apagar os dois
   _as_int duplicados; gate de grep no CI.
3. Bloco A: client_request_id nas 8 acoes de dinheiro, reusando o claim do POS.
   ⚠️ Isto toca shopman/backstage/api/operations.py — branch UNICO com o WP-03 e o WP-05.
4. Bloco C: export_marketing_schema e export_hub_schema + testes de export.

NAO divida operations.py. NAO altere setup_groups.py aqui (onda 4, PR unico).
~~~
