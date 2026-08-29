# WP-09-agente-d — Admin Canonico / Unfold

**Status:** pronto para implementação · **Autor:** Agente D (revisão do WP-09 do Agente G)
**Superfície:** Django Admin/Unfold, 'admin_console', package-level ModelAdmins
**Objetivo:** manter o Admin como superfície canônica de cadastro, configuração, auditoria e correção assistida — sem ação de dinheiro executável por view-only, sem segredos expostos, sem PII exportável sem controle e sem drift de Unfold.

## Diferenças vs. WP original (Agente G)

**Mantidos (validados):** gate não cobre 'packages/*/shopman/*/admin.py' (7 admins planos + contribs fora do 'DEFAULT_TARGETS' — 'check_unfold_canonical.py:253-273,361-363'); 'table_badge' reconstrói badge por classes ('tables.py:38-47,100-105' — anti-padrão que o próprio pacote corrigiu em 'badges.py'); 'BaseModelAdmin' injeta 'style' em textarea ('base.py:77,93' — o gate não pega: regex '\bstyle=' não casa com 'attrs["style"]'); 'PaymentIntentAdmin' read-only expõe refund; reset de PIN mostra temporário em mensagem ('operators.py:119-135'); token do POS agent em HTML; import/export e PII sem permissão fina; settings hub sem filtrar permissão; 2FA Admin default off.

**Recalibrados / agravados:**
- **P0 refund** — pior que o WP pinta: com 'has_change_permission=False' para todos ('admin.py:311-318') e actions sem 'allowed_permissions', o Django executa 'refund_selected' no POST do changelist sem checar permissão de change — **qualquer staff com view em PaymentIntent executa refund** (total/parcial), sem permissão dedicada, sem step-up, sem LogEntry (só 'messages.success'). Não é "sem permissão clara": é **sem permissão nenhuma**.
- **P1 import/export** — agravado: 'django-import-export' default é 'has_import_permission=True'/'has_export_permission=True' (settings não define 'IMPORT_EXPORT_*_PERMISSION_CODE') — **qualquer staff importa catálogo (preços/NCM) e exporta PII**; 'guestman/contrib/admin_unfold/admin.py:527-547' exporta 'first_name/last_name/email/phone' como action normal executável por view-only.
- **P1 gate + "make admin final obrigatório"** — **contradição resolvida**: ampliar o gate hoje quebra 'make admin' imediatamente (dezenas de violações em doorman/orderman/guestman). Fase 1: inventário + waivers explícitos; Fase 2: ampliar o gate. O aceite "novo HTML cru falha" só é satisfazível depois da migração — declarado como dependência.
- **P1 token do agente** — nuance: a linha citada ('pos_counter_agent.py:56') é o botão de copiar; a exposição real é 'projections/pos_agent.py:227' em '<pre><code>' — o token **precisa** estar no DOM para o clipboard (tradeoff documentado em 'pos_agent.py:8-10'). A proposta certa: step-up + log de visualização/cópia; **não** remover do HTML.
- **P2 2FA** — manter: não existe system check; 'check --deploy' deve falhar sem 'SHOPMAN_ADMIN_REQUIRE_2FA=true' e 'SHOPMAN_ADMIN_HOST'.

**Novos (achados da verificação):**
- **Segredos de gateway expostos a view-only**: 'gateway_data_display' renderiza 'client_secret'/'qrcode'/'txid' crus para qualquer staff com view ('packages/payman/.../admin.py:297-309', truncados a 300 chars) — no mesmo admin do refund.
- **'reset_pin' sem trilha de auditoria**: 'registrar_no_historico' só roda em 'issue_badge'/'revoke_badge' ('operators.py:165,176') — gerar novo segredo (PIN) não grava LogEntry.
- **TrustedDevice deletável**: 'doorman/contrib/admin_unfold/admin.py:334-338' bloqueia add/change mas **não** 'has_delete_permission' — o teste "TrustedDevice não pode ser deletado diretamente" do WP falharia hoje.

## Fronteira Natural

Admin guarda decisões de baixo ritmo e alta responsabilidade. Operação ao vivo pertence aos apps Nuxt. **Dono de permissão/modelo**: refund é do payman (permissão 'payman.refund_paymentintent' em modelo de core — coordenação com o dono do payman); PII/masking do cliente é do guestman; TrustedDevice/2FA é do doorman; import/export de catálogo é do offerman; o check de deploy 2FA é de config/deploy. Este WP é dono do **gate canônico** e da **camada de Admin** — as permissões novas cruzam donos e devem ser assinadas por eles.

## Evidências (verificadas)

- Gate varre só 'contrib/admin_unfold' + 'templates/admin': 'scripts/check_unfold_canonical.py:253-273,361-363,706'.
- Violações reais fora do gate: 'packages/doorman/shopman/doorman/admin.py:97-101,313-317' (mark_safe inline style); 'orderman/admin.py:209-680' (tailwind à mão); 'guestman/admin.py:234,244-245' (link cru + style).
- 'table_badge' reconstrói badge: 'packages/utils/shopman/utils/contrib/admin_unfold/tables.py:38-47,100-105'; 'badges.py:1-13' (docstring do anti-padrão).
- 'BaseModelAdmin' injeta style: '.../base.py:77,93' (deliberado, escopado a textarea, mas invisível ao guardrail).
- Refund view-only: 'packages/payman/.../admin.py:154,202-204,289-294,311-318'; actions sem 'allowed_permissions'.
- Reset PIN em message storage: 'shopman/backstage/admin/operators.py:119-135'; 'issue_badge' roteia pela sessão (':137-159') — padrão a seguir.
- Token do agente: 'shopman/backstage/projections/pos_agent.py:227', 'admin_console/pos_counter_agent.py:56'.
- Import/export abertos: 'admin_unfold/admin.py:282-285,319' (ProductAdmin), 'resources.py:17-27,31-59'; guestman export PII: 'contrib/admin_unfold/admin.py:527-547'.
- Segredos de gateway: 'packages/payman/.../admin.py:297-309'.
- TrustedDevice sem delete bloqueado: 'doorman/contrib/admin_unfold/admin.py:334-338'.
- Sem system check 2FA: 'config/settings.py:1321-1323'.

## Achados Priorizados

### P0 — Refund mutante executável por view-only (read-only de fachada)

Proposta:
- Permissão dedicada 'payman.refund_paymentintent' (dono: payman — coordenação formal).
- Actions com '@action(permissions=["refund_paymentintent"])' (nunca sem 'allowed_permissions').
- Remover row action direta de reembolso total; dialog action com 'BaseDialogForm': saldo, valor, pedido, gateway, motivo, confirmação (gate canônico do Unfold).
- Step-up 2FA recente para refund.
- 'LogEntry' + dossiê de ação (antes/depois).
- **Proteger os segredos de gateway no mesmo admin**: 'gateway_data_display' mascarado por padrão; revelar exige permissão + motivo.

Aceite:
- Usuário view-only não executa refund (teste: POST da action com view-only → 403).
- Refund sem motivo/step-up não passa (teste).
- Row action direta de reembolso total deixa de existir.
- 'client_secret' não aparece para view-only sem passo de revelação (teste assert-negativo).

### P1 — Gate não cobre fallback 'packages/*/admin.py' (com migração dimensionada)

Proposta (2 fases):
- Fase 1: inventário das violações nos 7 admins planos + contribs; emitir waivers explícitos OU migrar para helpers canônicos (decisão por arquivo, registrada).
- Fase 2: incluir 'packages/*/shopman/*/admin.py' no 'DEFAULT_TARGETS' do gate; a partir daí, HTML cru novo falha 'make admin'.

Aceite:
- Fase 2 só entra quando 'make admin' passa com os arquivos no gate.
- Waivers documentados (exceção explícita, não silêncio).
- Nenhum HTML cru novo em package admin carregado passa despercebido.

### P1 — Helpers Unfold são contornados (drift invisível ao guardrail)

Proposta:
- 'table_badge()' delega para o helper canônico ('unfold_badge'/'unfold/helpers/label.html').
- Remover 'style' de widgets ('BaseModelAdmin') ou registrar waiver estreito; **ampliar o guardrail** para pegar 'attrs["style"]' (não só 'style=' em template).
- Migrar 'payment_refund.html' para 'unfold/helpers/field.html' + dialog action; trocar links crus por 'unfold_link()'.

Aceite:
- 'make admin' inclui guardrail para 'style' em attrs, badge manual e field helper.
- 'table_badge' não contém classes de badge reconstruídas (teste).

### P1 — PIN temporário e token de agente expostos sem step-up

Proposta:
- PIN temporário em página one-time (padrão do 'issue_badge': sessão → página única), sem message storage acumulável.
- **'reset_pin' ganha LogEntry** (hoje não registra nada).
- Token do agente: revelado apenas após step-up + log de visualização/cópia (mantém o copy-to-clipboard; não remover do DOM).

Aceite:
- Message framework não contém PIN temporário (teste assert-negativo).
- Resetar PIN gera trilha (teste).
- Visualizar token gera LogEntry.

### P1 — Import/export e PII sem permissão fina (aberto a todo staff)

Proposta:
- Definir 'IMPORT_EXPORT_IMPORT_PERMISSION_CODE'/'IMPORT_EXPORT_EXPORT_PERMISSION_CODE' (dono: offerman/guestman conforme o modelo).
- Permissão dedicada para import de catálogo, export PII e actions de massa; dry-run com diff humano.
- Mascaramento por padrão nas listas; revelar/exportar exige motivo (LGPD) — dono: guestman.
- 'export_selected_csv' deixa de ser action de view-only.

Aceite:
- Usuário sem permissão dedicada não exporta PII nem importa catálogo (teste).
- Export PII exige motivo registrado.
- "Import de Product não publica item fiscalmente incompleto" — **não é aceite deste WP**: é feature nova de integração offerman↔fiscalman (não existe validação fiscal no import hoje; 'ProductResource' importa 'is_published' direto). Registrar como dependência separada.

### P2 — Settings hub e 2FA default off

Proposta:
- Projection do settings hub recebe 'request/user' (aplica 'admin.gates'); card sem acesso aparece só com motivo operacional.
- System check: 'manage.py check --deploy' falha em produção sem 'SHOPMAN_ADMIN_REQUIRE_2FA=true' e 'SHOPMAN_ADMIN_HOST'.

Aceite:
- Usuário vê somente portas acessíveis ou bloqueios explicitamente úteis.
- 'check --deploy' falha em produção insegura.

## Melhorias UX

1. **RiskActionMixin:** preview, motivo, step-up, permissão dedicada, LogEntry e tabela de impacto.
2. **Radar downstream no ProductAdmin:** fiscal, imagem, preço, estoque, publicação, ficha técnica, alergênicos (leitura; escrita é do dono).
3. **Dossiê de ação:** refund, merge, revoke, release hold e import com antes/depois.
4. **Modo privacidade de cliente:** listas mascaradas; revelar/exportar exige motivo (dono: guestman).
5. **Import de catálogo com diff humano:** "12 preços sobem, 3 despublicam, 2 sem NCM".
6. **Hub de permissões por pessoa:** grupos + ações críticas efetivas.
7. **Terminal/agent health:** token visto, último doctor, última impressão, última gaveta.

## RBAC / setup_groups

Permissões novas: 'payman.refund_paymentintent' (payman), import/export (offerman/guestman), mascaramento (guestman). **Obrigatório atualizar 'setup_groups.py'** conforme o dono de cada uma e rodar o teste de paridade. Coordenação formal com payman/offerman/guestman/doorman para permissões em modelos de core.

## Pré-requisitos

- Fase 1 do gate (inventário + waivers) antes de ampliar o 'DEFAULT_TARGETS'.
- Coordenação com os donos de payman/offerman/guestman/doorman para permissões novas.
- "Import sem publicação fiscalmente incompleta" é dependência de fiscalman (fora deste WP).

## Testes

- View-only não executa refund/release/recalculate/export PII (POST direto → 403).
- Actions críticas exigem step-up.
- 'reset_pin' gera trilha; PIN não fica em message storage.
- Segredos de gateway mascarados para view-only.
- 'packages/*/admin.py' entra no gate só quando 'make admin' passa; waivers documentados.
- 'table_badge' não contém classes reconstruídas; widgets sem 'style'.
- Settings hub não lista portas sem permissão.
- TrustedDevice não pode ser deletado diretamente (corrigir 'has_delete_permission').
- 'make admin' final obrigatório.

## Fora De Escopo

Operação ao vivo de POS/KDS/Pedidos/Produção, fechamento de caixa no balcão, telas runtime headless, dashboards analíticos longos, revisão operacional de campanha, fluxos com scanner/impressora/refresh contínuo, e **validação fiscal no import de catálogo** (fiscalman).

## Prompt Para Agente Executor

~~~text
Execute WP-09-agente-d (Admin Canonico / Unfold).

Leia obrigatoriamente:
- docs/plans/backstage-app-audits-2026-08-29/agente_d/WP-09-agente-d-admin-canonico.md
- .codex/skills/unfold-admin-canonical/SKILL.md
- docs/engineering/unfold_admin_page_playbook.md
- docs/engineering/unfold_canonical_policy.md
- docs/reference/unfold_canonical_inventory.md
- packages/payman/shopman/payman/contrib/admin_unfold/admin.py
- packages/utils/shopman/utils/contrib/admin_unfold/*
- shopman/backstage/admin/operators.py
- shopman/backstage/admin_console/pos_counter_agent.py
- shopman/backstage/projections/pos_agent.py
- scripts/check_unfold_canonical.py
- shopman/shop/management/commands/setup_groups.py (coordenacao de permissoes)

Fases:
1. Fechar refund: permissao dedicada (dono payman), @action(permissions=...), dialog BaseDialogForm, step-up, LogEntry; mascarar segredos de gateway.
2. Gate packages admins: fase 1 inventario+waivers, fase 2 ampliar DEFAULT_TARGETS.
3. Remover drift Unfold: table_badge, style em attrs (ampliar guardrail), field helper.
4. Proteger PIN temporario (pagina one-time + LogEntry do reset) e token do agente (step-up + log de visualizacao).
5. Permissoes finas para import/export/PII (permission codes + motivo LGPD).
6. Settings hub permission-aware + system check 2FA.

Rode 'make admin' ao final. Nao crie console operacional no Admin. Coordene permissoes de core com os donos (payman/offerman/guestman/doorman).
~~~

