# Codex — sessão Gestor de Pedidos / orders-nuxt (2026-09-10)

## Contexto comum (leia primeiro)

Entre 10/09 22h e 23h40 entraram no `main` os PRs #591, #592, #593, #594 e #596 (Claude). **Rebaseie sua branch sobre o `main` antes de continuar.** Arquivos tocados por eles: `pos-nuxt/app/components/PosPaymentWorkspace.vue`, `pos-nuxt/app/presentation/receiptContact.ts`, `pos-nuxt/app/app.vue` (agora só escolhe entre `PosOperatorShell` e `PosCustomerDisplayShell`, por `route.name`), `pos-nuxt/app/pages/display.vue`, `pos-nuxt/app/presentation/customerDisplay.ts`, `pos-nuxt/app/types/customerDisplay.ts`, `pos-nuxt/tests/support/paymentWorkspaceProps.ts`, `operator-kit/app/assets/css/operator-theme.css` (regra única do `<select>` nativo: `appearance: none` + chevron + `padding-inline-end: 2.25rem !important`; quem não quer o chevron usa `bg-none`), `orders-nuxt/app/pages/catalog.vue` (uma palavra: `bg-none`).

Relatório de padronização visual: `docs/reports/SURFACES-CONTROLS-AUDIT-2026-09-10.md` (no `main`). É diagnóstico com arquivo:linha; nada nele foi aplicado além do chevron.

**Regra da triagem de design (dada pelo Pablo):** vários controles customizados são propositais. Para cada achado, classificar ANTES de tocar em arquivo:
- **Proposital** — o desvio tem razão (kiosk, impressão, painel Solari, tecla, barra invertida). Fica como está e ganha um comentário de UMA linha no call site dizendo por quê — é o que impede a próxima varredura de "corrigir" de novo.
- **Acidental** — cópia de receita vizinha sem razão. Migra para o primitivo (`UiButton`/`UiInput`/`UiTextarea`) ou para a receita canônica do app.
- **Decisão do dono** — gosto que muda o sistema inteiro (altura do campo `h-9` × `h-11`; qual das quatro receitas de foco; `bg-card` × `bg-background` no campo). NÃO decidir sozinho: lista curta com prós/contras e recomendação, e parar para o Pablo escolher.

**Não fazer:** rename em massa cruzando apps num PR só; criar `Ui/` novo copiado (se serve a mais de um app, nasce no `operator-kit`); "corrigir" o que o relatório já refutou (hex do Solari, branco de QR/recibo, `text-[11px]` de impressão, `text-muted-foreground` sobre `bg-muted`, `border` × `border-border`).

---

## 1. Rebase obrigatório

`orders-nuxt/app/pages/catalog.vue:692` recebeu `bg-none` no `main` (#594): o select da barra invertida de ação em lote não deve receber o chevron novo (escuro sobre barra escura). Sua branch `codex/orders-operational-excellence-20260910` toca `catalog.vue`; resolva mantendo o `bg-none`.

## 2. Triagem de design no orders-nuxt (do relatório)

Classificar pelas três caixas. Candidatos, com arquivo:linha:
- **Controles sem altura** (`p-2.5` no lugar da escala): select `OrderReasonDialog.vue:80` e `pages/index.vue:654`; inputs `pages/index.vue:702,739,750`, `pages/[ref].vue:541,551,596`; textareas `OrderReasonDialog.vue:106`, `pages/index.vue:665`, `pages/[ref].vue:468`. No diálogo de motivo de cancelamento o select fica mais baixo que o `UiButton` ao lado e "dança" com a fonte do sistema. Acidental.
- `CatalogProductPanel.vue:326` (`fieldClass` h-9/px-2.5, ×30) × `Ui/Input.vue` (h-11/bg-card): o mesmo app tem dois campos canônicos. Decisão do dono sobre a altura; o resto é acidental.
- **Tokens no lugar de paleta:** `text-amber-*` ×22 (`OrderCard.vue:116`, `pages/catalog.vue:468,475,546`) → `text-warning`; `text-destructive dark:text-orange-300` (`OrderCourierPanel.vue:55,147,148`, `OrderCard.vue:62,247`, `pages/index.vue:453,598`, `pages/[ref].vue:208`) → `text-destructive` puro; `text-success dark:text-lime-300` (`OrderCourierPanel.vue:67`, `catalog.vue:614`) → `text-success`; `text-white` sobre `bg-destructive` em `pages/index.vue:678` → `text-destructive-foreground` (no dark hoje fica ~2.6:1, no botão de cancelar).
- `text-muted-foreground/30…60` ×12 em `catalog.vue:661` e `feeds.vue` — contraste; decidir se a hierarquia precisa de opacidade ou de `text-muted-foreground` pleno.
- `rounded-xl` ×10 (`catalog.vue:355,365,668,685`, `feeds.vue:96`) contra a regra do `tailwind.css`.
- Cabeçalho de seção `text-sm font-bold uppercase tracking-wide` ×6 — uma das cinco receitas de título do sistema; escolher uma (a escala diz `text-lg font-semibold` para título de tela; para seção, propor).
- Botões crus: 89, 57 receitas; `rounded-md border px-3 py-2 … hover:bg-accent` ×7 é o "outline" da casa → `UiButton variant="outline"`. Triar; o que for proposital ganha comentário.
- `Ui/SearchInput.vue`, `FilterChip`, `IconButton`, `Toolbar` existem só em orders e marketing (idênticos): se Produção/KDS ganharem busca com lupa, é para o kit, não para uma terceira cópia.

## 3. Sequência

Primeiro fechar a branch atual (ela toca `pages/[ref].vue`, `catalog.vue`, `feeds.vue`, `index.vue`, `OrderCard.vue`, exatamente onde os achados estão). Depois, um PR por caixa: (a) tokens no lugar de paleta (zero risco funcional), (b) controles sem altura, (c) botões → `UiButton`. Nada de PR único cruzando os três.
