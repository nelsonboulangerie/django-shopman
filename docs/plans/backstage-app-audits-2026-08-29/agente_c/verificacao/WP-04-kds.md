# Verificação WP-04 — KDS

Verificado contra a worktree `coordenar-sessoes-deploys-b9cdac`, HEAD `9469c92a2`
(merge do #392, 2026-08-29). Todas as evidências foram abertas e lidas por função
inteira; quatro afirmações foram provadas rodando código (pytest com
`DJANGO_SETTINGS_MODULE=config.settings_test` + `.venv` da raiz).

---

## A. Superfície real (o que existe hoje)

### Backend

| Caminho | O que é |
|---|---|
| `shopman/backstage/api/kds.py` | 7 views DRF. 6 pedem `backstage.operate_kds`; `KDSCustomerStatusView` é pública (`permission_classes = []`). |
| `shopman/backstage/api/urls.py:175-182` | Rotas: `kds/`, `kds/cliente/`, `kds/<slug:ref>/`, `kds/tickets/<pk>/{items,done,recall,acknowledge}/`, `kds/expedition/<order_pk>/action/`. |
| `shopman/backstage/services/kds.py` | Fachada de mutação (78 linhas). Traduz exceção do core para o vocabulário do backstage. **É aqui que `checked` vira toggle** (`:23-27`). |
| `shopman/backstage/projections/kds.py` | 7 dataclasses + builders. `build_kds_board` (`:179`), `build_kds_ticket` (`:238`), `build_kds_customer_status` (`:246`), `_public_comanda_code` (`:322`), `_build_ticket` (`:418`). |
| `shopman/backstage/models/kds.py` | `KDSInstance` (`:8`) e `KDSTicket` (`:46`). Permissão custom `operate_kds` declarada em `KDSTicket.Meta` (`:92`). |
| `shopman/backstage/admin/kds.py` | `KDSInstanceAdmin`. Os quatro `has_*` gateados em `operate_kds` (`:53-63`). |
| `shopman/shop/services/kds.py` | Core: `fire_lines` (item nasce com `line_id`, `:238`), `toggle_ticket_item` (`:452`), `complete_ticket` (`:480`), `expedition_action_by_order_id` (`:598`), `_locked_ticket` (`:578`). |
| `shopman/shop/adapters/kds.py` | CRUD do ticket. `unfire_session_lines` (`:57-90`) **remove itens do meio de tickets vivos**. |
| `shopman/shop/handlers/_sse_emitters.py` | `emit_kds_change` (`:378-412`), `_track_kds_ticket_state` (`:415`), `_on_kds_ticket_saved` (`:432`), `_publish_backstage` (`:467`). |
| `shopman/shop/eventstream.py` | `ShopmanChannelManager` + `_BACKSTAGE_CHANNEL_RULES` (`:128-148`). |
| `shopman/backstage/urls.py:31-42` | `/events/<kind>/` → `backstage-<kind>-main`; `/events/<kind>/<scope>/` → `backstage-<kind>-<scope>`. |

### Superfície Nuxt (`surfaces/kds-nuxt`)

| Caminho | O que é |
|---|---|
| `app/pages/index.vue` | Seletor de estação. |
| `app/pages/[ref].vue` | Board da estação (554 linhas). Único lugar que emite `check`. |
| `app/pages/pickup.vue` | Painel público de retirada (dark, sem auth, sem rail). |
| `app/composables/useKdsBoard.ts` | Fetch canônico + poll 15s + SSE + fila serial otimista. `checkItem` em `:164-179`. |
| `app/composables/useKdsCustomerBoard.ts` | Board público: poll 10s + SSE best-effort em `/sse/orders`. |
| `app/presentation/board.ts` | `sortByUrgency`, `allDayCounts`, `splitRef`, `realtimeIndicator`. |
| `app/components/KdsTicketCard.vue:186-190` | `v-for="(item, idx)"` → `$emit('check', idx, !item.checked)`. |
| `app/components/KdsTicketModal.vue:153-157` | Mesmo padrão de índice. |
| `app/generated/kdsContract.ts` | Espelho TS gerado da projection; drift-guard em `test_kds_schema_export.py`. |
| `server/routes/sse/kds/[ref].ts`, `server/routes/sse/orders.ts` | Proxy SSE same-origin. |

### O que os dois WPs NÃO mencionaram

- **`app.vue`** monta `useOperatorLock("backstage.operate_kds")` e isenta `/pickup`
  do lock — é aqui que "não há vínculo operador→estação" se materializa: o lock é
  por permissão, nunca por estação.
- **`test_kds_sse.py:33`** já *afirma* `order_ref` no payload SSE. Qualquer fix do
  payload precisa inverter esse assert, não só adicionar um novo.
- **`test_group_permission_parity.py:69`** trava `backstage.operate_kds → {Cozinha}`.
  Toda proposta de RBAC passa por esse arquivo.
- **`test_api_kds_surface.py`** (261 linhas) já cobre gate, idempotência de done,
  404 por tipo, gate de pagamento e ausência de PII no board público. Não cobre
  ref inválida nem `checked` não-booleano.
- **`export_kds_schema`** (management command) — o contrato TS é gerado, então
  qualquer campo novo na projection é uma mudança de 2 arquivos + regeneração.
- **A rota é `kds/cliente/`** — em português (ver D6).

---

## B. Evidências dos WPs, veredito uma a uma

| # | Afirmação (G/D) | Arquivo:linha ATUAL | Veredito | Nota |
|---|---|---|---|---|
| 1 | `KDSItemProjection` não expõe `line_id` (G `kdsContract.ts:5`; D `projections/kds.py:42-51`, builder `:449-459`) | `shopman/backstage/projections/kds.py:41-51` (dataclass) e `:449-459` (builder) | CONFIRMADO | A dataclass tem 6 campos e nenhum é identidade; o builder lê `it.get("sku"/"name"/"qty"/"notes"/"checked"/"stock_warning")` e ignora `line_id`. D está certo de que o fix vive na projection — o `.ts` é gerado. |
| 2 | Ticket nasce com `line_id` (G `services/kds.py:232`; D `:238`) | `shopman/shop/services/kds.py:232-239` | CONFIRMADO | O dict do item é montado em `:232-239`; `"line_id": item["line_id"]` está na linha **238**. A linha de G (232) é o início do dict, não a chave. |
| 3 | UI envia `index` (G `useKdsBoard.ts:164`; D `:164,171`) | `surfaces/kds-nuxt/app/composables/useKdsBoard.ts:164` (assinatura) e `:171` (body `{ index, checked }`) | CONFIRMADO | Origem do índice: `KdsTicketCard.vue:186-190` e `KdsTicketModal.vue:153-157`, ambos `v-for` posicional. |
| 4 | API parseia `index` e `bool(...)` (G `api/kds.py:86,88`; D `:88`) | `shopman/backstage/api/kds.py:85` (`int(...)`) e `:88` (`bool(...)`) | PARCIAL | A linha do `int()` é **85**, não 86. A do `bool()` é 88 nos dois — correto. |
| 5 | Core muta `ticket.items[index]` (G `:452`; D `:452,467`) | `shopman/shop/services/kds.py:452` (entrada) e `:467` (mutação) | CONFIRMADO | `:467` é `ticket.items[index]["checked"] = not ticket.items[index].get(...)`. |
| 6 | `unfire_session_lines` remove itens do meio de tickets vivos (D) | `shopman/shop/adapters/kds.py:78-83` | CONFIRMADO | `kept = [it for it in items if it.get("line_id") not in targets]` → `ticket.items = kept`. Fluxo real do operador: `usePosSale.ts:1515-1547` (`unfireTab` por linha e `unfireSelected` em lote) → `POSTabUnfireView` → `pos.py:1205`. É o botão "Cancelar envio" do PDV (`PosCartPanel.vue:535,566`). |
| 7 | `checked = bool("false")` marca verdadeiro | `shopman/backstage/api/kds.py:88` | CONFIRMADO — mas ver gravidade | **Provado rodando**: form-encoded `checked="false"` → 200, item fica `True`; JSON com a *string* `"false"` → 200, item fica `True`. **Porém a UI nunca dispara**: `useKdsBoard.ts:171` manda `!item.checked`, um boolean JS real. Ver C2. |
| 8 | Board usa `ref` da URL (G `[ref].vue:14`; D `:14-15`) | `surfaces/kds-nuxt/app/pages/[ref].vue:14-15,30` | CONFIRMADO | `stationRef` do `route.params.ref`, passado uma vez ao composable. Sem validação client-side. |
| 9 | API exige apenas `backstage.operate_kds` (G `api/kds.py:47`) | `shopman/backstage/api/kds.py:49,65,81,116,138,160,182` | CONFIRMADO | Sete views, sete vezes o mesmo código. A linha 47 de G é a `class KDSIndexView`, a permissão está em 49. |
| 10 | SSE autoriza por tipo de canal, não por ref (G `eventstream.py:57,128`) | `shopman/shop/eventstream.py:57-58` + `:128-148` | CONFIRMADO como fato / REFUTADO como achado independente | `kind = suffix.split("-", 1)[0]` e o mapa só conhece `kind`. Mas o REST **também** não gateia por estação (`api/kds.py:67-69` aceita qualquer ref). Portanto o SSE não é uma porta mais larga que o fetch — é o mesmo buraco, contado duas vezes. D está certo ao dizer que a falha real é o payload. |
| 11 | Payload SSE do canal `kds` vaza `session_key` + `order_ref` (D `_sse_emitters.py:390-399`) | `shopman/shop/handlers/_sse_emitters.py:390-399` | CONFIRMADO | Linhas exatas. `"session_key": ticket.session_key` em `:396`, `"order_ref": order_ref` em `:397`. |
| 12 | `backstage-kds-main` é global (D) | `shopman/shop/handlers/_sse_emitters.py:474-476` | CONFIRMADO | `send_event(f"backstage-{kind}-main", ...)` é **incondicional**; o scope da estação é um envio *adicional*. `/events/kds/` (sem scope) monta `backstage-kds-main` (`backstage/urls.py:31-36`). |
| 13 | Ref de estação inexistente → HTTP 500 (D `api/kds.py:67-69`, `projections/kds.py:183`) | `shopman/backstage/api/kds.py:67-69` + `shopman/backstage/projections/kds.py:183` | CONFIRMADO — e pior que o descrito | **Provado rodando**: ref inexistente → 500; **estação desativada (`is_active=False`) → 500 também**. D não mencionou o segundo, que é o caso que um gerente provoca sozinho no Admin. |
| 14 | `KDSInstanceAdmin` usa `operate_kds` nos 4 `has_*` (D `admin/kds.py:53-63`) | `shopman/backstage/admin/kds.py:53-63` | CONFIRMADO | Inclusive `has_delete_permission`. `KDSTicket.kds_instance` é `on_delete=CASCADE` (`models/kds.py:69`), então apagar estação apaga ticket vivo. |
| 15 | `KDSTicket` não tem `version` nem `updated_at` (D `models/kds.py:46-95`) | `shopman/backstage/models/kds.py:46-95` | CONFIRMADO | Campos: `session_key`, `kds_instance`, `items`, `status`, `created_at`, `completed_at`, `cancelled_at`, `acknowledged_at`. Nenhum contador de revisão. |
| 16 | `help_text` de `models/kds.py:75` desatualizado (sem `line_id`) (D) | `shopman/backstage/models/kds.py:75` | CONFIRMADO | `'[{"sku", "name", "qty", "notes", "checked": false}]'` — `line_id` está no dado real desde `services/kds.py:238`. |
| 17 | Board de expedição é global por design (D `projections/kds.py:343-345`) | `shopman/backstage/projections/kds.py:343-345` | CONFIRMADO | `_build_expedition_board` ignora a instância na query: `Order.objects.filter(status="ready")`. A exceção que D pede no aceite é real. |
| 18 | Envelopes de mutação inconsistentes (G/D) | `api/kds.py:104` (`{"ticket": ...}`) vs `:126,148,170` (`{"ok", "ticket_pk"}`) vs `:204` (`{"ok","action","order_pk"}`) | CONFIRMADO como fato / REFUTADO como problema | A UI **não lê nenhum campo de nenhuma dessas respostas**: `useKdsBoard.ts:171-178` e `:193-199` só encadeiam `.then(scheduleReconcile)` / `.catch`. O envelope comum não conserta nada que esteja quebrado hoje. Ver E. |
| 19 | UX "estação lacrada" é inalcançável hoje (D) | `surfaces/kds-nuxt/app/app.vue:8-10` | CONFIRMADO | `useOperatorLock(OPERATOR_PERM)` — o lock conhece permissão, nunca estação. Não existe modelo operador→estação em lugar nenhum do repo. |
| 20 | ADR-016 governa o SSE (D) | `docs/decisions/adr-016-sse-first-realtime.md`, regra 1 | CONFIRMADO — e o código a viola | "O payload do SSE é mínimo (um sinal), **não dados sensíveis**." O canal `tabs` vizinho foi escrito exatamente assim (`_sse_emitters.py:407-412`, só `kind` + `session_key`); o canal `kds` não. É decisão documentada **descumprida**, não decisão errada. |
| 21 | Main já corrigiu algo disto? | `git log` por arquivo | REFUTADO | Último toque em `api/kds.py` é `fd33c5020`; em `_sse_emitters.py` é `b4a0595df`; em `adapters/kds.py` é `fd33c5020`. Nenhum commit posterior mexe em `bool(...)`, no índice ou no payload. Nada foi corrigido. |

---

## C. Achados confirmados, com gravidade recalibrada

### C1 — Estação KDS pode ser apagada por quem só sabe fritar pão · **P1**

**Risco × esforço:** o único achado dos dois WPs cujo dano é *irreversível* e cujo
gatilho é um clique num botão vermelho do Admin. Fix é remoção de código.

**Mecanismo, do clique ao efeito:** o grupo Cozinha tem `is_staff` e entra no
Admin (`setup_groups.py:106-122` dá `view_*` de craftsman/buyman/stockman). Como
`KDSInstanceAdmin.has_view_permission` devolve True para `operate_kds`
(`admin/kds.py:62-63`), "estações KDS" aparece no índice do Admin para o cozinheiro.
`has_delete_permission` (`:59-60`) devolve True pela mesma régua. Ele apaga a
estação; `KDSTicket.kds_instance` é `on_delete=CASCADE` (`models/kds.py:67-72`),
então **todos os tickets vivos daquela estação somem do banco** — sem cancelamento,
sem alerta, sem trilha. O board da outra bancada esvazia no próximo poll de 15s e
ninguém sabe o que era para fazer. O caminho menos dramático é o mesmo botão de
mudar `collections`: o roteamento quebra e os itens deixam de chegar à cozinha
(`services/kds.py:211-230` só emite um `OperatorAlert`).

**Arquivo:linha:** `shopman/backstage/admin/kds.py:53-63`.

**Fix mínimo correto — menor que o dos dois WPs:** não criar
`backstage.manage_kds_config`. **Apagar os quatro overrides `has_*`** (linhas
53-63). Sem eles o `ModelAdmin` cai nas permissões de modelo padrão do Django
(`view_kdsinstance` / `add_` / `change_` / `delete_`), que já existem desde
`backstage/migrations/0001_initial.py`. Efeito:

- Cozinha perde a tela inteira (não tem `_ver("backstage")` em `setup_groups.py`).
- Gerente já tem `view_kdsinstance` via `*_ver("backstage")` (`setup_groups.py:142`).
- Uma linha nova em `setup_groups.py`, no bloco Gerente:
  `*_escrever("backstage", "kdsinstance"),`

Isso evita permissão custom nova, evita migração, e **não toca**
`test_group_permission_parity.py` (que rastreia perms custom, não perms de modelo).

---

### C2 — `checked = bool(request.data.get("checked", False))` · **P2** (G disse P1, D promoveu a P0 — os dois erraram)

**Risco × esforço:** o bug é real e provado, mas **a UI não consegue dispará-lo**.
Fix de uma linha; gravidade de hardening, não de incidente.

**Mecanismo:** `bool("false") is True` em Python. Provado rodando contra este HEAD:

- form-encoded `index=0&checked=false` → **200, item vira `True`**
- JSON `{"index": 0, "checked": "false"}` → **200, item vira `True`**

(DRF aceita form-encoded porque `config/settings.py:817-838` não define
`DEFAULT_PARSER_CLASSES`, então valem os três parsers padrão.)

**Por que não é P0:** `useKdsBoard.ts:171` envia `{ index, checked }` onde `checked`
vem de `!item.checked` (`KdsTicketCard.vue:190`) — boolean JS, serializado como
boolean JSON. **Nenhum caminho da superfície produz uma string.** Além disso o
efeito colateral é assimétrico: o backstage compara com o estado atual
(`services/kds.py:23-27`), então um `"false"` espúrio só marca um item que estava
*desmarcado* — nunca desmarca um marcado. Para virar P0 seria preciso um cliente
que não existe.

**Arquivo:linha:** `shopman/backstage/api/kds.py:88`.

**Fix mínimo (a linha):**

```python
checked = request.data.get("checked", False)
if not isinstance(checked, bool):
    return Response({"detail": "Campo 'checked' deve ser booleano.", "field": "checked"},
                    status=status.HTTP_400_BAD_REQUEST)
```

---

### C3 — Índice mutável: `unfire` do PDV desloca os itens de um ticket vivo · **P2** (G e D disseram P1)

**Risco × esforço:** o deslocamento é real e o fluxo que o causa é real, mas a
janela é curta e o dado para consertar já existe. Fix de esforço médio (projection
+ API + core), valor durável.

**Mecanismo:** ticket com `[A, B, C]`. O operador do PDV clica "Cancelar envio" na
linha B (`PosCartPanel.vue:535` → `usePosSale.ts:1525` → `POSTabUnfireView` →
`pos.py:1205` → `adapters/kds.py:78-83`). O ticket passa a `[A, C]` e o
`post_save` emite SSE (`_on_kds_ticket_saved:444-445`), que faz o board refazer o
fetch. **Se o cozinheiro tocar antes do refetch chegar**, ou se o toque já estiver
na fila serial de `useKdsBoard.ts:141-162`, o POST carrega índice velho:
`index=2` → 400 "Item não encontrado"; `index=1` → **marca C achando que é B**.

**Por que P2 e não P1:** o único mutador de `ticket.items` que muda comprimento é
`unfire_session_lines`. `fire_lines` sempre cria ticket novo (`adapters/kds.py:49-54`),
nunca faz append; `_complete_ticket_locked` só marca tudo `True`; as projections
preservam ordem (`_add_stock_warnings:553-566`). A janela é o intervalo entre o
commit do trim e a chegada do SSE — sub-segundo no caso normal. O efeito é um
*check* errado (crença do cozinheiro), não um item errado *produzido*.

**Arquivo:linha:** `shopman/backstage/projections/kds.py:449-459` (identidade
descartada) · `shopman/backstage/api/kds.py:85,92-97` · `shopman/shop/services/kds.py:464-467`.

**Fix mínimo correto:** projetar `line_id` como `item_ref` em `KDSItemProjection`
(o dado já está em `ticket.items`, `services/kds.py:238`), aceitar `item_ref` no
POST e resolver o índice **dentro do lock** por busca de `line_id`. **Não** criar
campo `version`/`rev` no `KDSTicket`: resolver por `line_id` sob o lock já elimina
a classe inteira de erro sem migração. Item cujo `line_id` sumiu → 409 com
"Este item saiu do pedido." (mensagem acionável, não 400 genérico).

*Ressalva de compatibilidade:* `KDSItemProjection` também é usada pelo card de
expedição (`_build_expedition_card:503-513`), onde a fonte é `OrderItem`, que tem
`line_id` próprio (`services/kds.py:275`). Dá para preencher os dois.

---

### C4 — Ref de estação inválida **ou desativada** → 500 · **P1** (D achou; a metade "desativada" é nova)

**Risco × esforço:** o gatilho é uma ação normal de gerente, o sintoma é um kiosk
morto, e o fix é um `try/except`.

**Mecanismo:** `build_kds_board` faz `KDSInstance.objects.get(ref=..., is_active=True)`
sem guarda. `KDSInstance.DoesNotExist` não é `APIException` nem `Http404`, então o
`EXCEPTION_HANDLER` (`api_errors.py:54-56`) devolve `None` e o Django serve 500.
**Provado rodando** contra este HEAD: ref inexistente → 500; e **estação existente
com `is_active=False` → 500 também**.

Do lado do operador: o gerente desativa "Bancada 2" no Admin no fim do turno. O
tablet daquela bancada, com a URL no bookmark do kiosk, passa a mostrar "Falha ao
carregar o board. Reconectando…" (`[ref].vue:327-332`) para sempre — o poll de 15s
(`useKdsBoard.ts:115`) bate num 500, e o operator-kit trata 5xx como *retryável*,
então ele tenta a cada 15s indefinidamente, enchendo a telemetria de erro de
servidor. O operador não tem como saber que a estação foi desligada de propósito.

Isso contraria uma regra já escrita da casa: `docs/reference/errors.md:34` —
"Não encontrado mapeia por TIPO de exceção". A regra existe; a view do board não a
aplica. (`test_api_kds_surface.py:193-207` prova o padrão certo para ticket e pedido.)

**Arquivo:linha:** `shopman/backstage/api/kds.py:67-69` · `shopman/backstage/projections/kds.py:183`.

**Fix mínimo:** exceção de domínio nova em `services/exceptions.py`
(`KDSInstanceNotFound`, irmã de `KDSTicketNotFound`), levantada na projection e
mapeada para 404 na view — mensagem distinguindo "estação não existe" de "estação
está desativada", que são coisas diferentes para quem está com o tablet na mão.

---

### C5 — Payload SSE do canal `kds` carrega `session_key` e `order_ref` · **P2** (D disse P0)

**Risco × esforço:** viola ADR-016 explicitamente, o fix é apagar duas chaves e
nenhum cliente lê nenhuma delas. Mas a exposição incremental hoje é quase nula.

**Mecanismo:** `emit_kds_change` monta um payload de 7 chaves (`_sse_emitters.py:390-399`)
e publica em `backstage-kds-main` **sempre** (`:474`) e no scope da estação
adicionalmente (`:475-476`). O gate lê só o `kind` (`eventstream.py:57`), então
qualquer portador de `backstage.operate_kds` assina `/events/kds/` e recebe o fluxo
de todas as estações, com `session_key` — a chave que costura ticket ↔ comanda ↔ Order.

**Por que P2 e não P0:** quem recebe isso já pode fazer `GET /api/v1/backstage/kds/<qualquer-ref>/`
e ler o board inteiro *com nome do cliente* (`projections/kds.py:437-441`). O único
dado marginal é o `session_key`, e o grupo Cozinha **não tem `cashman.operate_pos`**
(`test_group_permission_parity.py:67-69`), que é o gate dos endpoints que aceitam
`session_key` como entrada (`api/operations.py:2493,2515,2543`). Ou seja: hoje é
uma chave que o portador não consegue usar. O que torna o achado legítimo é a
regra, não o dano: ADR-016 regra 1 diz "payload mínimo, não dados sensíveis", e o
canal `tabs` ao lado foi escrito exatamente assim (`:407-412`).

**Arquivo:linha:** `shopman/shop/handlers/_sse_emitters.py:381-389` (a query de
`order_ref`), `:396-397` (as duas chaves).

**Fix mínimo (é uma deleção):** apagar `"session_key"` e `"order_ref"` do dict — e
com eles a query de `:381-389`, que vira morta. **Zero risco de regressão no
cliente**: `useKdsBoard.ts:94-96` faz `const onPush = () => { refresh(); }` — a UI
não lê campo nenhum do evento. O único ajuste é inverter
`test_kds_sse.py:33` (`assert args[2]["order_ref"] == ...`) em assert negativo.

---

### C6 — Estação não é vinculada a nada · **P2** (G e D disseram P1)

**Risco × esforço:** o dano é confusão operacional, não escalada de privilégio; e o
fix de RBAC proposto pelos dois é caro (modelo novo, override de supervisor,
migração) para um risco que a metade barata resolve.

**Mecanismo:** `api/kds.py:67-69` aceita qualquer `ref`; `api/kds.py:83,118,140,162`
aceitam qualquer `ticket_pk` sem conferir a qual estação ele pertence;
`app.vue:8-10` tranca por permissão. O operador da Bancada 1 abre a URL da Bancada 2
(bookmark errado, tablet trocado) e dá "Finalizar" em tickets que a Bancada 2 ia
fazer. Os tickets viram `done`, os itens viram todos `checked`
(`services/kds.py:510-514`) e o pedido pode avançar para READY sem que aquele
preparo tenha existido.

**Por que P2:** não é escalada — quem faz isso já tem permissão para operar KDS, e
o board é kiosk numa cozinha com uma equipe só. É erro humano com consequência
física, e o antídoto proporcional é identidade, não RBAC.

**Fix mínimo correto (e é o barato):** a "identidade gigante da estação" que os dois
WPs já listam como UX #2 — nome/cor/código da estação grandes no topo, mais
confirmação no "Finalizar". Isso resolve o erro real. O vínculo
operador→estação (`station_ref`, allowlist, override de supervisor) **não deve entrar
neste WP**: é modelo novo sem consumidor provado e depende de uma decisão de
produto (ver H1). D acertou ao vetar o acoplamento a `Terminal` (cashman) e ao exigir
exceção explícita para `type="expedition"` (`projections/kds.py:343-345`).

---

## D. Achados NOVOS (que G e D perderam)

### D1 — "Marcar item" é implementado como *toggle*, com a leitura fora do lock · **P1**

**Risco × esforço:** duas telas na mesma estação é a configuração normal de uma
cozinha, e o efeito é o item **desmarcar sozinho**. Fix é pequeno e mora no core.

**Mecanismo, do toque ao efeito:** a API recebe um comando de *estado desejado*
(`checked: true`). `shopman/backstage/services/kds.py:23-27` lê `ticket.items[index]["checked"]`
**fora de qualquer transação**, compara com o desejado, e só então chama
`kds_core.toggle_ticket_item`, que abre a sua própria transação e faz
`select_for_update` (`shopman/shop/services/kds.py:456-458`, `_locked_ticket:578-579`).
Ou seja: a decisão "isto muda ou não" é tomada com dado sujo; o lock protege só a
inversão.

Dois tablets mostrando a mesma bancada (ou o card e o modal, `[ref].vue:446` e `:460-462`,
que emitem para o mesmo `checkItem`): os dois cozinheiros tocam o mesmo item quase
juntos, ambos querendo `checked=true`. Requisição A lê `current=False` → chama toggle
→ `True`. Requisição B, que já tinha lido `current=False`, chama toggle → **`False`**.
Resultado: o item volta a desmarcado. As duas UIs mostram marcado por otimismo
(`useKdsBoard.ts:169`) e ~500ms depois o `scheduleReconcile` reverte as duas ao
mesmo tempo. O cozinheiro vê o pão que ele marcou desmarcar sozinho e não tem
explicação nenhuma na tela.

**Arquivo:linha:** `shopman/backstage/services/kds.py:23-27` · `shopman/shop/services/kds.py:452-477`.

**Fix mínimo correto:** o core precisa de um `set` em vez de um `toggle`. Dentro de
`_toggle_ticket_item_locked`, receber o estado desejado e escrever
`ticket.items[index]["checked"] = checked` (em vez do `not ...` de `:467`), e apagar
a comparação pré-lock de `services/kds.py:23-24`. A operação vira idempotente por
construção, que é o que a API já dizia ser (`test_api_kds_surface.py:111-121` chama
o teste de "idempotent" — e ele só passa porque roda em série).

Combina bem com C3: os dois fixes tocam a mesma função e a mesma linha do core.

---

### D2 — O painel público de retirada mostra telefone/CPF inteiro quando a comanda é numérica · **P1**

**Risco × esforço:** é a tela do salão, à vista de todo mundo, e a função que
deveria proteger contra isso se chama `_public_comanda_code` e promete no docstring
que protege. Fix de uma linha.

**Mecanismo:** `_public_comanda_code` (`projections/kds.py:322-337`) trata "puramente
numérico" como sinônimo de "não identificante": se `tab_ref` ou `handle_ref` é
`isdigit()`, devolve o número; só o caso não-numérico cai no hash. Mas
`normalize_tab_ref` (`shop/services/pos.py:132-142`) só faz `zfill(8)` em numéricos
**de até 8 dígitos** — acima disso guarda o valor cru. Um telefone (11 dígitos) ou
um CPF (11 dígitos) digitado como referência de comanda passa `isdigit()`, passa por
`display_tab_ref` sem alteração, e vai inteiro para a TV.

**Provado rodando:** `normalize_tab_ref("43999887766")` → `'43999887766'`;
`build_kds_customer_status()` devolve `preparing = ['43999887766']`.

O caminho do operador: o balcão abre a comanda usando o telefone do cliente
(hábito comum de padaria — é o identificador que ele já pediu para o WhatsApp),
dispara para a cozinha, e o número aparece em fonte de 7rem no painel de retirada
(`pickup.vue:148-151`). O `assert "Bia" not in blob` de
`test_api_kds_surface.py:254-261` não pega isto: ele testa nome, não dígito.

Nota: o outro lado da tela é seguro — `Order.ref` de pedido comitado é gerado por
`generate_order_ref` (1 letra + 2 dígitos, `packages/orderman/.../commit.py:363`),
sem relação com o cliente.

**Arquivo:linha:** `shopman/backstage/projections/kds.py:322-337` (especificamente `:333-335`).

**Fix mínimo (a linha):** amarrar a heurística ao formato real de comanda numérica,
que é conhecido e tem no máximo 8 dígitos:

```python
if text.isdigit() and len(text) <= 8:
    return display_tab_ref(text)
```

Tudo acima disso cai no hash `blake2s`, que é o comportamento que o docstring já promete.

---

### D3 — `action` não-string na expedição vira 500 · **P2**

**Mecanismo:** `api/kds.py:185` faz `(request.data.get("action") or "").strip()`.
Um JSON com `"action": {...}` ou `"action": [...]` chega como dict/list, o `or`
não o descarta (truthy), e `.strip()` levanta `AttributeError` → 500.
**Provado rodando**: dict → 500, list → 500.

Contraste que torna isto uma inconsistência e não um detalhe: `test_api_kds_surface.py:164-178`
existe justamente para garantir que **500 significa bug de programação** ("o
operator-kit trata 4xx como não-retryável e a telemetria classifica como erro de
cliente"). Aqui um payload malformado é classificado como bug do servidor e o
cliente entra em retry.

**Arquivo:linha:** `shopman/backstage/api/kds.py:185`.

**Fix mínimo (a linha):** `action = str(request.data.get("action") or "").strip()` —
a validação do conjunto em `:186` já rejeita o resto com 400.

---

### D4 — A rota pública é `kds/cliente/`, em português · **P2**

**Mecanismo:** `shopman/backstage/api/urls.py:176` monta
`/api/v1/backstage/kds/cliente/`. O CLAUDE.md diz, sem exceção: "URL é em inglês.
Ponto. Vale para **toda** rota do sistema — apps Nuxt de operador, telas custom do
Admin, SSE do backstage, APIs. Não há exceção por superfície." A varredura de URLs
(PR #169) pegou Admin e backstage HTML e deixou esta rota de API para trás — ela é
resíduo da era HTMX (`/operacao/kds/cliente/`, ver `docs/plans/completed/OPERATOR-APPS-PLAN.md:252`).
Não há waiver documentado.

Efeito colateral pequeno mas real: como `kds/cliente/` vem antes de `kds/<slug:ref>/`
(`urls.py:176-177`), uma estação cadastrada com `ref="cliente"` fica inalcançável.

**Arquivo:linha:** `shopman/backstage/api/urls.py:176` · `shopman/backstage/api/kds.py:8`
(docstring) · `surfaces/kds-nuxt/app/composables/useKdsCustomerBoard.ts:2,13` ·
`surfaces/kds-nuxt/tests/e2e/README.md:6`.

**Fix mínimo:** renomear para `kds/pickup/`, zerando o nome antigo (pré-go-live, e
não é bookmark de kiosk — é chamada de BFF, o kiosk aponta para `/pickup` do Nuxt).
Sem 301.

---

### D5 — `backstage.operate_kds` lê o canal `orders` por causa de um consumidor que quase nunca está autenticado · **P2 (observação de superfície, não incidente)**

**Mecanismo:** `eventstream.py:129` concede leitura de `backstage-orders-*` a
`backstage.operate_kds`, justificado no comentário `:103-106` pelo "painel de
retirada do KDS, que consome o mesmo `/sse/orders`". Mas o painel de retirada é a
tela pública (`app.vue:13,30,59` isenta `/pickup` de login) e o endpoint REST dele
é `permission_classes = []`. Numa TV de salão sem sessão de operador o `EventSource`
recebe 403 e o painel cai para poll de 10s — o indicador honesto até mostra "Atualiza
sozinho" (`board.ts:227-232`). O grant só é exercido quando alguém abre `/pickup`
no mesmo navegador onde a estação está logada.

O que o grant custa: quem tem só `operate_kds` recebe `ref` + `status` de todo
pedido e, via `_on_payment_changed` (`_sse_emitters.py:300-325`), o `payment_status`
de todo pedido. Não é PII, mas é mais superfície do que o consumidor citado usa.

**Não proponho remover** — a TV de salão logada é um caso plausível e derrubar o
grant a quebraria em silêncio. Registro para que o WP final **não** trate isso como
achado de autorização (é o que o comentário sugere) e para que a pergunta H3 seja
feita ao dono.

---

## E. Achados a DESCARTAR

| Achado | Origem | Por quê |
|---|---|---|
| **`checked` como P0** | D | O fix continua certo, a prioridade não. Provado: a UI só manda boolean real (`useKdsBoard.ts:171` ← `KdsTicketCard.vue:190`). Um bug que nenhum cliente do sistema dispara não é P0. Mantém-se como P2 (C2). |
| **`session_key`/`order_ref` no SSE como P0** | D | Mesma coisa: regra violada, dano marginal. O leitor do canal já lê o board inteiro por REST, com nome do cliente; e não tem `cashman.operate_pos` para usar o `session_key`. P2 (C5). |
| **"SSE autoriza por tipo de canal" como falha de autorização** | G | O REST tem exatamente o mesmo gate grosso (`api/kds.py:67-69`). Contar isso como achado separado do vínculo de estação é contar o mesmo buraco duas vezes. D já corrigiu. |
| **Campo `version`/`rev` novo em `KDSTicket`** | G (implícito) e D (explícito) | Migração + campo novo no Core para um problema que a identidade estável do item resolve sozinha. O CLAUDE.md é explícito: "Não adicionar campos a modelos do Core sem necessidade comprovada." Resolver por `line_id` **dentro do lock** (C3 + D1) elimina a corrida sem `rev` nenhum. Se depois aparecer um segundo consumidor de versão, aí sim. |
| **Vincular `KDSInstance` a `Terminal`** | G | D já vetou e está certo: acopla cozinha a caixa/cashman. Fica fora. |
| **Vínculo operador→estação com override de supervisor** | G e D | Não descartado, mas **fora deste WP**: modelo novo, permissão nova e fluxo de exceção, para um risco de confusão que a identidade visual da estação resolve. Ver C6 e H1. |
| **Envelope comum em todas as mutações (P2)** | G e D | O cliente não lê **nenhum** campo de **nenhuma** dessas respostas (`useKdsBoard.ts:171-178`, `:193-199`). Padronizar `updated_at`/`version`/`blocked_reason` é inventar contrato para consumidor que não existe — e `version` reabre o campo que E descartou acima. Se um dia a UI parar de refazer o fetch e passar a aplicar a resposta, aí o envelope ganha dono. |
| **Checklist de expedição com troco/equipamento (UX #5)** | G; D já ressalvou | Nem `KDSExpeditionCardProjection` nem `Order` expõem esses dados para o KDS. É contrato novo com payman/cashman. Fica como intenção registrada, não como escopo. |
| **`help_text` desatualizado (`models/kds.py:75`)** | D | Correto, mas é uma string de docstring. Entra de carona no fix de C3 (que é quando `line_id` deixa de ser invisível), nunca como item próprio. |

---

## F. Aceites verificáveis

Cada um checável contra o código/teste de hoje, sem infra nova.

1. **Cozinha não vê estações KDS no Admin.** Teste de permissão (padrão de
   `test_permissions.py:192-245`): usuário do grupo Cozinha faz GET em
   `/admin/backstage/kdsinstance/` → 403. E POST no delete → 403.
   *Prova:* teste de backend.
2. **Gerente configura estação.** Mesmo teste, usuário Gerente → 200 na change view.
   *Prova:* teste de backend + `test_group_permission_parity.py` continua verde sem
   entrada nova (é perm de modelo).
3. **`checked` não-booleano é 400 e não altera o ticket.** `"false"` (string, JSON e
   form-encoded), `null`, `1`, `[]` → 400 com `field: "checked"`; `ticket.items[0]["checked"]`
   inalterado. Boolean real continua 200.
   *Prova:* teste de API, quatro casos + o caso feliz.
4. **Marcar item é idempotente sob concorrência.** Duas chamadas simultâneas com
   `checked=true` sobre um item desmarcado deixam o item `True` (hoje deixam `False`).
   *Prova:* teste de backend com `transaction=True` e duas threads, ou — mais barato e
   suficiente — teste unitário provando que `_toggle_ticket_item_locked` **escreve** o
   estado desejado em vez de inverter (assert direto na função, sem corrida).
5. **Item é endereçado por identidade estável.** Remover o item do meio via
   `unfire_session_lines`, depois marcar pelo `line_id` do item sobrevivente → o item
   certo fica marcado. `item_ref` inexistente → 409 com mensagem acionável.
   *Prova:* teste de backend (estende `test_pos_fire.py:233-281`, que já monta o cenário
   de unfire).
6. **`KDSItemProjection` carrega identidade.** `item_ref` presente e não vazio para
   ticket de preparo e para card de expedição; `kdsContract.ts` regenerado.
   *Prova:* teste de contrato — `test_kds_schema_export.py:32-40` já falha sozinho se
   o espelho ficar velho.
7. **Ref de estação inválida → 404; estação desativada → 404 com mensagem própria.**
   Hoje os dois são 500 (medido).
   *Prova:* teste de API, dois casos.
8. **`action` não-string na expedição → 400, nunca 500.** dict e list.
   *Prova:* teste de API (hoje os dois dão 500, medido).
9. **Nenhum evento do canal `kds` contém `session_key` ou `order_ref`.**
   *Prova:* assert-negativo de payload sobre `emit_kds_change`, invertendo
   `test_kds_sse.py:33`. `assert "session_key" not in payload and "order_ref" not in payload`.
10. **Painel público não mostra número de 9+ dígitos.** Sessão aberta com
    `tab_ref` de 11 dígitos e `fired_lines` → o `ref` projetado começa com `#` (hash).
    Comanda de até 8 dígitos continua aparecendo como número.
    *Prova:* teste de projection (estende `test_api_kds_surface.py:254-261`, que já é o
    assert-negativo de PII — hoje ele só cobre nome).
11. **Board de expedição continua global.** Estação de `type="expedition"` lista todos
    os pedidos `ready` independentemente de qualquer regra de estação introduzida.
    *Prova:* teste de backend (guarda de regressão para C6).
12. **A rota pública fala inglês.** `reverse("api-backstage-kds-customer")` resolve para
    `/api/v1/backstage/kds/pickup/`; `kds/cliente/` não existe mais em nenhum arquivo.
    *Prova:* teste de API + `grep` no CI (ou o gate de URL que já existir).

---

## G. Fronteiras e colisões

### Arquivos que este WP precisa tocar

**Backend — mutação:**
- `shopman/backstage/api/kds.py` — C2 (`:88`), C4 (`:67-69`), D3 (`:185`), C3 (`:85,92-97`), D4 (docstring `:8`)
- `shopman/backstage/api/urls.py` — D4 (`:176`)
- `shopman/backstage/services/kds.py` — C3, D1 (`:18-28`)
- `shopman/backstage/services/exceptions.py` — C4 (`KDSInstanceNotFound`)
- `shopman/backstage/projections/kds.py` — C3 (`:41-51`, `:449-459`, `:503-513`), C4 (`:183`), D2 (`:322-337`)
- `shopman/backstage/models/kds.py` — só o `help_text` (`:75`). **Sem migração.**
- `shopman/backstage/admin/kds.py` — C1 (apagar `:53-63`)
- `shopman/shop/services/kds.py` — C3/D1 (`:452-477`)
- `shopman/shop/handlers/_sse_emitters.py` — C5 (`:381-399`)
- `shopman/shop/management/commands/setup_groups.py` — C1 (uma linha no bloco Gerente, ~`:148`)

**Backend — testes:**
- `shopman/backstage/tests/test_api_kds_surface.py`
- `shopman/backstage/tests/test_kds_sse.py` (**inverter `:33`**)
- `shopman/backstage/tests/test_kds_projections.py`
- `shopman/backstage/tests/test_kds_service.py`
- `shopman/shop/tests/test_permissions.py` (C1)

**Superfície:**
- `surfaces/kds-nuxt/app/composables/useKdsBoard.ts` (`:164-179` — mandar `item_ref`)
- `surfaces/kds-nuxt/app/composables/useKdsCustomerBoard.ts` (`:2,13` — D4)
- `surfaces/kds-nuxt/app/components/KdsTicketCard.vue` (`:186-190`)
- `surfaces/kds-nuxt/app/components/KdsTicketModal.vue` (`:153-157`)
- `surfaces/kds-nuxt/app/pages/[ref].vue` (`:446,460-462` — assinatura do evento; identidade da estação em C6)
- `surfaces/kds-nuxt/app/generated/kdsContract.ts` (**gerado** — `python manage.py export_kds_schema`, nunca à mão)
- `surfaces/kds-nuxt/tests/*`

### Colisões prováveis com outros WPs

| Arquivo | Com quem colide |
|---|---|
| `shopman/shop/handlers/_sse_emitters.py` | **Alta.** Arquivo único para todos os canais SSE (orders, cash, tabs, production, alerts). Qualquer WP de PDV/Gestor/Produção mexe aqui. |
| `shopman/shop/eventstream.py` | Alta, mesmo motivo — mas **este WP não precisa tocá-lo** se o fix de C5 for só no payload. Recomendo não tocar. |
| `shopman/shop/management/commands/setup_groups.py` | **Alta.** Todo WP com RBAC passa por aqui. Uma linha só reduz o atrito. |
| `shopman/shop/tests/test_group_permission_parity.py` | Alta — mas a solução de C1 **não o altera** (perm de modelo, não custom). Vantagem concreta sobre a proposta de G/D. |
| `shopman/shop/services/kds.py` / `shopman/shop/adapters/kds.py` | Média. `unfire_session_lines` é consumido pelo PDV (`pos.py:1205`); qualquer WP de PDV que mexa em fire/unfire encosta aqui. |
| `shopman/backstage/api/urls.py` | Média. Arquivo de 400+ linhas compartilhado por todas as APIs do backstage. |

### Permissões novas propostas e impacto em `setup_groups.py`

**Nenhuma permissão custom nova.** Li `shopman/shop/management/commands/setup_groups.py`
inteiro (grupos Caixa `:102-105`, Cozinha `:106-122`, Gerente `:123+`, Dono). A
proposta de C1 usa as perms de modelo que a migração `0001_initial` já criou:

- **Cozinha:** perde o acesso ao `KDSInstance` no Admin automaticamente (não tem
  `_ver("backstage")`). Zero linha alterada no bloco.
- **Gerente:** já tem `view_kdsinstance` via `*_ver("backstage")` (`:142`). Falta
  escrita — **uma linha**: `*_escrever("backstage", "kdsinstance"),`
  (`_escrever` dá `add_` + `change_`; `delete_` fica de fora por decisão já
  documentada em `:91-94`: "Apagar fica de fora de propósito"). Isso, de quebra,
  resolve o CASCADE de C1 pela raiz — **ninguém** passa a poder apagar estação pelo
  Admin, que é o comportamento certo.

`backstage.manage_kds_config`, proposta por D, **não é necessária** e custa
migração + entrada nova em `test_group_permission_parity.py`.

### O que pertence a outro app/dono

- **`unfire_session_lines`** (`shop/adapters/kds.py:57-90`) é escrito pelo PDV. O KDS
  é vítima do deslocamento, não dono da causa. Este WP conserta o *endereçamento*
  (C3); mudar a semântica do unfire é WP do PDV.
- **`_on_payment_changed` / canal `orders`** (`_sse_emitters.py:300-325`,
  `eventstream.py:129`) é do Gestor de Pedidos. D5 é observação para o dono daquele
  WP, não trabalho deste.
- **`generate_order_ref`** (orderman) e `normalize_tab_ref` (`shop/services/pos.py:132`)
  são de outros donos. D2 se resolve **inteiramente dentro da projection do KDS** —
  não mexer em `pos.py`.
- **`Terminal` / cashman** — fora, conforme D.
- **Sons, densidade, undo, visual regression** (UX #3, #4, #7, #8) são melhorias de
  superfície sem contrato de backend; podem ir num WP de UX separado sem bloquear nada
  daqui.

---

## H. Perguntas abertas para o dono do produto

**H1. Uma bancada pode dar "Finalizar" no ticket de outra bancada, e isso deve ser
impedido pelo sistema ou pela tela?**
Hoje qualquer `operate_kds` opera qualquer estação (C6). Existem dois caminhos com
custo muito diferente: (a) identidade visual gigante + confirmação no Finalizar —
barato, resolve o erro humano; (b) vínculo operador→estação com override de
supervisor — modelo novo, permissão nova, fluxo de exceção. Só o dono sabe se, na
Nelson, "a Bancada 1 nunca deve tocar na Bancada 2" é regra ou só etiqueta. A
resposta decide se C6 é UX ou RBAC.

**H2. O balcão usa o telefone do cliente como referência de comanda?**
Se sim, D2 é P0 e não P1 — hoje o número aparece inteiro na TV do salão (medido). Se
a comanda é sempre número de mesa/senha (≤ 8 dígitos), o fix de uma linha é apenas
higiene preventiva. A pergunta muda a prioridade, não o fix.

**H3. A TV de retirada do salão roda logada como operador ou em navegador anônimo?**
Se roda anônima, o grant de `backstage.operate_kds` sobre o canal `orders`
(`eventstream.py:129`) não serve a ninguém e pode encolher; se roda logada, ele é
load-bearing e sair dele quebraria o push do painel em silêncio (D5). Não dá para
descobrir isso lendo código.
