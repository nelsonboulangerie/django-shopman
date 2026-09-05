# Auditoria adversarial — Django Admin (django-unfold)

> ⚠️ **SEVERIDADE REVISADA — leia [`verify-02-06-storefront-admin.md`](verify-02-06-storefront-admin.md) antes de agir por este laudo.**
> 
> Um passe de refutação em 01/09 atacou cada P0 deste arquivo com uma régua única
> (P0 = perde dinheiro, corrompe dado, viola segurança, ou impede tarefa central sem
> contorno). **4 P0 alegados → 1 sobreviveu**, com escopo corrigido de "~20 ações" para **5 escalações vivas**. O estorno em massa NÃO chama gateway — o dano é inverso. O reajuste de preço em massa foi refutado: o preço de prateleira vem de `ListingItem.price_q`.
> 
> As contagens NO CORPO deste arquivo são as originais e estão infladas. O fato de
> cada achado quase sempre se sustenta; a **severidade** não.

Escopo: `shopman/backstage/admin/`, `shopman/backstage/admin_console/`, `shopman/shop/admin/`,
`shopman/storefront/admin/`, todo `admin.py` / `contrib/admin_unfold` sob `packages/*`, todo template
Admin do repositório, `shopman/backstage/projections/` consumidas por páginas Admin, e a máquina do
Unfold Canonical Gate (`Makefile`, `scripts/check_unfold_canonical.py`).

Método: leitura estática. Nenhum teste executado (regra do repositório: banco compartilhado).
Todo achado está ancorado em `arquivo:LINHA` verificado por leitura.

Nota de método importante: **o que está escrito num `admin.py` de pacote nem sempre é o que roda.**
Três camadas reescrevem o registro final:

1. `packages/{craftsman,payman,stockman}/…/admin.py` só registram se o contrib Unfold **não** estiver
   instalado (`packages/stockman/shopman/stockman/admin.py:24`, `packages/craftsman/…/admin.py:12`,
   `packages/payman/…/admin.py:13`). Como o contrib está no `INSTALLED_APPS`
   (`config/settings.py:215-219`), esses módulos são código morto no deployment.
2. `packages/{offerman,guestman,doorman,refs}/…/contrib/admin_unfold/admin.py` fazem
   `admin.site.unregister(...)` no import e re-registram (ex.: `packages/offerman/…/admin.py:46-50`).
3. `shopman/backstage/admin/curation.py:39-68` (`HIDDEN_SCREENS`) faz um `unregister` final de 26
   models, chamado em `shopman/backstage/admin/__init__.py:52`.

Este relatório fala sempre do **estado efetivo do deployment**, não do código-fonte isolado.

---

## Inventory

### A. Páginas Admin custom (contrato canônico)

Contrato exigido por `docs/engineering/unfold_canonical_policy.md:124` e
`.codex/skills/unfold-admin-canonical/SKILL.md` (passo 2-3): `UnfoldModelAdminViewMixin` +
`TemplateView` + `title` + `permission_required` + `.as_view(model_admin=...)` + template estendendo
`admin/base.html` + projection registrada.

| URL | View (arquivo:linha) | title | permission_required | Template | Projection | Contrato |
|---|---|---|---|---|---|---|
| `/admin/settings/` e `/admin/settings/<slug>/` (`config/urls.py:49-53`, `:86-90`) | `SettingsHubView` — `shopman/backstage/admin_console/settings_hub.py:31` | "Configuração" | `shop.view_shop` (`:33`) | `admin_console/settings_hub/index.html` | `projections.settings_hub` | ✅ |
| `/admin/settings/copy/` (`config/urls.py:56-60`) | `CopyCatalogView` — `shopman/backstage/admin_console/copy_catalog.py:46` | "Textos da interface" | `shop.view_omotenashicopy` (`:48`) | `admin_console/copy_catalog/index.html` | `projections.copy_catalog` | ✅ |
| `/admin/pos/terminal/<ref>/agent/` (`config/urls.py:61-65`) | `PosCounterAgentView` — `shopman/backstage/admin_console/pos_counter_agent.py:36` | "Instalar o agente do balcão" | `cashman.change_terminal` (`:24`) | `admin_console/pos_counter_agent/index.html` | `projections.pos_agent` | ✅ |
| `/admin/pos/terminal/<ref>/agent/counter_agent.py` (`config/urls.py:66-70`) | função `pos_counter_agent_download` — `…/pos_counter_agent.py:79` | — | checagem manual `has_perm(REQUIRED_PERM)` (`:85`) | — (FileResponse) | — | ⚠️ fora do contrato **por natureza** (download, não página). Gate manual presente e correto. |
| `/admin/cash/receipt/` e `/<code>/` (`config/urls.py:71-80`) | `CashReceiptVerifyView` — `shopman/backstage/admin_console/cash_receipt.py:51` | "Conferir comprovante" | `cashman.audit_shift` (`:31`) | `admin_console/cash_receipt/index.html` | `projections.cash_receipt` | ✅ |
| `/admin/operators/badge/` (`config/urls.py:81-85`) | `OperatorBadgeView` — `shopman/backstage/admin_console/operator_badge.py:74` | "Crachá do operador" | `cashman.manage_operators` (`:76`) | `admin_console/operator_badge/index.html` | `projections.operator_badge` | ✅ |
| `/admin/2fa/verify/` (`config/urls.py:91`) | `admin_2fa_verify` — `shopman/backstage/views/two_factor.py:28` | — | staff-only manual (`:29`) | `two_factor/verify.html` | — | ⚠️ fora do contrato; **registrado como exceção** no gate (`scripts/check_unfold_canonical.py:303`, `runtime-admin-2fa`). Correto: é interstício de auth, fora do shell Unfold. |
| Dashboard `/admin/` | `dashboard_callback` — `shopman/backstage/admin/dashboard.py:120` | — | — | `shopman/shop/templates/admin/dashboard.html` | `projections.dashboard` | ⚠️ o gate **isenta** esta superfície do check de contrato (ver P2-5) |

**Páginas intermediárias de ação** (idioma Django, não "custom page" — mas montam contexto ad-hoc,
sem projection):
`packages/payman/…/admin.py:288` → `admin/payman/payment_refund.html`;
`packages/refs/…/admin.py:170` → `admin/refs/rename_confirm.html`;
`packages/guestman/…/admin_unfold/admin.py:512` → `admin/guestman/customer/tag_confirm.html`;
`packages/guestman/…/merge/admin.py:111` → `admin/guestman/customer/merge_confirm.html` (**órfã**, ver P1-1).

**Nenhuma página custom viola o contrato canônico.** Este eixo está saudável.

### B. ModelAdmins efetivamente registrados (pós-`unregister`, pós-curadoria)

Legenda de permissão: `A`=add, `C`=change, `D`=delete, `V`=view. `—` = default do Django.

| Model | Admin (arquivo:linha) | list_display legível? | busca/filtro | A/C/D/V sobrescritos | Ações |
|---|---|---|---|---|---|
| `offerman.Product` | `packages/offerman/…/admin_unfold/admin.py:306` (subclassado por `fiscalman/contrib/offerman/apps.py:29` e `offerman/contrib/social/apps.py:30`) | ✅ header + preço + margem + estoque | ✅ ✅ | — / — / **—** / — | 6 (2 mutam preço/coleção) |
| `offerman.Collection` | `…/admin_unfold/admin.py:112` | ✅ | ✅ ✅ | — | — |
| `offerman.Listing` | `…/admin_unfold/admin.py:191` | ✅ | ✅ ✅ | — | — |
| `guestman.Customer` | `packages/guestman/…/admin_unfold/admin.py:286` | ✅ header + RFM + churn | ✅ ✅ | — | 3 (`tag_selected`, `export_selected_csv`, `recalculate_insights`) |
| `guestman.PriceTier` | `…/admin_unfold/admin.py:142` | ✅ | ✅ ✅ | — | — |
| `customer_loyalty.LoyaltyAccount` | `…/admin_unfold/admin.py:748` | ✅ | ✅ ✅ | — | — |
| `orderman.Order` | `shopman/shop/admin/orders.py:73` (subclasse de `packages/orderman/…/admin.py:494`) | ✅ | ✅ ✅ | A=`False` (`:692`), D=`False` (`:696`); **C não** | 1 (histórico, `permissions=["view"]`) |
| `orderman.Session` | `packages/orderman/…/admin.py:147` | ✅ | ✅ ✅ | **nenhum** — tudo readonly, mas D aberto | 1 (histórico) |
| `orderman.Directive` | `packages/orderman/…/admin.py:755` | ✅ | ✅ ✅ | **nenhum** — tudo readonly, D aberto | 1 (histórico) |
| `orderman.Fulfillment` | `packages/orderman/…/admin.py:947` | ✅ | ✅ ✅ | nenhum (editável de propósito) | 1 |
| `payman.PaymentIntent` | `packages/payman/…/admin_unfold/admin.py:164` | ✅ | ✅ ✅ | A/C/D=`False` (`:364`,`:367`,`:370`) | **3 de estorno** |
| `stockman.Quant` | `packages/stockman/…/admin_unfold/admin.py:181` | ✅ | ✅ ✅ | A/C/D=`False` (`:202`,`:205`,`:208`) | 1 (`recalculate_quants`) |
| `stockman.Hold` | `…/admin_unfold/admin.py:348` | ✅ | ✅ ✅ | A/C/D=`False` (`:367`,`:370`,`:373`) | 2 (`release_holds`, `release_hold_row`) |
| `stockman.Move` | `…/admin_unfold/admin.py:294` | ✅ | ✅ ✅ | A/C/D=`False` (`:306`,`:309`,`:312`) | — |
| `stockman.Position` / `StockAlert` / `Batch` | `…:162` / `:479` / `:507` | ✅ | ✅ ✅ | — | — |
| `craftsman.Recipe` | `packages/craftsman/…/admin_unfold/admin.py:357` | ✅ | ✅ ✅ | — | — |
| `craftsman.WorkOrder` | `…/admin_unfold/admin.py:481` | ✅ | ✅ ✅ | — | 1 (abre o Produção) |
| `buyman.Material` / `Supplier` | `packages/buyman/…/admin.py:52` / `:67` | ✅ | ✅ ✅ | — | — |
| `cashman.Terminal` | `shopman/backstage/admin/terminal.py:188` (re-registra por cima de `packages/cashman/…/admin.py:139`; `unregister` em `:246`) | ✅ + saúde | ✅ ✅ | — | — |
| `cashman.Shift` | `packages/cashman/…/admin_unfold/admin.py:152` | ✅ | ✅ ✅ | A/C/D=`False`, **V=`audit_shift`** (`:217`) | — |
| `doorman.PinCredential` | `shopman/backstage/admin/operators.py:62` | ✅ | ✅ ✅ | A=`False`; C/V/módulo/D = `manage_operators` | 4 (crachá, PIN) |
| `refs.Ref` | `packages/refs/…/admin_unfold/admin.py:84` | ⚠️ mostra `target_type`/`target_id` crus | ✅ ✅ | A=`False` (`:113`); **C/D abertos** | 2 (`deactivate_selected`, `rename_value_action`) |
| `shop.Shop` + 8 proxies (`ShopAppearance`, `ShopOperation`, `ShopMenu`, `ShopOrdering`, `ShopProduction`, `ShopLoyalty`, `ShopPurchase`, `ShopPos`, `ShopIntegrations`) | `shopman/shop/admin/shop.py:1518-1773` | ✅ singleton | n/a | A/D=`False` (`:1518`,`:1521`) | — |
| `shop.Channel` | `shopman/shop/admin/channel.py:138` | ✅ | ✅ ✅ | — | — |
| `shop.RuleConfig` | `shopman/shop/admin/rules.py:142` | ✅ + "carrega?" | ✅ ✅ | A/C/D = `manage_rules` (`:187`-`:194`) | 2 |
| `shop.Promotion` / `Coupon` | `shopman/shop/admin/promotion.py` | ✅ | ✅ ✅ | — | 1 (`reset_usage`) |
| `shop.OmotenashiCopy` | `shopman/shop/admin/omotenashi.py:44` | ✅ + "onde aparece" | ✅ ✅ | — | 1 (`reset_to_default`) |
| `shop.DeliveryZone` / `DeliveryDistanceBand` | `shopman/shop/admin/delivery.py:42` / `:12` | ✅ | ✅ ✅ | — | — |
| `shop.QualityGrade` / `QualityDefect` | `shopman/shop/admin/quality.py:16` / `:37` | ✅ | — / — | D=`False` no Grade (`:31`) | — |
| `shop.NotificationTemplate` | `shopman/shop/admin/shop.py:1839` | ✅ | ✅ ✅ | — | — |
| `backstage.DayClosing` | `shopman/backstage/admin/closing.py:15` | ✅ | ✅ ✅ | A/C/D=`False`; V=`perform_closing` (`:56`) | — |
| `backstage.OperationChecklistRun` | `shopman/backstage/admin/operation.py:113` | ✅ | ✅ ✅ | — | 1 (`complete_selected`) |
| `backstage.OperationTaskTemplate` / `OperationChecklistTemplate` | `…/operation.py:31` / `:58` | ✅ | ✅ ✅ | — | — |
| `backstage.OperatorAlert` | `shopman/backstage/admin/alerts.py:17` | ✅ | ✅ ✅ | — (campos readonly) | — |
| `backstage.SignInEvent` | `shopman/backstage/admin/sign_in.py:24` | ✅ | ✅ ✅ | A/C/D=`False` (`:48`-`:54`) | — |
| `backstage.ImportBatch` / `HistoricalSale` / `DailySalesFact` | `shopman/backstage/admin/imports.py:38` / `:75` / `:105` | ✅ | ✅ ✅ | A/C/D=`False` (`_ReadOnly`, `:25-35`) | — |
| `backstage.ProductAlias` / `CategoryAlias` / `PaymentMethodAlias` | `shopman/backstage/admin/aliases.py:86` / `:102` / `:115` | ✅ | ✅ ✅ | — | 2 (`confirm_selected`, `reject_selected`) |
| `backstage.BIAlertRule` | `shopman/backstage/admin/bi_alerts.py:20` | ✅ | ✅ ✅ | D=`False` (`:66`) | — |
| `backstage.BIAlertEvent` / `BIScenarioReport` | `…/bi_alerts.py:71` / `:97` | ✅ | ✅ ✅ | A/C/D=`False` | — |
| `backstage.ConsumptionRole` / `ProductConsumptionTag` | `shopman/backstage/admin/consumption.py:23` / `:56` | ✅ | ✅ ✅ | D=`False` no Role (`:50`) | 1 (`mark_reviewed`) |
| `backstage.OperationEpisodeKind` / `OperationEpisode` | `shopman/backstage/admin/episodes.py:22` / `:46` | ✅ | ✅ ✅ | Episode A/C/D=`False` (`:55`-`:61`) | — |
| `backstage.SeatingSpot` | `shopman/backstage/admin/seating.py:22` | ✅ | ✅ ✅ | D=`False` (`:42`) | — |
| `backstage.POSTab` | `shopman/backstage/admin/pos.py:15` | ✅ | ✅ ✅ | A/C/D/V (`:48`-`:57`) | — |
| `backstage.KDSInstance` | `shopman/backstage/admin/kds.py` | ✅ | ✅ ✅ | A/C/D/V (`:53`-`:62`) | — |
| `storefront.StockAlertSubscription` | `shopman/storefront/admin/stock_alerts.py:33` | ✅ | ✅ ✅ | A/C=`False` (`:52`,`:56`) | — |
| `auth.User` / `auth.Group` / `otp_totp.TOTPDevice` | `shopman/backstage/admin/accounts.py:28` / `:38` / `:66` | ✅ | ✅ ✅ | — | — |

**Telas ocultadas pela curadoria** (`shopman/backstage/admin/curation.py:39-68`, 26 entradas):
`orderman.IdempotencyKey`, `orderman.SessionEvent`, `orderman.Fulfillment`,
`payman.PaymentTransaction`, `doorman.{AccessLink,VerificationCode,CustomerUser}`,
`guestman.{ExternalIdentity,CustomerAddress,ContactPoint}`, `customer_identifiers.*`,
`customer_consent.*`, `customer_insights.*`, `customer_preferences.*`, `customer_timeline.*`,
`customer_loyalty.LoyaltyTransaction`, `refs.RefSequence`, `storefront.CustomerFavorite`,
`taggit.Tag`, `buyman.{SupplierMaterialCost,MaterialConversion}`,
`backstage.OperationTaskRun`, `shop.{Campaign,AnnouncementTemplate,Announcement}`.
Isso invalida vários "riscos" aparentes do código-fonte (ex.: `IdempotencyKeyAdmin` com `status`
editável, `TimelineEventAdmin` sem nenhum override) — as telas não existem.

**Código morto latente** (não roda hoje; volta a valer se alguém tirar um contrib do `INSTALLED_APPS`):
`packages/offerman/shopman/offerman/admin/product.py` (rótulos em inglês + `style=` inline em
`:85-98`), `packages/doorman/shopman/doorman/admin.py`, `packages/guestman/shopman/guestman/admin.py`,
`packages/refs/shopman/refs/admin.py`, `packages/stockman/shopman/stockman/admin.py`,
`packages/craftsman/shopman/craftsman/admin.py`, `packages/payman/shopman/payman/admin.py`.
Nenhum deles é varrido pelo gate (`scripts/check_unfold_canonical.py:261` só alcança
`contrib/admin_unfold`) — ver P1-8.

---

## P0

### P0-1 — Estorno em massa sem confirmação: um clique errado devolve o dinheiro de N cobranças

`packages/payman/shopman/payman/contrib/admin_unfold/admin.py:313-329`

```python
@admin.action(
    description=_("Reembolsar total dos selecionados"),
    permissions=["view"],
)
def refund_selected(self, request, queryset):
    done = 0
    for intent in queryset:
        if self._refund_one(request, intent, quiet=True):
```

A ação de LINHA (`refund_row`, `:230-265`) tem `dialog=` com `RefundConfirmForm` e um texto que diz a
consequência — e o comentário em `:238-247` explica exatamente por que o diálogo existe. A ação de
LOTE, que é N vezes mais destrutiva, **não tem confirmação nenhuma**: ações em massa do Django
executam direto no POST do changelist, sem página intermediária.

Cenário: o Dono abre Cobranças, marca a caixa do cabeçalho ("selecionar todos os N desta página"),
quer "Exportar" e escolhe o item vizinho no seletor. Todos os pagamentos capturados da página voltam
para os clientes, pelo gateway, de verdade. Não há desfazer — só uma cobrança nova, cliente por
cliente. `PaymentService.refund` é chamado com `amount_q=None`, ou seja, saldo restante inteiro.

**Correção:** dar à ação de lote a mesma régua da de linha. Ou (a) transformá-la numa página
intermediária de confirmação que **liste ref, cliente e valor de cada intent** e exija digitar o total
(padrão já usado em `refs.rename_value_action` e `guestman.tag_selected`), ou (b) removê-la — estorno
em lote não é fluxo real de padaria; a ação de linha cobre o caso. A opção (b) é a mais barata e a
mais honesta.

### P0-2 — O mesmo estorno em lote inventa a causa da falha e engole o erro

`packages/payman/…/admin_unfold/admin.py:325-329` e `:331-342`

```python
if done < queryset.count():
    messages.warning(
        request,
        _("%(n)d intent(s) não puderam ser reembolsados (sem saldo capturado).")
```
```python
except Exception as exc:  # PaymentService valida elegibilidade e levanta
    logger.warning("refund failed for %s: %s", intent.ref, exc)
    if not quiet:
        messages.error(request, str(exc))
    return False
```

`quiet=True` é passado pela ação de lote, então **toda** exceção some da tela. A mensagem então
afirma uma causa única — "sem saldo capturado" — para qualquer falha: timeout do gateway, 500 da Efí,
credencial expirada, erro de rede. Duas mentiras possíveis, ambas caras:

- O estorno **falhou por elegibilidade** → mensagem certa por acidente.
- O estorno **saiu no gateway e a resposta se perdeu** (timeout) → o sistema diz ao dono que não
  reembolsou. Ele reembolsa de novo pela tela de linha. Dinheiro sai duas vezes.

Isso viola diretamente a regra da casa *"falhar fechado, ou falhar gritando"* — dinheiro não pode ter
omissão otimista.

**Correção:** acumular `(intent.ref, str(exc))` e listar as falhas com o motivo real, uma linha por
intent, em `messages.error`. Nunca sintetizar uma causa. E `except Exception` deveria ao menos separar
"erro de elegibilidade do domínio" de "erro de transporte", porque a segunda categoria exige
reconciliação, não repetição.

### P0-3 — Ações que mutam estado rodam com permissão de **ler**

`packages/django/contrib/admin/options.py:1021-1035` (Django): uma `@admin.action` **sem**
`permissions=` nunca é filtrada — fica disponível para qualquer um que consiga abrir o changelist,
isto é, quem tem `view_<model>`.

Isso colide de frente com a regra da casa registrada em memória: *"agir ≠ abrir a tela — `view_<model>`
junto"*. O RBAC real (`shopman/shop/management/commands/setup_groups.py`) concede blocos inteiros de
`view_*` por app (`_ver()`, `:60-89`) e deliberadamente **não** concede `delete_*` (`_escrever()`,
`:91-99`). Resultado: os grupos existem exatamente na configuração em que este furo é explorável.

Casos concretos, checados contra os grupos que o `setup_groups` cria:

| Ação | arquivo:linha | `permissions=` | Quem alcança hoje | O que muda |
|---|---|---|---|---|
| `recalculate_quants` | `packages/stockman/…/admin_unfold/admin.py:211` | **ausente** | **Cozinha** e **Gerente** (`setup_groups.py:112`, `:140` — só `view_quant`) | reescreve `Quant._quantity` a partir dos Moves; um saldo semeado sem ledger vira zero |
| `complete_selected` | `shopman/backstage/admin/operation.py:149` | **ausente** | **Gerente** (`setup_groups.py:142` = `*_ver("backstage")`, sem `change_operationchecklistrun`) | conclui checklist operacional carimbando `completed_by`/`completed_at` — assinatura de conformidade |
| `confirm_selected` / `reject_selected` | `shopman/backstage/admin/aliases.py:59` / `:76` | **ausente** | **Gerente** (tem add/change de alias, mas a porta não exige) | carimba a curadoria que decide o que o B.I. lê |
| `mark_reviewed` | `shopman/backstage/admin/consumption.py:105` | **ausente** | **Gerente** (`view_productconsumptiontag`) | marca proposta da máquina como revisada por gente |
| `deactivate_selected` / `rename_value_action` | `packages/refs/…/admin_unfold/admin.py:130` / `:144` | **ausente** | superusuário (nenhum grupo tem `view_ref`) | desativa/renomeia refs em massa, além das linhas selecionadas |
| `update_price_percent`, `unpublish/publish/pause/resume`, `add_to_collection` | `packages/offerman/…/admin_unfold/admin.py:587`, `:571-583`, `:621` | **ausente** | Gerente / Admin de Catálogo (que também têm `change_product` — exposição baixa hoje, mas por acidente) | preço e visibilidade do catálogo |
| `tag_selected`, `export_selected_csv`, `recalculate_insights` | `packages/guestman/…/admin_unfold/admin.py:467`, `:526`, `:549` | **ausente** | Gerente | etiquetas, **exportação de PII**, insights |
| `reset_usage` | `shopman/shop/admin/promotion.py:89` | **ausente** | Gerente (`view_promotion`) | zera contador de usos de promoção |
| `reset_to_default` | `shopman/shop/admin/omotenashi.py:99` | **ausente** | Gerente | desativa textos personalizados |
| `enable_rules` / `disable_rules` | `shopman/shop/admin/rules.py:229` / `:234` | **ausente** | mitigado: `has_change_permission` exige `manage_rules` (`:190`) e `enabled`/`disabled` só aparecem para quem abre a tela, que também exige `manage_rules`… **mas** as ações não checam nada, e `_filter_actions_by_permissions` não as filtra. Como `has_view_permission` cai no default (`view_ruleconfig`, que **Gerente tem** via `_ver("shop")` em `setup_groups.py:146`), **a Gerente pode ligar e desligar regras de preço sem ter `manage_rules`**. |

O último é o mais grave da lista: `manage_rules` é descrito no próprio arquivo como "portão de
segurança do WP-GAP-06" (`setup_groups.py:216-219`), e o grupo "Rules Managers" nasce vazio de
propósito. As duas ações de lote furam o portão inteiro.

**Correção (mecânica, uniforme):** declarar `permissions=` em **toda** `@admin.action` que escreve.
Onde `has_change_permission` é `False` incondicional (payman, stockman), usar a forma pontuada
(`permissions=["shop.manage_rules"]`) — o Unfold/Django resolve via `has_perm` e não pelo método,
como o próprio comentário em `packages/payman/…/admin.py:238-247` já documenta. Guardrail sugerido:
um teste que varre `admin.site._registry`, coleta `get_actions` e falha se alguma ação mutante não
declarar `allowed_permissions`.

### P0-4 — Reajuste de preço em massa: sem confirmação, sem prévia, sobre a seleção "todos os N"

`packages/offerman/shopman/offerman/contrib/admin_unfold/admin.py:587-618`

```python
multiplier = 1 + (percent / 100)
updated = 0
for product in queryset:
    new_price = int(product.base_price_q * multiplier)
```

O percentual vem de um campo de texto na barra de ações (`ProductActionForm.price_percent`,
`:539-545`), livre: aceita `10`, `-5`, `1000`. Não há página de confirmação, não há prévia de
"de → para", não há teto. `Decimal("1000")` → multiplicador 11× em todo o catálogo selecionado.

Cenário: o dono quer subir 10% e digita `110` (pensando "novo preço = 110% do atual"). O catálogo
inteiro multiplica por 2,1. A loja online passa a vender pão a R$ 21. A mensagem que volta
(`:611-617`) diz "N produto(s) atualizado(s) com 110%" — tecnicamente verdadeira, humanamente inútil.

Atenuante real: `Product` tem `history = HistoricalRecords()`
(`packages/offerman/shopman/offerman/models/product.py:190`), então o preço antigo é recuperável — por
alguém que saiba usar `simple_history`, não pelo dono, não pela tela.

Agravante: o reajuste toca só `base_price_q`. Preço por canal vive em `ListingItem.price_q`
(`packages/offerman/…/admin_unfold/admin.py:275`) e **não** é tocado. A mensagem "N produto(s)
atualizado(s)" afirma um efeito que pode não aparecer na vitrine — a mesma classe de desonestidade do
P0-2, em outro domínio.

**Correção:** página intermediária de confirmação (o padrão já existe em
`refs.rename_value_action:144-202`), listando SKU / preço atual / preço novo, com o total de linhas
no topo; teto de sanidade (recusar |percent| > 50 sem uma segunda confirmação); e a mensagem final
deve dizer explicitamente que **preços de canal não foram alterados**, ou alterá-los junto.

---

## P1

### P1-1 — Unificar clientes duplicados: a função existe, tem tela, tem teste — e é inalcançável

`packages/guestman/shopman/guestman/admin.py:123` monta `class CustomerAdmin(MergeAdminMixin, admin.ModelAdmin)`
com `actions = ["merge_customers_action"]` (`:135`). Mas
`packages/guestman/shopman/guestman/contrib/admin_unfold/admin.py:37-41` faz `unregister(Customer)` e
`:286-287` registra `class CustomerAdmin(BaseModelAdmin)` — **sem o mixin** — com
`actions = ["tag_selected", "export_selected_csv", "recalculate_insights"]` (`:376`).

`register_merge_action()` (`packages/guestman/…/merge/admin.py:118`) existe para religar a ação, e
**não é chamada em lugar nenhum** — `packages/guestman/shopman/guestman/contrib/merge/apps.py` não tem
`ready()`. Consequências verificadas:

- A ação "Unificar clientes" não aparece no Admin do deployment.
- A URL `admin:guestman_customer_merge` (`merge/admin.py:27`) não é registrada → qualquer `reverse`
  dela levanta `NoReverseMatch`.
- O template `packages/guestman/shopman/guestman/templates/admin/guestman/customer/merge_confirm.html`
  é órfão.
- `MergeService` (`merge/service.py:40`), com transação, `select_for_update`, snapshot de undo e
  migração de pedidos/contatos/fidelidade, é código sem chamador na aplicação.

E o teste que "prova" o recurso não prova nada de alcance:
`packages/guestman/shopman/guestman/tests/test_hardening.py:497-502` faz
`inspect.getsource(MergeAdminMixin.merge_view)` e verifica que a **string** do template aparece. Passa
verde com a feature morta. É o modo de falha *"o teste prova a string, não a porta"*.

Impacto para o dono: duplicata de cliente (mesma pessoa com dois telefones, ou pedido de balcão vs.
loja) não tem como ser resolvida. O histórico e a fidelidade ficam partidos ao meio, permanentemente,
sem tela que resolva.

**Correção:** ou (a) fazer `CustomerAdmin` do Unfold herdar `MergeAdminMixin` e acrescentar
`merge_customers_action` a `actions`, ou (b) chamar `register_merge_action()` no `ready()` do
`customer_merge`. Junto: um teste de **alcance** (`admin.site._registry[Customer].get_actions(request)`
contém a ação, e `reverse("admin:guestman_customer_merge")` resolve) — não de inspeção de código-fonte.

### P1-2 — Se a ação de merge for religada, ela precisa de dois consertos antes

Ao consertar o P1-1, dois defeitos existentes entram junto:

1. **`packages/guestman/…/merge/admin.py:48`** — `short_description = "Unificar clientes (o 1º
   selecionado é absorvido pelo 2º)"`. Falso. `merge_customers_action` (`:42`) faz
   `queryset.values_list("pk", flat=True)` e usa `ids[0]` como source, `ids[1]` como target — ordem de
   **pk**, não ordem de clique (a ordem de seleção nem chega ao servidor). O rótulo promete um controle
   que não existe: o cliente com pk menor é sempre o absorvido. Numa padaria, isso quase sempre é o
   **cliente mais antigo** — exatamente o que se quer preservar.
   A variante em `:135-166` (`register_merge_action`) é pior: `order_by("pk")`, mesma inversão, e
   **sem página de confirmação nenhuma** (merge irreversível direto do changelist).
2. **`packages/guestman/…/merge/admin.py:71`** — `evidence={"staff_override": True}` hard-coded.
   `Gates.merge_safety` (`packages/guestman/shopman/guestman/gates.py:383-395`) só exige que **uma**
   chave de `VALID_MERGE_EVIDENCE` seja verdadeira. Passar `staff_override=True` fixo satisfaz o
   portão G6 sempre — o gate "exige evidência forte" é, pelo Admin, decorativo.

**Correção:** a tela de confirmação (`merge_confirm.html`, que já mostra a tabela comparativa em
`merge/admin.py:94-102`) deve deixar o operador **escolher a direção** (dois botões: "manter A" /
"manter B"), e a evidência deve refletir o que de fato justificou (telefone verificado igual,
e-mail igual) com `staff_override` só quando não houver nenhuma — registrado como tal na trilha.
Apagar a função `register_merge_action` (`:118-171`), que é a variante sem confirmação.

### P1-3 — Apagar uma sessão de venda destrói, em cascata, a trilha anti-fraude que o próprio sistema blinda

`packages/orderman/shopman/orderman/admin.py:147` — `SessionAdmin` declara **todos** os campos
readonly (`:170-186`) e comenta "Sessões são imutáveis após criação", mas **não sobrescreve
`has_delete_permission`**. Compare com o vizinho: `SessionEventAdmin` (`:428`) fecha
add/change/delete (`:450`,`:453`,`:456`) com um docstring explícito — *"este log defende contra os
operadores que usam o sistema"*.

A cascata desfaz essa defesa: `SessionEvent` e `SessionItem` apontam para `Session` com
`on_delete=models.CASCADE` (`packages/orderman/shopman/orderman/models/session.py:289`). Apagar a
sessão apaga o log de eventos junto, sem passar por `SessionEventAdmin`.

A tela está no menu, em **Auditoria** (`shopman/backstage/admin/navigation.py:161`, "Sessões de
venda"). O alcance é superusuário — `_escrever()` nunca concede `delete_*` (`setup_groups.py:91-99`) —
mas o dono da padaria **é** superusuário, e a ação de lote "Excluir sessões selecionadas" fica no
mesmo seletor das outras.

Mesmo padrão em `DirectiveAdmin` (`packages/orderman/…/admin.py:755`): campos todos readonly, sem
`has_delete_permission`. Apagar uma directive `queued` de `payment.refund` ou `fiscal.emit_nfce` some
com o comando antes de ele rodar, silenciosamente — e o arquivo tem 25 linhas de comentário
(`:821-849`) explicando com que cuidado a **execução** foi removida dessa tela.

**Correção:** `has_delete_permission → False` em `SessionAdmin` e em `DirectiveAdmin`. Se um dia
precisar apagar sessão, isso é comando de manutenção com retenção, não botão.

### P1-4 — `release_holds` em lote: sem confirmação, e conta só os sucessos

`packages/stockman/shopman/stockman/contrib/admin_unfold/admin.py:408-424`

```python
for hold in queryset.filter(status__in=[HoldStatus.PENDING, HoldStatus.CONFIRMED]):
    try:
        stock.release(hold.hold_id, reason='Liberado via admin')
        count += 1
    except (ValueError, LookupError) as exc:
        logger.warning("release_holds: failed to release %s: %s", hold.hold_id, exc)

self.message_user(request, _('{count} hold(s) liberado(s).').format(count=count))
```

Dois problemas, os mesmos do payman em escala menor:

1. A ação de LINHA (`release_hold_row`, `:426-478`) tem `dialog=` com um texto que diz a consequência
   exata — *"A quantidade volta para o estoque disponível e pode ser vendida a outro cliente. O pedido
   que a reservou deixa de ter garantia."* A de LOTE não tem confirmação nenhuma. A casa já escreveu
   a frase que explica o risco e não a mostra no caminho mais arriscado.
2. Falhas somem: só o `count` de sucessos é reportado. Liberar 10 reservas e ver "3 hold(s)
   liberado(s)" deixa o operador achando que selecionou errado, quando 7 falharam por outro motivo.
   E a linha filtrada (`queryset.filter(status__in=...)`) descarta silenciosamente os holds já
   resolvidos, que também não são contados como "não liberados".

**Correção:** reportar sucessos **e** falhas com motivo (`f"{hold.hold_id}: {exc}"`); e ou dar
confirmação à ação de lote, ou remover a ação de lote e deixar a de linha, que já está correta.

### P1-5 — `quantity` e `target_date` da Ordem de Produção editáveis, atropelando `craft.adjust()`

`packages/craftsman/shopman/craftsman/contrib/admin_unfold/admin.py:570-578` define
`readonly_fields = ["ref", "output_sku", "status", "finished", "rev", "started_at", "finished_at"]`.
O fieldset "Quantidades" (`:543-549`) expõe `quantity`; o "Agendamento" (`:550-556`) expõe
`target_date`. Ambos ficam editáveis no formulário.

O docstring da classe (`:483-493`) diz *"Campos editáveis: quantity (via adjust enquanto planned)"* —
mas o Admin não passa por `adjust`: salva o campo direto. Numa WO já `started`, os insumos já foram
consumidos no ledger (`craftsman/contrib/stockman`, `kind=MAKE`); mudar `quantity` no Admin muda o
número planejado sem devolver nem consumir nada, e sem gravar `WorkOrderEvent.ADJUSTED`. A ficha
passa a dizer uma coisa e o estoque, outra — e o `rev` (readonly) não incrementa, então nenhum
consumidor percebe.

O guardrail `INVENTORY_BACKEND` (ligado desde o WP-B5b, conforme `CLAUDE.md`) roda em `adjust`/`finish`,
não no `save()` do Admin.

**Correção:** `get_readonly_fields` deve acrescentar `quantity` quando `obj.status != PLANNED`
(mínimo), e idealmente sempre — ajuste de quantidade é operação e vive no Produção, como o próprio
docstring afirma. `target_date` de WO já iniciada tem o mesmo problema em menor escala.

### P1-6 — Exportação de PII de clientes sem permissão dedicada e sem trilha

`packages/guestman/shopman/guestman/contrib/admin_unfold/admin.py:526-547`

A ação escreve `ref, first_name, last_name, customer_type, email, phone, price_tier, is_active` num
CSV e devolve como download. Sem `permissions=` (ver P0-3), sem `LogEntry`, sem limite de linhas.
Combinada com "selecionar todos os N", é a base de clientes inteira saindo do prédio num clique, sem
deixar rastro de quem exportou nem quando.

Isso é LGPD material — e a casa já demonstra que sabe carimbar trilha quando importa: emitir crachá
grava `LogEntry` (`shopman/backstage/admin/operators.py:30-58`, com um comentário longo explicando por
quê). Exportar a base de clientes merece o mesmo tratamento, no mínimo.

**Correção:** `permissions=["guestman.change_customer"]` (ou uma permissão própria
`export_customers`); `registrar_no_historico`-equivalente gravando quantas linhas e quando; e teto de
linhas por exportação com aviso quando truncar.

### P1-7 — `Ref` editável e apagável: nenhuma trava, e a tela está viva

`packages/refs/shopman/refs/contrib/admin_unfold/admin.py:84` — `RefUnfoldAdmin` fecha só
`has_add_permission` (`:113`). `has_change_permission` e `has_delete_permission` caem no default.
Todos os campos estão em `readonly_fields` (`:100-106`), então o formulário não altera nada — **mas
apagar continua disponível**, inclusive `delete_selected` em lote.

`Ref` é o registro de identificadores tipados de todo o sistema (SKU, refs de canal, de posição).
Apagar linhas ali quebra resolução de refs em silêncio: nada aponta para `Ref` por FK, então não há
`PROTECT` que segure. A ação `deactivate_selected` (`:130`) existe justamente porque desativar é o
gesto certo — e a alternativa destrutiva continua ao lado dela no mesmo seletor.

`rename_value_action` (`:144-202`) tem página de confirmação (bom), mas atua por
`(ref_type, value).distinct()` → `RefBulk.rename` renomeia **todas** as refs daquele par no banco, não
só as linhas marcadas. A mensagem final ("{total} referência(s) renomeadas") revela o total depois do
fato; a tela de confirmação mostra só o `queryset` selecionado. Quem seleciona 2 linhas pode renomear
200.

**Correção:** `has_delete_permission → False` (desativar é o caminho, e o próprio módulo diz isso).
Na tela de confirmação do rename, mostrar a contagem **real** que será afetada (`RefBulk` sabe
calcular) antes de confirmar, não depois.

### P1-8 — O gate declara cobrir os ModelAdmin dos pacotes e não cobre

`docs/engineering/unfold_canonical_policy.md:32` lista `packages/*/shopman/*/contrib/admin_unfold/` e
`:118` afirma que o contrato conhece "package-level Unfold `ModelAdmin` customizations". Na prática
`scripts/check_unfold_canonical.py:261` só alcança `contrib/admin_unfold`. Ficam **fora do gate**:

- os 7 `packages/*/shopman/*/admin.py` (o de `offerman` tem `style=` inline em
  `packages/offerman/shopman/offerman/admin/product.py:85-98` e rótulos em inglês);
- `packages/offerman/shopman/offerman/admin/` (pacote);
- `packages/utils/shopman/utils/admin/`.

Além disso, `packages/utils/shopman/utils/contrib/admin_unfold/base.py:93` faz
`widget.attrs["style"] = "; ".join(...)` — injeta `height: 50%; max-height: 50%` e
`width: 100%; max-width: 42rem` em widgets do Admin. A regra "inline `style=` é sempre proibido"
(`unfold_canonical_policy.md:88`) é implementada como `re.compile(r"\bstyle=")`
(`check_unfold_canonical.py:480`), que não casa `attrs["style"] =`. O arquivo **está** no escopo
varrido e passa mesmo assim.

**Correção:** acrescentar os caminhos faltantes a `DEFAULT_TARGETS`, e um padrão adicional para
`attrs\[["']style["']\]` em arquivos `.py` do escopo.

### P1-9 — `--maturity` / `--strict` não faz nada; a política diz que é o gate de aceitação

`scripts/check_unfold_canonical.py:485` — `STRICT_PATTERNS: tuple[...] = ()`. É a única coisa que
`strict=True` acrescenta (`:553-558`). Ou seja: `make admin` (que passa `--maturity`, `Makefile:474`),
`make unfold-strict`, `make admin-ui-strict` e `make admin-update` (sem flag) executam **exatamente as
mesmas regras**.

A política afirma o contrário em dois lugares:
`docs/engineering/unfold_canonical_policy.md:59-65` — *"A page can pass the default blocking gate while
still being unfit for maturity"* — e `:113` — *"The strict maturity audit is part of `make admin`"*.

Isso é a categoria mais perigosa de portão: um que a documentação descreve como duas camadas e o
código implementa como uma. Quem lê a política acredita ter uma revisão de maturidade que não existe.

**Correção:** ou preencher `STRICT_PATTERNS` com as regras que a prosa promete, ou corrigir a política
para descrever uma camada só. A segunda é honesta e barata; a primeira é o trabalho real.

### P1-10 — A exceção `headless-operator-api` cresceu de 2 para 21 projections em dois meses, sem revisão possível

`scripts/check_unfold_canonical.py:320-358` — uma única entrada de `EXCEPTION_SURFACES` isenta 21
módulos de projection (`:323-344`) sob **um** `exception_reason` em prosa (`:345-358`).

Histórico (`git log -p --follow -- scripts/check_unfold_canonical.py`): criada em `c96b02db4`
(2026-06-25) com 2 módulos (`order_queue.py`, `kds.py`); chega a 21 em `48bcb976b` (2026-08-27), por
16 commits que só somam, nunca tiram. O bloco do B.I. sozinho (9 módulos, `:333-343`) entrou
descrevendo-se como *"terceira exceção explícita ao gate"*.

Estruturalmente: acrescentar o 22º módulo é um diff de uma linha que nenhuma regra pode recusar, e o
`exception_reason` coletivo não distingue qual módulo justifica o quê. Enquanto isso, o mecanismo de
waiver *formal* — `unfold-canonical: allow …` com `authorized-by` / `authorization-ref` / `reason` —
tem **zero usos no repositório**; `_valid_authorization` (`:525-533`) é código morto. O canal real de
exceção não passa por autorização nenhuma.

(E a validação do waiver formal, se um dia for usada, é fraca: `:529` recusa só
`{"", "self", "codex", "agent", "pending", "todo", "tbd"}` — `authorized-by=claude` passa; o
`authorization-ref` não é verificado contra arquivo/URL nenhum; `reason` só precisa de 20 caracteres.)

**Correção:** quebrar `headless-operator-api` em entradas por família com razão própria, e exigir no
schema da entrada os mesmos campos do waiver de template (`authorized_by`, `authorization_ref`). E
fortalecer `_valid_authorization`: `authorized-by` numa allowlist de pessoas reais;
`authorization-ref` precisa existir como caminho no repo ou casar `https?://`.

### P1-11 — `make admin url=<...>` desliga o contrato global E os testes — e é fácil confundir com o gate

`Makefile:474-480`: com `url=` preenchido, os três arquivos de teste
(`test_unfold_canonical_templates.py`, `test_admin_operational_integration.py`,
`test_admin_smoke.py`) **não rodam**, e `check_unfold_canonical.py:1100-1102` passa
`enforce_global_contract=False`, desligando o registro de superfícies/projections inteiro.

A documentação avisa (`unfold_canonical_policy.md:110-112`, `CLAUDE.md`), e o CI roda `make admin` sem
escopo (`.github/workflows/runtime-gate.yml:148`) — então o risco é local, não de merge. Mas
`.pre-commit-config.yaml:4-8` registra `entry: make admin` sem escopo, o que é o comportamento certo.
Fica como aviso: `make admin url=…` é ~4× mais fraco do que parece, não ~1 tela mais estreito.

---

## P2

**P2-1 — `Product` sem `has_delete_permission=False`.**
`packages/offerman/…/admin_unfold/admin.py:306`. `Product` tem `history`, mas apagar cascateia
`CollectionItem` e `ListingItem` (`packages/offerman/…/models/collection.py:167`,
`models/listing.py:86`) e some com o produto do cardápio. `is_published`/`is_sellable` já são o
caminho reversível, e as quatro ações existem para isso. Alcance: superusuário (o dono). Sugestão:
`has_delete_permission → False`, com o mesmo comentário que `QualityGradeAdmin:31` e
`SeatingSpotAdmin:42` já usam.

**P2-2 — `Product.metadata` é JSON cru editável, sem schema.**
`packages/offerman/…/admin_unfold/admin.py:436` — o fieldset "Metadados" expõe `metadata` como
textarea JSON. É a mesma chave onde vive a classificação fiscal NFC-e
(`packages/fiscalman/shopman/fiscalman/contrib/offerman/admin.py:88`), rótulo nutricional
(`nutrition_form.py:238-256`) e configuração de PDV. Os campos tipados reescrevem suas próprias chaves
no `clean()`, então um erro ali é corrigido no save — mas chaves de terceiros não são validadas, e um
JSON malformado só falha na hora de emitir a nota. Sugestão: tornar `metadata` readonly na tela
(os campos tipados já cobrem tudo que o dono precisa) e deixar a edição crua para o shell.

**P2-3 — `IdempotencyKey`, `Fulfillment` e afins: risco neutralizado pela curadoria, mas o código não sabe.**
`packages/orderman/…/admin.py:905` deixa `status` e `expires_at` fora de `readonly_fields`
(editar uma chave de idempotência de `done` para `in_progress` reabre a porta para reprocessar um
webhook de pagamento). Hoje é inofensivo: `curation.py:41` retira a tela. Mas a segurança depende de
uma lista em outro app; se a entrada sair da curadoria, o furo volta. Sugestão: acrescentar
`readonly_fields += ("status", "expires_at")` — defesa em profundidade, custo zero.
Mesmo raciocínio para `FulfillmentAdmin` (`:947`, tudo editável, oculto por `curation.py:53`).

**P2-4 — `unfold_component` marca `children` como seguro sem escapar.**
`packages/utils/shopman/utils/contrib/admin_unfold/render.py:42-43` —
`render_to_string(template, {"children": mark_safe(children), ...})`. `unfold_link(href, text)`
(`:58-65`) passa `text` por esse caminho. Os badges **são** seguros (`badges.py:39-46` escapa via
template do Django antes do `mark_safe`), e todos os chamadores hoje passam literal ou saída de
`format_html`. O mais próximo de dado externo é
`packages/stockman/…/admin_unfold/admin.py:269` — `unfold_link(url, obj.batch)`, com `batch` vindo de
importação. Sugestão: escapar `children` por padrão (`conditional_escape`) e exigir `SafeString`
explícito de quem realmente precisa de HTML.

**P2-5 — O dashboard é a única superfície canônica isenta do contrato de custom page.**
`scripts/check_unfold_canonical.py:238-246` não define `requires_model_admin_view_mixin` para
`admin-dashboard`, então o check de `UnfoldModelAdminViewMixin`/`TemplateView`/`permission_required`
(`:900-918`) nunca roda nela — apesar de `unfold_canonical_policy.md:124` afirmar a regra para todas
as páginas custom canônicas. Na prática o dashboard é um `DASHBOARD_CALLBACK` do Unfold, não uma
custom page — a isenção é defensável, mas está implícita. Sugestão: registrar a isenção com razão,
como as outras.

**P2-6 — `ChannelAdmin` pede JSON ao dono da padaria.**
`shopman/shop/admin/channel.py:34-81` — oito textareas de JSON (confirmação, pagamento, entrega,
estoque, notificações, preço, edição, regras). O `help_text` é bom e o `clean()` valida via
`ChannelConfig.from_dict().validate()` (`:114-120`), então JSON inválido não entra. Ainda assim é a
única tela do Admin que exige sintaxe de programador. Não bloqueia o go-live (canal se configura uma
vez), mas é a próxima candidata a virar campos tipados, como `RuleConfig` e `ShopIntegrations` já
viraram.

**P2-7 — 2FA do Admin desligada por padrão.**
`shopman/backstage/middleware_2fa.py:35` + `config/settings.py:1354`:
`SHOPMAN_ADMIN_REQUIRE_2FA` vem de env e é `False` sem ela. O Admin em produção
(`admin.boulangerie.com.br`) concentra estorno de pagamento, emissão de crachá de operador e a
configuração inteira da loja. A verificação TOTP em si está correta (throttling herdado de
`django_otp.models.ThrottlingMixin`, `verify_token` respeita `verify_is_allowed`), e o
`_safe_next` (`views/two_factor.py:19-24`) não permite open redirect. Falta só ligar. Já consta como
bloqueador conhecido nos "Tier 1 fallbacks"; registrado aqui por completude do eixo de permissões.

**P2-8 — `refs.Ref` mostra `target_type`/`target_id` crus no changelist.**
`packages/refs/…/admin_unfold/admin.py:89-97` — colunas `guestman.Customer` / `4711`. Para quem lê,
não diz de quem é a ref. Sugestão: uma coluna única com link para o objeto (o padrão
`table_admin_link` já existe em `packages/utils/…/tables.py:69`).

**P2-9 — Ações de lote sem prévia do escopo, transversalmente.**
`aliases.confirm_selected/reject_selected`, `consumption.mark_reviewed`,
`operation.complete_selected`, `omotenashi.reset_to_default`, `promotion.reset_usage`,
`refs.deactivate_selected` — todas executam direto e reportam o `count` depois. Nenhuma é
irreversível o bastante para virar P1, mas o padrão da casa (página intermediária) já existe em
`refs.rename_value_action` e `guestman.tag_selected` e vale a generalização para as que carimbam
assinatura humana (`confirm_selected`, `complete_selected`, `mark_reviewed`).

**P2-10 — Inglês vazando em módulos latentes.**
Nenhum dos rótulos em inglês está visível no deployment atual (os módulos estão desregistrados), mas
eles são a superfície que volta se um contrib sair do `INSTALLED_APPS`. Ver tabela de reescrita.

---

## Copy rewrite table

Prioridade: as três primeiras são visíveis **hoje** e mentem ou escondem consequência.

| # | arquivo:LINHA | Texto atual | Problema | Proposta |
|---|---|---|---|---|
| 1 | `packages/payman/…/admin_unfold/admin.py:314` | `"Reembolsar total dos selecionados"` | Não diz que é definitivo nem que é dinheiro real saindo. A ação de linha, muito menos arriscada, diz. | `"Devolver o valor cheio ao cliente (não tem desfazer)"` — e a página de confirmação (P0-1) repete a frase da ação de linha: *"O valor capturado volta inteiro para o cliente pelo gateway. Não há desfazer: um estorno a mais só se corrige com uma cobrança nova."* |
| 2 | `packages/payman/…/admin_unfold/admin.py:327-328` | `"%(n)d intent(s) não puderam ser reembolsados (sem saldo capturado)."` | Inventa a causa (P0-2) e usa "intent", que é palavra de código. | `"%(n)d cobrança(s) não foram devolvidas:"` seguido de uma linha por cobrança com `ref` e o motivo real do gateway. Nunca uma causa sintética. |
| 3 | `packages/offerman/…/admin_unfold/admin.py:587` | `_("Atualizar preço +X%%")` | "+X%" não diz que aceita negativo, não diz que é sobre o preço-base (não o de canal), não diz que é em massa. | `"Reajustar o preço-base dos selecionados (%)"` + `help_text` do campo já existente ampliado: `"Ex.: 10 para subir 10%, -5 para baixar 5%. Só o preço-base — preços por canal (vitrines) não mudam."` |
| 4 | `packages/offerman/…/admin_unfold/admin.py:611-617` | `"%(count)d produto(s) atualizado(s) com %(pct)s%%."` | Afirma efeito que pode não chegar à vitrine. | `"%(count)d produto(s) com o preço-base reajustado em %(pct)s%%. Preços por canal (vitrines) não foram alterados."` |
| 5 | `packages/stockman/…/admin_unfold/admin.py:230` e `:242` | `_('Liberar reservas selecionadas')` / `_('{count} hold(s) liberado(s).')` | O rótulo diz "reserva" (certo) e a mensagem diz "hold" (jargão). Duas palavras para a mesma coisa, na mesma ação. E omite falhas (P1-4). | Mensagem: `"{count} reserva(s) liberada(s)."` + quando houver falha: `"{n} não puderam ser liberadas: {detalhes}"` |
| 6 | `packages/guestman/…/merge/admin.py:48` | `"Unificar clientes (o 1º selecionado é absorvido pelo 2º)"` | **Falso** (P1-2): a ordem é por pk, não por clique. | `"Unificar dois clientes duplicados…"` (reticências = abre confirmação), e a escolha de quem sobrevive passa a ser feita na própria tela de confirmação, com dois botões nomeados. |
| 7 | `packages/guestman/…/merge/admin.py:95` | headers `["Campo", "Source (será desativado)", "Target (receberá dados)"]` | "Source"/"Target" são termos de código numa tela de decisão irreversível para o dono. | `["Campo", "Este some (vira inativo)", "Este fica (recebe tudo)"]` |
| 8 | `packages/refs/…/admin_unfold/admin.py:130` | `_("Desativar selecionados")` | Desativar o quê? A tela lista refs; o gesto tem consequência técnica invisível. | `"Desativar estas referências (param de resolver)"` |
| 9 | `packages/refs/…/admin_unfold/admin.py:84` (`:86` docstring/`:144`) | `"Renomear valor…"` + mensagem `"{total} referência(s) renomeadas para '{new_value}'."` | O total só aparece **depois**, e pode ser muito maior que a seleção (P1-7). | Tela de confirmação: `"Isto renomeia {total} referência(s) no sistema inteiro — não só as {n} selecionadas."` |
| 10 | `shopman/backstage/admin/aliases.py:73` | `" {refused} recusado(s): falta dizer o que significam (alvo, leitura ou forma)."` | Boa intenção, mas não diz **quais** foram recusados. Numa lista de 100, o gestor não sabe onde voltar. | `" {refused} recusado(s) — filtre por “proposto” para ver quais: falta dizer o que significam."` |
| 11 | `shopman/backstage/admin/operators.py:132-134` | `"PIN temporário (anote e informe ao operador — não será mostrado de novo): "` | Ótima, mas não diz o prazo nem que o operador é obrigado a trocar. | `"PIN temporário — anote agora, não aparece de novo. O operador é obrigado a trocá-lo no primeiro uso: "` |
| 12 | `packages/offerman/shopman/offerman/admin/product.py:119-135` (latente) | `"Unpublish selected products"`, `"Publish selected products"`, `"Disable selling for selected products"`, `"Enable selling for selected products"` + mensagens `"{n} product(s) unpublished."` | Inglês. Módulo desregistrado hoje, mas é o fallback se `offerman.contrib.admin_unfold` sair do `INSTALLED_APPS`. | Copiar os rótulos já corretos do contrib (`…/admin_unfold/admin.py:571-583`): "Ocultar produtos selecionados" etc. Ou apagar o módulo, que é a opção limpa. |
| 13 | `packages/offerman/shopman/offerman/admin/product.py:41-66` (latente) | fieldsets `"Price & Cost"`, `"Publication & Sellability"`, `"Configuration"`, `"Metadata"`; `description` `"is_published controls catalog exposure, is_sellable controls…"` | Inglês + nomes de campo como prosa. | Idem: usar os do contrib, ou apagar. |
| 14 | `packages/doorman/shopman/doorman/admin.py:225` (latente) | `"Expire selected codes"` | Inglês. Tela oculta pela curadoria hoje. | `"Expirar os códigos selecionados"` (o contrib Unfold já está em pt-BR). |
| 15 | `shopman/shop/admin/shop.py:1576` | grupo de prévia de cor rotulado `"Status"` | Único rótulo em inglês numa tela viva. | `"Situação"` |

---

## Verified-safe

Coisas que auditei e que estão **certas** — vale registrar para ninguém "consertar" depois:

**Dinheiro e livro-caixa.**
`packages/cashman/…/admin_unfold/admin.py` é o melhor arquivo do conjunto. `Entry` (o livro) não é
registrado no Admin em lugar nenhum — existe só como inline readonly (`:101-136`, `can_delete=False`,
add/change `False`). `ShiftAdmin` fecha A/C/D (`:208`-`:215`) e trava `has_view_permission` em
`cashman.audit_shift` (`:217-224`), com o raciocínio do fechamento cego escrito ao lado. Todas as FKs
de `entry.py` e `shift.py` são `PROTECT` (`entry.py:124`,`:130`,`:137`,`:161`; `shift.py:50`,`:56`).
Não há caminho no Admin que apague ou altere um lançamento de caixa.

**"Admin não executa directive" — cumprido, e com prova.**
`packages/orderman/…/admin.py:821-849`: os três botões de execução foram **removidos** (não
repermissionados), com o inventário dos 25 tópicos que eram alcançáveis (`payment.refund`,
`fiscal.emit_nfce`, `announcement.publish`) escrito no comentário. Varri todo o `admin.py` e
`admin_console/`: nenhum caminho do Admin chama `process_directives`, executa handler de directive, ou
enfileira efeito colateral fora de um service.

**Trilhas de auditoria imutáveis (as que estão registradas).**
`SessionEventAdmin` (`orderman/admin.py:450`-`:456`), `SignInEventAdmin`
(`shopman/backstage/admin/sign_in.py:48`-`:54`), `PaymentTransactionAdmin`
(`packages/payman/…/admin.py:408`-`:414`), `MoveAdmin` (`packages/stockman/…/admin.py:306`-`:312`),
`ImportBatch`/`HistoricalSale`/`DailySalesFact` (`imports.py:25-35`), `BIAlertEvent`/`BIScenarioReport`
(`bi_alerts.py:87`-`:121`), `OperationEpisode` (`episodes.py:55`-`:61`), `DayClosing`
(`closing.py:47`-`:56`) — todas fecham add/change/delete com justificativa no docstring.

**Sem XSS pelos helpers de badge/tabela.**
`packages/utils/…/badges.py:39-46` renderiza `unfold/helpers/label.html` (auto-escape do Django) e só
então `mark_safe` do resultado — o texto do badge é escapado. `tables.py:148-164` faz
`format_html("{}", cell)` para células não-`SafeText`. `dashboard.py:169-194` passa
`r.comment` (texto livre do cliente) como `str` puro, que o template do Unfold escapa.
Os únicos `|safe` do repositório em templates Admin/próximos são
`admin_console/operator_badge/index.html:73` (SVG gerado pelo sistema),
`shop/templates/fiscal/danfe.html:130` e `menuboard/board.html:135` — nenhum recebe entrada de
usuário.

**Menu e dashboard perguntam à porta, não repetem a regra.**
`shopman/backstage/admin/gates.py:24-38` — `can_open_changelist` chama
`model_admin.has_view_or_change_permission(request)`; `can_open_view` lê
`view.permission_required`. `navigation.py` e `dashboard.py` usam só esses dois. Isso elimina por
construção a classe "link no menu que dá 403" — e o arquivo explica por quê (`gates.py:1-12`).

**`ShopIntegrations` não é JSON livre.**
Ao contrário do que o nome sugere, `shop.integrations` é editado por quatro `ChoiceField` cujas
escolhas saem de `_adapter_choices(...)` (`shopman/shop/admin/shop.py:454-485`), e o campo JSON cru é
removido do form (`:718`). `_build_integrations` (`:1022-1056`) preserva chaves que não estão na tela.
Não há caminho pelo Admin para apontar o adapter de pagamento para um valor arbitrário.

**Confirmação em GET não existe mais.**
As duas ações de linha perigosas (`refund_row`, `release_hold_row`) usam `dialog=` com
`BaseDialogForm`, e os comentários (`packages/payman/…/admin.py:238-247`,
`packages/stockman/…/admin.py:426-452`) documentam que a mudança foi feita justamente porque o Unfold
executava o corpo em GET com `SameSite=Lax`. Confirmei que ambas têm `dialog` e `form_class`.

**`RuleConfig` mostra quando uma regra não carrega.**
`shopman/shop/admin/rules.py:211-227` — a coluna "carrega?" tenta `load_rule(obj)` e mostra
"NÃO CARREGA" em vermelho. Regra morta aparece **onde o dado mora**, não só num WARNING de log.

**Gate no CI, e versão do Unfold travada de verdade.**
`.github/workflows/runtime-gate.yml:126-148` roda `make admin` em `pull_request` e `merge_group`, sem
`continue-on-error`. A checagem de drift de versão é real e bloqueante
(`scripts/check_unfold_canonical.py:964-973`, igualdade exata contra
`importlib.metadata.version("django-unfold")`), e os quatro pontos de pin batem:
`docs/reference/unfold_canonical_inventory.md:9` = `0.92.0`, `pyproject.toml:36` = `>=0.92,<0.93`,
`constraints.txt:69` = `==0.92.0`, `Makefile:34` idem; instalado = 0.92.0.

**Zero waivers de template no repositório.** A sintaxe `unfold-canonical: allow` só aparece na
documentação (`unfold_canonical_policy.md:79`) e na mensagem de erro do script (`:1110`). Nenhuma
tela do Admin está operando sob dispensa de regra.

**Curadoria do Admin é honesta e testada.** `curation.py:71-92` — `unregister` não apaga dado, cada
entrada tem motivo escrito, entrada obsoleta vira `logger.warning` e o teste `test_admin_curation`
derruba a suíte. Duas telas que "pareciam corte óbvio" ficaram, com o porquê registrado (`:18-23`).
