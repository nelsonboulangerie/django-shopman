# PDV: prévia A (atual) × C (compacto)

Somente prévia, 30/10/2026. A = `origin/main` intacto; C = A + `apply-compact.mjs`
(âncoras que falham alto). Reproduzir: `bash run.sh` (mock 38910, A 4301, C 4302) e,
com os três de pé, `node evidence.mjs <A>/surfaces/pos-nuxt .`. Medidas em `evidence.json`,
capturas em `shots/` (`<A|C>-<tela>-<viewport>.png`, exercícios `*-ex-*`).

Simulador: `prepare-mock.mjs` + `mock-extension.mjs` da prévia anterior
(`origin/codex/shopman-ux-product-review`, `docs/previews/navigation-2026-10-29/native`) +
`mock-patch.mjs` (Avisos fictícios e consulta de cliente). `PosSettingsTabs.vue` é cópia
literal da mesma prévia (abas roláveis).

## Medidas a 320×568 (topo do 1º conteúdo útil, px)

| Tela | A | C |
|---|---|---|
| Encomendas (1º cartão) | 271 | 115 |
| Encomendas com recorte "A receber" | 320 | 168 |
| Encomendas com busca "Ana" | 206 | 156 |
| Detalhe da encomenda (painel do Balcão) | 128 | 75 |
| Caixa (título "Caixa") | 132 | 75 |
| Ajustes › Impressoras (1º cartão) | 129 | 116 |
| Ajustes › Salão | 178 | 100 |
| Comandas | 77 | 69 |
| Venda (1º produto) / área útil da grade até a barra da comanda | 250 / 118 | 242 / 126 |
| Checkout | 136 | 112 |

Sem rolagem horizontal em nenhum viewport. Alvos do cabeçalho compacto todos ≥ 44 px.
Desktop 1440×900: idêntico (mesmo hash da captura de Encomendas; o compacto é `md:hidden`).

## Preservado
Barra da venda (`PosTabHeader` no `#below`), folha da comanda, checkout, `OperatorActionBar`,
avisos da tela (`alerts`), `OfflineBanner`, a barra inferior com "Mais" (gaveta), desktop.
"Não salvo" e "Pix aguardando" ficam na linha (na identidade), nunca no ⋮.

## Melhorado
- Encomendas: de até 6 faixas para 1 linha; período, recortes e painel no Filtros, com o
  filtro ativo nomeado na faixa ("Pagamento: A receber. 3 encomendas na tela." + Limpar) e
  no nome do botão. "Nova encomenda" vira a 2ª ação da barra de baixo que já existia
  ("Nova" | "Ler código") e o 1º item do ⋮.
- Detalhe: voltar na linha, identidade "Encomenda / NB-1042" em duas linhas (não corta);
  o "Voltar" do conteúdo some só no celular.
- Caixa: a toolbar só de texto "Caixa 1 · Ana" vira o topo das Opções.
- Ajustes: sem título duplicado; abas roláveis com a aba ativa à vista.
- Sem conexão: o chip do selo mostra × além da faixa (no A o indicador some offline).

## Precisa de decisão
1. A linha "Hoje: 9 para entregar, A receber R$ 228,00" saiu da tela de Encomendas (vai ao
   topo do ⋮ e do painel Filtros). É leitura de caixa; talvez mereça ficar.
2. Na Venda, o selo da Central e o chip de conexão dão lugar ao voltar; "Últimas vendas"
   (ícone fixo no A) cai no ⋮. Ganho na Venda é só 8 px: o aperto real a 320×568 é a barra
   da comanda (135 px) + barra inferior (64 px), não o cabeçalho.
3. O painel completo de filtros (`OperatorFilterPanel`) abre um segundo painel de dentro do
   Filtros (ícone sem rótulo ao lado de "Recortes").
4. "Limpar" volta ao dia de hoje (tira busca, recortes e período).
5. Fim do dia e Relatório (corredores) ficaram como no A.

## Riscos a 320 px / pouca altura
Título da identidade trunca quando "Não salvo" e Pix aparecem juntos (o título vira só
leitor de tela). A ação "Entregar" da barra de baixo do detalhe aparece só com ícone a
320 px (já no A).

## O mock não cobre
Selo "Não salvo" e "Pix aguardando" não foram provocados em runtime (a falha programada
caiu em `sale/review`); checkout no desktop não abriu pelo script; SSE real (só o tom
"A cada 60 s"), impressão, gaveta, câmera, fiscal, troca de operador/PIN. Nada disso é
equivalência funcional.
