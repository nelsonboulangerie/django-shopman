# WP-UX-13: auditoria visual e operacional exaustiva dos apps Nuxt

**Status:** proposto em 06/10/2026, aguardando validação do dono antes da implementação ampla

**Planos pais:** [SUITE-UX-V2-PLAN](SUITE-UX-V2-PLAN.md) e
[WP-UX-8](WP-UX-8-NUXT-UI-REKA-CANONICALIZATION.md)

**Escopo:** Shopman Apps, PDV, Cozinha, Gestor, Produção, Marketing, Compras e B.I.

**Fora do escopo:** Storefront, por decisão anterior do dono, e Admin/Unfold, que segue seu
próprio cânone. A exclusão não autoriza copiar soluções de operador para essas superfícies.

**Regra absoluta:** nenhuma função, estado, opção, ação, informação, permissão, atalho legítimo,
recuperação ou contrato de backend pode regredir. Uma tela não está pronta porque compila ou
porque o caminho feliz cabe num screenshot.

---

## 1. Por que este WP existe

A canonização estrutural do WP-UX-8 não substitui a revisão dedicada de cada produto. Ela
resolve a infraestrutura comum e impede novas divergências, mas não prova que cada composição
local ficou boa. O PDV tornou essa diferença visível: componentes individualmente válidos
foram montados numa geometria que corta conteúdo e deixa ações importantes sem lugar confortável.

O estado de partida tem **59 arquivos de rota**, mais a Central concentrada em `app.vue`, e
**60 superfícies registradas** no ledger. Todas ainda precisam de um aceite visual e operacional
explícito. O pedido deste WP é literal: olhar todos os cantos de todas as telas aplicáveis, em
todos os estados relevantes, com desktop, tablet e celular tratados como contextos diferentes.

Este WP não autoriza “mudar por mudar”. Cada alteração precisa apontar o defeito observado, o
caso de uso prejudicado, a solução proposta e a prova de que não retirou nada.

## 2. Resultado obrigatório

Ao terminar, cada superfície terá:

1. inventário funcional anterior à mudança;
2. capturas reais do estado atual nas matrizes aplicáveis;
3. laudo visual e operacional com severidade e evidência;
4. decisão de componente canônico, inclusive quando a decisão for manter o existente;
5. prévia visual da proposta antes da implementação que altere anatomia;
6. implementação aprovada, com de-para de cada função;
7. testes de função, teclado, toque, foco, acessibilidade e conteúdo extremo;
8. capturas posteriores nos mesmos estados e dimensões;
9. entrada do ledger sem `pending` e sem exceção vaga;
10. relatório de encerramento por app e um relatório final da suíte.

“Revisado” significa que a tela foi realmente aberta e inspecionada. Busca por classes,
typecheck, axe ou teste unitário não contam como revisão visual isoladamente.

## 3. Princípios que governam toda decisão

### 3.1 Anatomia canônica primeiro

O ponto de partida é o componente oficial do Nuxt UI disponível na versão travada da suíte.
O wrapper Shopman conserva tokens, tipografia, copy e especializações operacionais. Reka direto
ou HTML direto só entram quando uma necessidade real não é bem servida pelo Nuxt UI, com motivo
e teste registrados.

Famílias prioritárias:

| necessidade | anatomia de referência | regra Shopman |
|---|---|---|
| ação | `UButton` | hierarquia, loading, disabled e alvo canônicos |
| campo | `UFormField` + `UInput`/`UTextarea` | label, descrição e erro inseparáveis |
| múltipla escolha | `UCheckboxGroup` `variant="card"` | cartão quando as opções precisam ser comparadas |
| busca/seleção dinâmica | `USelectMenu` | busca real, teclado, portal e estado vazio |
| data/período | `UInputDate` + `UPopover` + `UCalendar` | restrições vindas do domínio |
| hora administrativa | `UInputTime` | nunca substituir slots operacionais livres pelo cliente |
| entrega/retirada | `UiSelect` ou cartões sobre slots do servidor | indisponibilidade e motivo permanecem visíveis |
| sequência | `UStepper` | anatomia oficial; tokens não podem deformá-la |
| carregamento | `USkeleton` | forma final, não retângulo arbitrário |
| painel redimensionável | `USplitter` | somente quando o operador ganha controle útil da divisão |
| modal/gaveta/menu | Nuxt UI sobre Reka | foco, portal, Escape, área segura e retorno de foco |

Personalização é bem-vinda quando melhora o caso de uso. Personalização que apenas afasta o
componente da anatomia reconhecível precisa ser removida.

### 3.2 Omotenashi-first por dispositivo

- **Desktop com teclado:** densidade útil, foco inequívoco, atalhos sem colisão, hover como
  complemento e não como requisito, painéis redimensionáveis quando isso reduz trabalho.
- **Tablet com toque e giro:** alvos de 48 a 56 px nas ações de chão, uso consciente de paisagem
  e retrato, painéis ou folhas que não dependem de hover, teclado físico detectado quando plugado.
- **Celular:** tarefa própria, polegar, áreas seguras, teclado virtual, câmera, vibração,
  compartilhamento e localização somente quando trouxerem ganho operacional claro.
- **Estação/kiosk:** tela sempre acesa, orientação coerente, saída recuperável, contraste à
  distância, som e foco resistentes ao ritmo de produção.

Breakpoint é só o começo. Se a mesma composição apenas encolheu, a revisão não terminou.

### 3.3 Uma escala, um significado

- tipografia usa tokens `op-*`; tamanho não muda para fazer um nome caber;
- nomes longos recebem copy curta ou segunda linha deliberada, nunca fonte aleatoriamente menor;
- espaçamento segue uma escala única; exceção de pixel precisa de justificativa registrada;
- cor comunica estado; não decora;
- ação principal é única por momento e não disputa destaque com ação contextual;
- números comparáveis usam alinhamento e dígitos tabulares;
- nenhuma borda, divisor ou sombra nasce apenas para “separar melhor” sem necessidade perceptiva.

## 4. Método de auditoria: tela por tela, estado por estado

### 4.1 Congelamento da referência

Antes de mexer num app:

1. atualizar a frente sobre `main` e registrar o SHA;
2. carregar seed/mocks canônicos e anotar a fonte dos dados;
3. registrar versão do Chromium da CI; somente ela grava baseline oficial;
4. capturar console, requests falhos e estado de conexão;
5. gravar inventário funcional e mapa de atalhos existentes.

Relógio, IDs e dados dinâmicos recebem máscaras determinísticas. Não se mascara layout,
conteúdo, loading, erro, foco ou controles.

### 4.2 Matriz mínima de dimensões

| perfil | dimensões obrigatórias | intenção |
|---|---|---|
| desktop amplo | 1920×1080 | espaço real de escritório/balcão |
| desktop comum | 1440×900 | composição principal |
| desktop baixo | 1366×768 | altura crítica e painel lateral |
| desktop compacto | 1280×800 | negociação entre colunas |
| tablet paisagem | 1180×820 | toque e painéis lado a lado |
| tablet retrato | 820×1180 | troca de anatomia e giro |
| celular padrão | 390×844 | polegar e teclado virtual |
| celular estreito/baixo | 320×568 | reflow e conteúdo extremo |
| zoom | 200% em 1280×800 | WCAG e uso ampliado |

Quando o app suporta tema escuro, a matriz cobre claro e escuro. `forced-colors`, redução de
movimento, aumento de espaçamento de texto e preferência de contraste entram no gate do app.

### 4.3 Estados obrigatórios por superfície

Cada tela marca os estados aplicáveis no ledger:

- carregando inicial e carregamento parcial;
- vazio verdadeiro;
- dados escassos, normais, densos e extremos;
- nomes, valores e observações longos;
- erro recuperável, erro definitivo, conflito, permissão negada e sessão expirada;
- offline, degradado e dado desatualizado;
- ação em progresso, sucesso, falha, repetição idempotente e desfazer;
- modal, popover, menu, tooltip, sheet e combinações de camadas;
- teclado, toque, scanner, câmera e giro, quando aplicáveis;
- item selecionado, múltipla seleção, foco, hover e disabled;
- primeira visita, retorno com estado salvo e deep link.

### 4.4 Inspeção geométrica

O runner de cada app verifica mecanicamente:

- `scrollWidth <= clientWidth` em viewport e painéis que não declaram rolagem horizontal;
- nenhum elemento interativo fora do viewport ou sob chrome fixo;
- nenhuma caixa de texto cortada, sobreposta ou com elipse sem `title`/expansão útil;
- distância mínima de 8 px entre alvos independentes e alvo mínimo conforme o contexto;
- conteúdo final não coberto por barra fixa, safe area ou teclado virtual;
- popover, calendário, select e diálogo acima da camada que os abriu;
- foco visível inteiro, inclusive junto a `overflow: hidden`;
- painéis com `min-width: 0`, limites explícitos e quebra previsível;
- grids sem coluna fantasma, card órfão ou alinhamento dependente do número de itens;
- labels, ícones, atalhos e badges alinhados por baseline consistente;
- skeleton com as mesmas dimensões da forma carregada;
- impressão e tela do cliente sem herdar chrome operacional.

O pixel diff bloqueia mudança não aprovada. O scanner de overflow bloqueia problemas que o diff
pode não tornar óbvios, como o conteúdo existente além da borda da imagem.

### 4.5 Inspeção operacional

Para cada jornada são contados:

- toques/cliques;
- teclas digitadas;
- mudanças de tela;
- consultas externas;
- esperas;
- pontos de decisão sem contexto;
- correções e recuperações;
- distância entre dado, consequência e ação.

O antes e o depois ficam no relatório. Uma proposta visual que piora a jornada é rejeitada.

### 4.6 Mapa de teclado e colisões

Cada app publica um único mapa de comandos com proprietário e escopo. O teste roda em Chrome e
Edge, em Windows e macOS quando o atalho usa modificador do sistema. É obrigatório provar:

- nada dispara enquanto o usuário digita em campo, editor ou busca;
- overlays capturam e devolvem foco corretamente;
- atalho do app não colide com navegador, menu do SO, leitor de tela ou tecla morta do layout;
- comandos globais e locais não executam juntos;
- `event.repeat`, composição IME e teclado ABNT2 são tratados;
- o atalho impresso é o que realmente funciona naquele contexto;
- toda ação continua acessível sem atalho.

Atalho com colisão não é remendado com mais `preventDefault`. Ele é substituído por um comando
reservado e testado.

## 5. Dossiê imediato do PDV

A captura de 06/10 e a leitura do código já comprovam cinco defeitos prioritários. Eles formam
o incremento `WP-UX-13A`, antes da auditoria longa.

### 5.1 Coluna direita e conteúdo cortado

**Evidência atual.** A comanda usa larguras fixas `lg:w-[360px]` e `xl:w-[400px]` em
`pos-nuxt/app/pages/index.vue`. A composição não negocia o espaço com a grade e, na captura de
1360 px, a borda direita da comanda fica fora do viewport. O total do Pagamento é cortado.

**Hipótese aprovada para protótipo.** Sim, é um caso legítimo de Splitter no desktop:

- pane do catálogo e pane da comanda dentro de `USplitter` canônico;
- largura inicial derivada do conteúdo, não de um breakpoint isolado;
- comanda com mínimo que comporte quantidade, nome e valor sem sobreposição;
- catálogo com mínimo que preserve busca, categorias e ao menos três produtos úteis;
- limites sugeridos para a prova: comanda entre 360 e 560 px, nunca além de 42% do espaço útil;
- divisor com nome acessível, foco, setas, Home/End e alvo de ponteiro confortável;
- duplo clique ou ação “Restaurar largura”; valor persistido por terminal e classe de viewport;
- conteúdo responde enquanto o divisor se move; nenhuma pane cria rolagem horizontal oculta;
- tablet e celular **não** herdam o splitter: usam folha/painel adaptado ao toque.

Os números finais saem da prova em 1280, 1366, 1440 e 1920 px. Não se instala um Splitter sobre
uma raiz que já estoura; primeiro são corrigidos `min-width`, overflow e ownership das panes.

### 5.2 Botão de Pagamento

**Evidência atual.** O botão junta ícone, “Pagamento”, `F4`, espaçador, “total” e valor numa única
linha flexível; quando o painel é comprimido, o total sai do viewport.

**Direção para prévia.** Transformar o rodapé da comanda num dock estável:

- total é a informação dominante e tem largura reservada;
- verbo e atalho formam um bloco próprio, sem competir com o número;
- em largura mínima, o dock vira duas linhas deliberadas, nunca conteúdo cortado;
- estado disabled explica o que falta; loading não muda largura;
- F4 permanece funcional e impresso apenas com ponteiro fino;
- valor extremo, desconto, taxa, peso e edição de encomenda entram no teste;
- o botão nunca cobre a última linha ou o editor do item.

### 5.3 “Enviar à cozinha”

**Evidência atual.** A ação disputa o cabeçalho estreito com contagem, seleção, badge, atalho e
estado de envio automático. Isso faz uma etapa operacional parecer encaixada onde sobrou espaço.

**Direção para prévia.** Separar **estado** de **ação**:

- cabeçalho mantém somente identidade e resumo da comanda;
- “N itens aguardam envio” fica junto das linhas afetadas;
- quando há trabalho pendente, uma faixa de ação contextual aparece entre a lista e o dock de
  pagamento: `Enviar N itens à cozinha` + F9;
- depois do envio, a faixa some e o cabeçalho recebe apenas o estado compacto;
- envio automático permanece informação/ajuste secundário, sem aparência de CTA;
- seleção múltipla preserva “enviar somente marcados”; falha e repetição idempotente são testadas;
- no touch, a ação permanece na zona do polegar da folha, sem trocar inesperadamente o CTA final.

### 5.4 Atalho `Alt+S`

**Evidência atual.** `PosCartPanel.vue` instala um listener global que captura `Alt+S` para entrar
na seleção. O conflito relatado pelo dono torna o comando reprovado até nova escolha.

**Ação.** O incremento cria uma tabela real de colisões, identifica qual camada está tomando o
comando e escolhe outra combinação somente depois da prova. Critérios:

- funcionar em Chrome/Edge, Windows/macOS, ABNT2 e teclado internacional;
- não colidir com menu, “Salvar como”, leitor de tela ou busca por digitação;
- não disparar sob modal, campo, terminal travado ou resultado da venda;
- entrar na lista, anunciar o modo e permitir sair só com teclado;
- botão “Selecionar” continua visível e utilizável por toque.

### 5.5 Tipografia e rail

**Evidência atual.** `RailSection.vue` permite 10 ou 11 px; atalho usa 9,5 px; grupos usam 9 px;
“Terminal” é uma composição própria. Na captura, nomes equivalentes parecem pertencer a escalas
diferentes sem que o significado explique a diferença.

**Ação.** Canonizar a anatomia do rail em toda a suíte:

- um token para nome de seção, um para metadado/atalho e um para grupo;
- nenhum app ou item escolhe fonte menor para caber;
- copy curta e `shortLabel` resolvem falta de espaço;
- “Terminal”, Avisos, Atalhos, Bloquear e seções passam pela mesma grade de ícone, label e badge;
- estado ativo mantém respiro lateral e não toca a largura do rail;
- teste visual compara todos os itens na mesma captura, com e sem badge, atenção e atalho.

### 5.6 Gate do incremento PDV imediato

- [ ] nenhuma rolagem horizontal ou corte em 1280×800 e 1366×768;
- [ ] pane direita ajustável no desktop, persistente e controlável por teclado;
- [ ] pagamento legível com `R$ 9.999,99` e nome de ação longo;
- [ ] cozinha tem zona própria, estados pending/loading/success/error e F9;
- [ ] `Alt+S` removido ou aprovado por matriz de colisão;
- [ ] rail usa a mesma escala nos itens equivalentes;
- [ ] fluxo de venda, encomenda, edição, pagamento, resultado e impressão sem regressão;
- [ ] capturas antes/proposta/depois aprovadas pelo dono.

## 6. Execução app por app

Cada bloco abaixo é um sub-WP independente, com branch e PR próprios. O executor começa pelas
rotas listadas e expande o ledger quando encontrar subtela, estado ou composição não registrada.

### 6.1 `WP-UX-13B` — Operator Kit e gates transversais

**Arquivos principais:** `surfaces/operator-kit` e ledger canônico.

Entregas:

- runner único de matriz visual;
- scanner de overflow, clipping, alvo, foco e chrome fixo;
- inventário automático de rotas + variantes declaradas;
- mapa canônico de atalhos e detector de colisões internas;
- tokens únicos de rail, cabeçalho, barra de ação, pane e espaçamento;
- wrapper de Splitter com persistência e comportamento por ponteiro;
- catálogo vivo dos componentes Nuxt UI/Reka adotados;
- relatório que reprova tela não visitada, captura faltante e ledger `pending`.

### 6.2 `WP-UX-13C` — Shopman Apps (`hub-nuxt`)

**Superfície:** `/`, concentrada em `app.vue`.

**Estados:** apps disponíveis, precisa de atenção, avisos do dispositivo, offline, bloqueado,
sem permissão, app indisponível e retorno de deep link.

**Foco da auditoria:** hierarquia dos tiles, busca da suíte, estado sem alarmismo, densidade em
desktop, lista de polegar no celular, PWA instalado versus navegador, teclado, foco, copy e
consistência com o selo dos outros apps.

### 6.3 `WP-UX-13D` — Gestor (`orders-nuxt`)

| rota | superfícies/estados a provar |
|---|---|
| `/` | quadro, tabela, lote, recusa, acerto, despacho, conteúdo denso |
| `/:ref` | resumo, linha do tempo, cliente, pagamento, fiscal e entrega |
| `/catalog` | matriz, painel do produto, preços em lote, coleções e canais |
| `/channels/:ref/catalog` | publicação, disponibilidade, divergência e erro |
| `/customers` | busca, filtros, segmentos e vazio |
| `/customers/:ref` | perfil, pedidos, endereços, preferências e fidelidade |
| `/customers/merges` | candidatos, comparação, confirmação e conflito |
| `/feeds` | canais, feeds, sincronização e falha parcial |
| `/history` | filtros, eventos, detalhe e paginação |
| `/settings` | operação, notificações e canais |
| `/workstations` | lista, detalhe, provisionamento e revogação |

**Foco:** cabeçalho que não quebra, busca/filtros canônicos, tabela útil em mobile, detalhe com
volta contextual, ações de lote, painel ajustável somente onde fizer sentido e atualização SSE.

### 6.4 `WP-UX-13E` — Marketing (`marketing-nuxt`)

| rota | superfícies/estados a provar |
|---|---|
| `/` | decisões, calendário, vazio, bloqueio e dado degradado |
| `/campaigns` | lista, filtros, criar, editar, stepper, revisão e disparo |
| `/announcements/:id` | composição, prévia, destinos, agenda, publicação e resultado |
| `/history` | filtros, detalhe, exportação e desconhecido |
| `/offers` | ofertas, cupons, período, horários e restrições |
| `/platforms` | conexões, catálogo, conta, teste e desconexão |
| `/scheduled` | calendário, lista e cancelamento |
| `/second-control/:ref` | código, dispositivo confiável, expirado e sucesso |
| `/templates` | lista, busca, prévia, aplicação e indisponibilidade |

**Foco:** confirmar em tela real a canonização já iniciada, card groups, calendário/período,
slots, selects pesquisáveis, stepper oficial, previews sem vazamento, texto extremo e campanhas
com muitos destinos. Nada é aceito apenas porque o wrapper está correto.

### 6.5 `WP-UX-13F` — B.I. (`bi-nuxt`)

| rota | superfícies/estados a provar |
|---|---|
| `/` | KPIs, alertas e fontes |
| `/sales` | faturamento, horas, canais e produtos |
| `/cash` | resumo, diferenças, movimentos e turnos |
| `/customers` | segmentos, retenção e RFM |
| `/profiles` | lista, perfil, pedidos e preferências |
| `/forecast` | demanda, confiança, produtos e exceções |
| `/scenarios` | lista, editor e comparação |
| `/explore` | construtor, tabela, gráfico e visão salva |

**Foco:** período na URL, legenda e tooltip acessíveis, contraste das séries, comparação sem
depender de cor, tabela/gráfico responsivos, números sem truncar, fontes de dados claras,
exportar/compartilhar e uma leitura de celular realmente útil, não oito gráficos espremidos.

### 6.6 `WP-UX-13G` — Compras (`purchase-nuxt`)

**Rota única:** `/`, que contém pelo menos Painel, Comprar, Receber, Base/Insumos,
Base/Fornecedores, Base/Custos, Base/Contagem, detalhe de insumo, detalhe de fornecedor,
mínimos em lote, NF, recebimento manual, divergência, devolução e scanners.

**Foco:** tornar cada subtela endereçável no ledger e na URL; câmera e scanner; teclado virtual;
giro; conferência lado a lado no tablet; gesto de recebimento no celular; campos canônicos;
tabelas que viram tarefa móvel; rascunho e divergência; unidade, custo e quantidade sem ambiguidade.

O arquivo único de quase 3 mil linhas não pode esconder superfícies da auditoria. Cada branch
interna e cada drawer relevante recebe uma entrada e uma captura própria.

### 6.7 `WP-UX-13H` — Produção (`production-nuxt`)

| rota | superfícies/estados a provar |
|---|---|
| `/` | abertura, produção, confirmação, compromissos e falta |
| `/board` | resumo, fullscreen, offline e recuperação |
| `/close` | pendências, revisão, confirmação e conclusão |
| `/mise-en-place` | lista, item e confirmação |
| `/plan` | sugestões, manual, revisão e commit |
| `/quality` | fila, inspeção, lote e exceção |
| `/recipes` | lista, filtros e vazio |
| `/recipes/new` | identidade, ingredientes, procedimento e revisão |
| `/recipes/:ref` | fórmula, versões, publicação e arquivo |
| `/recipes/:ref/edit` | edição, rascunho e saída protegida |
| `/recipes/compare` | seleção e comparação |
| `/reports` | visão, período e exportação |
| `/settings` | estação, etiquetas e defaults |
| `/timers` | ativos, criar, tocando e histórico |

**Foco:** mãos ocupadas, farinha/luvas, alvos, leitor de etiqueta, timer audível e vibratório,
contraste à distância, fullscreen recuperável, teclado numérico, falta de insumo, rascunho e
orientação. Desktop de planejamento, tablet de chão e celular de bolso têm tarefas diferentes.

### 6.8 `WP-UX-13I` — Cozinha (`kds-nuxt`)

| rota | superfícies/estados a provar |
|---|---|
| `/` | estações, vazio e bloqueio |
| `/:ref` | preparo, saída, detalhe, concluídos, som bloqueado e avalanche |
| `/pickup` | aguardando, pronto, vazio, offline e tela cheia |

**Foco:** leitura a distância, quatro a seis tickets úteis em vez de miniaturização, prioridade,
tempo, som, toque rápido, luvas, giro, tela sempre acesa, avalanche, perda de SSE, retorno após
offline e saída segura do kiosk.

### 6.9 `WP-UX-13J` — PDV completo (`pos-nuxt`)

Depois do incremento imediato, o PDV inteiro recebe fechamento:

| rota | superfícies/estados a provar |
|---|---|
| `/` | comandas, abertura, busca, venda, editor, cozinha, pagamento, resultado e impressão |
| `/display` | ocioso, carrinho, pagamento e resultado |
| `/preorders` | hoje, busca, vazio, erro e paginação |
| `/preorders/:ref` | resumo, retirada, pagamento, edição e entrega |
| `/session` | caixa fechado/aberto, gaveta, movimentos, reembolsos e crédito |
| `/session/closing` | contagem, diferença, revisão, lacre e conclusão |
| `/session/report` | resumo, movimentos e impressão |
| `/settings/card-machines` | lista e edição |
| `/settings/kitchen` | roteamento e envio automático |
| `/settings/printers` | lista, teste e edição |
| `/settings/seating` | áreas, mesas, edição e conflito |
| `/settings/shortcuts` | referência e busca |
| `/settings/terminal` | identidade, hardware e saúde |

**Foco:** teclado e scanner sem colisões, operação contínua, Splitter desktop, folha touch,
catálogo denso sem truncamento enganoso, comanda, cozinha, pagamento, troco, PIX, maquininha,
impressão, offline, bloqueio, gerente e segundo monitor. O fluxo principal é repetido com mouse,
somente teclado e somente toque.

### 6.10 `WP-UX-13K` — fechamento transversal

- ledger sem `pending`;
- nenhum app com cópia local não justificada de primitiva canônica;
- mapa de atalhos sem colisão;
- relatório de exceções com responsável e teste;
- contact sheet final por app e dispositivo;
- comparação de jornadas antes/depois;
- lint, typecheck, build, unit/component, E2E, axe e matriz visual verdes;
- documentação de criação de novo app atualizada para herdar automaticamente os gates.

## 7. Ordem e política de PRs

1. `13A`: correções urgentes do PDV, após prévia aprovada;
2. `13B`: runner, tokens e gates transversais;
3. `13C` a `13I`: um app por vez; quando o diff exceder cerca de 800 linhas, dividir por jornada,
   nunca por camada técnica invisível ao revisor;
4. `13J`: fechamento completo do PDV sobre a infraestrutura já provada;
5. `13K`: fechamento, guia de novo app e trava definitiva.

Cada app tem um dono por vez. Baselines oficiais não são regenerados em sessões concorrentes.
Cada mudança aprovada segue a esteira completa: commit, push, PR e fila no mesmo turno.

## 8. Artefatos obrigatórios de cada PR

| artefato | conteúdo |
|---|---|
| inventário | função anterior, novo lugar e prova de paridade |
| laudo | achado, severidade, contexto, evidência e solução |
| decisão canônica | Nuxt UI, Reka ou HTML, e aparência manter/refinar/adotar |
| contact sheet | antes e depois nas dimensões aplicáveis |
| estados | matriz executada, inclusive extremos e falhas |
| teclado/toque | comandos, foco, colisões e gestos |
| a11y | axe, zoom, reflow, contraste, leitor e text spacing |
| desempenho | bundle, hidratação, INP e listas densas |
| exceções | motivo operacional, responsável e teste que impede piora |
| testes | comandos e saídas factuais |

## 9. Critérios de aceite final

- [ ] as 60 superfícies atuais e todas as subtelas descobertas foram abertas e registradas;
- [ ] nenhum item permanece `pending` no ledger;
- [ ] não existe overflow, sobreposição ou corte não deliberado na matriz;
- [ ] nenhuma ação fixa cobre conteúdo ou safe area;
- [ ] toda família usa anatomia canônica ou exceção comprovada;
- [ ] desktop, tablet e celular têm tarefa e composição próprias quando aplicáveis;
- [ ] todos os atalhos passaram pela matriz de colisão;
- [ ] rail, cabeçalho, busca, filtros, ações e feedback falam a mesma linguagem visual;
- [ ] PDV tem pane direita ajustável e pagamento integralmente legível;
- [ ] cozinha do PDV tem ação contextual confortável e estado inequívoco;
- [ ] nenhum contrato funcional ou de backend regrediu;
- [ ] cada app possui E2E do caminho principal e da recuperação crítica;
- [ ] baselines foram gravados pelo Chromium da CI e aprovados pelo dono;
- [ ] o gerador de novo app já nasce com wrappers, ledger, matriz e gates deste WP.

## 10. Definição de “não passou despercebido”

O executor não pode concluir um app dizendo apenas que “os testes passaram”. O relatório final
precisa listar cada rota, cada variante, cada viewport e cada estado inspecionado. Se algo não
pôde ser aberto, fica explicitamente vermelho com motivo e próximo passo; não vira silêncio.

O objetivo não é uma coleção de telas perfeitas isoladamente. É um único produto em que o
operador reconhece a anatomia, entende a consequência de cada gesto e recebe a melhor forma da
tarefa para o dispositivo que está usando.
