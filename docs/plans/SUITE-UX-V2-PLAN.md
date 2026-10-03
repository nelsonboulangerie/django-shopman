# SUITE-UX-V2-PLAN: oito apps, um produto

**Proposta de 03/10/2026. Terceira rodada (v3), depois do retorno do dono na mesma data.**
Escopo decidido por ele: **só os apps de operador** (PDV, Cozinha, Gestor, Produção, Compras,
Marketing, B.I. e Shopman Apps). **A Loja e o Admin/Unfold ficam de fora.** Direção visual:
**evolução** do que existe (mesmos tokens, latão sobre papel Faubourg).

Regra que vale para o plano inteiro: **nenhuma funcionalidade regride.** Toda ação, filtro,
atalho, informação e estado que existe hoje continua existindo; a reforma muda o lugar e a
forma. O §7 diz como isso é garantido por mecanismo, não por cuidado.

Este plano **continua** o [SUITE-UX-PLAN](SUITE-UX-PLAN.md) (22/09/2026). O WP-UX-1 de lá está
entregue; os WP-UX-3, 4 e 7 estão em execução.

**Prévias** em [`suite-ux-v2/`](suite-ux-v2/): `comparar-*.jpg` (captura real "Hoje" × proposta,
desktop), `depois-*.annotated.jpg` (proposta com pinos e legenda), `depois-*-tablet.jpg` e
`depois-*-celular.jpg` (propostas por dispositivo) e `antes-*-celular.jpg`/`antes-*-tablet.jpg`
(como os apps ficam hoje nesses dispositivos). As propostas usam os tokens reais do
`operator-kit` (`operator-theme.css`), Instrument Sans e Lucide. ⚠️ Fotos de produto e ícones PWA
aparecem quebrados nas capturas reais porque o ambiente não tinha as imagens do catálogo.

### O que o dono já decidiu (03/10)

| ponto | decisão |
|---|---|
| Anatomia e padrões (v2) | gostou no geral; preocupação: o PDV perdia altura na lista de itens → **v3 resolve (§2.4)** |
| Rail como trocador de apps | o trocador é bom, mas não pode tomar o lugar das seções; as seções no rail economizam altura → **v3: seções no rail, trocador vira um botão (§2.1)** |
| Busca da suíte (Ctrl K) | dois campos confundem; um campo só e o operador escolhe o alcance → **v3: busca única (§2.2)** |
| Um sino só | **aprovado** |
| "Ao vivo" igual em todo app | **aprovado**, mas ocupava espaço demais → **v3: ponto + hora (§2.3)** |
| Shopman Apps com estado | função aprovada; aparência anterior, mais limpa, era melhor → **v3: tiles limpos (§2.5)** |
| Ordem dos WPs | **aprovada**: kit primeiro, Gestor piloto, PDV por último |
| Dispositivos | "ajuste de breakpoint é o mínimo do mínimo"; cada dispositivo usado a fundo; apps de campo plenamente úteis no celular → **§3** |
| Navegação | "não há um padrão bem estabelecido em nenhum app" → **auditoria e modelo único no §4** |

---

## 1. O que a medição encontrou

Cinco varreduras (kit; PDV/Cozinha/Produção; Gestor/Hub/Compras; B.I./Marketing; navegação dos
oito apps) e capturas reais em desktop, tablet e celular.

| tema | hoje |
|---|---|
| Cópias de primitivas | 7 árvores `components/Ui/` (~270 arquivos); Dialog e Sheet com 3 variantes; o kit depende em silêncio da cópia do app hospedeiro |
| Botão | Gestor: 146 `<button>` à mão e 0 `UiButton`; Compras: 67; B.I.: botões de 36 px |
| Cabeçalho e navegação | 7 cabeçalhos; seção no rail em 4 apps, barra de seções em 3, abas próprias na Produção, 3 controles para as mesmas seções no Compras |
| Busca | 4 implementações; `type="search"` cru em 5 apps; B.I. e Hub sem busca |
| Controle segmentado | não existe peça: ~46 `aria-pressed` fazendo o papel, com 3 estilos de "ativo" |
| Overlays à mão | ~11 `fixed inset-0` sem trap de foco nem scroll-lock; "Close" em inglês em 3 apps |
| Estados | nenhuma peça de vazio, esqueleto ou campo no operador; ~114 "Nenhum…" literais |
| Status | 6 mapas de cor em 3 vocabulários; paleta crua do Tailwind |
| Sino | 4 implementações |
| Tablet e celular | o desktop espremido: abas cortadas, tabela estourando, barra do Gestor em 3 linhas antes do primeiro pedido |
| Recursos do dispositivo | só a câmera da NF (Compras), `capture` em upload, wake lock e giro no kit; nada de vibração, compartilhar, NFC, nem noção de teclado × toque, loja × fora |
| Navegação | ver §4.1: telas cheias sem saída, 4 jeitos de voltar só no Gestor, estado que se perde ao recarregar, metade dos apps sem endereço |

O inventário funcional de cada tela está no apêndice A.

---

## 2. A anatomia v3

**O operador aprende a suíte uma vez.** Toda tela é montada com as mesmas peças, na mesma
ordem; o que muda de um app para outro é o trabalho, não o jeito de fazê-lo.

![Gestor v3](suite-ux-v2/depois-gestor-pedidos.annotated.jpg)

```
┌───────┬──────────────────────────────────────────────────────────────────┐
│ selo  │ Título · ● 22:03 │ busca única (/ · Ctrl K) │ controles · ⋯ · AÇÃO │  cabeçalho único
│ (troca├──────────────────────────────────────────────────────────────────┤
│ de app)│ filtros em chips (só se a tela filtra)                          │
│───────├──────────────────────────────────────────────────────────────────┤
│ seções│                                                                  │
│ do app│ CONTEÚDO  cards · tabela · quadro · painel lateral               │
│ c/ nº │                                                                  │
│───────├──────────────────────────────────────────────────────────────────┤
│ Avisos│ RODAPÉ    barra de lote · ação fixa · MoreBelow                  │
│ Atalh.│                                                                  │
│ Bloq. │                                                                  │
└───────┴──────────────────────────────────────────────────────────────────┘
```

### 2.1 Rail: seções do app, trocador num botão

O rail (76 px) volta a ser **a navegação do app**: cada seção com ícone, nome, contagem, ponto de
atenção e a tecla (Alt 1…9). No topo, o **selo do app** abre o trocador com os oito apps e o
Shopman Apps: ocupa um botão, não uma faixa. No pé: **Avisos** (o sino único), Atalhos,
Bloquear e o operador. Sai a barra de seções do topo e sobra altura: o cabeçalho do Gestor vai
de ~205 px hoje (as barras quebram em 3 linhas a 1440 px) para **104 px**.

### 2.2 Uma busca só, uma tecla só

Um campo no cabeçalho, `/` ou Ctrl K. Ao digitar, **filtra a tela atual** (o que o operador quer
9 em 10 vezes) e abre um painel com o alcance em controle segmentado: **Esta tela · App ·
Toda a suíte** (Tab alterna). Resultados desta tela primeiro; logo abaixo, a suíte (cliente,
encomenda, perfil no B.I., insumo, tela), cada um com o selo do app de destino; e **ações**
("Abrir venda para Maria Santos"). Esc fecha e mantém o filtro. No celular, a mesma busca em tela
cheia, com a **câmera** para ler qualquer código (QR do pedido, EAN do insumo, chave da NF).

![Busca única](suite-ux-v2/depois-gestor-busca.annotated.jpg)

### 2.3 "Ao vivo" discreto

Um ponto verde e a hora da última leitura ao lado do título. Só cresce quando a leitura atrasa:
"Sem conexão. O que está na tela é de 21:58." + Atualizar.

### 2.4 PDV: a lista de itens ganha altura

A preocupação do dono era a v2, que encolhia a lista de itens para 275 px. A v3 faz o
contrário: **648 px no desktop**, contra 485 px hoje (cerca de 10 linhas visíveis contra 8), porque
o teclado numérico da tela **recolhe numa faixa de 44 px quando há teclado físico** (as teclas
continuam funcionando como hoje, e "Mostrar teclado" abre de volta). Seções e saúde do terminal
vão para o rail; o contexto da comanda (Balcão/Encomendas, #1007, Cliente F6, Recebimento F7,
Quando F8, PIX, Liberar) cabe numa barra única de 56 px. **No tablet**, sem teclado físico, o
teclado numérico fica visível e a lista mantém a altura de hoje (406 px × 405 px), com o total
dentro do botão Pagamento.

| | altura da lista de itens | linhas visíveis |
|---|---|---|
| desktop hoje | 485 px | ~8 |
| desktop v2 | 275 px | ~4 |
| **desktop v3** | **648 px** | **~10** |
| tablet hoje | 405 px | ~7 |
| **tablet v3** (teclado numérico visível) | **406 px** | **6, com a linha ativa aberta** |

![PDV v3](suite-ux-v2/depois-pdv-venda.annotated.jpg)

### 2.5 Shopman Apps limpo, com estado

Tiles brancos e calmos como antes: ícone na cor do app, nome, uma linha do que faz e **uma linha
de estado** discreta (âmbar só quando pede atenção); o tile inteiro é o link para o lugar exato.
"Precisa de você" vira uma lista fina de até 3 linhas, só quando há algo. Avisos e versão numa
linha de rodapé.

---

## 3. Cada dispositivo, a fundo (Omotenashi-first)

Retorno do dono em 03/10: *"Não serve apenas ajustes superficiais de breakpoints, media
queries, rearranjo de colunas/larguras. Isso é o mínimo do mínimo. Cada tipo de dispositivo
exige atenção para favorecer fortemente seu uso. O sistema precisa entender profundamente ONDE o
operador está e oferecê-lo o MÁXIMO em recursos."*

**Como está hoje** (capturas em `suite-ux-v2/antes-*-celular.jpg` e `antes-*-tablet.jpg`): no
celular e no tablet os apps são o desktop espremido. Abas cortadas na borda (Compras, Gestor), a
tabela de insumos estourando para o lado, a barra do Gestor quebrando em três linhas antes do
primeiro pedido. Dos recursos do dispositivo, o código usa só a câmera da NF no Compras (zxing),
upload com `capture` em 4 apps, wake lock e trava de giro no kit. Nenhum app usa vibração,
compartilhar, NFC, nem sabe se o operador está com teclado, com o dedo, na loja ou fora.

### 3.1 O motor de contexto: `useOperatorContext()`

Um composable do kit que toda tela consulta. Ele responde **onde o operador está** e cada tela
declara o que muda:

| sinal | como se sabe | o que muda na tela |
|---|---|---|
| **Classe de dispositivo** | ponteiro fino/grosso, `hover`, tamanho, giro | anatomia: rail + cabeçalho (desktop), rail compacto e painéis divididos (tablet), barra de cima + barra de seções embaixo (celular) |
| **Modo de entrada do momento** | último evento: tecla, toque ou caneta | com teclado: teclas impressas, foco visível, teclado numérico da tela recolhido; com toque: teclas somem, alvos crescem, teclado numérico aparece. Plugar um teclado no tablet traz as teclas de volta |
| **Estação × dispositivo pessoal** | estação provisionada (já existe no PDV e na Cozinha) | estação: tela sempre acesa, giro travado, bloqueio por PIN/crachá; pessoal: login próprio, push, modo "no bolso" |
| **Na loja × fora** | rede da loja ou geolocalização com consentimento | fora da loja, o Gestor abre em "resumo e decisões"; o PDV no celular só consulta |
| **Conexão** | `useConnectivity` (já existe) | ao vivo, desatualizado, sem conexão, com o mesmo texto em todo app |
| **Turno** | hora + agenda da loja | ex.: Produção abre em Planejamento antes do turno e em Expedição durante o forno |

### 3.2 Recursos do dispositivo, por app

| recurso | onde entra | substitui ou acelera |
|---|---|---|
| **Câmera** (código de barras, QR, chave de NF, EAN, etiqueta de lote, foto) | Compras (NF e EAN do insumo no recebimento), Produção (etiqueta do lote, foto da ficha), PDV no celular (QR da encomenda na retirada), busca única (ler qualquer código) | digitação da chave de 44 dígitos, busca por nome |
| **Vibração** | confirmação de ato no celular, alerta de pedido novo, forno tocando | o operador não precisa olhar a tela para saber que deu certo |
| **Push** (já existe) | pedido novo, anúncio para aprovar, forno, alerta de canal; toque abre o lugar exato | entrar no app para descobrir se precisava |
| **Tela acesa e giro** (já existem no kit) | Cozinha, Produção no suporte, Painel de retirada, Letreiro | a tela apagando no meio do serviço |
| **NFC do crachá** (Android) | desbloquear estação e assinar como gerente | digitar PIN com a mão suja de farinha |
| **Compartilhar** | comprovante, relatório do B.I., recorte da lista | baixar e anexar |
| **Leitor físico e teclado** (já há leitor de ticket no PDV) | PDV, Compras na doca, Expedição | — |
| **Localização** (só com consentimento, só onde muda algo) | Gestor "fora da loja"; nunca rastreio de pessoa | — |

### 3.3 Matriz app × dispositivo

O que cada app **é** em cada dispositivo. Não é a mesma tela encolhida:

| app | desktop (teclado) | tablet (toque, giro) | celular (polegar, câmera) |
|---|---|---|---|
| **PDV** | balcão completo, teclado primeiro, teclado numérico da tela recolhido | balcão de toque, teclado numérico visível, deslizar para remover | balcão de bolso: retirada de encomenda por QR, consulta, comanda rápida na fila |
| **Cozinha** | (raro) | estação de parede, tema escuro, alvos de 56 px | — |
| **Gestor** | escritório: quadro, tabela, catálogo | gestão no salão: quadro em abas, detalhe em painel | dono em movimento: push, aceitar/recusar, resumo fora da loja |
| **Produção** | gestor: plano, relatórios, receitas | chão: dia de produção em lista + painel com teclado numérico | no bolso: timers que vibram, finalizar lote, ler etiqueta |
| **Compras** | base, custos, fornecedores | conferência: lista + linha da nota lado a lado | doca: escanear NF, conferir item com deslizar, confirmar entrada |
| **Marketing** | compor campanhas | — | aprovar anúncio vindo do push |
| **B.I.** | análise completa | leitura | olhada: números, um gráfico, compartilhar |
| **Shopman Apps** | painel | painel | lista de apps + busca única com câmera |

---

## 4. Navegação: um modelo único

Pedido do dono: *"Não há um padrão bem estabelecido, em basicamente nenhuma das Apps."* A
auditoria confirmou, com arquivo e linha.

### 4.1 O que a auditoria encontrou

| tema | hoje |
|---|---|
| **Seções** | rail como seção no PDV, Cozinha, Produção e Compras; barra de seções no Gestor, B.I. e Marketing; abas próprias + rail na Produção (e o "Painel" do rail é a mesma página da aba "Produção"); Compras com **três** controles para as mesmas 4 seções (rail, barra e barra de baixo no celular). O próprio kit diz que seção não deveria morar no rail (`OperatorRail.vue:11-13`) |
| **Telas cheias sem saída** | o Painel de retirada da Cozinha abre em tela cheia sem rail, sem link, sem caminho de volta, num PWA `fullscreen` (`kds-nuxt/app/pages/[ref].vue:382`); o Letreiro da Produção, igual |
| **Voltar** | o Gestor sozinho tem 4 jeitos: reconstrói o filtro (pedido), `router.back()` (cliente; vindo de um aviso, sai do app), link fixo (Unificações, Canais); PDV mistura voltar inteligente (encomenda) e fixo (relatório) |
| **Estado fora da URL** | período do B.I. só em memória; todo o Compras em `useState` (seção, aba, seleção, rascunho); data e busca da Produção só lidas, nunca escritas; coleção e produto do Catálogo; fila Expedição/Qualidade |
| **Dado perdido ao navegar** | Finalizar lote (QC) com rail e abas clicáveis por cima e sem guarda; editor de receita e nota do Compras sem guarda; o Gestor guarda com `window.confirm` |
| **Marketing** | "Abrir revisão" leva a `/`, que redireciona para a mesma tela; "Voltar ao painel" cai em "Hoje"; `/platforms` e `/v2?area=platforms` são duas telas para uma seção; truque `?experience=v2`; "Marketing V2" no título |
| **Entre apps** | só 4 dos 8 apps têm endereço (Hub, Gestor, PDV, Produção); nenhum link leva origem nem volta; Cozinha, Gestor, Produção e B.I. não linkam para nenhum app irmão; frases "verifique no Gestor" sem link |
| **Teclado** | navegação por seção só na Produção (Alt+1…4); a prop `shortcut` do `OperatorAppBar` não é usada por ninguém |
| **Títulos** | faltam na venda do PDV, na fila e no pedido do Gestor, em toda a Cozinha, no B.I. e no Compras; nenhum app tem "onde estou" além da aba |
| **Atalhos de PWA** | o "Hoje" do Gestor (`/?sort=commitment`) é ignorado em silêncio; o `?view=` do Compras é lido uma vez e envelhece |
| **Peças** | `RailItem` sem `to`: cada app reescreve `navigateTo` e o teste de ativo; restauração de rolagem e foco ao voltar só no quadro do Gestor |

### 4.2 O modelo: cinco níveis

![Navegação](suite-ux-v2/depois-navegacao.jpg)

| nível | o que é | desktop | tablet | celular | voltar | endereço |
|---|---|---|---|---|---|---|
| **0 · Suíte** | trocar de app, achar qualquer coisa | selo no rail, busca única, aviso | selo, busca | selo na barra de cima, busca em tela cheia com câmera, push | — | host do app |
| **1 · Seção** | Pedidos, Base, Expedição | item do rail com nome, contagem e Alt 1…9 | rail compacto (deitado), barra embaixo (em pé) | barra embaixo, até 4 + Mais | — | caminho (`/base`) |
| **2 · Recorte** | Insumos/Fornecedores, Expedição/Qualidade | controle segmentado, `[` `]` | segmentado, deslizar | abas roláveis, deslizar | — | caminho ou query (`/base/insumos`, `?fila=qualidade`) |
| **3 · Item** | pedido, produto, lote, insumo | painel lateral se a lista precisa ficar à vista; página se é área de trabalho | deitado: lado a lado; em pé: painel de baixo | tela cheia com ‹ | **"‹ Pai"** com filtro, rolagem e foco restaurados; Esc | caminho ou `?item=` |
| **4 · Fluxo** | pagar, finalizar lote, conferir NF | tela de foco (esconde rail e seções) | tela de foco com teclado numérico | tela cheia, "Concluir" fixo, vibra | sair com dado → diálogo do kit | etapa na query |

![Detalhe com volta](suite-ux-v2/depois-gestor-detalhe.annotated.jpg)

### 4.3 As regras

1. **Todo lugar tem endereço.** Seção, recorte, filtro, período, item aberto e etapa vão para a
   URL. Recarregar, compartilhar ou abrir pelo aviso cai no mesmo lugar.
2. **Voltar é subir, com contexto.** Um `OperatorUpButton` ("‹ Pedidos") e um `useListContext`
   no kit, generalizando o que o quadro do Gestor já faz. Chegou por link direto? Sobe para a
   lista padrão. Nunca `router.back()` às cegas.
3. **Toda tela cheia tem saída declarada.** Painel de retirada, Letreiro e Tela do cliente abrem em
   janela própria; na estação, toque longo no canto (ou Esc) pede o PIN e volta à origem.
4. **Entre apps, com bilhete de volta.** `appUrl(app, caminho, { de })` no kit para os oito apps;
   o destino mostra "‹ Voltar ao PDV · comanda #1007". Frase que manda ir a outro app vira link.
5. **Um nome por lugar.** O mesmo nome no rail, no título, na URL em inglês e no atalho de PWA.
6. **Guarda única** (`useUnsavedGuard`): diálogo do kit no lugar do `window.confirm`, cobrindo
   rota, recarga e fechar a janela.
7. **Título em toda tela**: "Página · App".

### 4.4 Mapa de endereços por app

URLs em inglês (convenção da casa); endereço antigo responde 301, como já foi feito em outros apps.

| app | seções (rail) | recortes e itens | muda |
|---|---|---|---|
| **PDV** | Comandas `/` · Encomendas `/preorders` · Caixa `/cash` · Tela do cliente (janela) | comanda `/tabs/1007`, pagamento `?step=payment`; encomenda `/preorders/:ref`; relatório e fechamento `/cash/report`, `/cash/closing` | `/session` vira `/cash`; venda ganha endereço |
| **Cozinha** | Estações `/` · estação `/:ref` (Preparo/Saída) · Painel de retirada (janela) | `?date=` | Painel ganha saída |
| **Gestor** | Pedidos `/` · Catálogo `/catalog` · Clientes `/customers` · Canais `/channels` | pedido `/:ref`; produto `?sku=&tab=` (escrito, não só lido); coleção `?collection=` | `/feeds` vira `/channels` |
| **Produção** | Planejamento `/plan` · Preparação `/mise-en-place` · Produção `/` · Expedição `/expedite` · Timers · Receitas · Relatórios · Letreiro (janela) | `?date=&q=` escritos; `?queue=quality`; Finalizar lote `/expedite/:lot/close` | some o "Painel" duplicado |
| **Compras** | Painel `/` · Comprar `/buy` · Receber `/receive` · Base `/base` | `/base/materials` · `/suppliers` · `/costs` · `/count`; nota em conferência `/receive/:draft` | sai do `useState` |
| **Marketing** | Hoje `/today` · Campanhas `/campaigns` · Ofertas `/offers` · Plataformas `/platforms` · Histórico `/history` | anúncio `/announcements/:id`; modelos `/campaigns/templates` | some `/v2?area=` e `?experience=v2` |
| **B.I.** | as 8 seções de hoje | `?period=28d&compare=previous&channel=` em todas; aprofundar leva ao pedido, produto ou insumo no app certo | período vai para a URL |

Trava `guardrails.navigation`: seção fora da URL, página sem título, `RailItem` sem `to`, link entre
apps sem origem e atalho de PWA que não resolve fazem o CI falhar.

---

## 5. Padrões por intenção (um jeito canônico para cada coisa)

| intenção | padrão único | peça | hoje |
|---|---|---|---|
| **Buscar** | um campo no cabeçalho, `/` ou Ctrl K; filtra a tela ao digitar; alcance Esta tela · App · Suíte; câmera no celular; termo na URL | `OperatorSearch` (evolui o `UiSearchInput`) | 4 implementações, 5 apps com `type="search"` cru, 2 apps sem busca |
| **Filtrar** | chips com contagem para os 3 a 6 recortes mais usados; "+ Filtro" para o resto; filtro aplicado vira chip removível e "Limpar filtros"; no celular, linha rolável + painel de baixo; tudo na URL | `UiFilterChip`, `FilterBar` | chips em 1 app; selects soltos; checkbox como filtro |
| **Recortar a lista** | controle segmentado no cabeçalho; no celular, abas roláveis com deslizar | `UiSegmentedControl` (nova) | 3 estilos de aba |
| **Trocar visão** | controle segmentado; preferência por dispositivo | `UiSegmentedControl` | popover no PDV, botão-ciclo na Cozinha, botões no Gestor |
| **Ordenar** | botão "↕ Critério ▾" com menu de rádio | `UiMenu` (nova) | menu à mão sem Esc |
| **Período** | seletor do kit; no cabeçalho quando vale para o app inteiro, na URL sempre | `OperatorDayPicker`, `OperatorPeriodPicker` | select nativo na Cozinha; B.I. fora da URL |
| **Ação primária** | uma por tela, último à direita do cabeçalho ou fixa no rodapé; no celular, no alcance do polegar | `UiButton` | ~86 estilos de botão |
| **Ação rara** | menu ⋯ com a mesma tecla de antes; destrutiva por último, em vermelho, com confirmação | `UiMenu` | espalhadas na barra (o Gestor tinha 10 botões nela) |
| **Ação em lote** | checkbox (desktop), seleção por toque longo (toque); barra flutuante com revisão quando muda preço ou publicação | `UiBulkBar` (nova) | só o Catálogo tem |
| **Ação rápida no item** | menu ⋯ (desktop), toque longo (tablet), deslizar o card (celular) | `UiMenu`, `UiSwipeActions` (nova) | botões soltos |
| **Confirmar** | título-pergunta, consequência, o verbo do ato no botão; desfazer quando é reversível; vibra no celular | `UiDialog`, `OperatorReasonDialog` | 5 jeitos, inclusive `window.confirm` |
| **Status** | pílula de tom: info, andamento, sucesso, alerta, erro, neutro; mapa único | `presentation/status.ts` | 6 mapas, 3 vocabulários |
| **Vazio · carregando · erro · desatualizado** | vazio que explica; esqueleto no formato do conteúdo; erro que diz o que fazer; desatualizado com a hora | `UiEmpty`, `UiSkeleton` (novas), `UiAlert` | literais, "Carregando…", 3 a 4 variantes por app |
| **Ao vivo** | ponto + hora ao lado do título | `OperatorLiveStatus` (nova) | faixa de texto, ponto solto, nada |
| **Avisos** | um sino no pé do rail (barra de cima no celular), abas Alertas e Avisos; push abre o lugar exato | `NotificationBell` | 4 sinos |
| **Atalhos** | tecla impressa em todo controle com atalho quando há teclado; `?` lista as da tela | `OperatorShortcutsHelp` (nova) | só PDV e Produção |
| **Campo · número de painel · tipografia** | `UiField`; `UiStatTile`; 6 papéis `op-*` | — | 8 dialetos de rótulo; 2 desenhos de KPI; 2.287 combinações à mão |

![Kit](suite-ux-v2/depois-kit.jpg)

---

## 6. As telas-chave, antes e depois

### 6.1 Desktop (hoje × v3)

**Gestor · Pedidos** · inventário A.1 · [anotada](suite-ux-v2/depois-gestor-pedidos.annotated.jpg)

![Gestor · Pedidos](suite-ux-v2/comparar-gestor-pedidos.jpg)

**Gestor · Catálogo** · inventário A.2 · [anotada](suite-ux-v2/depois-gestor-catalogo.annotated.jpg)

![Gestor · Catálogo](suite-ux-v2/comparar-gestor-catalogo.jpg)

**PDV · Venda** · inventário A.3 · [anotada](suite-ux-v2/depois-pdv-venda.annotated.jpg)

![PDV · Venda](suite-ux-v2/comparar-pdv-venda.jpg)

**Cozinha · Estação (tema escuro)** · inventário A.4 · [anotada](suite-ux-v2/depois-cozinha-estacao.annotated.jpg)

![Cozinha · Estação (tema escuro)](suite-ux-v2/comparar-cozinha-estacao.jpg)

**Produção · Produção do dia** · inventário A.5 · [anotada](suite-ux-v2/depois-producao-dia.annotated.jpg)

![Produção · Produção do dia](suite-ux-v2/comparar-producao-dia.jpg)

**Compras · Base › Insumos** · inventário A.6 · [anotada](suite-ux-v2/depois-compras-base.annotated.jpg)

![Compras · Base › Insumos](suite-ux-v2/comparar-compras-base.jpg)

**Marketing · Campanhas** · inventário A.7 · [anotada](suite-ux-v2/depois-marketing-campanhas.annotated.jpg)

![Marketing · Campanhas](suite-ux-v2/comparar-marketing-campanhas.jpg)

**B.I. · Vendas** · inventário A.8 · [anotada](suite-ux-v2/depois-bi-vendas.annotated.jpg)

![B.I. · Vendas](suite-ux-v2/comparar-bi-vendas.jpg)

**Shopman Apps** · inventário A.9 · [anotada](suite-ux-v2/depois-hub.annotated.jpg)

![Shopman Apps](suite-ux-v2/comparar-hub.jpg)

### 6.2 Tablet e celular hoje

O desktop espremido: abas cortadas, tabela estourando, barras quebrando em várias linhas.

![Celular hoje](suite-ux-v2/antes-celular.jpg)

![Tablet hoje](suite-ux-v2/antes-tablet.jpg)

### 6.3 Tablet (v3)

**PDV · balcão de toque (deitado)**

![PDV · balcão de toque (deitado)](suite-ux-v2/depois-pdv-venda-tablet.annotated.jpg)

**Produção · dia de produção no suporte (deitado)**

![Produção · dia de produção no suporte (deitado)](suite-ux-v2/depois-producao-dia-tablet.annotated.jpg)

**Compras · conferência da nota (em pé)**

![Compras · conferência da nota (em pé)](suite-ux-v2/depois-compras-receber-tablet.annotated.jpg)

### 6.4 Celular (v3)

**Compras · recebimento na doca: câmera, deslizar, vibração**

![Compras · recebimento na doca: câmera, deslizar, vibração](suite-ux-v2/depois-compras-receber-celular.annotated.jpg)

**Produção · no bolso: forno, finalizar lote, timer tocando**

![Produção · no bolso: forno, finalizar lote, timer tocando](suite-ux-v2/depois-producao-celular.annotated.jpg)

**PDV · balcão de bolso: retirada por QR**

![PDV · balcão de bolso: retirada por QR](suite-ux-v2/depois-pdv-celular.annotated.jpg)

**Gestor · pedido por push, aceite no polegar, fora da loja**

![Gestor · pedido por push, aceite no polegar, fora da loja](suite-ux-v2/depois-gestor-celular.annotated.jpg)

**Marketing e B.I. · aprovar anúncio e olhar os números**

![Marketing e B.I. · aprovar anúncio e olhar os números](suite-ux-v2/depois-marketing-bi-celular.annotated.jpg)

**Shopman Apps · lista + busca única com câmera**

![Shopman Apps · lista + busca única com câmera](suite-ux-v2/depois-hub-celular.annotated.jpg)


---

## 7. A trava de não-regressão

"Nenhuma funcionalidade pode regredir" vira mecanismo no CI:

1. **Inventário funcional como contrato.** Cada tela ganha
   `surfaces/<app>/tests/inventory/<tela>.inventory.ts`: ações (rótulo e tecla), filtros,
   visões, estados, tempo real, permissões. Um teste monta a tela e confere que cada item está
   acessível por papel e nome, inclusive dentro do ⋯ e do painel de filtros, **em cada perfil
   de dispositivo** (desktop, tablet, celular). O apêndice A é o rascunho.
2. **"Mover, nunca remover".** Todo PR da reforma traz a tabela "função de hoje → onde ficou",
   por dispositivo. Sem ela, não entra na fila.
3. **Testes atuais intactos**: unitários, e2e, sondas ao vivo do PDV, `guardrails.*` do kit.
   Seletores por papel e nome.
4. **Retrato antes/depois** por tela e por dispositivo com o `test:visual` que já existe
   (só regera baseline quem tem o Chromium da CI, numa sessão só).
5. **Travas de forma**: `guardrails.primitives` (sem botão, busca, overlay e segmentado à mão fora
   do kit), `guardrails.palette` (só tokens) e `guardrails.navigation` (§4.4).

---

## 8. Work packages

Mesma numeração do SUITE-UX-PLAN. Cada WP é um PR (ou um por app quando passar de ~800 linhas).
**Ordem aprovada: kit primeiro, Gestor piloto, PDV por último.**

| WP | o quê | depende de | risco |
|---|---|---|---|
| **UX-5** tipografia e status | `op-*` em CSS; `status.ts`; trava de paleta | — | baixo |
| **UX-8** primitivas no kit | uma cópia só de Button, Dialog, Sheet, Popover, Input, Textarea, Badge; apagar as 7 árvores; overlays à mão migram | — | médio |
| **UX-12** contexto e navegação *(novo)* | `useOperatorContext`, `RailItem` com `to`, `OperatorUpButton`, `useListContext`, `useUnsavedGuard`, `appUrl()` para os 8 apps, títulos, trava de navegação | UX-8 | médio |
| **UX-6** campo, vazio, carregando | `UiField`, `UiEmpty`, `UiSkeleton`, `UiAlert` | UX-8 | baixo |
| **UX-2** cabeçalho único e busca única | rail v3 com seções, cabeçalho único, `OperatorSearch` com alcance, `UiSegmentedControl`, `UiMenu`, `UiBulkBar`; estado na URL | UX-12 | médio |
| **UX-10** sino, ao vivo, atalhos | `NotificationBell` único, `OperatorLiveStatus`, `OperatorShortcutsHelp` | UX-2 | baixo |
| **UX-13** dispositivos *(novo)* | anatomia de celular (barra de cima + seções embaixo) e tablet (divisão lista/detalhe) no kit; câmera, vibração, compartilhar, NFC; app a app, na ordem aprovada | UX-2, UX-12 | médio |
| **UX-9** telas ricas | PDV, Cozinha, Produção sobre a anatomia v3, com retrato antes/depois por dispositivo | UX-13 | **alto** |
| **UX-7** (2ª metade) Shopman Apps com estado | projeção de estado por app no `hub.py`; tiles limpos com deep link | UX-10 | baixo |
| **UX-11** busca na suíte | alcance "App" e "Suíte" da busca única, lendo as buscas que já existem | UX-2 | médio |

Piloto: **Gestor** (o mais perto do padrão e o que mais ganha). **PDV por último** (balcão com
cliente esperando, o que mais depende de teclado).

---

## 9. O que ainda é decisão do dono

1. **Aprovar a v3**: seções no rail com trocador no selo, busca única com alcance, "ao vivo"
   discreto, PDV com teclado numérico recolhido no desktop, Shopman Apps limpo.
2. **Aprovar o papel de cada app em cada dispositivo** (matriz do §3.3) e os recursos do §3.2,
   em especial **localização** (Gestor "fora da loja") e **NFC do crachá**, que pedem
   consentimento e política.
3. **Aprovar o modelo de navegação** (§4), inclusive a troca de endereços que ele implica
   (Compras e Marketing ganham rotas próprias; os antigos respondem 301, como a casa já fez
   em outros apps).

Nada aqui muda dado nem regra de negócio; a reforma é da camada de tela.

---

## Apêndice A: inventário funcional das telas-chave

Rascunho dos arquivos `*.inventory.ts` do §7. Cada linha: função de hoje → onde fica na proposta.
"⋯" é o menu de mais ações da tela. ⚠️ Escrito na v2: onde se lê **"barra de seções"**, na v3 leia
**"rail"** (as seções voltaram para o rail); **"faixa global"** é, na v3, a busca única no cabeçalho
+ o ponto "ao vivo" ao lado do título + Avisos e Atalhos no pé do rail; **"barra de trabalho"** é o
cabeçalho único. No PDV, o teclado numérico da tela recolhe numa faixa quando há teclado físico
(§2.4). O de-para por dispositivo de cada tela está nas legendas das prévias de tablet e celular.

### A.1 Gestor · Pedidos (`orders-nuxt/app/pages/index.vue`)

| hoje | proposta |
|---|---|
| Abas Pedidos · Catálogo · Clientes (com permissão) · Canais (ponto de atenção) | barra de seções, igual; contagem de pedidos na aba |
| Busca código/cliente/item, tecla `/` | barra de trabalho, `UiSearchInput` com `/` |
| Chips de canal com contagem e "Todos" | barra de trabalho, iguais |
| Chips Entrega / Retirada (alternam) | chip "Entrega/retirada" que abre as duas opções com contagem (FilterBar) |
| Ordenar Chegada / Urgência / Mais recentes (menu à mão), tecla `s` | botão Ordenar com `UiMenu`; `s` mantido |
| Quadro/Tabela (à mão), tecla `v` | `UiSegmentedControl`; `v` mantido |
| Exportar CSV, Imprimir, Atualizar (`r`) | ⋯ com as mesmas teclas |
| Ponto "Ao vivo" + faixa "Última leitura útil" | "Ao vivo hh:mm" da faixa global; desatualizado vira aviso padrão |
| Som (3 estados, inclusive bloqueado) e "Ciente" | controles do app na barra de seções |
| Sino de alertas (`AlertsBell`) + sino do kit | um sino só, abas Alertas e Avisos |
| Esc limpa filtros; tecla qualquer reconhece o som | mantidos |
| Card: selecionar, Atender/liberar, tempo, código, canal, cliente, itens, status, pagamento, total, progresso da OP, endereço, troco, maquininha na rua, prazo de confirmação | card padrão com os mesmos campos; status em pílula de tom |
| Card: Aceitar, Avançar/rótulo, Recusar, Acertar entrega, Receber na retirada, Maquininha voltou, Entregador voltou; bloqueio com motivo | botão largo do card (ação principal) + ⋯ do card para as demais; bloqueio tracejado com motivo, igual |
| Card: reimprimir DANFE, link NFC-e não autorizada, negociação iFood | ⋯ do card |
| Lote: Aceitar N, Avançar N, Limpar | `UiBulkBar` |
| Diálogos Recusar (motivos iFood / texto), Acertar dinheiro, Despacho, Entregador voltou | `UiDialog`/`OperatorReasonDialog`, mesmo conteúdo |
| Vazio por coluna, vazio por filtro com "Limpar filtros", erro | `UiEmpty` e `UiAlert` |
| URL guarda filtros; volta do detalhe restaura rolagem e foco | mantido |

### A.2 Gestor · Catálogo (`orders-nuxt/app/pages/catalog.vue`)

| hoje | proposta |
|---|---|
| Busca produto/SKU | `UiSearchInput` com `/` (tecla nova) |
| FilterBar (envio, canal, publicação, venda, estoque, PIM; pré-preenchida por `?surface=&sync=`) | "+ Filtro"; filtro aplicado como chip removível + "Limpar filtros" |
| ColumnPicker (cookie) | "Colunas", igual |
| Chips de coleção com contagem, arrastar para reordenar (ponteiro e setas), ✦ inteligente | segunda linha da barra de trabalho (recortes), mesmas funções |
| Contagens "131 produtos · 4 canais · 4 feeds", Atualizar | contagem do recorte à direita; Atualizar no ⋯ |
| Linha: seleção, foto (lightbox), nome, status, esgotado/pouco estoque, reenviar, SKU, preço, coleção, alça de arrastar | linha padrão com os mesmos itens; status em pílula de tom |
| ⋯ da linha: Editar detalhes, Pausar/Ativar em todos, Ocultar/Exibir, Dados para redes sociais, Reenviar | `UiMenu` da linha, mesmos itens |
| Célula: switch por canal, auditoria da pausa, popover de preço (Enter/Esc, conflito), ponto de sincronização | iguais |
| Lote: superfície, Pausar, Ativar, Preço… (Definir/Ajustar %/Ajustar R$, Revisar→Confirmar), Ocultar, Exibir, prévia de publicação | `UiBulkBar`, mesmas ações e revisão |
| Painel do produto (5 abas, Permitir compra, sugestão por IA, conflito, rodapé "N campos alterados") e `?sku=&tab=` | `UiSheet` com `UiSegmentedControl` nas abas; deep link mantido |
| Esqueleto, erro com retry, vazios, guarda de saída com rascunho | peças padrão; guarda mantida |

### A.3 PDV · Venda (`pos-nuxt/app/pages/index.vue`, `PosProductGrid`, `PosCartPanel`)

| hoje | proposta |
|---|---|
| Rail: Comandas, Sessão de caixa/Abrir caixa, Encomendas (badge), Tela do cliente, Atualizar, saúde do terminal | abas Comandas (F2) · Encomendas · Caixa; "Tela do cliente" e "PDV-01" (saúde: agente, impressora, gaveta, fiscal) como controles do app; Atualizar no popover do terminal |
| Voltar, Balcão/Encomendas, renomear comanda, Cliente F6, Recebimento F7, Quando F8, Liberar comanda (confirmação), PIX aguardando | barra de trabalho da venda, mesmas teclas; Recebimento e Quando só em Encomendas, como hoje |
| Atalhos (?), Últimas vendas | botão de atalhos da faixa global; Últimas vendas na barra de seções |
| Não salvo / descartar e atualizar; edição de pedido com descartar; alerta de fechamento | mantidos, em `UiAlert` padrão |
| Busca F3 (Enter adiciona, Esc sai; letra digitada começa a busca) | campo de 48 px com a dica "Enter adiciona · Esc sai" |
| Densidade Compacta/Padrão/Ampla (popover) | `UiSegmentedControl` visível |
| Chips de coleção | `UiFilterChip`, com a cor da coleção |
| Tiles, esgotado, sem foto, grupo com variantes, pesados, opções | iguais; esgotado em pílula neutra |
| Carrinho: Selecionar Alt+S, linhas, −/+, Remover (confirma + desfazer), detalhes, cartão da cozinha, desfazer envio, teclado de linha (Qtd, Desc %, Desc R$, Obs.), motivo de desconto | iguais |
| Total parcial, Enviar à cozinha F9, Transferir F10, Pagamento F4 / Salvar alterações | iguais; Pagamento como ação primária fixa |
| Todas as teclas globais e bloqueio de teclas sob diálogo/lock; leitor de ticket | mantidos (`utils/keyboardGuard.ts`) |
| Pagamento, resultado, Últimas vendas, sessão, fechamento, encomendas | fora desta prévia; seguem a mesma anatomia no WP-UX-9 |

### A.4 Cozinha · Estação (`kds-nuxt/app/pages/[ref].vue`)

| hoje | proposta |
|---|---|
| Eyebrow Preparo/Saída + nome; lista de estações em página própria | selo + nome; abas "‹ Estações" · Preparo · Saída com contagem |
| Relógio, dia de serviço (select) | barra de seções; dia com o seletor do kit |
| Contadores, busca, densidade, som (bloqueado), Visto, recuperar concluídos (Reabrir), Painel de retirada | contadores e densidade na barra de trabalho; som, Reabrir e Painel como controles do app (48 px); Visto vira aviso de pedido novo com botão grande |
| — | chips Todos · Retirada · Entrega · Atrasados (novos, opcionais) |
| Faixa "A fazer", cancelado com "Recebi o cancelamento", grade por urgência | iguais |
| Ticket: tempo, atraso, itens, sem estoque, Iniciar → Finalizar → Desfazer (5 s), prévia de data futura, bloqueio | iguais, botão de 56 px; status em pílula de tom |
| Toque no ticket abre o detalhe | mantido |
| Saída: Pronto por estação, Entregar/Despachar, ver itens, volumes | na aba Saída, mesma anatomia |
| Vazio "Tudo em dia" + "Ligar o som", busca vazia, erro com e sem dados (âmbar cru) | peças padrão em token |
| SSE + poll 15 s, bipe | mantidos; "Ao vivo" na faixa global |

### A.5 Produção · Produção do dia (`production-nuxt/app/pages/index.vue`, `ProductionStageGrid`)

| hoje | proposta |
|---|---|
| Etapas Planejamento/Preparação/Produção/Expedição, Alt+1…4 | abas da barra de seções com a tecla |
| "5 PRODUZIDOS" + barra 33% | figura de progresso à direita da barra de trabalho |
| Busca `/` | `UiSearchInput` |
| Timers (badge, pulsa) | controle do app na barra de seções; também no ⋯ |
| Sino de alertas próprio | sino da faixa global |
| Atualizar R, Atalhos ? | ⋯ e botão de atalhos |
| Dia (‹ › e seletor), "Todas as bases" | `OperatorPeriodPicker`; chip "Base: todas ▾" |
| — | chips Todos · A confirmar · Produzidos (novos) |
| Chip de unidades comprometidas → diálogo | "N un. encomendadas", abre o mesmo diálogo; também no ⋯ da linha |
| Produzido ✓ → diálogo com Estornar… | valor + "Ver lançamento"; ⋯ da linha com Corrigir e Estornar… |
| "Confirmar ›" → "Quanto foi produzido?" (lote, stepper, Enter, falta de insumo) | botão Confirmar, mesmo diálogo |
| Desatualizado (chip âmbar), vazio com CTA, busca vazia | aviso padrão e `UiEmpty` |

### A.6 Compras · Base › Insumos (`purchase-nuxt/app/pages/index.vue`)

| hoje | proposta |
|---|---|
| Painel/Comprar/Receber/Base em `useState` (sem URL) | abas com URL própria (`/base/insumos`) |
| Abas Insumos/Fornecedores/Custos/Contagem à mão | `UiSegmentedControl` na barra de trabalho |
| Busca crua, checkbox "Atenção" | `UiSearchInput` com `/`; chip "Atenção 120" |
| Pílulas 0 reposições / 120 sem preferencial / 0 estimados | faixa de resumo clicável sob a barra de trabalho |
| Tabela: SKU, insumo (tipo, receitas, chips), estoque, cobertura, mínimo editável, custo-base, status | tabela padrão; lista de receitas por extenso passa para o painel (a linha mostra a contagem) |
| Rodapé Limpar / Salvar mínimos | barra de ação fixa "N mínimos alterados · Limpar · Salvar mínimos" |
| Detalhe: avisos, Permitir revenda → preço → Colocar à venda, "Quando aberto, vira" (form), receitas | painel lateral fixo, mesmas funções |
| Fornecedores, Custos, Contagem (modal à mão de divergências) | mesma anatomia; o modal vira `UiDialog` |
| Sem SSE nem poll; Atualizar só na faixa de status | Atualizar no ⋯; "Ao vivo"/desatualizado na faixa global (WP-UX-10) |

### A.7 Marketing · Campanhas (`marketing-nuxt/app/pages/campaigns.vue`)

| hoje | proposta |
|---|---|
| Seções Hoje · Campanhas · Ofertas e cupons · Plataformas; sino próprio | barra de seções do kit; sino da faixa global |
| Cartão "Encontrar uma campanha": Buscar (debounce, `?q`), Situação, Plataforma, Limpar filtros | barra de trabalho: busca com `/` (mesmo debounce e `?q`), chips Todas/Ligadas/Desligadas com contagem, chip "Plataforma ▾", Limpar filtros |
| "Modelos", "Histórico completo" | ⋯ (com Atualizar e Atalhos) |
| "Nova campanha" | ação primária no fim da barra de trabalho |
| Linha: switch (com permissão e ocupado), linha abre edição, Preparar disparo, Automática, motivo de bloqueio, gatilho → destinos, público, agenda, desempenho | tabela padrão com colunas Campanha, Gatilho, Destinos, Público, Situação, Ações; bloqueio tracejado com motivo |
| Paginação 12/página | rodapé padrão de paginação |
| Faixa "criada" e destaque da linha; vazio, sem resultado, desatualizado; esqueleto; erro | peças padrão |
| Diálogos de edição, disparo e confirmação forte (senha/TOTP) | inalterados |
| Fonte própria, `rounded-xl`, títulos com eyebrow | Instrument Sans e `op-*`, como os outros apps |

### A.8 B.I. · Vendas (`bi-nuxt/app/pages/sales.vue`)

| hoje | proposta |
|---|---|
| 8 seções; período (presets dia → máx + intervalo, ‹ ›) compartilhado entre páginas, fora da URL | barra de seções; período como controle do app e na URL |
| Comparação implícita "vs período anterior" | "Comparar com: período anterior ▾" na barra de trabalho (explícita) |
| — | chips de canal, ⋯ com Exportar CSV, Copiar link do recorte, Atualizar, Fontes dos números (novos) |
| 4 KPIs com delta | `UiStatTile` padrão, delta em pílula de tom e o valor anterior escrito |
| Faturamento por dia (barras, traço do período anterior, pico, histórico Yooga em tom claro, legenda) | cartão de gráfico padrão; cores `--chart-*` |
| Nota de fontes em conflito | ⋯ "Fontes dos números" (ou linha de rodapé no cartão, se o dono preferir à vista) |
| Pedidos por hora, por dia da semana, por canal, top produtos | cartões padrão; canais pelo nome ("PDV", não "pdv") |
| "Carregando…" em texto; "Tentar de novo" de 36 px | `UiSkeleton`; botão de 44 px |

### A.9 Shopman Apps (`hub-nuxt/app/app.vue`)

| hoje | proposta |
|---|---|
| Cabeçalho à mão com "Olá, Admin" | barra de seções com selo, saudação, dia e loja |
| — | busca da suíte larga (ideia §6.2) |
| 8 tiles com ícone, nome e descrição; abre instalado ou no navegador | tile com cor do app, estado, número-chave e deep link; ícone diz se abre instalado ou no navegador |
| — | faixa "Precisa de você" com o urgente dos 8 apps (ideia §6.5, aprovada) |
| Avisos neste dispositivo; versão | cartões de rodapé, mesmo conteúdo |
| Login, bloqueios (estação, sem permissão, indisponível), nenhum app liberado, offline | inalterados; tiles seguem a permissão do operador |

### O que as prévias não desenham (e continua igual)

Diálogos internos (Quanto foi produzido?, Estornar, Recusar com motivos do iFood, Acertar
dinheiro, Despacho, confirmação forte do Marketing), as telas de Pagamento, Resultado, Sessão e
Fechamento do PDV, a Saída da Cozinha, Expedição/Planejamento/Receitas da Produção, Receber e
Comprar do Compras e as outras sete páginas do B.I. Elas entram na mesma anatomia nos WPs, e
o inventário de cada uma é escrito no PR que mexer nela, antes do código.
