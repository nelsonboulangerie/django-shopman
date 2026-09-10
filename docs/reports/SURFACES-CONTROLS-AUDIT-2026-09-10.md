# Auditoria de controles — apps Nuxt de operador (2026-09-10)

Pedido do Pablo: revisar a aparência dos controles nas telas Nuxt ("a setinha do
select encostada na borda") e fazer uma revisão fina de padronização — tipografia,
espaçamento, alinhamento, bordas, raios, cores, contraste — e se os controles
comuns estão sendo compartilhados como deveriam.

Base medida: `origin/main` em `822aea24a`. Escopo: os 8 apps de operador
(`bi`, `hub`, `kds`, `marketing`, `orders`, `pos`, `production`, `purchase`) e o
`operator-kit`. O storefront fica de fora (superfície de cliente, `UiSelect` do
reka-ui, zero `<select>` nativo). Contagens excluem `components/Ui/` e
`node_modules`; tags multilinha foram parseadas, então os números batem com o que
o template renderiza. Cada achado traz arquivo:linha; o que pareceu errado e não
era está listado como **refutado**.

**O que o PR que carrega este relatório corrige:** só a seta do `<select>` nativo,
numa regra única em `operator-kit/app/assets/css/operator-theme.css`
(`appearance: none` + chevron Lucide + `padding-inline-end` reservado). Nenhum
call site foi padronizado, de propósito — há trabalho do Codex em voo em PDV,
Gestor de Pedidos, Produção e Marketing (ver §6). O resto deste documento é
diagnóstico com ordem de ataque.

---

## 1. Inventário: controles nativos com classe ad hoc × componentes `Ui*`

| app | `<select>` | `<input>` texto | checkbox/radio | `<textarea>` | `<button>` | UiInput | UiButton | UiSelect | UiTextarea |
|---|---|---|---|---|---|---|---|---|---|
| bi | **8** | 6 | 0 | 0 | 19 | 0 | 0 | 0 | 0 |
| hub | 0 | 2 | 0 | 0 | 2 | 0 | 0 | 0 | 0 |
| kds | 0 | 3 | 0 | 0 | 16 | 0 | 0 | 0 | 0 |
| marketing | 4 | 20 | 12 | 4 | 43 | 0 | 0 | 0 | 0 |
| orders | 6 | 38 | 11 | 7 | 89 | 0 | 0 | 0 | 0 |
| pos | 3 | 4 | 0 | 0 | 46 | **38** | **138** | 0 | 4 |
| production | **18** | 33 | 3 | 3 | **126** | 0 | 9 | 0 | 4 |
| purchase | 8 | 19 | 2 | 3 | 65 | 0 | 0 | 0 | 0 |
| operator-kit | 0 | 1 | 0 | 0 | 34 | 1 | 2 | 0 | 0 |
| **total** | **47** | 126 | 28 | 17 | 440 | 39 | 149 | **0** | 8 |

Leitura direta: **só o PDV usa os primitivos**. `production-nuxt` tem
`Ui/Button.vue` e `Ui/Input.vue` idênticos aos do PDV (md5 igual) e mesmo assim
escreve 126 `<button>` e 33 `<input>` à mão. `UiSelect` não existe em app nenhum
de operador (nenhum `SelectRoot`/`SelectTrigger` do reka-ui em `surfaces/*/app`).

**Refutado:** `purchase-nuxt/app/components/MaterialPicker.vue:7` casa em
`grep '<select'`, mas é docstring ("Um `<select>` nativo com 56 insumos é castigo
no celular") — o componente é um combobox próprio, de propósito.

### 1a. Todos os `<select>` nativos (arquivo:linha → classe)

`selectClass`/`fieldClass` resolvidos pela constante do próprio arquivo.

**bi-nuxt** — `h-9 … border border-border … px-2 text-sm`, sem foco
- `bi-nuxt/app/pages/scenarios.vue:44`
- `bi-nuxt/app/pages/profiles.vue:99`, `:110`, `:277` (`selectClass`, `:80`)
- `bi-nuxt/app/pages/explore.vue:126` (`min-w-44`), `:147`, `:157`, `:169`

**marketing-nuxt** — idem bi + `outline-none focus:ring-1 focus:ring-ring`
- `marketing-nuxt/app/components/CampaignForm.vue:191`, `:204`, `:238`
- `marketing-nuxt/app/components/AnnouncementTemplateForm.vue:122`

**orders-nuxt** — três receitas no mesmo app
- `orders-nuxt/app/components/OrderReasonDialog.vue:80` — `w-full rounded-md border bg-background p-2.5 text-sm …` (**sem altura**)
- `orders-nuxt/app/pages/index.vue:654` — idem (sem altura)
- `orders-nuxt/app/components/CatalogProductPanel.vue:454`, `:599`, `:659` — `fieldClass` (`:326`): `h-9 w-full … px-2.5 … focus:ring-1`
- `orders-nuxt/app/pages/catalog.vue:692` — select na barra invertida de ação em lote (`bg-transparent text-background`); com o chevron novo precisa de `bg-none` (feito no mesmo PR)

**pos-nuxt** — três receitas, três alturas
- `pos-nuxt/app/components/PosMoveLinesDialog.vue:144` — `h-9 … bg-transparent px-3 … focus-visible:ring-[3px] focus-visible:ring-ring/50`
- `pos-nuxt/app/components/PosCartPanel.vue:1095` — `h-11 w-full … bg-card px-2 text-xs` (`text-xs` num controle `h-11`)
- `pos-nuxt/app/pages/session/index.vue:602` — `h-10 … bg-background px-3 text-sm` (`h-10` não está na escala)

**production-nuxt** — 18, a maior concentração; sem foco em 17 de 18
- `production-nuxt/app/components/ProductionStageGrid.vue:613` — único com foco; e `text-muted-foreground`, o valor escolhido parece placeholder
- `production-nuxt/app/pages/reports.vue:310`, `:326`
- `production-nuxt/app/pages/recipes/new.vue:355`, `:370`, `:403`, `:420`, `:478`, `:491`
- `production-nuxt/app/pages/recipes/compare.vue:76`
- `production-nuxt/app/pages/recipes/[ref]/index.vue:499`
- `production-nuxt/app/pages/recipes/[ref]/edit.vue:379`, `:387`, `:390`, `:458`, `:464`, `:514`, `:544` (`selectClass`, `:277`). No mesmo arquivo `inputClass` (`:276`) TEM foco e `selectClass` não — input e select lado a lado, foco diferente.

**purchase-nuxt** — receita própria: `h-10`/`h-11`, `px-3`, `mt-1`, sem foco
- `purchase-nuxt/app/components/ReceiptConversion.vue:145` (`bg-card`) e `:186` (`bg-background`) — **mesmo componente, dois fundos**
- `purchase-nuxt/app/pages/index.vue:1000`, `:1415` (`w-56`), `:1472` (`h-9`), `:1533`, `:1538`, `:1543`

### 1b. `<input>` — receitas mais frequentes

| app | nº | receitas distintas | top |
|---|---|---|---|
| bi | 6 | 4 | login `h-11 … px-3 … focus:ring-1` ×2 · `h-9 … px-2` ×2 |
| hub | 2 | 1 | login (`hub-nuxt/app/app.vue:81`, `:92`) |
| kds | 3 | 2 | login ×2 · busca expansível (`kds-nuxt/app/pages/[ref].vue:214`) |
| marketing | 32 | 13 | `h-9 w-full … px-3 … focus:ring-1` ×8 · checkbox `size-4 rounded border-border` ×10 |
| orders | 49 | 8 | `fieldClass` (h-9, px-2.5) ×30 · **sem altura** `p-2.5` ×6 (`pages/index.vue:702,739,750`, `pages/[ref].vue:541,551,596`) |
| pos | 4 | 3 | login `h-12 … text-base` ×2 (`pos-nuxt/app/app.vue:146`, `:158`) — única tela em h-12/text-base |
| production | 36 | **18** | `h-9 … px-2 text-sm text-foreground` ×6 · `h-9 w-20 … text-right` ×6 |
| purchase | 21 | **15** | `mt-1 h-11 w-full … bg-card px-3 text-sm` ×5 · busca `h-10 … pl-9` ×2 |

### 1c. `<textarea>` (17) — três receitas
- marketing ×4: `w-full resize-y … px-3 py-2 text-sm … focus:ring-1` (`AnnouncementCard.vue:174`, `FireCampaignPanel.vue:157`, `AnnouncementTemplateForm.vue:95,148`)
- orders ×7: `p-2.5` (`OrderReasonDialog.vue:106`, `pages/index.vue:665`, `pages/[ref].vue:468`) · `areaClass` ×3 (`CatalogProductPanel.vue:404,503,643`) · `min-h-9 … p-2` (`pages/[ref].vue:501`)
- production ×3: `rounded-md border bg-background px-3 py-2` **sem `text-sm`, sem foco** (`ShortageDialog.vue:107`, `QcCloseScreen.vue:750`) · `ProductionStageGrid.vue:1164`
- purchase ×3: `mt-1 w-full resize-none … px-3 py-2 text-sm` sem foco (`pages/index.vue:957,982,1122`)
- `UiTextarea` existe em kds/marketing/orders/pos/production; usado só em pos (4) e production (4).

### 1d. `<button>` — 440 nativos, 297 receitas distintas

| app | nº | receitas | mais frequente |
|---|---|---|---|
| bi | 19 | 12 | `h-9 rounded-md border border-border px-3 text-sm font-medium` ×7 |
| kds | 16 | 16 | nenhuma repete |
| marketing | 43 | 29 | `rounded-md border border-border px-3 py-2 text-sm font-medium transition hover:bg-muted` ×5 |
| orders | 89 | 57 | `rounded-md border px-3 py-2 text-sm font-medium transition hover:bg-accent` ×7 |
| pos | 46 | 39 | pílulas `h-9 rounded-full border px-3 text-sm` ×5 · teclas `h-11 text-xl font-semibold tabular-nums` ×2 |
| production | 126 | 75 | `rounded-md px-2.5 py-1.5 text-sm font-medium transition` ×10 · `… px-3 py-2 … hover:bg-accent` ×9 |
| purchase | 65 | 43 | `h-10 … border-border px-3 text-sm font-medium hover:bg-accent disabled:opacity-50` ×4 · h-14 ×3 · h-12 ×5 · h-8 ×3 |
| kit | 34 | 24 | menus/chips internos do FilterBar/ColumnPicker/Numpad |

Fora do PDV, a altura do botão vem de `py-2`/`py-1.5` (orders 60+, production
100+, marketing 25+): ~38px e ~34px, entre `h-8` e `h-9`, e cresce se o texto
quebrar. `UiButton` (`size="default"` = `h-11`) resolveria em uma linha e já está
no diretório desses apps.

**O que mais importa (§1)**
1. production-nuxt: 18 selects, 33 inputs, 126 buttons à mão com `Ui/Button.vue` e `Ui/Input.vue` idênticos ao PDV parados no diretório.
2. Não existe `UiSelect` em app nenhum de operador.
3. `OperatorLogin.vue` é o mesmo arquivo em 5 apps (md5 `830bc677…`: bi/kds/marketing/orders/production), variante em purchase, e inline em `hub-nuxt/app/app.vue:75-95` e `pos-nuxt/app/app.vue:140-160`. Sete cópias da tela de senha; candidato direto ao kit.
4. orders `OrderReasonDialog.vue:80` e `pages/index.vue:654`: select sem altura — num diálogo de motivo de cancelamento, o select fica mais baixo que o `UiButton` ao lado.
5. `ProductionStageGrid.vue:613`: select com `text-muted-foreground` — "escolhi" e "não escolhi" têm a mesma cara.

---

## 2. Variação de receita para o mesmo controle

Escala declarada (`*/app/assets/css/tailwind.css:159-164`, idêntica nos 8 apps):
campo/botão padrão = **h-11**, chip/inline = h-9, CTA = h-14, `px-3`, foco por
`outline-ring` (`:176-178`), e `@layer base { * { @apply border-border outline-ring/50 } }` (`:185-188`).

**Refutado antes de acusar:** `border` × `border-border` × `border-input` **não
produzem cor diferente** — a base aplica `border-border` em `*`, e `--input` =
`--border` (`operator-theme.css:64-65` e `:113-114`). `border-border` explícito é
ruído de leitura, não bug visual.

### 2a. Altura de `<input>`/`<select>` nativos

| app | h-8 | h-9 | h-10 | h-11 | h-12 | sem altura |
|---|---|---|---|---|---|---|
| bi | – | 4 inp + 8 sel | – | 2 (login) | – | – |
| hub | – | – | – | 2 | – | – |
| kds | – | 1 | – | 2 | – | – |
| marketing | 3 | 12 inp + 4 sel | – | 2 | – | 3 |
| orders | 2 | 32 inp + 3 sel | – | 2 | – | **6 inp + 2 sel + 7 txt** |
| pos | – | 1 sel | 1 sel | 1 sel | 2 (login) | – |
| production | – | 21 inp + 17 sel | – | 2 | 2 | 8 |
| purchase | – | 2 inp + 1 sel | **6 inp + 5 sel** | 10 inp + 2 sel | – | 3 |
| `UiInput` | | | | **h-11** | | |

O campo nativo canônico de fato é **h-9** (≈80 ocorrências), um degrau abaixo do
que a escala chama de "campo" (h-11) e do `UiInput`. Purchase escolheu **h-10**,
que não existe na escala (18 buttons + 6 inputs + 5 selects). Concreto: no PDV o
campo tem 44px e o botão ao lado 44px; em receitas (production) o campo tem 36px
e o botão `py-2` ~38px; em Compras o campo tem 40px.

### 2b. Foco — quatro linguagens coexistindo

| receita | onde |
|---|---|
| `outline-none focus:ring-1 focus:ring-ring` | ~80: bi 2, hub 2, kds 3, marketing 18, orders 45, production 8, purchase 2 (todos os logins) |
| `focus-visible:ring-[3px] focus-visible:ring-ring/50` | `UiButton`, `UiTextarea`, `PosMoveLinesDialog.vue:144` |
| `focus-visible:ring-2 focus-visible:ring-ring/20` + `focus-visible:border-ring` | `UiInput` |
| `focus-visible:ring-2 focus-visible:ring-ring/40` | `Ui/FilterChip.vue`, `Ui/IconButton.vue` (orders/marketing) |
| **nada** (herda `outline-ring/50` da base) | bi 4 inp + 8 sel, production 17 sel + ~14 inp + 2 txt, purchase 16 inp + 8 sel + 3 txt, pos 2 sel |

Os três primitivos `Ui*` discordam entre si (3px/50 · 2px/20 · 2px/40), e ~80
call sites escrevem `outline-none` para **apagar** o mecanismo que o
`tailwind.css` declara canônico. Quem não escreve nada é quem segue a regra.

### 2c. Padding / texto / fundo
- `px-2`: bi 9, marketing 7, production 30, orders 2 · `px-2.5`: orders 33 · `px-3`: purchase 21, logins 14, pos 4 · `p-2.5` (sem altura): orders 15. A escala diz `px-3`.
- Texto: `text-sm` em todos, exceto `pos-nuxt/app/app.vue:146,158` (`text-base`), `PosCartPanel.vue:1095` (`text-xs`), production `ShortageDialog.vue:107`/`QcCloseScreen.vue:750` (sem tamanho).
- Fundo: `UiInput` = **`bg-card`**; nativos = **`bg-background`** em ~110 casos; `bg-card` em purchase (5) e `PosCartPanel.vue:1095`. Dentro de um `UiDialog` (fundo `bg-card`) o `UiInput` some na superfície e o nativo contrasta; fora, o inverso.

### 2d. O mesmo controle, receitas diferentes por app

**Busca com lupa** — cinco receitas: kds `pages/[ref].vue:214` · production `RecipeHeader.vue:54` (cópia do KDS com larguras diferentes) · orders `Ui/SearchInput.vue:29` (bg-card, botão limpar) · pos `PosProductGrid.vue:96` (`UiInput h-11 text-base`) · purchase `pages/index.vue:1213,1606` (h-10, sem foco, sem expansão).

**Select de filtro** — `bi explore.vue:147` (h-9, px-2, sem foco) · `production reports.vue:310` (idem, `border`) · `purchase pages/index.vue:1415` (h-10, mt-1, px-3, w-56) · `orders CatalogProductPanel.vue:454` (h-9, px-2.5, focus:ring-1) · `pos session/index.vue:602` (h-10, px-3).

**Botão secundário "outline"** — bi (`h-9`, sem hover) · marketing (`py-2`, `hover:bg-muted`) · orders (`py-2`, `hover:bg-accent`) · production (idem + `px-2.5 py-1.5` ×10) · purchase (`h-10`, `disabled:opacity-50`) · PDV (`UiButton variant="outline"`, h-11, ring 3px). Seis hovers/alturas para o mesmo botão.

**Disabled** — `disabled:opacity-50` (Ui*, purchase, bi) · `disabled:opacity-40` (marketing 4, orders 4, pos 7 em `PosPaymentWorkspace.vue:1198-1258`, kit 5 em `ColumnPicker.vue:86,94` e `OperatorNumpad.vue:22,30`) · `disabled:opacity-60` (logins ×14).

**O que mais importa (§2)**
1. Campo nativo em h-9 quando a escala diz h-11 (~80 casos): campo e botão de alturas diferentes na mesma linha; toque < 44px no tablet de produção.
2. Foco: 4 receitas + ~80 `outline-none` que anulam o mecanismo canônico.
3. `UiInput` bg-card × nativo bg-background — decidir um.
4. Purchase em h-10, degrau inexistente; 29 controles.

---

## 3. `components/Ui/` duplicados, kit e `tailwind.css`

| app | `Ui/` | conteúdo |
|---|---|---|
| kds | 12 | conjunto base (Alert, Badge, Button, Card, Dialog, Input, Popover, Separator, Sheet, Sonner, Textarea, Tooltip) |
| production | 12 | **idêntico ao kds** |
| pos | 13 | base + `Switch.vue` |
| orders | 16 | base + `FilterChip`, `IconButton`, `SearchInput`, `Toolbar` |
| marketing | 16 | **idêntico ao orders** |
| bi | 4 | Button, Card, Input, Sonner (idênticos) |
| purchase | 2 | Sheet (divergiu), Sonner (divergiu) |
| hub | 0 | — |

**Idênticos entre apps (md5):** Button, Input, Textarea, Badge, Separator, Alert,
Card, Dialog, Popover, Tooltip, Sheet (exceto purchase), Sonner (exceto purchase).
O risco hoje não é drift, é 5-6 cópias a manter em sincronia.

**Divergências reais:**
- `purchase-nuxt/app/components/Ui/Sheet/Content.vue` é versão reduzida (sem `floating`/`fullscreen`/`translucent`, sem slots, `side` padrão `right` vs `left`, durações diferentes). Fork consciente, mas já não é a mesma gaveta.
- `purchase-nuxt/app/components/Ui/Sonner.vue`: `top-center`, `rich-colors`, 3 toasts visíveis, e mapeia `--success/--error/--warning` para os tokens do tema. **Os outros 6 apps ainda mostram erro e sucesso no mesmo cinza** — purchase corrigiu um defeito que persiste nos demais.

**`UiSelect`:** inexistente. Um `UiNativeSelect` no kit cabe (o kit já auto-importa
`OperatorRail`, `FilterBar`, `ColumnPicker`, `OperatorNumpad`…). Atenção: **o kit
já depende de `Ui*` do app hospedeiro** — `OperatorIdentify.vue:182` usa
`<UiInput>`, `OperatorStationSetup.vue:66,70` usa `<UiButton>`,
`OperatorManagerAuth.vue:95-109` usa `<UiDialog*>`. Só funciona porque só pos e
orders os montam; em hub/purchase quebrariam em runtime. Um `UiNativeSelect` no
kit deve ser autocontido (um `<select>` + a classe), sem essa dependência invertida.

**`tailwind.css` — 8 arquivos, 5 versões:** bi = marketing = orders = purchase
(canônica, 230 linhas) · kds (uma linha em branco) · production (comentário do
`@source`) · hub: canônica + 24 linhas de `#pos-print-area`/`@media print`
**copiadas do PDV** (`hub-nuxt/app/assets/css/tailwind.css:230-253`; hub não
imprime recibo) · pos: canônica + `.pos-tile-fallback` + geometria do rolo
(legítimo). O bloco "ESCALA DE DESIGN" (`:143-183`) é idêntico nos 8 — a regra
existe; o que não existe é o mecanismo que a impõe.

**O que mais importa (§3)**
1. Cinco cópias idênticas de Button/Input/Dialog: a correção de foco (§2b) precisa ser aplicada 5-6 vezes, ou vai para o kit.
2. O kit depende de `Ui*` do hospedeiro — dependência invertida que já impede hub/purchase de usar identificação por PIN sem copiar mais arquivos.
3. `Sonner` de purchase corrigiu um defeito que os outros 6 apps ainda têm.
4. `hub-nuxt` carrega CSS de impressão do PDV — prova de que `tailwind.css` é copiado à mão.

---

## 4. Tipografia, espaçamento, cores fora da escala

Contagens em `.vue` fora de `Ui/`:

| item | bi | hub | kds | mkt | orders | pos | prod | purch | kit |
|---|---|---|---|---|---|---|---|---|---|
| hex hardcoded | 0 | 0 | 1 | 0 | 0 | 0 | **19** | 0 | 0 |
| `text-white`/`bg-white`/`bg-black` | 0 | 0 | 2 | 1 | 6 | 4 | 4 | 6 | 0 |
| `dark:` explícito | 1 | 0 | 5 | 8 | 27 | 20 | 24 | 0 | 4 |
| `text-amber-*` (em vez de `text-warning`) | 2 | 0 | 6 | 17 | 22 | **46** | **44** | 0 | 8 |
| `text-orange-*` (em vez de `text-destructive`) | 0 | 0 | 1 | 0 | 11 | 0 | 7 | 0 | 0 |
| `text-warning` (token) | 0 | 0 | 3 | 3 | 3 | 5 | 5 | **20** | 0 |
| `text-muted-foreground/≤60` | 0 | 0 | 3 | 0 | 12 | 1 | 0 | 0 | 0 |
| `rounded-lg` | 0 | 0 | 4 | 30 | 20 | 25 | **88** | 0 | 18 |
| `rounded-xl` | 1 | 0 | 1 | 19 | 10 | 0 | 2 | 1 | 2 |
| `leading-*` | 1 | 2 | 23 | 4 | 12 | 28 | 15 | 1 | 2 |
| `tabular-nums` | 37 | 0 | 25 | 4 | 32 | 91 | 97 | 37 | 5 |

**Refutados / legítimos:**
- Hex em `production-nuxt/app/pages/board.vue:316-323` e `SplitFlap.vue:140,160`: painel Solari do kiosk, "noturna por natureza, alheia ao tema". Decisão de produto. Idem `kds KdsTicketCard.vue:75` (máscara de gradiente).
- `purchase pages/index.vue:1731-1750` `bg-zinc-950`/`text-white`: overlay de câmera para escanear NF; preto atrás de vídeo é correto.
- `text-white`/`bg-white` em `PosReceipt.vue:26`, `ProductionLabelPrintDialog.vue:293`, `PosPaymentResult.vue:102` (QR), `display.vue:131` (QR): papel/impressão/QR precisam de branco de verdade.
- `text-muted-foreground` sobre `bg-muted` (~30 casos): light `#6e5a48` sobre `#f5e7dd` ≈ 5.4:1, dark ≈ 6.8:1. Passa AA.
- `text-[11px]`/`[12px]` em `PosReceipt.vue`, `text-[0.6rem]` em `WeighingLabels.vue`: impressão térmica/etiqueta, tamanho físico.
- `bi profiles.vue:187,384,386` sem `tabular-nums`: `tdClass` (`:83`) já traz.

**Achados reais:**

a) **`text-amber-700 dark:text-amber-400` como sinônimo de `text-warning`** — 90 em pos/production, 22 em orders, 17 em marketing. O tema define `--warning` (`operator-theme.css:59,108`) e purchase prova que basta (20 usos, zero `amber`). Ex.: `PosCartPanel.vue:161` (`bg-warning/10 text-amber-800 dark:text-amber-300` — fundo pelo token, texto pela paleta), `PosTerminalHealth.vue:54`, `PosDenominationCounter.vue:48`, `orders OrderCard.vue:116`, `orders pages/catalog.vue:468,475,546`, `kds pages/[ref].vue:335`, `marketing platforms.vue:58`. Mesmo padrão para destrutivo (`text-destructive dark:text-orange-300`: `OrderCourierPanel.vue:55,147,148`, `OrderCard.vue:62,247`, `orders pages/index.vue:453,598`, `pages/[ref].vue:208`) e sucesso (`text-success dark:text-lime-300`: `kds pickup.vue:99`, `OrderCourierPanel.vue:67`, `catalog.vue:614`). Se o `--warning` do dark está fraco para texto, o conserto é no token.

b) **`text-white` sobre `bg-destructive`** — `orders pages/index.vue:678`, `production ProductionStageGrid.vue:1185`, `AlertsBell.vue:28,62`, e `UiButton variant="destructive"` (herdado do shadcn). No dark `--destructive-foreground` é `#2b1d16` e `text-white` sobre `#e06a5e` fica ~2.6:1. É o botão de cancelar/excluir.

c) **Título de tela em 5 receitas:** `marketing pages/index.vue:48`, `campaigns.vue:75`, `history.vue:30` (`text-xl font-bold`) vs `templates.vue:60`, `platforms.vue:67` (`text-xl font-semibold`) no mesmo app · `purchase pages/index.vue:708,807,930,1196` (`text-xl font-semibold` no h1; `text-lg font-semibold` ×10 nos h2) · orders `text-sm font-bold uppercase tracking-wide` ×6 · pos `session/*` `h3 text-base font-semibold` ×20 · production `reports.vue:120,258,565`, `recipes/[ref]/index.vue:318`, `recipes/new.vue:332` `h2 text-base font-bold`. `Ui/Dialog/Title.vue:27` = `text-lg`, `Ui/Sheet/Title.vue:27` e `Ui/Card/Title.vue:35` sem tamanho. Só bi (35× `text-lg font-semibold`) e hub seguem a escala.

d) **Labels de campo:** production (30×), bi (10×), purchase (8×) seguem `text-xs font-medium text-muted-foreground`. marketing alterna `mb-1 block text-sm font-medium` ×12 e `text-xs` ×4; pos alterna `text-sm` (`PosTabPickerDialog.vue:83`, `PosPaymentWorkspace.vue:1944`) e `text-xs` (`PosScheduleModal.vue:119`).

e) **Números sem `tabular-nums`:** `marketing pages/index.vue:106,110,114,121` (tiles "Números de hoje" pulam de largura ao atualizar) · `pos pages/session/index.vue:551` (estorno) · `PosPaymentResult.vue:65,73` (comprovante) · `purchase pages/index.vue:678,1391,1554` · `production FormulaLens.vue:115`.

f) **Raios avulsos** (a regra `:180-182` proíbe `rounded-lg/xl/2xl`): `rounded-lg` 88× em production (`reports.vue` 17, `recipes/new.vue` 9, `recipes/[ref]/edit.vue` 9, `mise-en-place.vue` 8), 25× no PDV (`session/index.vue` 11, `closing.vue` 9), 18× no kit (`OperatorIdentify.vue` 5, `NotificationBell.vue` 5, `OperatorPinChange.vue` 4; `FilterBar.vue:118` e `NotificationBell.vue:60` em `rounded-xl`); `rounded-xl` 19× em marketing e 10× em orders; `OperatorLogin.vue:37` e `OperatorLock.vue:107` `rounded-xl`; `display.vue:131` `rounded-2xl`. Production e marketing têm dois raios de card na mesma tela.

g) **`leading-*` avulsos:** 70 usos, concentrados em kds (23, kiosk — defensável) e pos (28: `h2 … text-lg font-semibold leading-tight tracking-tight` ×8 em títulos que a escala define sem `leading`/`tracking`).

h) **Opacidades baixas:** `text-muted-foreground/30` em `kds KdsTicketCard.vue:240`/`KdsTicketModal.vue:203` (o item que a cozinha ainda precisa fazer é o mais apagado — inversão da prioridade) · `orders pages/catalog.vue:661` · `pos PosDrawerLockDialog.vue:99` `/25` num botão de 44px, quase invisível até hover · `/40-60` ×10 em orders catalog/feeds.

**O que mais importa (§4)**
1. 90+ `text-amber-* dark:text-amber-*` no lugar de `text-warning`: três âmbares diferentes, e mudar a cor de atenção exige tocar 130 linhas em 6 apps.
2. `text-white` sobre `bg-destructive`: o botão de cancelar/excluir é o que menos pode ficar ilegível no dark.
3. Título de tela em 5 receitas: quem troca de app (hub → orders → production) vê hierarquias diferentes para o mesmo nível.
4. Números que mudam sem `tabular-nums`: layout pula a cada atualização por SSE.
5. `rounded-lg` ×88 em production e ×25 no PDV contra a regra escrita no próprio `tailwind.css`.

---

## 5. Ordem de ataque

1. **`UiNativeSelect` (e a receita de campo) no `operator-kit`, autocontido.** 47 selects em 6 receitas; a regra do chevron centraliza o ícone, mas altura/borda/foco continuam do call site. Sequência de baixo risco: bi (8), purchase (8), production `pages/recipes/**` + `reports.vue` (12) → orders/pos/marketing quando o Codex fechar.
2. **Decidir o foco uma vez e aplicar nos primitivos:** `UiButton` (3px/50), `UiInput` (2px/20), `UiTextarea` (3px/50), chips (2px/40) e ~80 `outline-none focus:ring-1` nativos. Button/Input/Textarea são idênticos nos 5 apps: 3 arquivos × 5 cópias — ou × 1 se forem para o kit.
3. **Campo nativo h-9 → h-11** (ou rebaixar a escala e o `UiInput` para h-9; decidir). O tablet de produção é toque.
4. **`text-warning`/`text-destructive-foreground` no lugar de `amber-*`/`orange-*`/`text-white`** — 130 linhas, zero risco funcional, contraste real no dark.
5. **`OperatorLogin.vue` para o kit** (7 cópias, 2 inline) e **`Sonner` de purchase como canônico**.

## 6. Risco de merge com o Codex (medido em `git worktree list` + `diff --stat main...`)

- `codex/pdv-execution-20260910-a1`: `PosCartPanel.vue` (+1050), `pages/index.vue`, `pages/session/index.vue`, `usePosSale.ts`. → `PosCartPanel.vue:1095` e `session/index.vue:602` em zona de conflito.
- `codex/orders-operational-excellence-20260910`: `pages/[ref].vue`, `catalog.vue`, `feeds.vue`, `index.vue`, `OrderCard.vue`. → os selects/inputs sem altura de `pages/index.vue:654,702` e `[ref].vue:541-596` colidem. (O `bg-none` em `catalog.vue:692` é uma palavra numa linha; conflito, se houver, é trivial.)
- `codex/production-*`: WIP em `ProductionLabelPrintDialog.vue`, `WeighingLabels.vue`; branch antiga alveja `ProductionStageGrid.vue`, `QcCloseScreen.vue`, `ShortageDialog.vue`.
- `codex/marketing-irrepressible-excellence-20260908` (+89 commits): reescreve `tailwind.css`, `CampaignForm.vue`, `OperatorLogin.vue`, vários `Ui/*`. → **marketing congelado para padronização** até fechar.
- Sem risco: bi, hub, kds, purchase, e production fora dos arquivos listados (`pages/recipes/**`, `pages/reports.vue` — 12 dos 18 selects).
