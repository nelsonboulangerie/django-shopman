# Plano — Reconstrução do Admin/Unfold

> Status: **PROPOSTA — aguardando aprovação do Pablo** (Fase 3 da missão de 2026-08-14).
> Nada deste plano foi executado. A Fase 4 (execução em WPs) só começa após aprovação.

## 1. Contexto e veredito

Veredito do Pablo (2026-08-14): o Admin está "blotado, bagunçado, repetitivo, redundante,
esquisito, desorganizado — um Frankenstein"; ele "não acha absolutamente nada lá" e estima
que deveria existir metade das telas atuais.

O diagnóstico confirma o veredito — e explica o "não acho nada" com precisão cirúrgica:

- **80 ModelAdmins registrados**, para uma operação que já migrou para 7 superfícies Nuxt.
- **5 links mortos no menu lateral** (`href="#"`), e são justamente telas de configuração
  que o Pablo usa: **Promoções, Cupons, Zonas de entrega, Faixas de distância, Grupos de
  clientes**. Os quatro primeiros quebraram quando os models migraram de `storefront` para
  `shop` (o nav aponta `admin:storefront_*`, que não reverte mais); o quinto é resíduo do
  rename `CustomerGroup → PriceTier` (migração guestman 0002) — violação da regra
  zero-residuals que sobreviveu no menu.
- **41 dos 80 ModelAdmins são órfãos**: registrados, mas sem nenhum item de menu
  (`show_all_applications: False` — o sidebar custom é a única navegação). Só aparecem na
  busca ⌘K. Entre os órfãos há config real que o Pablo precisa achar (Insumos, Fornecedores,
  Faixas de preço, Qualidade de fornada, Terminais do PDV).
- **O histórico de pedidos aterrissa vazio**: date_hierarchy cai no dia corrente ("0
  resultados (328 total)") com um botão "Adicionar pedido" — que nunca deveria existir num
  trail de auditoria — e empty state que sugere "criar o primeiro item".
- **Colunas mortas**: a changelist de Produtos exibe Custo e Margem 100% vazios
  (`OFFERMAN["COST_BACKEND"] = None`) e uma coluna Combo com badge vermelho em todos os 59
  produtos (ruído sem informação).
- **Redundâncias**: Campanhas/Anúncios têm CRUD no Admin **e** superfície própria
  (marketing-nuxt) — violação de one-question-one-owner. Transações de pagamento,
  expedições, movimentações de caixa e transações de fidelidade têm tela própria **e**
  inline na tela-mãe.
- **Vocabulário duplicado**: `orderman.Session` = "comanda" × `backstage.POSTab` = "comanda
  do PDV" (aberto conhecido do admin-excellence pass 4). No menu: "Comandas abertas" e
  "Comandas do PDV" são coisas diferentes com o mesmo nome.

## 2. Papel do Admin (Fase 1 — régua de corte)

Consolidado de CLAUDE.md, `feedback_admin_crud_config_only`, `feedback_no_standalone_admin`,
`feedback_one_question_one_owner`, skill unfold-admin-canonical e políticas do gate:

1. **Admin não opera.** Operação vive nas superfícies (PDV, KDS, Pedidos, Produção,
   Marketing, Hub). O Admin é retaguarda: configuração, CRUD de cadastros, auditoria.
2. **Uma pergunta, um dono.** Se uma superfície Nuxt já responde a pergunta, o Admin não
   duplica a tela — no máximo linka.
3. **Config inseparável da operação mora onde a operação acontece** — não no Admin.
4. **Tela de sistema não é tela de gente.** Tabela que só o sistema escreve e ninguém lê
   (idempotência, códigos de verificação, refs) não merece ModelAdmin.
5. **Canonicidade Unfold**: primitiva oficial > classe copiada; páginas custom via
   `UnfoldModelAdminViewMixin` + projection registrada; gate `make admin` antes de PR.
6. **Core é sagrado**: o Admin se dobra aos models de `packages/`, nunca o contrário.

## 3. Inventário global com veredito (Fase 2)

Legenda: ✅ manter · 🔒 manter read-only (auditoria) · 👻 tirar do menu, manter registro
(busca/debug) · ✂️ **remover registro** · 🔧 consertar. Contagens de linhas do DB de dev em
14/08/2026.

### Config que o Pablo edita (manter e polir)

| Tela | Linhas | Veredito | Nota |
|---|---|---|---|
| shop.Shop + 8 singletons (Appearance, Operation, Menu, Ordering, Loyalty, Pos, Production, Integrations) | 1 cada | ✅ | Padrão bom: redirect direto pro form, fieldsets, help text. É o coração da config. |
| shop.Channel | 8 | ✅ | |
| shop.RuleConfig | 4 | ✅ | |
| shop.Promotion / shop.Coupon | 5 / 3 | ✅ 🔧 | Link do menu morto (`storefront_*`) — consertar rota. |
| shop.DeliveryZone / shop.DeliveryDistanceBand | 2 / 3 | ✅ 🔧 | Idem. O help text de "Pedidos e entrega" manda pra cá e o link está morto. |
| shop.NotificationTemplate | 23 | ✅ | |
| shop.OmotenashiCopy | 2 | ✅ | Porta única = tela "Catálogo de copy" (custom, canônica, PR #110). Changelist crua sai do menu. |
| shop.QualityDefect / QualityGrade | 7 / 4 | ✅ 🔧 | Config do QC de fornada — hoje **órfãos**, entrar no menu (Produção). |
| offerman.Product / Collection / Listing | 59 / 9 / 3 | ✅ 🔧 | Tirar colunas mortas Custo/Margem (COST_BACKEND=None) e ruído da coluna Combo; breadcrumb "Catálogo de Produtos" → sentence case. |
| craftsman.Recipe | 18 | ✅ | |
| buyman.Material / Supplier / SupplierMaterialCost | 23 / 0 / 0 | ✅ 🔧 | Buyman Fase 1 — hoje **órfãos**, entrar no menu. |
| guestman.PriceTier | 3 | ✅ 🔧 | É o sucessor do CustomerGroup; assumir o lugar do link morto "Grupos de clientes". |
| guestman.Customer / CustomerAddress | 7 / 9 | ✅ | Customer vira a tela-360 (ver corte lote 3). |
| customer_loyalty.LoyaltyAccount | 5 | ✅ | |
| backstage.KDSInstance / POSTab / POSTerminal | 4 / 6 / 1 | ✅ 🔧 | POSTerminal hoje órfão. |
| backstage.OperationChecklistTemplate / OperationTaskTemplate | 3 / 11 | ✅ 🔧 | Config; hoje órfãos. |
| doorman.PinCredential | 4 | ✅ | Gestão de operadores (crachá, PIN, unlock). |
| auth.User / auth.Group / otp_totp.TOTPDevice | 5 / 5 / 0 | ✅ | Sistema & acesso (superuser). |

### Auditoria (manter, mas travar como leitura)

| Tela | Linhas | Veredito | Nota |
|---|---|---|---|
| orderman.Order | 328 | 🔒 🔧 | Sem "Adicionar"; consertar aterrissagem vazia (sem drill-down default no dia corrente); empty state de auditoria, não de CRUD. |
| orderman.Session | 8 | 🔒 | Resolver naming (ver §5). |
| orderman.Directive | 638 | 🔒 | Mantém `execute_now` (ferramenta de saúde da fila, ADR-003). |
| payman.PaymentIntent | 312 | 🔒 | Mantém `refund_selected` (retaguarda financeira, não operação de balcão). |
| backstage.DayClosing / CashShift | 1 / 2 | 🔒 | Fechamento opera no PDV; aqui é trilha. |
| backstage.OperatorAlert | 7 | 🔒 | Item "Alertas ativos" do menu. |
| backstage.OperationChecklistRun | 3 | 🔒 | Remover a action `complete_selected` (Admin não opera checklist). |
| stockman.Quant / Move / Batch / Position / StockAlert | 281 / 564 / 1670 / 7 / 8 | ✅/🔒 | Quant/Position/StockAlert = config e leitura; Move/Batch = trilha. |
| storefront.StockAlertSubscription | 0 | 🔒 | Sinal de demanda dos clientes ("avise-me"). |
| craftsman.WorkOrder | 395 | 🔒 | Já tem o aviso "a operação acontece em Produção do dia" — manter como auditoria/manutenção. |
| doorman.TrustedDevice | 2 | 🔒 | Fica pela action de segurança `revoke`. |

### Corte — remover do registro (✂️)

**Lote 1 — artefatos de sistema puro** (só o sistema escreve, ninguém lê no Admin):

| Tela | Linhas | Por quê |
|---|---|---|
| orderman.IdempotencyKey | 4 | Infra de dedupe; debug é via DB/shell. |
| orderman.SessionEvent | 3 | Trilha técnica da comanda; sem consumidor humano. |
| doorman.AccessLink | 3 | Artefato de login; expira sozinho. |
| doorman.VerificationCode | 0 | Idem. |
| doorman.CustomerUser | 1 | Ponte user↔customer; nunca editada à mão. |
| guestman.ExternalIdentity | 0 | Identidade de provedor externo; sistema. |
| customer_identifiers.CustomerIdentifier | 0 | Sistema. |
| refs.Ref / refs.RefSequence | 0 / 0 | Registro de refs tipadas — infra, vazio, e rename tem fluxo próprio. |
| storefront.CustomerFavorite | 0 | Escrito pelo cliente na loja; leitura já projetada na superfície. |
| taggit.Tag | 108 | 👻 (não ✂️): sai do menu; edição segue nos widgets de tag. |
| stockman.Hold | 3 | 👻: sai do menu; `release_holds` fica acessível pela busca p/ reparo raro. |

**Lote 2 — duplicatas de inline** (a tela-mãe já mostra):

| Tela standalone | Linhas | Tela-mãe (inline existente) |
|---|---|---|
| payman.PaymentTransaction | 310 | PaymentIntent |
| orderman.Fulfillment | 313 | Order |
| backstage.CashMovement | 2 | CashShift |
| customer_loyalty.LoyaltyTransaction | 37 | LoyaltyAccount |
| backstage.OperationTaskRun | 11 | OperationChecklistRun |
| guestman.ContactPoint | 14 | Customer (vira inline/seção read-only) |

**Lote 3 — duplicatas de superfície + Cliente 360**:

| Tela | Linhas | Por quê |
|---|---|---|
| shop.Campaign | 3 | Marketing-nuxt é o dono (ADR-018/019/020). One question, one owner. |
| shop.AnnouncementTemplate | 2 | Idem. |
| shop.Announcement | 0 | Idem — trilha de publicação vive na superfície. |
| customer_insights.CustomerInsight | 7 | Badges de RFM/churn já aparecem na changelist do Cliente; detalhe vira seção read-only no form do Cliente. |
| customer_timeline.TimelineEvent | 1 | Vira seção read-only no Cliente (quando fizer falta). |
| customer_preferences.CustomerPreference | 3 | Idem. |
| customer_consent.CommunicationConsent | 5 | Registro LGPD: **não se apaga o dado**, apaga-se a tela avulsa — vira seção read-only no Cliente. |

**Resultado: 80 → 54 registros** (26 saem: 23 ✂️ + 3 viram seção no Cliente), menu de 46
itens → ~38 organizados por intenção, zero link morto, zero órfão de config. Com os cortes
adicionais opcionais (§7), dá para chegar a ~50.

### Telas custom (admin_console) e dashboard

| Tela | Veredito | Nota |
|---|---|---|
| Catálogo de copy (`/admin/configuracao/copy/`) | ✅ | Canônica (projection + Unfold), boa. Unificar o NOME (ver §5). |
| Crachá do operador (`operator_badge`) | ✅ | Par do PinCredential. |
| Agente da gaveta (`pos_drawer_agent`) | ✅ | Necessário p/ instalar no balcão. |
| Dashboard (`dashboard_callback`) | ✅ 🔧 | Atualizar atalhos após reorganização; hoje aponta só para 5 configs e há 20+. |

## 4. Menu lateral proposto — por intenção de uso, não por app Python

8 grupos, ordem de frequência de uso (operação → config → auditoria → sistema):

1. **Operação ao vivo** (não colapsável, como hoje): links condicionais para as superfícies
   (Pedidos, PDV, Fechamento, KDS, Produção ao vivo) + Alertas ativos.
2. **Catálogo**: Produtos · Coleções · Listagens.
3. **Loja & canais**: Loja & contato · Marca & aparência · Horários & operação · Cardápio ·
   Pedidos & entrega · Fidelidade · PDV & alertas · Produção · Integrações · Canais ·
   Textos da interface · Templates de notificação.
4. **Vendas & entrega**: Regras de preço · Promoções · Cupons · Faixas de preço ·
   Zonas de entrega · Faixas de distância.
5. **Clientes**: Clientes · Endereços · Contas de fidelidade · Avisos de reposição.
6. **Produção & insumos**: Fichas técnicas · Ordens de produção · Defeitos de fornada ·
   Graus de qualidade · Insumos · Fornecedores · Custos de insumo.
7. **Estoque**: Saldos · Movimentos · Lotes · Posições · Alertas de estoque.
8. **Auditoria**: Histórico de pedidos · Comandas/sessões abertas · Ações pendentes ·
   Cobranças · Fechamentos · Turnos de caixa.
9. **Sistema & acesso** (só admin/superuser): Usuários · Grupos · Operadores (PIN & crachá) ·
   Dispositivos confiáveis · 2FA · Estações KDS · Comandas do PDV · Terminais ·
   Modelos de checklist · Execuções de checklist · Agente da gaveta.

Tabs do Unfold (`UNFOLD["TABS"]`) seguem os mesmos agrupamentos (ex.: tab de Produção ganha
Ordens + Fichas + Qualidade; some a situação atual de estar numa tela sem tab ativa).

## 5. Renomeações de copy (pt-br, sentence case, sem jargão)

- **Comanda × sessão (decisão do Pablo, recomendação abaixo)**: por
  `feedback_comanda_is_tab_not_command`, comanda = POSTab. Recomendo renomear o verbose de
  `orderman.Session` para **"sessão de pedido"** (Meta do Core; gera uma migração
  `AlterModelOptions` append-only, permitida pós-reset) e no menu "Comandas abertas" →
  "Sessões abertas". POSTab segue "comanda do PDV" — e no dia a dia, só "comanda".
- **Unificar "Catálogo de copy" × "Textos da interface"**: um nome só nas duas portas
  (menu, dashboard, título da tela). Recomendo **"Textos da interface"**.
- **Sentence case** nos resíduos: breadcrumb "Catálogo de Produtos" → "Catálogo de
  produtos"; varrer `verbose_name` dos ModelAdmins e títulos de fieldsets (a varredura das
  superfícies foi o PR #153; esta é a parte backend que ficou registrada como pendente).
- Login "Welcome back to" → copy pt-br da marca.
- Ícones: revisar 1:1 na reorganização (ex.: "Lotes" com ícone `science` é esquisito;
  `inventory`/`calendar_clock` comunicam validade melhor).

## 6. WPs de execução (Fase 4 — após aprovação)

Cada WP = 1 PR pequeno contra `main`, com `make admin` (sem url) + `make test-framework`
antes. Ordem pensada para valor imediato primeiro e demolição depois.

- **WP-ADM-R0 — Consertar o quebrado** (sem remover nada): 5 rotas mortas do menu
  (`storefront_*` → `shop_*`; "Grupos de clientes" → "Faixas de preço"/PriceTier); Order sem
  botão "Adicionar" e sem aterrissagem vazia; empty states de auditoria; breadcrumb do
  catálogo. _Risco zero, ganho imediato._
- **WP-ADM-R1 — Corte lote 1** (artefatos de sistema): unregister dos 9 ✂️ do lote 1 +
  Tag/Hold fora do menu. Ajustar testes que referenciem essas URLs.
- **WP-ADM-R2 — Corte lote 2** (duplicatas de inline): unregister dos 6; conferir que cada
  inline da tela-mãe cobre a leitura (readonly, paginação Unfold onde precisar).
- **WP-ADM-R3 — Corte lote 3** (duplicatas de superfície + Cliente 360): unregister de
  Campaign/Announcement/AnnouncementTemplate; seções read-only (Unfold sections) no form do
  Cliente para consentimento/insight/contatos; conferir marketing-nuxt como porta única.
- **WP-ADM-R4 — Menu novo + tabs + dashboard**: reescrever
  `shopman/backstage/admin/navigation.py` nos 9 grupos por intenção; TABS coerentes;
  dashboard com os atalhos da nova arquitetura; read-only nos trails de auditoria
  (has_add/has_change conforme inventário).
- **WP-ADM-R5 — Copy**: renomeações do §5 (inclui a decisão comanda×sessão e a migração
  `AlterModelOptions` se aprovada).
- **WP-ADM-R6 — Polimento por seção** (uma seção por PR, na ordem que o Pablo eleger):
  Catálogo (colunas mortas, combo, autocomplete de FKs), Clientes, Estoque, Auditoria
  (filtros, busca, fieldsets, list_editable onde fizer sentido).

## 7. Cortes adicionais possíveis (segunda rodada, se o Pablo quiser ir a ~50%)

- CustomerAddress standalone → inline no Cliente (o model fica, a tela some).
- TrustedDevice → 👻 fora do menu (revoke pela busca).
- Move/Batch → tela única de trilha de estoque com filtro por tipo.
- OperationChecklistRun/Template → avaliar se checklists já operam 100% na superfície; se
  sim, Templates ficam e Runs viram 👻.

## 8. Riscos e notas

- O contrato de superfícies do `make admin` conhece os ModelAdmins dos pacotes — remoções
  precisam atualizar o registry do gate junto (mesmo PR).
- `packages/*/admin.py` (não-Unfold) não é carregado neste deployment (quem carrega é
  `contrib/admin_unfold`); é a face standalone dos pacotes — **não mexer** (Core é sagrado).
- CLAUDE.md está desatualizado num ponto: diz que Promotion/Coupon/DeliveryZone vivem em
  `storefront/models/` — vivem em `shop/models/`. Sincronizar no WP-ADM-R0.
- Unregister não apaga dado nenhum: só remove a tela. Reversível com uma linha.
- A busca ⌘K continua cobrindo o que ficar registrado (inclusive os 👻).
