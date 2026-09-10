# Verificação WP-09 — Admin canônico

Base: worktree `coordenar-sessoes-deploys-b9cdac`, HEAD `9469c92a2` (descendente do main de 2026-08-29).
Método: leitura de cada arquivo/função citada + execução do gate (`scripts/check_unfold_canonical.py`, com `.venv` da raiz) + introspecção do registry do Admin com `django.setup()` e usuário sintético view-only. Onde escrevo "provado", rodei; onde escrevo "li", só li.

---

## A. Superfície real (o que existe hoje)

**Gate e política**
- `scripts/check_unfold_canonical.py` (1121 linhas) — o gate. `DEFAULT_TARGETS` (`:362-364`) = templates+controllers das `CANONICAL_ADMIN_SURFACES`. **Rodei o gate default com `--maturity`: passa (exit 0).**
- `Makefile:426-433` — alvo `admin`: gate `--maturity` + `pytest` de 3 arquivos (`test_unfold_canonical_templates.py`, `test_admin_operational_integration.py`, `test_admin_smoke.py`).
- `docs/engineering/unfold_canonical_policy.md`, `unfold_admin_page_playbook.md`, `docs/reference/unfold_canonical_inventory.md`.

**Telas custom do Admin (`shopman/backstage/admin_console/`)** — 5 arquivos: `settings_hub.py`, `pos_counter_agent.py`, `operator_badge.py`, `cash_receipt.py`, `copy_catalog.py`. Todas seguem `UnfoldModelAdminViewMixin` + `permission_required`.

**ModelAdmins do backstage (`shopman/backstage/admin/`)** — 17 arquivos: `accounts.py` (User/Group/TOTPDevice), `operators.py` (PinCredential), `aliases.py`, `alerts.py`, `bi_alerts.py`, `closing.py`, `consumption.py`, `curation.py`, `dashboard.py`, `episodes.py`, `imports.py` (B.I., todo read-only), `kds.py`, `navigation.py`, `operation.py`, `pos.py`, `seating.py`, `terminal.py`, `gates.py`.
- **`gates.py` — nenhum dos dois WPs menciona.** É a primitiva canônica "esta pessoa consegue abrir esta tela?" (`can_open_changelist` / `can_open_view`), já usada por menu e dashboard. É a peça que o achado do settings hub precisa.

**ModelAdmins de packages** — dois formatos:
- `packages/*/shopman/*/contrib/admin_unfold/` (10 pacotes) — **dentro** do gate.
- `packages/*/shopman/*/admin.py` (craftsman, doorman, guestman, orderman, payman, refs, stockman) + `offerman/admin/` + `utils/admin/` — **fora** do gate.
  ⚠️ **Nenhum dos dois WPs verificou quais desses estão VIVOS.** Verifiquei: craftsman/payman/stockman se auto-desativam por `apps.is_installed(...contrib.admin_unfold)`; refs/doorman/guestman/offerman são **desregistrados** pelo contrib (`admin.site.unregister`). **Só `packages/orderman/shopman/orderman/admin.py` está registrado de fato** — orderman não tem `contrib/admin_unfold`.

**Testes existentes relevantes (nenhum dos dois WPs cita)**
- `shopman/backstage/tests/test_admin_reachability.py` — roda `setup_groups` de verdade e pede cada link do menu/dashboard com as personas reais. É o molde pronto para os aceites de permissão deste WP.
- `test_admin_2fa.py` (8 testes), `test_payman_admin_refund.py` (4 testes, **todos com `admin_client` = superusuário**), `test_admin_operational_integration.py`, `test_admin_smoke.py`, `test_admin_navigation.py`, `test_admin_display_canonicity.py`, `test_admin_widget_canonicity.py`, `test_admin_format_html_contract.py`.
- `shopman/shop/checks.py` — 15 `Error` + 16 `Warning` com `@register(deploy=True)`. É o padrão pronto para o check de 2FA.

---

## B. Evidências dos WPs, veredito uma a uma

| # | Afirmação (G/D) | Arquivo:linha ATUAL | Veredito | Nota |
|---|---|---|---|---|
| 1 | Gate passa hoje (G) | — | **CONFIRMADO** | Rodei `check_unfold_canonical.py --maturity` sem argumentos: exit 0, "check passed". (Não rodei o pytest do alvo.) |
| 2 | Gate não cobre `packages/*/shopman/*/admin.py` (G/D) | `scripts/check_unfold_canonical.py:253-273` (só `contrib/admin_unfold` + `templates/admin`), `:362-364` | **CONFIRMADO** | `_glob("packages/*/shopman/*/contrib/admin_unfold")` — `admin.py` plano fica de fora, e `offerman/admin/` e `utils/admin/` também. |
| 3 | "Ampliar o gate quebra `make admin` com **dezenas** de violações em doorman/orderman/guestman" (D) | — | **PARCIAL** | Rodei o gate `--maturity` sobre os 9 alvos: **20 violações em 4 arquivos** — doorman 8, orderman 7, offerman/admin/product.py 3, guestman 2. Não são "dezenas", e D esqueceu offerman. E, decisivo: **3 dos 4 arquivos são código morto em runtime** (desregistrados); só orderman serve tela. |
| 4 | "Violações reais fora do gate: doorman:97-101,313-317; orderman:209-680; guestman:234,244-245" (D) | doorman `:97,99,101,202,212,313,315,317`; orderman `:209,243,260,606(×2),631(×2)`; guestman `:244,245` | **PARCIAL** | Linhas existem (guestman `:234` não é violação — o gate não a reporta). Mas "reais" é a palavra errada: doorman e guestman nunca renderizam. |
| 5 | `table_badge` reconstrói badge por classes (G/D) | `packages/utils/.../tables.py:38-47` (`BADGE_COLORS`), `:47` (`BADGE_BASE_CLASSES`), `:88-105` (`table_badge`) | **CONFIRMADO** | E `badges.py:1-13` nomeia exatamente esse anti-padrão como já corrigido ali. Rodei o gate sobre `utils/contrib/admin_unfold`: **passa** — o guardrail não enxerga classe em constante Python. Usada por 3 telas vivas (`admin/dashboard.py:202`, `admin_console/cash_receipt.py:82`, `admin_console/copy_catalog.py:91,93`). |
| 6 | `BaseModelAdmin` injeta `style` e o gate não pega porque a regex é `\bstyle=` (D) | `packages/utils/.../base.py:77,93` | **CONFIRMADO** | `widget.attrs["style"] = ...` em `get_form`. Gate passa nesse arquivo (rodei). D acertou o mecanismo. |
| 7 | **P0: refund executável por qualquer staff com view** (D) | `packages/payman/.../admin.py:202-204` (actions), `:311-318` (has_add/change/delete = False), `:206-217` (`refund_row`), `:263-278` (`refund_selected`) | **CONFIRMADO — e pior do que D descreveu** | **Provado por introspecção**: usuário só com `payman.view_paymentintent` abre a changelist e recebe `['refund_selected']` + row action `payman_paymentintent_refund_row`. Mecanismo: `_filter_actions_by_permissions` só filtra quem tem `allowed_permissions` (Django) e `unfold/mixins/action_model_admin.py:322-325` faz o mesmo. **Além disso**: a URL da row action é registrada em `unfold/admin.py:210-217` embrulhada só por `admin_site.admin_view` (= `is_active and is_staff`, sem AdminSite custom no projeto) e o `@action` sem `permissions=` não checa nada (`unfold/decorators.py:36`). Ou seja: **qualquer staff, mesmo sem NENHUMA permissão em payman, executa `/admin/payman/paymentintent/<id>/refund/` por GET.** |
| 7b | O cenário do refund é real? (pergunta do briefing) | `shopman/shop/management/commands/setup_groups.py:246` (`"Dono": [..., *_ver("payman")]`) | **PARCIAL — recalibrar para baixo** | O **único** grupo não-superusuário com `payman.view_*` é **"Dono"** — a persona que o próprio RBAC define como dona do dinheiro. Pela porta da frente (changelist), quem executa refund é exatamente quem deveria. O que é real é a **porta lateral**: a URL da row action, aberta a Caixa/Cozinha/Gerente. Ver C-1. |
| 8 | Import/export abertos: default `has_import_permission=True` (D) | `import_export/admin.py:124-132` e `:641-649` (v4.4.0); `config/settings.py` **não define** `IMPORT_EXPORT_*_PERMISSION_CODE` (grep vazio); `packages/offerman/.../admin_unfold/admin.py:282-285,307,319` | **CONFIRMADO** | `ProductAdmin` herda `ImportExportModelAdmin` e não sobrescreve `has_import_permission`. `import_action`/`process_import` (`:436,443` e `:152,156`) só checam essa função, e a URL é `admin_site.admin_view` — **qualquer staff POSTa em `/admin/offerman/product/import/`**. `ProductResource` (`packages/offerman/shopman/offerman/contrib/import_export/resources.py:16-27`) faz upsert por `sku` de `base_price_q`, `is_published`, `is_sellable`. |
| 8b | Evidência de D `resources.py:17-27,31-59` | `packages/offerman/.../admin_unfold/resources.py` tem **6 linhas** | **NÃO LOCALIZADO** | D apontou o arquivo errado (é um re-export de compat). O conteúdo está em `contrib/import_export/resources.py`. |
| 9 | Export de PII por action de view-only: `guestman .../admin.py:527-547` (D) | `packages/guestman/.../admin_unfold/admin.py:376` (actions), `:526-547` (`export_selected_csv`) | **CONFIRMADO na mecânica, REFUTADO na consequência** | Provado: view-only recebe `['tag_selected','export_selected_csv','recalculate_insights']`. Mas o único grupo com `guestman.view_customer` é **Gerente**, que também tem `change_customer` (`setup_groups.py:140`). Não há escalonamento view→escrita. O que sobra é ausência de motivo/trilha LGPD — política, não authz. |
| 10 | Segredos de gateway expostos a view-only (D) | `packages/payman/.../admin.py:297-309` (`gateway_data_display`), `:49-58` (`_GATEWAY_LABELS`), `:62-80` (`_gateway_rows`) | **CONFIRMADO, gravidade menor** | `client_secret`, `qrcode`, `txid` renderizados crus (corte em 300 chars). Só "Dono" e superusuário veem. É higiene, não brecha. |
| 11 | `reset_pin` sem LogEntry (D) | `shopman/backstage/admin/operators.py:119-135`; comparar com `:165` e `:176` (`registrar_no_historico`) | **CONFIRMADO** | `reset_pin` gera segredo novo e não grava nada. `unlock_pin` (`:188-194`) também não — D não viu essa. |
| 12 | PIN temporário em message storage (G/D) | `shopman/backstage/admin/operators.py:130-135` | **CONFIRMADO, com agravante que ninguém viu** | `MESSAGE_STORAGE` não está em `config/settings.py` ⇒ default `FallbackStorage`, que tenta **cookie** primeiro. O PIN temporário sai no cookie `messages` (assinado, **não** cifrado). |
| 12b | Reset de PIN é escalonamento de view-only? | `operators.py:198-209` | **REFUTADO** | `has_view_permission` e `has_change_permission` são **a mesma** `cashman.manage_operators`. Quem vê a tela é quem já pode resetar. Ação sem `allowed_permissions` aqui é inofensiva. |
| 13 | Token do agente: G aponta `pos_counter_agent.py:56`, D corrige para `pos_agent.py:227` | `shopman/backstage/projections/pos_agent.py:227`; `admin_console/pos_counter_agent.py:56` é o `@click` do botão copiar | **D CONFIRMADO / G REFUTADO na linha** | A correção de D está certa. Mas ambos superdimensionam: a tela é gateada por `cashman.change_terminal` (`pos_counter_agent.py:24,38,85`), o token só abre a gaveta daquele balcão, o tradeoff está escrito em `pos_agent.py:8-10`, e no `TerminalAdmin` o token já aparece **mascarado** (`shopman/backstage/admin/terminal.py:122`, `mask_badge`). P2. |
| 14 | TrustedDevice deletável (D) | `packages/doorman/.../admin_unfold/admin.py:334-338` — só `has_add_permission`/`has_change_permission` | **CONFIRMADO, gravidade menor** | E vale para os **4** admins do doorman (`:65,68`, `:150,153`, `:250,253`, `:334,337`), não só TrustedDevice. Mas nenhum grupo do `setup_groups` tem qualquer permissão em `doorman` — só superusuário chega lá, e o delete do Django grava `LogEntry`. P2. |
| 15 | Settings hub não filtra permissão (G/D) | `shopman/backstage/projections/settings_hub.py:180` (`build_settings_hub(*, q="", slug="")` — sem `request`/`user`); view em `admin_console/settings_hub.py:33` (`permission_required="shop.view_shop"`) | **CONFIRMADO** | Para o Gerente, pelo menos 5 cards levam a 403: `auth_user`, `auth_group`, `doorman_trusteddevice`, `otp_totp_totpdevice`, `refs_ref` (`settings_hub.py:158-163`). E existe a primitiva pronta (`admin/gates.py`) que o menu e o dashboard já usam. |
| 16 | Sem system check de 2FA (D) / 2FA default off (G) | `config/settings.py:1321-1323`; `shopman/shop/checks.py` — grep por `2FA`/`REQUIRE_2FA`/`ADMIN_HOST` volta **vazio** | **CONFIRMADO** | 15 `Error` deploy já existem no arquivo; falta este. O middleware (`shopman/backstage/middleware_2fa.py:34-35`) é no-op sem a env. |
| 17 | Migrar `payment_refund.html` para `unfold/helpers/field.html` (G/D) | `packages/payman/shopman/payman/templates/admin/payman/payment_refund.html` (44 linhas) | **REFUTADO em quase tudo** | O template **já** usa `{% component %}` para container/title/card/text/button/icon. O único desvio é montar label/help/errors à mão em volta de `{{ form.amount_reais }}` (`:19-28`). Não é "HTML cru". |
| 18 | Aceite "Import de Product não publica item fiscalmente incompleto" (G) / D declara fora de escopo | `contrib/import_export/resources.py:16-27` importa `is_published` direto; sem validação fiscal | **D CONFIRMADO** | A leitura de D está certa: é feature nova (offerman↔fiscalman), não aceite deste WP. |
| 19 | O main já corrigiu algo? | `git log --oneline -5` em payman admin, operators.py, gate, tables.py, settings_hub.py, doorman contrib | **NÃO** | Nada nos últimos commits toca esses pontos. |

---

## C. Achados confirmados, com gravidade recalibrada

### C-1 · P0 — Ação de estado executada por GET, sem permissão de modelo e sem CSRF

**Não é "o refund do payman".** É um padrão de 3 ocorrências, e o payman é a menos perigosa das três.

**Mecanismo (provado):**
1. Unfold registra a URL de `actions_row`/`actions_detail`/`actions_submit_line` embrulhada **apenas** em `admin_site.admin_view` (`unfold/admin.py:210-217`). Não há `AdminSite` custom no projeto (grep vazio em `shopman/`+`config/`), então isso é `is_active and is_staff` — **zero permissão de modelo**.
2. O `@action` só checa permissão se receber `permissions=` (`unfold/decorators.py:36-73`). **Nenhuma action do repositório usa `permissions=` ou `allowed_permissions`** (grep global: 0 ocorrências).
3. Nenhuma dessas funções checa `request.method`. Executam em **GET**.
4. `SESSION_COOKIE_SAMESITE = "Lax"` (`config/settings.py:116`) — Lax **envia** o cookie em navegação top-level GET. Um link num WhatsApp, clicado pelo gestor logado, dispara a ação e redireciona para a changelist como se nada tivesse acontecido.

**As três ocorrências, com o grupo real:**

| Ação | arquivo:linha | Quem alcança pela changelist | Quem alcança pela URL |
|---|---|---|---|
| `refund_row` / `refund_selected` | `packages/payman/.../admin_unfold/admin.py:206-217`, `:263-278` | só **Dono** (`setup_groups.py:246`) | **qualquer staff** |
| `release_hold_row` / `release_holds` | `packages/stockman/.../admin_unfold/admin.py:352-353`, `:400-412`, `:419-440` | **Cozinha e Gerente** (`_ver("stockman")`, sem change) | qualquer staff |
| `execute_row` / `execute_now_action` / `execute_now_detail_action` | `packages/orderman/shopman/orderman/admin.py:766-767`, `:797`, `:856-868`, `:876-893`, `:895-919` | **Gerente** (`_ver("orderman")`, sem change) | qualquer staff |

**O que dói de verdade, e que nem G nem D viram:** entre os handlers de Directive existe `shopman/shop/handlers/payment_refund.py` (topic `payment.refund`). O `setup_groups.py:127-131` diz por escrito que *"Dinheiro fica de fora, e não é esquecimento: payman é do Dono"*. **O Gerente, excluído do payman de propósito, reexecuta um directive de estorno pela tela de Diretivas.** A fronteira de dinheiro desenhada no RBAC é contornada um model adiante. (Escopo honesto: ele não cria directive novo — `add_directive` ele não tem —, só reexecuta os que estão `queued`/`failed`.)

**Fix mínimo (por ação, 2 linhas cada):**
```python
@action(description=_("Reembolsar (total)"), url_path="refund", icon="undo",
        variant=ActionVariant.DANGER, permissions=["refund"])   # ← e definir has_refund_permission
```
```python
@admin.action(description=_("Reembolsar total dos selecionados"), permissions=["refund"])
```
mais `def has_refund_permission(self, request): return request.user.has_perm("payman.refund_paymentintent")`, e o mesmo padrão em stockman (`stockman.release_hold`) e orderman (`orderman.execute_directive`). Adicionalmente, `@method_decorator(require_POST)` nas três `*_row` — ou migrar para dialog action do Unfold, que já POSTa.

---

### C-2 · P1 — Import de catálogo aberto a qualquer staff

`ProductAdmin` (`packages/offerman/.../admin_unfold/admin.py:282-285,307,319`) herda `ImportExportModelAdmin` sem sobrescrever `has_import_permission`; `IMPORT_EXPORT_IMPORT_PERMISSION_CODE` não existe em `config/settings.py` ⇒ `import_export/admin.py:127-128` retorna `True`. `import_action` e `process_import` são `admin_site.admin_view`. **Um usuário do grupo Caixa POSTa um CSV em `/admin/offerman/product/import/` e reescreve `base_price_q`, `is_published` e `is_sellable` de todo o catálogo por SKU.** Sem dry-run visível para o gestor, sem trilha agregada.

**Fix mínimo (uma linha em `config/settings.py`):**
```python
IMPORT_EXPORT_IMPORT_PERMISSION_CODE = "change"
IMPORT_EXPORT_EXPORT_PERMISSION_CODE = "view"
```
(`"change"` já é o recorte certo: Gerente e Admin de Catálogo têm `change_product`; Caixa e Cozinha não.) Permissão dedicada nova só se o dono quiser separar "importar" de "editar".

---

### C-3 · P1 — Ações de massa do catálogo sem confirmação

`unpublish_products`, `publish_products`, `pause_products`, `resume_products`, `update_price_percent`, `add_to_collection` (`packages/offerman/.../admin_unfold/admin.py:548-655`). Sem `allowed_permissions`, sem página de confirmação, sem preview. Provado: view-only recebe as 6.
**Recalibração:** não é escalonamento — os dois grupos com `view_product` (Gerente, Admin de Catálogo) também têm `change_product`. É risco de **erro humano**: "selecionar tudo" + `update_price_percent` reprecifica o catálogo inteiro em um clique. O `save()` por item preserva o histórico do simple_history, então há como reverter — o que baixa isto de P0 para P1.
**Fix mínimo:** `permissions=["change"]` nas 6 + página de confirmação (o padrão já existe: `tag_selected` do guestman usa `TemplateResponse` com `tag_confirm.html`).

---

### C-4 · P1 — `reset_pin` e `unlock_pin` sem trilha; PIN temporário sai por cookie

`shopman/backstage/admin/operators.py:119-135` e `:188-194`. Gerar segredo novo não grava `LogEntry`, enquanto `issue_badge` (`:165`) e `revoke_badge` (`:176`) gravam — a assimetria é o achado. E, novo: sem `MESSAGE_STORAGE` em `config/settings.py`, o default é `FallbackStorage`, que escreve o PIN no **cookie** `messages` (assinado, não cifrado) antes de tentar a sessão.
**Fix mínimo:**
- `registrar_no_historico(request, cred.user, "PIN resetado (temporário emitido).")` dentro do laço de `reset_pin`, e o equivalente em `unlock_pin` — uma linha cada;
- `MESSAGE_STORAGE = "django.contrib.messages.storage.session.SessionStorage"` em `config/settings.py` (uma linha, resolve a metade do problema de graça);
- o PIN em página one-time seguindo o padrão de `issue_badge` (sessão → `admin_console_operator_badge`) é o fix completo.

---

### C-5 · P1 — Drift do Unfold invisível ao próprio guardrail

`table_badge` (`packages/utils/.../tables.py:38-47,88-105`) reconstrói o badge com a tabela de cores copiada, exatamente o anti-padrão que `badges.py:1-13` documenta como já resolvido. `BaseModelAdmin` injeta `attrs["style"]` (`base.py:77,93`). **Rodei o gate sobre esses dois arquivos: passa.** O gate lê classe em literal de template; classe em constante Python e `style` em `attrs` escapam.
**Fix mínimo:** `table_badge` delega para `unfold_badge` (o vocabulário de cor já existe em `badges.py:22-30`); e uma regra nova no gate para `attrs["style"]` / `attrs\[.style.\]` e para constantes com `bg-`/`text-` + `format_html('<span class="{}...')`.

---

### C-6 · P1 — Sem system check de 2FA no deploy

`config/settings.py:1321-1323` define `SHOPMAN_ADMIN_REQUIRE_2FA` default `False`; `shopman/shop/checks.py` tem 15 `Error(deploy=True)` e nenhum sobre 2FA. Um deploy de produção sobe com o Admin sem segundo fator e nada acusa.
**Fix mínimo:** mais um check no arquivo que já existe, no molde do `SHOPMAN_E010`, id `SHOPMAN_E016`: erro se `not DEBUG and not SHOPMAN_ADMIN_REQUIRE_2FA`, e erro se `SHOPMAN_ADMIN_HOST` vazio em produção.

---

### C-7 · P2 — Settings hub oferece cards que respondem 403

`shopman/backstage/projections/settings_hub.py:180` — `build_settings_hub` não recebe `request`. Pelo menos 5 cards 403 para o Gerente (`:158-163`). A primitiva certa já existe e já é usada por menu e dashboard: `shopman/backstage/admin/gates.py:24,32`.
**Fix mínimo:** `build_settings_hub(*, request=None, q="", slug="")` filtrando por `can_open_changelist`/`can_open_view`. O teste é cópia de `test_admin_reachability.py:99`.

---

### C-8 · P2 — Segredos de gateway crus e `has_delete_permission` faltando no doorman

`gateway_data_display` (`packages/payman/.../admin.py:297-309`) mostra `client_secret`/`qrcode`/`txid` sem máscara — mas só para "Dono" e superusuário. Os 4 admins do doorman (`contrib/admin_unfold/admin.py:65-72,150-157,250-257,334-340`) não bloqueiam delete — mas nenhum grupo tem permissão em `doorman`, e o delete do Django grava `LogEntry`. Ambos são higiene: baratos de fazer, nada urgente.

---

## D. Achados NOVOS (que G e D perderam)

### D-1 · P1 — Os fieldsets pt-BR do TOTPDevice são código morto, e a chave do 2FA está exposta

`shopman/backstage/admin/accounts.py:66-85`. A classe declara `fieldsets` como atributo, mas herda de `TOTPDeviceAdmin`, **que sobrescreve `get_fieldsets()` e ignora `self.fieldsets`** (`django_otp/plugins/otp_totp/admin.py:39-91`).

**Provado por introspecção (`django.setup()` + `ma.get_fieldsets(...)`):**
```
get_fieldsets vem de: TOTPDeviceAdmin.get_fieldsets
OTP_ADMIN_HIDE_SENSITIVE_DATA: False
fieldsets efetivos: [('Identity', [...]), ('Timestamps', [...]),
                     ('Configuration', ['key', 'step', 't0', 'digits', 'tolerance']),
                     ('State', ['drift']), ('Throttling', [...]), (None, ['qrcode_link'])]
list_display: [..., 'qrcode_link']
```
Duas consequências:
1. A tela **continua em inglês** ("Identity/Timestamps/Configuration/State/Throttling"), exatamente o que o docstring do arquivo (`:68-75`) afirma ter consertado. Ninguém percebeu porque a tela é superusuário-only.
2. `OTP_ADMIN_HIDE_SENSITIVE_DATA` é `False` (default do `django_otp/conf.py:16`, e o projeto não o define). Logo o **segredo TOTP (`key`) e o link do QR de enrollment** aparecem na change page e na changelist de qualquer TOTPDevice. Quem lê a `key` de outro usuário gera os códigos dele — o que anula o step-up 2FA que este WP quer usar como controle. Hoje só superusuário chega; mas o settings hub **oferece esse card** (`settings_hub.py:162`), então a intenção é abrir.

**Fix mínimo — uma linha em `config/settings.py`:**
```python
OTP_ADMIN_HIDE_SENSITIVE_DATA = True
```
e apagar o `fieldsets` inerte de `accounts.py:78-85` (ou sobrescrever `get_fieldsets` de verdade, se a tradução importar).

### D-2 · P1 — O Gerente reexecuta estorno pela tela de Diretivas

Detalhado em C-1. Registro aqui porque é achado próprio: nem G nem D ligaram `orderman.Directive` + `shopman/shop/handlers/payment_refund.py` + a exclusão deliberada do Gerente do payman em `setup_groups.py:127-131`.

### D-3 · P2 — `unlock_pin` também não deixa trilha

`shopman/backstage/admin/operators.py:188-194`. D achou só o `reset_pin`. Desbloquear um PIN travado por tentativas é decisão de segurança e some sem rastro. Uma linha, mesmo fix.

### D-4 · P2 — O gate cobre `packages/*/contrib/admin_unfold` mas não `offerman/admin/` nem `utils/admin/`

Os dois WPs falam em "`packages/*/admin.py`". Faltam dois diretórios ao inventário: `packages/offerman/shopman/offerman/admin/` (3 dos 20 achados do gate estão em `product.py:85,90,96`) e `packages/utils/shopman/utils/admin/`. Se a Fase 2 do gate for escrita como "`packages/*/shopman/*/admin.py`", esses dois passam batido.

### D-5 · P2 — `test_payman_admin_refund.py` prova o refund com superusuário

`shopman/backstage/tests/test_payman_admin_refund.py:35,43,51,59` — os 4 testes usam `admin_client`. Ou seja, a suíte hoje **atesta que o refund funciona** e nada diz sobre quem pode. É o teste que dá a falsa sensação de cobertura no achado mais grave.

**O que procurei e NÃO achei** (registro para não inflar o WP): nenhuma action destrutiva sem trilha em `shopman/backstage/admin/imports.py` (todo read-only, `:25-36`); `TerminalAdmin` já mascara o token (`terminal.py:122`); PII do cliente não aparece em `list_display` (`guestman/.../admin.py:297-306` mostra header/badges), só em `search_fields` (`:317`, inclui `document`, `phone`, `email` — busca vai para a querystring, mas isso é comportamento padrão do Admin, não vou chamar de achado); nenhum caminho que estoure 500 na cara do gestor que eu tenha conseguido reproduzir lendo.

---

## E. Achados a DESCARTAR

1. **"Migrar `payment_refund.html` para `unfold/helpers/field.html`" (G e D).** O template já é 100% `{% component %}` canônico (44 linhas, lidas). Sobra montar label/help/errors à mão em `:19-28`. Custo de mexer > risco. **Descartar** — ou reduzir a uma nota de estilo.
2. **"Dezenas de violações" como justificativa do faseamento do gate (D).** São 20, em 4 arquivos, todas da mesma família (span colorido / tailwind à mão). E 17 delas estão em **código morto**. O faseamento continua certo, mas o argumento é outro: não é volume, é que ampliar o gate faria `make admin` falhar por causa de arquivos que nenhuma tela renderiza. **Descartar a premissa, manter o faseamento.**
3. **"Reset de PIN é exposição a view-only" (implícito em G).** `has_view_permission` e `has_change_permission` do `PinCredentialAdmin` são a mesma `cashman.manage_operators` (`operators.py:198-206`). Não há assimetria. **Descartar** — o que fica é a trilha (C-4).
4. **"Remover o token do agente do HTML" (G).** D já corrigiu, e com razão: o token precisa estar no DOM para o clipboard, o tradeoff está escrito (`pos_agent.py:8-10`), a tela é gateada por `cashman.change_terminal`, e o `TerminalAdmin` já mostra mascarado. **Descartar a remoção**; se algo entrar, que seja só o log de visualização, e como P2.
5. **"Teste: TrustedDevice não pode ser deletado diretamente" como aceite de P1 (G/D).** Nenhum grupo tem permissão em `doorman`; só superusuário; o delete grava `LogEntry`. Vira P2 de higiene, não aceite de WP.
6. **"Usuário view-only não exporta PII" como escalonamento (D).** Provado que a action aparece para view-only, mas o único grupo com `view_customer` também tem `change_customer`. O achado real é motivo/trilha LGPD, não permissão. **Reescrever, não descartar.**
7. **"Import de Product não publica item fiscalmente incompleto" (G).** D acertou: é feature nova offerman↔fiscalman. **Fora deste WP.**

---

## F. Aceites verificáveis

Todos checáveis contra o código de hoje; os de permissão têm molde pronto em `shopman/backstage/tests/test_admin_reachability.py` (que roda `setup_groups` de verdade).

1. **Nenhuma action muda estado sem `permissions=`.**
   Prova: teste que varre `admin.site._registry`, e para cada `ModelAdmin` compara `get_actions(req_view_only)` com uma allowlist de actions inócuas. Hoje esse teste falha com `refund_selected`, `release_holds`, `execute_now_action`, as 6 do Product, `export_selected_csv`, `recalculate_insights`, `recalculate_quants`.
2. **Nenhuma `actions_row`/`actions_detail`/`actions_submit_line` executa em GET.**
   Prova: `client.get("/admin/payman/paymentintent/<pk>/refund/")` com staff sem permissão ⇒ 403 (hoje: executa). Idem `/admin/stockman/hold/<pk>/release-hold/` e `/admin/orderman/directive/<pk>/execute-row/`.
3. **Caixa e Cozinha não importam catálogo.**
   Prova: `client.post("/admin/offerman/product/import/")` com usuário do grupo Caixa ⇒ 403. Hoje: 200.
4. **Reset e desbloqueio de PIN geram `LogEntry`.**
   Prova: `LogEntry.objects.filter(object_id=str(user.pk)).count()` antes/depois da action.
5. **PIN temporário não sai em cookie.**
   Prova: `assert "messages" not in response.cookies` após `reset_pin`, ou `MESSAGE_STORAGE.endswith("SessionStorage")`.
6. **`key` do TOTPDevice não aparece.**
   Prova (roda hoje, falha hoje): `assert "key" not in [f for _, o in admin.site._registry[TOTPDevice].get_fieldsets(req, dev) for f in o["fields"]]`.
7. **Settings hub só oferece o que abre.**
   Prova: para cada persona de `setup_groups`, pedir todo `entry.url` de `build_settings_hub(request=req)` e exigir 200 — cópia literal de `test_admin_reachability.py:99-110`.
8. **`table_badge` não contém classe de badge reconstruída.**
   Prova: `assert "bg-green-100" not in inspect.getsource(tables)`; e o gate ganha regra que faz `make admin` falhar em `attrs["style"]`.
9. **`check --deploy` falha em produção sem 2FA.**
   Prova: `call_command("check", deploy=True)` com `DEBUG=False`, `SHOPMAN_ADMIN_REQUIRE_2FA=False` ⇒ `SystemCheckError` com o id novo.
10. **Fase 2 do gate:** `check_unfold_canonical.py --maturity` com os `packages/*/admin.py`, `offerman/admin/`, `utils/admin/` nos `DEFAULT_TARGETS` ⇒ exit 0. Hoje: exit 1, 20 violações (número medido, use-o como linha de base).
11. **`make admin` sem `url` ao final.**

---

## G. Fronteiras e colisões

### Arquivos que este WP precisa tocar (lista exata)

Alta probabilidade de colisão — o mesmo arquivo é alvo de outros WPs:
- `packages/payman/shopman/payman/contrib/admin_unfold/admin.py` (C-1, C-8)
- `packages/stockman/shopman/stockman/contrib/admin_unfold/admin.py` (C-1)
- `packages/orderman/shopman/orderman/admin.py` (C-1; e é o **único** package admin plano vivo — colide com a Fase 2 do gate)
- `packages/offerman/shopman/offerman/contrib/admin_unfold/admin.py` (C-3)
- `shopman/backstage/admin/operators.py` (C-4)
- `shopman/backstage/admin/accounts.py` (D-1)
- `shopman/backstage/projections/settings_hub.py` (C-7)
- `packages/utils/shopman/utils/contrib/admin_unfold/tables.py` (C-5)
- `packages/utils/shopman/utils/contrib/admin_unfold/base.py` (C-5)
- `scripts/check_unfold_canonical.py` (C-5 regra nova; Fase 2 `DEFAULT_TARGETS`)
- `shopman/shop/checks.py` (C-6)
- **`config/settings.py`** (C-2 import/export, C-4 `MESSAGE_STORAGE`, D-1 `OTP_ADMIN_HIDE_SENSITIVE_DATA`) — ⚠️ arquivo de 1500+ linhas disputado por praticamente todo WP. Agrupe as 4 linhas num bloco só, com um comentário, para o conflito ser trivial de resolver.
- `shopman/shop/management/commands/setup_groups.py` (se houver permissão nova)
- Testes novos: `shopman/backstage/tests/test_admin_action_permissions.py` (arquivo novo, sem colisão)

Fase 2 do gate (só migração de estilo, mas toca):
- `packages/doorman/shopman/doorman/admin.py` (8), `packages/orderman/shopman/orderman/admin.py` (7), `packages/offerman/shopman/offerman/admin/product.py` (3), `packages/guestman/shopman/guestman/admin.py` (2)

### Permissões novas e impacto em `setup_groups.py`

Li o arquivo inteiro. Ele usa `group.permissions.set(perms)` (`:255`) — **é a fonte da verdade e revoga o que sair da lista**. Toda permissão nova precisa estar ali ou não chega a ninguém, e `tests/test_group_permission_parity.py` falha se uma permission que gateia superfície não for concedida a ninguém.

Proposta mínima — **prefira `permissions=["change"]` a permissão custom sempre que a divisão já esteja certa**:

| Ação | Recorte | Permissão | Grupo | Precisa mexer no setup_groups? |
|---|---|---|---|---|
| Refund | dinheiro é do Dono | `payman.refund_paymentintent` (custom, migration no payman) | **Dono** (`:246`, junto de `*_ver("payman")`) | **Sim** — 1 linha |
| Release hold | operação de estoque | `stockman.change_hold` (já existe) | Gerente | **Sim** — `_escrever("stockman","hold")` ou permissão custom; hoje ninguém tem change em stockman |
| Execute directive | fila do sistema | `orderman.change_directive` (já existe) | **decisão do dono** — ver H-1 | **Talvez** |
| Import/export catálogo | `IMPORT_EXPORT_*_PERMISSION_CODE = "change"/"view"` | reusa `offerman.change_product` | Gerente, Admin de Catálogo | **Não** ✅ |
| Ações de massa do catálogo | `permissions=["change"]` | reusa | idem | **Não** ✅ |
| Export PII | motivo LGPD, não permissão nova | — | — | **Não** |

### O que pertence a outro app/dono

- **payman**: `refund_paymentintent` é permissão custom em model de core ⇒ migration no `packages/payman`. Assinatura do dono do payman.
- **stockman**: `Hold`/`Quant` — quem decide se o Gerente pode liberar reserva é o dono do estoque.
- **orderman**: `Directive` é infraestrutura (ADR-003). O admin dela é o único package admin plano vivo — a Fase 2 do gate e o fix de permissão colidem no mesmo arquivo. Coordene.
- **offerman**: `ProductResource` e o dry-run do import.
- **guestman**: mascaramento e motivo LGPD.
- **doorman**: `has_delete_permission` dos 4 admins.
- **config/deploy**: as 4 linhas de settings e o check `SHOPMAN_E016`.
- **fiscalman**: validação fiscal no import — **fora**.

### Dimensionamento da Fase 2 do gate (medido, não estimado)

Rodei `scripts/check_unfold_canonical.py --maturity` sobre os 9 alvos fora do gate:
- **20 violações · 4 arquivos** — doorman 8, orderman 7, offerman/admin/product.py 3, guestman 2.
- Por regra: `inline-style` 13, `noncanonical-design-token` 4, `unknown-unfold-css-class` 2, `raw-visual-shell` 1.
- Nenhuma exige primitiva nova: 13 são `<span style="color: x">` → `unfold_badge(texto, cor)`; as 7 do orderman são classes tailwind à mão em `format_html`.
- **17 das 20 estão em código que nunca renderiza** (doorman, guestman, offerman: desregistrados pelo contrib respectivo; craftsman/payman/stockman planos se auto-desativam e nem aparecem na contagem).
- Trabalho real: **meio dia**. Sem waiver nenhum, se a decisão for migrar. A alternativa mais barata e mais honesta está em H-2.

---

## H. Perguntas abertas para o dono do produto

1. **O Gerente pode reexecutar uma diretiva de estorno?** O `setup_groups.py:127-131` diz por escrito que dinheiro é do Dono, mas a tela de Diretivas dá ao Gerente o botão "Executar" sobre directives `payment.refund`. Ou a tela ganha permissão dedicada e o Gerente perde o botão, ou a regra "dinheiro é do Dono" tem uma exceção que ainda não está escrita. Não dá para decidir lendo código.

2. **Os `packages/*/admin.py` mortos: migrar ou apagar?** 17 das 20 violações estão em admins que o contrib do próprio pacote desregistra — código que nunca aparece na tela. Migrar custa meio dia e mantém arquivos que ninguém usa; **apagar** custa menos, respeita "zero resíduos" do CLAUDE.md, e faz a Fase 2 do gate passar quase de graça — mas remove o fallback "roda sem Unfold" que os pacotes anunciam nos docstrings. Como os pacotes são pip-instaláveis, essa é uma decisão de produto sobre o pacote, não sobre este deployment.

3. **Refund no Admin: permissão dedicada ou tirar a ação da tela?** Hoje o único grupo que alcança o PaymentIntent é o Dono. Se o refund é sempre decisão do Dono, `permissions=["refund"]` + POST resolve com 4 linhas. Se a intenção é o Gerente poder estornar com autorização (o WP fala em step-up 2FA), isso é feature nova, com sessão verificada e dossiê — outro tamanho de trabalho.
