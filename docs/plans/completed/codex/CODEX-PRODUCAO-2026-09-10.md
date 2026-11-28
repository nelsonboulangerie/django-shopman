# Codex — sessão Produção / production-nuxt + itens transversais do kit (2026-09-10)

## Contexto comum (leia primeiro)

Entre 10/09 22h e 23h40 entraram no `main` os PRs #591, #592, #593, #594 e #596 (Claude). **Rebaseie sua branch sobre o `main` antes de continuar.** Arquivos tocados por eles: `pos-nuxt/app/components/PosPaymentWorkspace.vue`, `pos-nuxt/app/presentation/receiptContact.ts`, `pos-nuxt/app/app.vue` (agora só escolhe entre `PosOperatorShell` e `PosCustomerDisplayShell`, por `route.name`), `pos-nuxt/app/pages/display.vue`, `pos-nuxt/app/presentation/customerDisplay.ts`, `pos-nuxt/app/types/customerDisplay.ts`, `pos-nuxt/tests/support/paymentWorkspaceProps.ts`, `operator-kit/app/assets/css/operator-theme.css` (regra única do `<select>` nativo: `appearance: none` + chevron + `padding-inline-end: 2.25rem !important`; quem não quer o chevron usa `bg-none`), `orders-nuxt/app/pages/catalog.vue` (uma palavra: `bg-none`).

Relatório de padronização visual: `docs/reports/SURFACES-CONTROLS-AUDIT-2026-09-10.md` (no `main`). É diagnóstico com arquivo:linha; nada nele foi aplicado além do chevron.

**Regra da triagem de design (dada pelo Pablo):** vários controles customizados são propositais. Para cada achado, classificar ANTES de tocar em arquivo:
- **Proposital** — o desvio tem razão (kiosk, impressão, painel Solari, tecla, barra invertida). Fica como está e ganha um comentário de UMA linha no call site dizendo por quê — é o que impede a próxima varredura de "corrigir" de novo.
- **Acidental** — cópia de receita vizinha sem razão. Migra para o primitivo (`UiButton`/`UiInput`/`UiTextarea`) ou para a receita canônica do app.
- **Decisão do dono** — gosto que muda o sistema inteiro (altura do campo `h-9` × `h-11`; qual das quatro receitas de foco; `bg-card` × `bg-background` no campo). NÃO decidir sozinho: lista curta com prós/contras e recomendação, e parar para o Pablo escolher.

**Não fazer:** rename em massa cruzando apps num PR só; criar `Ui/` novo copiado (se serve a mais de um app, nasce no `operator-kit`); "corrigir" o que o relatório já refutou (hex do Solari, branco de QR/recibo, `text-[11px]` de impressão, `text-muted-foreground` sobre `bg-muted`, `border` × `border-border`).

---

## 1. Os botões customizados são propositais — então documente-os

O Pablo disse: "alguns botões customizados lá são absolutamente propositais", e a Produção é onde eles estão (126 `<button>` crus, 75 receitas; `Ui/Button.vue` idêntico ao do PDV parado no diretório). A tarefa NÃO é migrar tudo para `UiButton`. É:
1. Listar os botões crus por receita (o relatório §1d dá as contagens: `rounded-md px-2.5 py-1.5 text-sm font-medium transition` ×10, `… px-3 py-2 … hover:bg-accent` ×9, `px-3 py-1.5` ×8, o resto avulso).
2. Para cada família: **proposital** (tecla de kiosk, tile do quadro, chip de etapa, toque grande no tablet) → fica, e ganha um comentário de uma linha no call site com a razão (ex.: "toque de 56px para mão enfarinhada; não é o UiButton de propósito"). **Acidental** (cópia de vizinho) → `UiButton` com o `size`/`variant` certo.
3. Entregar ao Pablo a lista das famílias propositais em uma tabela curta (receita · onde · por quê) — é a decisão dele confirmar.

## 2. Selects e campos (aqui é acidental na maior parte)

- 18 selects, 17 sem foco: `pages/reports.vue:310,326`; `recipes/new.vue:355,370,403,420,478,491`; `recipes/compare.vue:76`; `recipes/[ref]/index.vue:499`; `recipes/[ref]/edit.vue:379,387,390,458,464,514,544` (`selectClass` em `:277` — e `inputClass` em `:276` TEM foco: input e select lado a lado com foco diferente).
- `ProductionStageGrid.vue:613`: select com `text-muted-foreground` — o valor escolhido parece placeholder; "escolhi" e "não escolhi" têm a mesma cara. Acidental.
- Textareas sem `text-sm` e sem foco: `ShortageDialog.vue:107`, `QcCloseScreen.vue:750`.
- 33 inputs em 18 receitas com `Ui/Input.vue` disponível.
- ⚠️ `ProductionStageGrid.vue`, `QcCloseScreen.vue`, `ShortageDialog.vue`, `ProductionLabelPrintDialog.vue`, `WeighingLabels.vue` estão em branches/WIP suas — sequencie: `pages/recipes/**` e `pages/reports.vue` primeiro (12 dos 18 selects, sem conflito), o resto quando fechar.

## 3. Cores e raios

- `text-amber-* dark:text-amber-*` ×44 → `text-warning`; `text-orange-*` ×7 → `text-destructive`; `text-white` sobre `bg-destructive` em `ProductionStageGrid.vue:1185` e `AlertsBell.vue:28,62` → `text-destructive-foreground` (no dark hoje ~2.6:1).
- `rounded-lg` ×88 (`reports.vue` 17, `recipes/new.vue` 9, `recipes/[ref]/edit.vue` 9, `mise-en-place.vue` 8) contra a regra do `tailwind.css`; há dois raios de card na mesma tela.
- Título `h2 text-base font-bold` (`reports.vue:120,258,565`, `recipes/[ref]/index.vue:318`, `recipes/new.vue:332`) — uma das cinco receitas de título do sistema.
- `FormulaLens.vue:115` sem `tabular-nums`.
- **Refutado, NÃO tocar:** hex do painel Solari (`pages/board.vue:316-323`, `SplitFlap.vue:140,160`), branco da etiqueta (`ProductionLabelPrintDialog.vue:293`), `text-[0.6rem]` de `WeighingLabels.vue`.

## 4. Itens transversais do kit — sugestão: esta sessão é a dona (tem mais call sites); o Pablo confirma

1. **`UiNativeSelect` no `operator-kit`**, autocontido (um `<select>` + classe canônica de altura/borda/foco), SEM depender de `Ui*` do app hospedeiro. O kit já tem essa dependência invertida em `OperatorIdentify.vue:182`, `OperatorStationSetup.vue:66,70`, `OperatorManagerAuth.vue:95-109` — é dívida, não modelo (em hub/purchase esses componentes quebrariam em runtime). Migrar os 47 selects começando por bi (8), purchase (8) e production/recipes+reports (12).
2. **`OperatorLogin.vue` para o kit** — 7 cópias (5 idênticas em bi/kds/marketing/orders/production, variante em purchase, inline em `hub/app.vue:75-95` e `pos/app.vue`).
3. **`Sonner.vue` de purchase como canônico** nos outros 6 apps (`rich-colors`, tokens success/error/warning, `top-center`): hoje erro e sucesso saem no mesmo cinza e o toast nasce atrás da barra inferior no celular.
4. **`hub-nuxt/app/assets/css/tailwind.css:230-253`** carrega CSS de impressão de recibo do PDV — apagar (o hub não imprime).
5. Só com a palavra do Pablo (caixa "decisão do dono"): altura do campo (`h-9` × `h-11`), receita única de foco nos primitivos (`UiButton` 3px/50 · `UiInput` 2px/20 · chips 2px/40 · ~80 `outline-none focus:ring-1`), fundo do campo (`bg-card` × `bg-background`). Preparar a lista com recomendação e parar.
