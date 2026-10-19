# Codex — sessão Marketing / marketing-nuxt (2026-09-10)

## Contexto comum (leia primeiro)

Entre 10/09 22h e 23h40 entraram no `main` os PRs #591, #592, #593, #594 e #596 (Claude). **Rebaseie sua branch sobre o `main` antes de continuar.** Arquivos tocados por eles: `pos-nuxt/app/components/PosPaymentWorkspace.vue`, `pos-nuxt/app/presentation/receiptContact.ts`, `pos-nuxt/app/app.vue` (agora só escolhe entre `PosOperatorShell` e `PosCustomerDisplayShell`, por `route.name`), `pos-nuxt/app/pages/display.vue`, `pos-nuxt/app/presentation/customerDisplay.ts`, `pos-nuxt/app/types/customerDisplay.ts`, `pos-nuxt/tests/support/paymentWorkspaceProps.ts`, `operator-kit/app/assets/css/operator-theme.css` (regra única do `<select>` nativo: `appearance: none` + chevron + `padding-inline-end: 2.25rem !important`; quem não quer o chevron usa `bg-none`), `orders-nuxt/app/pages/catalog.vue` (uma palavra: `bg-none`).

Relatório de padronização visual: `docs/reports/SURFACES-CONTROLS-AUDIT-2026-09-10.md` (no `main`). É diagnóstico com arquivo:linha; nada nele foi aplicado além do chevron.

**Regra da triagem de design (dada pelo Pablo):** vários controles customizados são propositais. Para cada achado, classificar ANTES de tocar em arquivo:
- **Proposital** — o desvio tem razão (kiosk, impressão, painel Solari, tecla, barra invertida). Fica como está e ganha um comentário de UMA linha no call site dizendo por quê — é o que impede a próxima varredura de "corrigir" de novo.
- **Acidental** — cópia de receita vizinha sem razão. Migra para o primitivo (`UiButton`/`UiInput`/`UiTextarea`) ou para a receita canônica do app.
- **Decisão do dono** — gosto que muda o sistema inteiro (altura do campo `h-9` × `h-11`; qual das quatro receitas de foco; `bg-card` × `bg-background` no campo). NÃO decidir sozinho: lista curta com prós/contras e recomendação, e parar para o Pablo escolher.

**Não fazer:** rename em massa cruzando apps num PR só; criar `Ui/` novo copiado (se serve a mais de um app, nasce no `operator-kit`); "corrigir" o que o relatório já refutou (hex do Solari, branco de QR/recibo, `text-[11px]` de impressão, `text-muted-foreground` sobre `bg-muted`, `border` × `border-border`).

---

## 1. Marketing está CONGELADO para padronização até a sua branch entrar

`codex/marketing-irrepressible-excellence-20260908` tem +89 commits e reescreve `marketing-nuxt/app/assets/css/tailwind.css`, `CampaignForm.vue` (+848), `AnnouncementCard.vue`, `OperatorLogin.vue` e vários `Ui/*`. Nada do relatório deve ser aplicado em marketing antes do merge dela. Ordem: fechar a branch → rebase → só então a triagem abaixo.

## 2. Ao fechar a branch, conferir que ela não diverge do compartilhado

- `tailwind.css` de marketing tem que continuar importando `operator-theme.css` do kit no topo (é de lá que vem a regra do `<select>` do #594 e os tokens). Se a branch reescreveu o arquivo, confira o `@import` e o bloco "ESCALA DE DESIGN" (`:143-183`), idêntico nos 8 apps.
- `Ui/*` alterados na branch (`Ui/VerificationCodeInput.vue` novo, outros editados): hoje Button/Input/Dialog são idênticos em 5 apps por md5. Se marketing os alterou, ou a alteração vale para todos (vai para os outros 4 ou para o kit) ou marketing vira a primeira cópia divergente — dizer qual das duas, explicitamente, no PR.
- `OperatorLogin.vue` editado na branch: há proposta de levá-lo para o kit (sessão Produção, item transversal 2). Coordenar: a versão que for para o kit deve ser a de marketing se ela é a mais nova.

## 3. Triagem de design no marketing-nuxt (depois do merge)

- Selects: `CampaignForm.vue:191,204,238`, `AnnouncementTemplateForm.vue:122` → `UiNativeSelect` do kit quando existir.
- 32 inputs em 13 receitas (`h-9 w-full … px-3 … focus:ring-1` ×8; checkbox `size-4 rounded border-border` ×10; `h-8 w-20` ×2); textareas ×4 (`AnnouncementCard.vue:174`, `FireCampaignPanel.vue:157`, `AnnouncementTemplateForm.vue:95,148`) com `UiTextarea` disponível e não usado.
- Botões: 43, 29 receitas; `rounded-md border border-border px-3 py-2 … hover:bg-muted` ×5 é o "outline" da casa aqui (nos outros apps é `hover:bg-accent`) → `UiButton variant="outline"`; `disabled:opacity-40` ×4.
- Títulos: `pages/index.vue:48`, `campaigns.vue:75`, `history.vue:30` em `text-xl font-bold` × `templates.vue:60`, `platforms.vue:67` em `text-xl font-semibold` — dois pesos para o mesmo h1 no mesmo app; a escala diz `text-lg font-semibold`.
- Rótulos: `mb-1 block text-sm font-medium` ×12 e `text-xs font-medium` ×4 no mesmo app — escolher a escala (`text-xs font-medium text-muted-foreground`).
- `pages/index.vue:106,110,114,121`: tiles "Números de hoje" em `text-2xl font-bold` SEM `tabular-nums` — os números pulam de largura a cada atualização (`FireCampaignPanel.vue:329` já tem).
- `rounded-xl` ×19 (cards de lista: `pages/index.vue:201`, `campaigns.vue:130`, `AnnouncementCard.vue:115`) contra a regra do `tailwind.css`; dois raios na mesma tela.
- `text-amber-*` ×17 (`platforms.vue:58` etc.) → `text-warning`.
