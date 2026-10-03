# Fontes das prévias da SUITE-UX-V2 (v3, aprovada no geral em 03/10/2026)

HTML estático + Tailwind v4 compilado com os tokens reais do `operator-kit`, renderizado em PNG
pelo Playwright. É o ponto de retorno pedido pelo dono; a tag `suite-ux-proposta-v3` marca o
commit.

Como regerar (de dentro desta pasta, com `surfaces/pos-nuxt/node_modules` instalado):

1. `node getfonts.mjs` baixa Instrument Sans e Fira Code para `fonts/` (o build lê `fonts/fonts.local.css`).
2. `node build.mjs <nome>` gera `out/<nome>.png` (limpa) e `out/<nome>.annotated.png` (pinos e legenda).
   Sem nome, gera todas. Arquivos `_*.html` são partials (`{{> nome chave="valor"}}`); `<i data-i="icone">`
   vira o SVG do Lucide.
3. Telas geradas por script: `node gen-pos3.mjs`, `python3 gen-purchase3.py`, `node gen-bi-sales3.mjs`.

⚠️ `build.mjs` aponta para caminhos absolutos do ambiente onde as prévias foram feitas
(`ROOT`, `NM`); ajuste-os para o seu checkout. `SPEC.md` e `SPEC3.md` são as especificações que
guiaram cada rodada. Arquivos sem sufixo `3` são da v2; os com `3` são da v3.
