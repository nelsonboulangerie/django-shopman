# Contra-auditoria dos P0 de `02-storefront-contract.md` e `06-admin.md`

**Método:** cada P0 foi tratado como FALSO até a fonte provar o contrário. Reli as linhas citadas
(números envelhecem), procurei o guarda que o auditor pode ter perdido, perguntei se o gatilho é
alcançável **neste deployment** (`config/settings.py`, `config/management/commands/seed.py`,
`setup_groups.py`, `setup_operators.py`), procurei teste que passe sobre o caminho, e checquei a
severidade contra a régua: **P0 = trava go-live, perde dinheiro, corrompe dado ou fura segurança.**
"Piora a experiência" é P1. "Podia ser melhor" é P2.

**Somente leitura.** Nenhum arquivo do repositório foi alterado, nenhum teste foi executado
(regra da casa: banco compartilhado). Django e Nuxt foram lidos no venv/`node_modules` instalados.

Raiz dos caminhos: `/Users/pablovalentini/Dev/Claude/django-shopman/.claude/worktrees/agente-c-audit-fixes-0dcab9/`

**Vocabulário dos veredictos**

| Veredicto | Significa |
|---|---|
| `CONFIRMED` | fato **e** severidade se sustentam. |
| `OVERSTATED` | o fato se sustenta, mas a consequência descrita ou a severidade não. |
| `REFUTED` | a consequência afirmada é falsa neste deployment. |
| `DUPLICATE` | mesmo defeito já contado em outro item. |

---

## Placar

| # | Claim | Veredicto | Severidade corrigida | Evidência decisiva |
|---|---|---|---|---|
| 1 | Chave de idempotência do cliente nunca chega ao Django; "Pedir de novo" vira no-op | `OVERSTATED` | **P1** | `surfaces/storefront-nuxt/server/utils/djangoProxy.ts:134-171` (monta headers do zero; repassa `x-forwarded-for`, **não** `x-idempotency-key`) × `shopman/shop/services/remote_mutations.py:37` (lê `Idempotency-Key`) × `:39-46` (fallback de **corpo** `idempotency_key`) × `shopman/storefront/api/surface.py:406-409`. O caminho do dinheiro (checkout) manda a chave no CORPO — `surfaces/storefront-nuxt/app/utils/checkoutPayload.ts:31,49` — e está intacto. |
| 2 | `PATCH /account/profile/` é um PUT disfarçado | `CONFIRMED` (**já corrigido**) | P0 no laudo → **resolvido** em `eb98961fb` | `shopman/storefront/api/account.py:373-381` (`"x" in payload` → `UNSET`), `shopman/shop/services/account.py:123-166` (`email_provided`, `campos` incremental), `shopman/shop/sentinels.py:1-41`. Testes de alcance: `shopman/storefront/tests/api/test_account_summary.py:177-216` (ausente não apaga) e `:218-240` (vazio ainda apaga). Fix correto e completo — ver §2. |
| 3 | Uma falha transitória apaga a tela de acompanhamento e ela nunca se recupera | `OVERSTATED` | **P1** | Mecânica confirmada no Nuxt instalado (4.5.2): `surfaces/storefront-nuxt/node_modules/nuxt/dist/app/composables/asyncData.js:375-376` reseta `data` para o default no `catch`. Guardas: `pedido/[ref]/index.vue:172` (foco/reconexão), `:180` (SSE), `:204-206` (poll), `:214-218` (deadline) — todas por `tracking.value?.is_active`. **Mas** a tela mostra estado de erro com "Tentar de novo" (`:451-458`) e o botão chama `refresh` (`:458`). |
| 4 | Reorder nunca pergunta antes de mexer numa sacola cheia; "Substituir" adiciona | `OVERSTATED` | **P1** | `surfaces/storefront-nuxt/app/composables/useReorder.ts:10,20` (`mode` default `'append'`, sempre no corpo) × `shopman/storefront/api/surface.py:401-403` (409 só sem `mode`). `performAction` sem 2º argumento em `conta/index.vue:243`, `conta/pedidos.vue:157`, `pedido/[ref]/index.vue:892`. Contraste correto: `oferta/[ref].vue:34,45` (`body: mode ? { mode } : {}`). |
| 5 | Painel de alérgenos some porque `has_any` é `@property` | `REFUTED` (como P0) | **P2** | `shopman/storefront/api/projections.py:14-18` (só `dataclasses.fields()`) e `presentation/product_detail.py:64-67` são verdade. **Mas** `config/management/commands/seed.py:718-721` semeia `food_safety_notice` não-vazio → `trace_notice` verdadeiro (`product_detail.py:364,534-542`) → o acordeão de `produto/[sku].vue:299` **sempre renderiza** e os alérgenos saem por campos reais (`:304-305`). Nutricional não usa `has_any` (`[sku].vue:70` → `presentation/product.ts:22-35`). |
| 6 | Estorno em massa sem confirmação devolve o dinheiro de N cobranças pelo gateway | `OVERSTATED` | **P1** | Ausência de confirmação: verdade (`packages/payman/…/contrib/admin_unfold/admin.py:313-329`; Django despacha ação de lote sem página intermediária — `django/contrib/admin/options.py:1590-1626`). **Mas não há gateway nenhum nesse caminho:** `PaymentService.refund` (`packages/payman/shopman/payman/service.py:584-729`) só grava `PaymentTransaction` e emite `payment_refunded`; o único receptor é o emissor de SSE (`shopman/shop/handlers/_sse_emitters.py:184,215`). Quem fala com a Efí/Stripe é `shopman/shop/services/payment.py:718-735`, que o Admin **não** chama. |
| 7 | O mesmo estorno inventa a causa da falha e engole o erro | `DUPLICATE` de #6 + `OVERSTATED` | **P2** | Mesmo bloco de 12 linhas do #6 (`…/admin.py:313-342`), contado como dois P0. O fato (mensagem sintética + `quiet=True`) é verdade em `:325-329` e `:331-342`. O cenário caro — "saiu no gateway e a resposta se perdeu → dinheiro sai duas vezes" — é **impossível**: não há chamada de gateway aqui (ver #6). |
| 8 | ~20 ações mutantes rodam com permissão de **ler** | `CONFIRMED` (escopo corrigido) | **P0** (só para `enable_rules`/`disable_rules`); P1 para o resto | Django 6.0.5, verificado no venv: `django/contrib/admin/options.py:1021-1035` — ação sem `allowed_permissions` **passa sem filtro**; `get_actions` é o único portão de `response_action` (`:1590-1626`). Escalação real e viva: `shopman/shop/admin/rules.py:229,234` (sem `permissions=`) com `has_view_permission` no default enquanto `has_change_permission` exige `manage_rules` (`:187-190`) — e a Gerente tem `view_ruleconfig` via `setup_groups.py:146` e **não** tem `manage_rules`. A Gerente é uma pessoa real e logável: `setup_operators.py:93` (`joyce`, is_staff, com senha). |
| 9 | Reajuste de preço em massa: sem confirmação, sem prévia, percentual livre, sem teto | `REFUTED` (como P0) | **P2** | Ausência de trava: verdade (`packages/offerman/…/contrib/admin_unfold/admin.py:587-618`; `price_percent` é `forms.CharField` sem validator — `:292-297`). **Mas o preço da vitrine não vem de `base_price_q`:** `packages/offerman/shopman/offerman/service.py:104-110` prefere o `ListingItem`, e o seed cria um item com `price_q` explícito para **todo** produto nas três listagens (`config/management/commands/seed.py:2722-2735`). O cenário "a loja passa a vender pão a R$ 21" não acontece. |

**Contagem:** 2 `CONFIRMED` (uma delas já corrigida) · 4 `OVERSTATED` · 2 `REFUTED` · 1 `DUPLICATE`.
Dos 9 P0 alegados, **1 sobrevive como P0** (#8, e só na parte de `RuleConfig`) e **1 era P0 e já foi
corrigido** (#2). Os outros 7 são P1 ou P2.

---

## §1 — Chave de idempotência: `OVERSTATED`, P1

**O que o auditor acertou.** Tudo, no plano do fato — e a duração é pior do que ele escreveu.

- O BFF monta `headers` do zero e nunca copia `x-idempotency-key`: `djangoProxy.ts:134-171`. (O
  laudo cita `:98-123`; as linhas correram por causa do fix de XFF de `a665b9ec2`, mas o conteúdo
  é o mesmo.)
- O Django procura `Idempotency-Key`, não `x-idempotency-key`: `remote_mutations.py:37`. Não é
  questão de caixa — `HttpHeaders` do Django é case-insensitive, mas o prefixo `x-` é outro nome.
- O fallback do reorder é determinístico: `surface.py:406-409` → `reorder:{ref}:{mode}`, e o front
  sempre manda `mode='append'` (`useReorder.ts:10,20`).
- `run_idempotent_mutation` do reorder não passa `cache_response`, então o default
  `response_code < 500` guarda o 200 (`remote_mutations.py:77-82`).

**O que ele subestimou.** `_acquire` (`remote_mutations.py:93-108`) devolve o registro `done`
**sem consultar `expires_at`**, e não existe comando de purga de `IdempotencyKey` em lugar nenhum
(varri `shopman/shop/management/commands/`). Não é "no-op por 24h": é no-op **permanente** para
aquele `(ref, mode)`.

**O que ele exagerou.** A severidade. Três razões:

1. **O caminho do dinheiro não passa por aqui.** O checkout manda a chave no **corpo**
   (`checkoutPayload.ts:31,49` → `idempotency_key`), e `idempotency_key_from_request` lê o corpo
   como segunda fonte (`remote_mutations.py:39-46`). O commit de pedido está protegido de verdade.
2. **Os outros fallbacks determinísticos são o comportamento correto.** `cancel:{ref}`,
   `waitlist-confirm:{ref}`, `confirm-received:{ref}` (`tracking.py:289,374,465`) são operações
   naturalmente uma-vez-por-pedido; replay é o que se quer. O único caso em que "repetir" é a
   intenção do cliente é o reorder — e a avaliação (`rate:{ref}`, `:549`), que o próprio auditor
   já classificou como menor.
3. Não perde dinheiro, não corrompe dado persistido, não fura permissão. Quebra uma conveniência
   de recompra — com um efeito colateral feio (`setFromServer` de uma sacola velha em
   `useReorder.ts:22`, dessincronizando o estado do cliente do da sessão).

**Teste que "prova" e não prova.** `shopman/storefront/tests/test_remote_multisurface_contract.py:427-431`
afirma `"order-reorder" in surface_api` e `"idempotency_key_from_request" in surface_api` — string,
não porta. E `surfaces/storefront-nuxt/tests/composables/useReorder.test.ts:42` prova que o
**cliente envia** o header; ninguém prova que ele **chega**. É o modo de falha que o próprio
laudo do admin nomeia em P1-1 ("o teste prova a string, não a porta"), aqui do lado do storefront.

**Veredicto:** fato confirmado (e pior que o descrito), severidade P1.

---

## §2 — `PATCH /account/profile/`: `CONFIRMED`, já corrigido — e o fix está certo

O P0 original era real. O commit `eb98961fb` o fechou. Auditei o **fix**, não a alegação:

**Semântica de três estados, e ela existe.** `UNSET` é singleton com `is` como teste
(`shopman/shop/sentinels.py:22-41`), mora em `shop` (lado certo da seta de dependência) e é
reexportado por `storefront/intents/types.py:8`, que é de onde a view importa
(`api/account.py:349`). O dataclass nasce com `UNSET` como **default** nos três campos opcionais
(`intents/types.py:94-97`) — então um chamador futuro que esquecer um campo cai no seguro, não no
apagador.

**Todos os chamadores conferidos.** Só existem dois construtores de `ProfileUpdateIntent`:
- `api/account.py:383-388` — o vivo. `"last_name" in payload` / `"email" in payload` /
  `"birthday" in payload` (`:373-381`). Correto.
- `intents/account.py:41-46` — o legado de form-POST, que passa os quatro explicitamente. **Não
  tem chamador nenhum** (grep em todo o repo: só a definição). Como ele preenche os quatro, a
  semântica dele é PUT — o que é o certo para um form completo. Não é uma segunda porta furada.

**O caminho "vazio ainda limpa" sobreviveu.** `services/account.py:150-156`: `elif email_provided`
apaga o `ContactPoint` primário quando veio `""`. E `campos["email"] = ""` desce para
`customer_service.update`, que só toca as chaves recebidas
(`packages/guestman/…/services/customer.py:246-265`) — a ordem importa e está certa: o delete do
ContactPoint acontece **antes** do `save()`, então o `_sync_contact_points` não o recria.
`last_name=""` e `birthday=""`→`None` idem (`api/account.py:376-381`).

**Travado por teste de comportamento, não de string.** `test_account_summary.py:177-216` (PATCH só
com `first_name` preserva e-mail, sobrenome, aniversário **e** o ContactPoint) e `:218-240`
(`{"email": ""}` apaga o ContactPoint). São chamadas HTTP reais contra a view.

**Resíduo (P2, não bloqueia):** se o corpo JSON for uma lista em vez de objeto,
`payload.get("first_name")` levanta `AttributeError` → 500. É pré-existente ao fix e vale para
outras views; anoto por completude, não como achado desta linha.

---

## §3 — Tela de acompanhamento: `OVERSTATED`, P1

**O que se sustenta.** A mecânica inteira, verificada contra o pacote instalado (não contra a
documentação): `node_modules/nuxt/dist/app/composables/asyncData.js:369-377` — no `catch`,
`asyncData.data.value = unref(options.default())`. Sem `default`, vira `undefined`; `tracking`
vira `null` (`pedido/[ref]/index.vue:58`); e as quatro rotas de auto-recuperação são todas
gateadas por `tracking.value?.is_active` (`:172`, `:180`, `:204-206`, `:214-218`). O `setInterval`
continua rodando, mas o corpo dele nunca mais executa. Isso é verdade e é feio.

**Onde a severidade não fecha.** O auditor descreve a tela como "fica ali para sempre" e só na
frase final admite que "só o botão Tentar de novo resolve". O botão **está na tela, com o texto
certo, ao lado do erro**: `:451-458`, dentro do `v-else-if="error"`, com
`@click="refresh"`. Não é uma tela morta sem saída — é uma tela que perdeu a recuperação
automática e mantém a manual, visível e rotulada.

P0 exige travar go-live, perder dinheiro, corromper dado ou furar segurança. Isto é degradação de
experiência num caminho com afordância de recuperação. **P1.**

---

## §4 — Reorder / "Substituir": `OVERSTATED`, P1

**Os dois fatos se sustentam,** verificados linha a linha:
1. `useReorder.ts:10` (`mode: 'append'|'replace' = 'append'`) e `:20` (`body: { mode }`) garantem
   que `mode` **sempre** chega; `surface.py:403` só devolve 409 quando `mode not in {"replace","append"}`.
   O 409, a `ReorderConflictProjection` e os três diálogos são código morto.
2. `performAction(conflictReplaceAction)` é chamado sem segundo argumento nos três lugares
   (`conta/index.vue:243`, `conta/pedidos.vue:157`, `pedido/[ref]/index.vue:892`) — se o diálogo
   aparecesse, "Substituir" somaria.

**Onde o P0 não fecha.** O efeito não é silencioso e não custa dinheiro sem consentimento: o
`submit` termina com `navigateTo('/sacola')` (`useReorder.ts:24`), então o cliente **aterrissa na
sacola**, vendo exatamente o que ficou lá dentro, antes de qualquer passo de pagamento; e o
checkout ainda reconfere o total contra `expected_total_q` (`checkoutPayload.ts:33`). O dano é
"a sacola cresceu sem me perguntar e eu tenho que desfazer na mão" — irritação real, não perda.

O item 2 é, hoje, **latente**: depende do item 1 ser corrigido primeiro. Vale consertar os dois no
mesmo commit exatamente por isso (senão a correção do 409 estreia com o botão "Substituir"
mentindo), mas latente-atrás-de-código-morto não é P0.

---

## §5 — Alérgenos: `REFUTED` como P0, P2 real

**O fato técnico é verdadeiro.** `projection_data` percorre só `dataclasses.fields()`
(`api/projections.py:14-18`), e `has_any` é `@property` (`presentation/product_detail.py:65-67`,
`:97-99`, `:113-115`). A chave nunca sai no JSON, e o TS mente (`types/shopman.ts:97,103,120`
declaram `has_any?`).

**Três coisas derrubam a conclusão.**

1. **O painel de alérgenos NÃO some neste deployment.** A condição é uma disjunção:
   `product.allergen?.has_any || product.ingredients_text || product.trace_notice`
   (`produto/[sku].vue:299`). `trace_notice` vem de `Shop.food_safety_notice`
   (`product_detail.py:364,534-542`) — e o seed da casa o preenche com
   *"Produzido em cozinha compartilhada. Pode conter traços de leite, ovos…"*
   (`config/management/commands/seed.py:718-721`). Uma padaria de cozinha compartilhada não
   esvazia esse campo; é o texto de conformidade dela. Com `trace_notice` verdadeiro, o acordeão
   **sempre** renderiza, e as linhas de alérgeno usam campos reais e serializados
   (`:304-305` → `product.allergen.allergens`). **Nenhum dado de alérgeno fica invisível.** A
   repro do laudo exige `Shop.food_safety_notice` vazio, que não é o estado do deployment.
2. **A projeção nutricional não é afetada.** O laudo cita `:97-99` como um dos três casos, mas a
   tela não usa `nutrition.has_any`: usa `nutritionTable(product.nutrition)`
   (`produto/[sku].vue:70`), que decide por `rows.length`/`energy_kcal_display`
   (`app/presentation/product.ts:22-35`). O `has_any` do nutricional é propriedade morta, inofensiva.
3. **O `has_any` é redundante por construção.** `_allergen` devolve `None` quando não há nada
   (`product_detail.py:450-451`) e `_conservation` idem (`:518-519`). Ou seja, quando o objeto
   existe, `has_any` é sempre `True`. A correção certa é apagar a propriedade e testar o objeto
   (`v-if="product.allergen"`), não promovê-la a campo.

**O que sobra, e é real:** o acordeão **"Conservação"** (`:329`). Ali não há terceiro termo com
fallback de loja: `product.conservation?.has_any || product.unit_weight_label ||
product.approx_dimensions_label`. O seed não preenche `conservation_tips_default`, mas define
`shelf_life_days` em ~15 produtos, e quase nenhum tem `unit_weight_g`. Para esses, a projeção de
conservação existe e a tela a esconde. É informação de validade sumindo da PDP — **P2**, uma
correção de uma linha.

---

## §6 — Estorno em lote: `OVERSTATED`, P1 (e o dano real é o inverso do descrito)

**O que se sustenta.** `refund_selected` (`packages/payman/…/contrib/admin_unfold/admin.py:313-329`)
não tem confirmação, enquanto a ação de linha irmã tem `dialog=` com o texto da consequência
(`:230-257`). Django despacha ação de lote direto no POST do changelist, sem página intermediária —
verificado em `django/contrib/admin/options.py:1590-1626`. Unfold não muda isso: o template
`unfold/templates/admin/actions.html` é seletor + botão "Run", sem confirmação. Assimetria real,
merece conserto.

**O que é falso: o gateway.** O laudo diz *"Todos os pagamentos capturados da página voltam para os
clientes, pelo gateway, de verdade. Não há desfazer"*. Segui a chamada:

- `_refund_one` → `PaymentService.refund(intent.ref, amount_q=None, reason="Reembolso via admin")`
  (`…/admin.py:344-347`).
- `PaymentService.refund` (`packages/payman/shopman/payman/service.py:584-729`) valida saldo, cria
  um `PaymentTransaction(type=REFUND)`, muda o status do intent para `REFUNDED` e emite
  `payment_refunded`. **Nenhuma chamada de gateway.** O `gateway_id` é *parâmetro de entrada*, e o
  Admin não passa nenhum.
- Receptores de `payment_refunded`: um só, o emissor de SSE (`shopman/shop/handlers/_sse_emitters.py:184,215`).
- Quem realmente fala com Efí/Stripe é `shopman/shop/services/payment.py:718-735`
  (`adapter.refund(...)`), e o adapter chama `PaymentService.refund` **depois** de o dinheiro sair
  (`shopman/shop/adapters/payment_stripe.py:326-333`). A ordem canônica é gateway → livro. O Admin
  faz só o livro.

**O dano real, que o laudo não descreve — e que é pior num sentido.** A ação **falsifica o razão**:
grava N transações de estorno imutáveis e marca N intents como `REFUNDED` sem que um centavo tenha
voltado. Duas consequências que ninguém vê:

- **O estorno de verdade fica bloqueado.** `_refund_intent` (`services/payment.py:703-706`) desiste
  quando `refundable_q <= 0`. Depois do "estorno" do Admin, o cancelamento legítimo do pedido
  **não estorna nada** e retorna 0 em silêncio. O cliente nunca recebe.
- **A fila de devolução em dinheiro perde a linha.** `pending_cash_refunds`
  (`services/payment.py:583-620`) é derivada de `capturado − estornado`; zerada a diferença, o
  pedido some da lista de "dinheiro a devolver no balcão".

**Severidade.** Corrompe dado financeiro — mas o alcance é `payman.view_paymentintent`, que só o
grupo **Dono** tem (`setup_groups.py:252`) além de superusuário; exige marcar linhas, escolher a
ação no seletor e clicar "Run"; e nenhum dinheiro se move. **P1**, com conserto barato e óbvio
(a opção (b) do próprio laudo — remover a ação de lote — continua sendo a certa, e agora por um
motivo mais forte: a ação **não faz o que o nome diz**).

---

## §7 — "Inventa a causa e engole o erro": `DUPLICATE` + `OVERSTATED`, P2

**É o mesmo defeito do #6.** Mesmas 12 linhas (`…/admin.py:313-342`), mesma ação, mesmo commit de
conserto. Contar a ausência de confirmação e a mensagem de erro da mesma função como **dois P0**
é inflação por fatiamento — o laudo passa de 2 achados para 4 na tabela de prioridade sem que
exista um segundo lugar para consertar.

**O fato menor se sustenta:** `quiet=True` engole a exceção (`:339-341`) e a mensagem afirma uma
causa única, "sem saldo capturado" (`:325-329`), para qualquer falha. Vale corrigir.

**O fato maior é falso.** O cenário caro — *"o estorno saiu no gateway e a resposta se perdeu
(timeout) → o dono estorna de novo → dinheiro sai duas vezes"* — **não pode acontecer**: não há
gateway neste caminho (§6). As exceções possíveis de `PaymentService.refund` são `PaymentError`
de domínio (`service.py:645-682`) e erro de banco. Nenhuma é "transporte", nenhuma deixa dinheiro
em voo. A citação de *"falhar fechado, ou falhar gritando"* está correta como princípio e errada
como diagnóstico: a omissão aqui não retém dinheiro de cliente, esconde por que uma linha de
livro não foi escrita. **P2.**

---

## §8 — Ações mutantes com permissão de ler: `CONFIRMED`, mas com escopo corrigido

Esta é a que sobrevive. Verifiquei empiricamente, como pedido.

**A mecânica do Django, no venv instalado (Django 6.0.5).**
`django/contrib/admin/options.py:1021-1035`:

```python
for action in actions:
    callable = action[0]
    if not hasattr(callable, "allowed_permissions"):
        filtered_actions.append(action)      # ← passa sem filtro
        continue
```

E `get_actions` é o **único** portão: `response_action` (`:1590-1626`) resolve a ação por
`self.get_actions(request)[action][0]` e executa, sem nenhuma checagem adicional de `change`.
Unfold não intercepta ações de lote (`unfold/mixins/action_model_admin.py` só trata
`actions_list/detail/row/submit_line`). Confirmado: **`@admin.action` sem `permissions=` é
executável por quem abre o changelist**, isto é, por quem tem `view_<model>`.

**Onde o laudo exagera: "~20".** Varri o repositório: 38 `@admin.action`, **36 sem `permissions=`**.
Mas a maioria não é escalação. Cruzando com `setup_groups.py`, sobram **cinco ações em quatro
admins** onde alguém tem `view` e **não** tem o direito de escrever:

| Ação | arquivo:linha | Quem escala | O que ganha |
|---|---|---|---|
| `enable_rules` / `disable_rules` | `shopman/shop/admin/rules.py:229` / `:234` | **Gerente** — `view_ruleconfig` via `_ver("shop")` (`setup_groups.py:146`), sem `manage_rules` | liga/desliga regra de preço, furando o portão do WP-GAP-06 |
| `recalculate_quants` | `packages/stockman/…/contrib/admin_unfold/admin.py:211` | **Cozinha** e **Gerente** (`_ver("stockman")`, `:112` e `:140`) | reescreve `Quant._quantity` num admin cujo `has_change_permission` é `False` para todos (`:205`) |
| `complete_selected` | `shopman/backstage/admin/operation.py:149` | **Gerente** (`_ver("backstage")`, `:142`; sem `change_operationchecklistrun`) | carimba `completed_by`/`completed_at` — assinatura de conformidade |
| `mark_reviewed` | `shopman/backstage/admin/consumption.py:105` | **Gerente** (view de `backstage`) | marca proposta da máquina como revisada por gente |

As demais linhas da tabela do laudo **não são escalação**, e vale dizer por quê:
- **offerman** (`update_price_percent`, publish/pause, `add_to_collection`): Gerente e Admin de
  Catálogo têm `change_product` (`setup_groups.py:133`, `:212`). Quem tem `view_product` aqui tem
  `change_product` junto.
- **guestman** (`tag_selected`, `export_selected_csv`, `recalculate_insights`): Gerente tem
  `change_customer` (`:135`). (A exportação de PII merecer portão próprio é outra conversa — não
  é view→write.)
- **`reset_usage`** e **`reset_to_default`**: Gerente tem `_escrever("shop", "promotion", "coupon", "omotenashicopy")` (`:146`).
- **`aliases.confirm/reject_selected`**: Gerente tem add/change dos três aliases (`:188-192`).
- **refs** (`deactivate_selected`, `rename_value_action`): nenhum grupo recebe `view_ref` — só
  superusuário. O próprio laudo já dizia isso e listou como escalação mesmo assim.
- **`backstage/admin/operators.py:119,137,170,188`** (4 ações de PIN/crachá): o admin fecha
  `has_view_permission` em `manage_operators` — a tela e a ação têm a mesma régua.
- **~11 ações em `packages/{offerman,stockman,craftsman,doorman}/…/admin.py`**: código morto, os
  módulos só registram quando o contrib Unfold **não** está instalado, e ele está
  (`config/settings.py:215-219`). O próprio laudo estabelece isso na nota de método e depois não
  a aplica na contagem.

**Por que a parte que sobra é P0 mesmo assim.** `manage_rules` é descrito no próprio arquivo como
*"portão de segurança do WP-GAP-06"* (`setup_groups.py:216-219`), e "Rules Managers" nasce vazio de
propósito. `RuleConfigAdmin` fecha add/change/delete nele (`rules.py:187-194`) e deixa
`has_view_permission` no default. As duas ações de lote furam o portão inteiro com dois cliques.
E o furo é **alcançável por uma pessoa que existe**: `setup_operators.py:93` cria `joyce`,
`is_staff=True`, com senha, no grupo "Gerente". Regra de preço executa expressão — é fronteira de
segurança, não de conveniência.

**O teste que dá falsa segurança.** `shopman/shop/tests/test_rules_hardening.py:100-133` chama
`admin_instance.has_change_permission(request)` e `has_add_permission` diretamente. Ele prova os
**métodos** e não a **porta**: passa verde com as duas ações de lote abertas. Um teste de alcance
(`admin.site._registry[RuleConfig].get_actions(request)` para um usuário só com `view_ruleconfig`)
falharia hoje — e é exatamente o guardrail que o laudo propõe. Concordo com a proposta.

**Severidade:** P0 para `enable_rules`/`disable_rules`. P1 para as outras três (escrita de saldo de
estoque e assinatura de checklist por quem só devia ler — corrompe dado operacional, não fura
dinheiro nem auth).

---

## §9 — Reajuste de preço em massa: `REFUTED` como P0, P2 real

**O que se sustenta.** `update_price_percent` (`…/contrib/admin_unfold/admin.py:587-618`) não tem
confirmação, prévia nem teto; o percentual é `forms.CharField` sem validator (`:292-297`), aceita
`Decimal("1000")`, e o único guarda é `if new_price < 0: new_price = 0` (`:608-609`). A mensagem
final (`:611-617`) é tecnicamente verdadeira e humanamente inútil. Tudo isso é verdade.

**O que derruba o P0.** O cenário é *"o catálogo inteiro multiplica por 2,1. A loja online passa a
vender pão a R$ 21"*. Não passa. A ação toca **só** `base_price_q`, e `base_price_q` **não é o
preço da vitrine neste deployment**:

- `CatalogService.unit_price` prefere o `ListingItem` da listagem e só cai em `base_price_q` quando
  não há item: `packages/offerman/shopman/offerman/service.py:104-110`, com o lookup em
  `:185-211` (`min_qty__lte=qty, is_sellable=True`, `min_qty` default `1` —
  `models/listing.py:105-110`).
- O seed cria `ListingItem` com `price_q` explícito para **todo** produto nas três listagens
  (`pdv`, `ifood`, `web`): `config/management/commands/seed.py:2722-2735`.
- A vitrine do storefront resolve preço por listagem: `shopman/storefront/presentation/catalog.py:452-469`
  (`price_map` primeiro, `contextual_price(listing_ref=channel_ref)` depois).

Ou seja: o dono digita `110`, vê "N produto(s) atualizado(s) com 110%", e **o cliente continua
pagando o mesmo**. O que quebra é o `base_price_q` — que alimenta a margem exibida no Admin
(`models/product.py:368-371`), a faixa de substitutos (`contrib/substitutes/substitutes.py:39-40`)
e o fallback de preço de produto sem listing item.

O auditor **enxergou esse mecanismo** — está lá, sob o rótulo "Agravante" — e tirou a conclusão
oposta: tratou a divergência entre `base_price_q` e o preço de canal como piora do desastre,
quando ela é justamente o que impede o desastre. O achado certo, e menor, é: **a ação promete um
efeito comercial que ela não tem**. Mesma família de desonestidade que ele apontou no #7, no
sentido inverso.

**Atenuante adicional confirmado:** `Product` tem `HistoricalRecords`
(`packages/offerman/shopman/offerman/models/product.py:190`), então o valor antigo é recuperável.

**Severidade: P2.** Vale confirmação e teto — não como trava de go-live, mas porque uma ação que
diz "atualizado" sem atualizar a vitrine é uma armadilha de confiança.

---

## Nota de método para o próximo laudo

Três padrões explicam 6 dos 7 rebaixamentos, e todos são checáveis antes de escrever "P0":

1. **Seguir a chamada até o efeito, não até o nome.** `PaymentService.refund` e
   `update_price_percent` têm nomes que prometem gateway e vitrine; nenhum dos dois entrega. Um
   grep de receptores de sinal e um grep de quem lê o campo teriam resolvido.
2. **Perguntar ao seed antes de escrever a repro.** As repro de #5 e #9 exigem um estado
   (`food_safety_notice` vazio, produto sem `ListingItem`) que o `seed` desta casa não produz.
3. **Contar o alcance, não a ocorrência.** "~20 ações" virou 5 depois de cruzar com
   `setup_groups.py` e com a própria nota de método do laudo sobre código morto — nota que ele
   escreveu e não aplicou.

E um padrão de inflação: **#6 e #7 são a mesma função**. Fatiar um defeito em dois P0 dobra o
tamanho aparente da fila de bloqueio sem dobrar o trabalho de conserto.
