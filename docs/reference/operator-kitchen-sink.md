# Operator Kitchen Sink canônico

## Revisão adversarial contra Nuxt UI 4.11.3 (06/10/2026)

A continuação cobre também o shell operacional do catálogo, navegação funcional,
ação persistente no footer oficial de DashboardPanel, modal, popover e Slideover,
readonly real, seleção parcial da tabela, reordenação e estados endereçáveis.
O catálogo inteiro recebe auditoria de contraste e geometria nos temas claro e
escuro nos nove viewports oficiais; estados adicionais e overlays interativos
rodam em desktop e 320px. A medição não é um certificado de cada pixel: limites
de cobertura e exceções são declarados abaixo, não escondidos por testes verdes.

Uma inspeção visual de toque encontrou o checkbox inflado e o switch circular.
A regra de tamanho mínimo agora exclui os desenhos desses controles. O tema
amplia somente o alvo por pseudo-elemento, preservando trilho, thumb e indicador
oficiais; a auditoria mede esse alvo e um teste clica fora do desenho do switch.
Seleção parcial usa o estado indeterminate oficial, não somente boolean.

Referência: documentação oficial corrente e implementação instalada. A versão
estável foi conferida também no registry npm. Esta revisão não certifica a
migração das telas existentes nem transforma o laboratório em catálogo completo.

| Achado                                                               | Correção ou limite explícito                                                                                |
| -------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------- |
| Sidebar independente aninhada em DashboardSidebar                    | Removida. Apenas DashboardGroup, DashboardSidebar e DashboardPanel gerenciam layout e estado.               |
| Conteúdo da navbar no slot central, oculto no mobile                 | Título pela prop oficial; ações no slot right; seletor contextual na DashboardToolbar.                      |
| Navegação repetida na toolbar e botão sem comportamento              | Toolbar agora representa contexto, não repete o menu global; botão sem ação removido.                       |
| Sidebar sem collapse e IDs implícitos                                | Collapse oficial, NavigationMenu recebe collapsed e painéis têm IDs determinísticos.                        |
| Resize handle com role presentation                                  | Removida alteração de semântica; eventos encaminhados ao handle oficial.                                    |
| Form state vazio e controles desconectados                           | Estado reativo, names, v-model, validate e submit reais, herméticos.                                        |
| Switch sem descrição e checkbox com API legada                       | NuxtSwitch e NuxtCheckbox diretos, com label e description oficiais.                                        |
| Descrição do Switch 4.11.3 não associada por ARIA no componente puro | Slot description e aria-describedby explícitos, sem substituir o controle. Regressão testada no consumidor. |
| Título da navbar truncado em 320px                                   | Quebra de linha no slot de título e toolbar contextual, sem reduzir a fonte.                                |
| Modal montado separado do acionador                                  | NuxtModal direto com acionador no slot default e ações nos slots oficiais.                                  |
| Tabela dentro de card com padding e duas rolagens                    | Body sem padding; uma área de scroll; apenas header sticky; footer participa do fluxo.                      |
| Seleção da tabela indexada pela posição                              | getRowId usa a ref estável, preservando identidade ao filtrar ou ordenar.                                   |
| Segunda tabela prometia transformação em cards sem implementá-la     | Copy corrigida para rolagem explícita; removido padding ao redor da tabela.                                 |
| Stepper com adaptação local de anatomia                              | Exemplo usa NuxtStepper direto, com navegação não linear explicitamente demonstrada.                        |
| Off-line, rede lenta e reconexão simulados por copy                  | São cenários visuais, não teste de rede. O laboratório demonstra useConnectivity real separadamente.        |

As escolhas aprovadas de superfície branca, outline, padding, tipografia e alvos
operacionais são tema, configurado na layer. Não autorizam implementações locais
de foco, portal, resize, navegação, validação ou seleção. `OperatorSplitter`
continua acrescentando persistência e atributos ARIA ao Splitter oficial; não é
uma substituição visual. O shell operacional do catálogo foi refeito com
DashboardGroup, DashboardSidebar, DashboardPanel, DashboardNavbar e
DashboardToolbar; isso não certifica os shells históricos das apps existentes.
Os exercícios de fetched/infinite data, rede simulada e periféricos ainda
não estão completos. A página única também não substitui receitas de telas
dedicadas e testadas: esses limites permanecem trabalho em aberto.

Fontes: [DashboardGroup](https://ui.nuxt.com/docs/components/dashboard-group),
[DashboardSidebar](https://ui.nuxt.com/docs/components/dashboard-sidebar),
[DashboardNavbar](https://ui.nuxt.com/docs/components/dashboard-navbar),
[DashboardPanel](https://ui.nuxt.com/docs/components/dashboard-panel),
[Card](https://ui.nuxt.com/docs/components/card),
[PageCard](https://ui.nuxt.com/docs/components/page-card),
[Form](https://ui.nuxt.com/docs/components/form),
[Switch](https://ui.nuxt.com/docs/components/switch),
[Table](https://ui.nuxt.com/docs/components/table),
[Modal](https://ui.nuxt.com/docs/components/modal).

O card padrão é `NuxtCard` outline: branco no tema claro (`bg-card`), borda,
sem sombra. Formulários e exemplos de controles usam esse padrão. No tema escuro,
a superfície acompanha `--card`, sem impor branco. Header, body e footer usam
padding de 1rem, inclusive no desktop. Cards solid mantêm texto invertido também
na descrição. Em ponteiro fino, Button, Input, Select e SelectMenu preservam a
geometria compacta oficial do Nuxt UI para o tamanho escolhido. Em ponteiro grosso,
uma regra compartilhada amplia o alvo interativo para 44px (48px em tablet touch),
sem transformar essa dimensão em altura visual universal no desktop. Textarea mantém
a tipografia, mas altura multilinha. Outros tamanhos exigem necessidade demonstrada,
não escolha estética arbitrária.

### Contrato compacto de Cards

O Card não é um container universal. A situação escolhe a primitiva e a anatomia;
nenhuma tela recria borda, divisor, padding ou sombra dentro de `NuxtCard`.

| Situação                                            | Componente e variante             | Anatomia                                                                           |
| --------------------------------------------------- | --------------------------------- | ---------------------------------------------------------------------------------- |
| unidade de trabalho ou formulário                   | `NuxtCard` `outline`              | corpo único quando basta; header para identidade/estado; footer somente para ações |
| bloco subordinado dentro de painel ou overlay       | `NuxtCard` `soft`                 | corpo compacto, sem competir com a superfície principal                            |
| grupo que exige limite e mudança de plano           | `NuxtCard` `subtle`               | header/body/footer oficiais, ainda sem sombra                                      |
| destino navegável ou destaque semântico             | `NuxtPageCard`                    | `to` para navegação; `highlight` apenas quando a cor comunica o estado             |
| falha, aviso, confirmação ou informação transitória | `NuxtAlert`                       | nunca embrulhar Alert em Card só para fabricar fundo                               |
| vazio, bloqueio ou ausência de resultado            | `NuxtEmpty`                       | não fingir conteúdo com Card vazio                                                 |
| carregamento                                        | `NuxtSkeleton` na geometria final | não criar um Card genérico que muda de forma ao carregar                           |

`NuxtCard` mantém os quatro variants oficiais (`outline`, `soft`, `subtle` e
`solid`). `solid` fica restrito a contexto invertido comprovado; não é recurso de
decoração. `NuxtPageCard` oferece ainda `ghost`, `naked`, orientação, link,
`highlight` e `spotlight`; no operador, spotlight não acrescenta informação e não
entra em unidades de trabalho. Um Card complexo não ganha header/body/footer por
cerimônia: os slots só existem quando criam regiões com responsabilidades
distintas. Isso economiza espaço sem retirar hierarquia.

O Operator Kitchen Sink é a superfície executável do design system das apps de
operador. Ele não é uma galeria paralela: a página real
`surfaces/kitchensink-nuxt` compõe `OperatorKitchenSink`, cujas fixtures,
componentes, tokens e receitas continuam em `surfaces/operator-kit`.

## Contrato

- Nuxt UI fornece anatomia, estados ARIA, foco e comportamento base.
- O `operator-kit` traduz tokens e acrescenta apenas contratos estruturais ou comportamento operacional compartilhado.
- A app Kitchen Sink não declara primitiva, token ou layout próprio.
- Diferença apenas estética não cria variante.
- Componente local de domínio pode existir; shell, navegação, page header, toolbar, splitter, overlay ou token visual novo precisa entrar no cânone ou no registro forte de exceções.
- Fixtures são estáticas e determinísticas. Nenhum cenário depende do Django ou de dados vivos.

## Léxico mínimo

| Nome                       | Responsabilidade                                                | Composição permitida                     | Não usar para                       |
| -------------------------- | --------------------------------------------------------------- | ---------------------------------------- | ----------------------------------- |
| `OperatorAppRoot`          | raiz Nuxt UI, toaster e contexto comum                          | uma vez na casca do app                  | shell ou navegação                  |
| `OperatorOfficeShell`      | sidebar, navbar, toolbar e painel Nuxt UI                       | gestão, análise, cadastros               | fluxo contínuo de chão              |
| `OperatorOperationalShell` | chrome estável e barra de ação                                  | PDV, Cozinha, Produção                   | dashboard administrativo            |
| `OperatorPage`             | container, header, body, links e aside                          | página com fluxo de leitura              | substituir pane de operação         |
| `OperatorPageHeader`       | título, posto, busca, status, filtros e ações                   | dentro de shell operacional              | inventar cabeçalho local            |
| `OperatorSuiteRail`        | navegação da suíte por seções                                   | um modelo de seção por app               | navegação de página                 |
| `OperatorSectionBar`       | alternativa responsiva ao rail                                  | celular e tablet em pé                   | segunda fonte de navegação          |
| `OperatorSplitter`         | panes redimensionáveis, teclado e persistência                  | lista/detalhe e editor/prévia no desktop | duas colunas comprimidas no celular |
| Nuxt UI puro               | card, alert, empty, skeleton, table, form, badge, tabs, popover | composição direta com tokens do kit      | wrapper que apenas renomeia         |

`UiButton` conserva somente a tradução legada de hierarquia e as alturas
operacionais já usadas. Efeitos, gradientes e sombra skeuomórfica sem consumidor
foram removidos. Eles não são variantes semânticas.

## Anatomias

### Escritório

`OperatorAppRoot > OperatorOfficeShell > OperatorPage`. A sidebar contém a
navegação do domínio; navbar contém identidade e ação principal; toolbar contém
filtros ou tabs. O corpo usa seções com títulos explícitos. `aside` explica a
decisão sem competir com a ação.

### Operação

`OperatorAppRoot > OperatorOperationalShell`. Navegação, `OperatorPageHeader`,
conteúdo e barra de ação são regiões distintas. A ação atual permanece estável;
o conteúdo usa `min-width: 0`, rolagem própria e safe area.

### Split view

`OperatorSplitter` é a única anatomia de panes simultâneas. Desktop preserva
limites, teclado e tamanho salvo. Em celular, a mesma necessidade vira sequência
ou sheet. Não se reduz tipografia para manter duas panes.

### Formulários e fluxos

`NuxtForm` + `NuxtFormField` organizam campos. Ajuda esclarece formato ou
consequência. Ações ficam no final e seguem a hierarquia primária, secundária,
destrutiva. Fluxos com etapas usam `UiStepper` e `useNextFocus`; a etapa atual
declara `data-focus-target`.

### Listas, tabelas, detalhes e filas

- lista: identidade, estado, dado para decidir e próximo ato;
- tabela: comparação entre colunas; abaixo do limite útil, vira cartões;
- detalhe: título, estado, fatos, histórico e ações, nesta ordem;
- fila: exceções humanas primeiro, depois ordenação, restante e vazio;
- dashboard: resposta e consequência antes do gráfico; métrica sem contexto não é dashboard.

### Overlays

Há cinco receitas, não uma largura por tela: confirmação, formulário curto,
workspace, detalhe lateral e captura em tela cheia. Popover é informação breve.
Sheet é detalhe ou ação responsiva. Modal não substitui página.

Modal, detalhe lateral e drawer usam `bg-card`; popover, menus e tooltip usam
`bg-popover` no tema da layer: branco no tema claro, superfície correspondente no
escuro. O backdrop continua translúcido, sem cobrir o contexto com branco opaco.
Alerts usam `subtle` por padrão. Exemplos têm ícone e
dismiss funcional; trocar o cenário reabre o aviso. Dismiss de um aviso não cancela
a operação nem altera o estado. Toast usa `useToast` e o toaster do `OperatorAppRoot`.
Quando um Alert oferece ação, o botão usa `outline` e a mesma cor semântica do
Alert; ações neutras não apagam a gravidade de um aviso `error`, `warning` ou
`info`. Na caixa de Avisos esse contrato vale para abrir, reconhecer, atualizar e
marcar como lido.

`NuxtKbd` usa globalmente a variante oficial `soft`. `NuxtChip` indicativo usa
`2xl` por padrão; o estado compacto On/Off usa `xl` para não competir com o texto.
O contador numérico de Avisos usa a extensão temática `4xl` (16 px, texto de 12
px), pois o componente oficial termina em `3xl` e esse tamanho não comporta
contagens com dois caracteres. Todos continuam sendo os componentes Nuxt UI, sem
bolinha ou tecla recriada por CSS local.

A busca usa `DashboardSearch` e `DashboardSearchButton`, com `Meta+K` oficial e
`Kbd`. O menu demonstra filhos e rodapé; o rodapé da página oferece referências.
A navegação interna rola apenas o corpo do `DashboardPanel`, não o chrome fixo.
`useScrollspy` acompanha as seções visíveis. O header recebe `collapsed` do
`DashboardSidebar` e conserva apenas o ícone quando recolhido.

Menus verticais com filhos declaram `popover` explicitamente: `collapsed` sozinho
não expõe os filhos. No catálogo, o popover usa `mode: 'click'` para suportar clique
e teclado, sem depender de hover; os itens conservam nomes acessíveis recolhidos.

## Laboratório visual e contratos oficiais

O início do catálogo mostra os três papéis aprovados lado a lado: unidade de
trabalho `outline`, bloco subordinado `soft` e contexto delimitado `subtle`, além
de ação principal em largura total, divisão 1:2 e largura pelo conteúdo. Não há
Card dentro de Card para simular profundidade, nem sombra decorativa.

Badges demonstram `solid`, `outline`, `soft` e `subtle` com cores semânticas,
primária e neutra. Grupos de checkbox e radio demonstram `list`, `card` e `table`.
Select e SelectMenu usam popovers oficiais, incluindo busca e item indisponível.
Calendários usam data fixa e intervalo fixo, sem depender do relógio ou do backend.

A tabela compõe seleção, expansão, badges, sorting, filtro, total de coluna,
paginação e rolagem externa. Reordenação manual tem exercício próprio com drag
and drop e alternativa equivalente por teclado/toque. Fetch e infinite scroll
devem consumir os contratos de dados e reconciliação do kit; não exigem nova
estética nem um mock de rede vivo no catálogo.

`useNextFocus` acompanha mudança de etapa. `usePendingAction` demonstra uma
resposta simulada concluída explicitamente, com bloqueio de repetição.
`useConnectivity` mostra a rede real do dispositivo separada dos estados de
fixture. O shell usa DashboardGroup/Sidebar/Panel/Navbar/Toolbar e a página usa
Container/Page/Header/Body/Aside oficiais.

O tema é definido em `operator-theme.css` e `app/app.config.ts` na layer:
`@theme` fornece tipografia e geometria, `--ui-*` traduz cores e superfícies para
o contrato oficial, e slots globais mantêm legibilidade dos alertas. O painel
não soma padding ao container da página. Ícones usam `@nuxt/icon`, SVG e coleções
locais; o scan inclui fixtures TypeScript. Fontes usam `@nuxt/fonts` com
Instrument Sans. Não se introduz CDN manual, fonte por componente ou paleta local.

Referências: [índice para agentes](https://ui.nuxt.com/llms.txt),
[design system](https://ui.nuxt.com/docs/getting-started/theme/design-system),
[variáveis CSS](https://ui.nuxt.com/docs/getting-started/theme/css-variables) e
[customização por slots](https://ui.nuxt.com/docs/getting-started/theme/components).

## Cenários determinísticos

O seletor do Kitchen Sink grava o cenário na URL. Os cenários cobrem `loading`,
`empty`, `error`, `offline`, `reconnecting`, `slow-network`, `readonly`,
`forbidden`, `success` e `extreme-content`, além do normal. A matriz do ledger
mantém também seleção, overlays, teclado, toque, conteúdo longo e estados salvos.

- loading inicial usa skeleton da anatomia final;
- atualização parcial preserva o dado anterior;
- offline diz o que ainda funciona;
- reconexão mantém o último dado confirmado;
- rede lenta bloqueia repetição ambígua do gesto;
- readonly mostra dados e explica por que a ação não está disponível;
- forbidden não vaza dado protegido;
- erro recuperável oferece próximo passo; erro terminal nomeia a saída;
- sucesso confirma a nova fonte da verdade;
- conteúdo extremo quebra linha, nunca reduz tipografia para caber.

## Matriz das necessidades reais

O inventário em `operator-component-ledger.json` contém 60 telas e 241 variantes
dos oito apps operacionais. O Kitchen Sink não promove cada diferença histórica;
condensa as necessidades abaixo.

| Apps      | Necessidade comprovada                  | Solução canônica                                              |
| --------- | --------------------------------------- | ------------------------------------------------------------- |
| Central   | launcher, atenção cross-app, avisos     | office dashboard, attention list, metric tile                 |
| PDV       | venda densa, carrinho, pagamento, caixa | operational split workspace, pane/sheet responsivo, step flow |
| Cozinha   | tickets, urgência, fila por telefone    | operational queue, live/stale status, action sheet            |
| Gestor    | fila, board, bulk, detalhe, catálogo    | queue recipe, table/cards, splitter, side detail              |
| Produção  | estágios, planejamento, QC, receitas    | operational grid, progress header, step flow, editor split    |
| Marketing | decisão, composição, revisão, agenda    | office list, workspace, form/stepper, preview split           |
| Compras   | compra, recebimento, contagem, cadastro | dashboard, master/detail, exception flow, scanner overlay     |
| B.I.      | KPIs, explicação, gráfico, comparação   | analytical dashboard, semantic palette, table fallback        |

Redundâncias que devem convergir: sete adapters locais de rail/barra, headers
manuais, shells de settings/list-detail, larguras próprias de modal, cards feitos
por classes, tabelas sem fallback e page states locais. Visualização de domínio
continua local quando carrega semântica, mas consome paleta e tipografia do kit.

## Exceções inevitáveis

Exceção exige `app`, `surface`, caso de uso, limitação concreta do cânone,
alternativas rejeitadas, justificativa, responsável e teste. Os registros
executáveis ficam em `operator-layout-exceptions.json`,
`operator-token-exceptions.json` e `operator-global-shortcut-exceptions.json`.

As exceções funcionais aceitas são: segundo monitor público do PDV, painel
público de retirada, quadro distante de Produção, mídia física de
impressão/etiqueta e captura por câmera, scanner, áudio ou periférico. Elas
mudam audiência, meio ou API do dispositivo. Não autorizam nova estética.

Marketing preview, colunas do Gestor, editor acoplado de Compras, gráficos do
B.I., page headers, menus e rails não justificam anatomia paralela.

## Como consumir

1. Estenda `../operator-kit` e mantenha SSR. Use `OperatorAppRoot` na casca.
2. Escolha `OperatorOfficeShell` ou `OperatorOperationalShell` pela tarefa, não pelo app.
3. Componha Nuxt UI diretamente quando ele já resolve o contrato.
4. Use as receitas do Kitchen Sink para página, estado e responsividade.
5. Se faltar capacidade recorrente em pelo menos dois casos reais, evolua o kit, acrescente cenário determinístico, documentação e teste.
6. Se a necessidade for realmente específica, registre a exceção forte antes do componente ou token.

## Desenvolvimento, preview e dispositivos reais

```bash
cd surfaces/operator-kit && npm ci
cd ../kitchensink-nuxt && npm ci && npm run dev
# http://127.0.0.1:3009
```

A surface é `deployment: preview`: participa de CI, Dependabot, PWA e imagem
standalone, mas não entra em `operator-office`, no ingress ou na Central. Isso
impede que o catálogo afete a saúde das apps operacionais. O preview usa a
permissão exclusiva `backstage.view_operator_kitchen_sink`, sem concessão a
grupos; apenas superusuário entra até uma concessão explícita.

```bash
docker build -f surfaces/Dockerfile.surface \
  --build-arg SURFACE=kitchensink-nuxt -t shopman-kitchensink .
cloudflared tunnel --url http://127.0.0.1:3009
```

Para testar num dispositivo real, abra a URL temporária no telefone/tablet,
autentique uma conta autorizada e percorra teclado externo, toque, rotação, safe
areas, zoom do sistema, overlays, perda/retorno da rede e textos longos. O túnel
deve apontar para o ambiente local; não reutilize cookies do domínio vivo em
`trycloudflare.com`.

## Gates

```bash
make test-surface-registry test-surface-versions test-operator-ux
python scripts/check_operator_component_ledger.py --app kitchensink --require-complete
cd surfaces/operator-kit && npm run lint && npm test && npm run typecheck && npm run catalog:build && npm run test:visual
cd ../kitchensink-nuxt && npm run lint && npm test && npm run typecheck && npm run build
```

Os gates derivam as apps do registry, bloqueiam layout estrutural novo, listener
global, import direto de Reka/Nuxt UI fora do kit, crescimento das dívidas de
controle, e qualquer custom property fora da lista exata de exceções. A matriz
visual oficial cobre 1920×1080, 1440×900, 1366×768, 1280×800, 1180×820 touch,
820×1180 touch, 390×844, 320×568 e 1280×800 a 200%.

## Revisão adversarial de 06/10/2026

Esta seção substitui promessas por estado medido. O que está _implementado_,
_verificado_, _pendente_ e _exceção justificada_ está separado abaixo.

**Implementado e verificado**

- Uma única fonte decide a casca por estado: `operatorSurfaceGate` (kit, puro),
  coberta por teste unitário para `authenticated`, `forbidden`, `checking`,
  `anonymous`, `expired`, travado, PIN temporário e erro de rede. A casca do
  catálogo e o molde `new-surface` consomem a mesma função; `checking` não
  empilha mais a tela de senha e `canIdentify` sozinho não libera a página.
- Hierarquia de título: o catálogo tem **um** `h1`, o do `PageHeader` oficial
  ("Anatomia canônica do operador"). O `DashboardNavbar` não repete o título da
  página; a identidade da janela vem da capability PWA.
- Locale pt-BR do Nuxt UI ligado em `OperatorAppRoot` (`pt_br`): barra lateral,
  alertas, calendário e menus internos saem em português. O gate visual usa os
  rótulos oficiais ("Abrir/Recolher/Expandir barra lateral").
- Alertas dinâmicos declaram papel: erro é `role="alert"`; sucesso, informação,
  offline, reconexão e rede lenta são `role="status"`.
- Grupos de checkbox/radio distinguem as três variantes na própria legenda.
- Lista reordenável usa `ul`/`li` (semântica de lista), alternativa por teclado
  e região `aria-live` que anuncia a nova posição.
- Receitas recorrentes com `NuxtInputNumber` (decimal), `NuxtInputDate`,
  `NuxtInputTime`, `NuxtDropdownMenu` (inclui destrutiva marcada e desfazer) e
  `NuxtFileUpload` (importação e captura). São componentes oficiais, sem wrapper.
- `UiToolbar` e `UiModal` foram removidos: tinham teste e documentação, nenhum
  consumidor de produção. O léxico da página reflete o que existe.
- O reporter visual registra **todas** as capturas de um teste (antes só a
  primeira) e o ledger deriva `capture` do caminho real
  `kitchensink/<surface>/<scenario>/<state>/<viewport>/<tema>.png`. O runner
  `run_operator_visual.py` fixa `OPERATOR_VISUAL_EVIDENCE_ROOT` na raiz do
  ledger, e a surface `kitchensink:home` declara `runner`.

**Pendente (não declarado pronto)**

- Cobertura da suíte: o ledger auditorado tem **9 apps, 61 superfícies, 254
  variantes e 60 superfícies `pending`**; só `kitchensink:home` está `migrated`.
  O fechamento global (`--require-complete`) continua vermelho por desenho.
- `OperatorOfficeShell`, `OperatorOperationalShell` e `OperatorAppRoot` **não são
  consumidos pelas oito apps reais**; elas ainda usam o chrome histórico
  (`OperatorSuiteRail`, `OperatorPageHeader`). O catálogo demonstra o alvo, mas a
  adoção app a app, sem regressão, segue aberta.
- Wrappers sem consumidor de produção permanecem no kit e ainda precisam de
  decisão (adotar ou apagar): `UiSearchInput`, `UiDateField`, `UiDateRangeField`,
  `UiDateTimeField`, `UiTimeField`, `UiTimeRangeField`, `UiStepper`. A receita do
  catálogo usa o componente Nuxt UI direto; o wrapper só entra se um app real o
  consumir.
- Evidência visual pixel a pixel **não é gate**: não há baseline versionada
  comparada na CI. O que existe é captura por matriz, scanner de geometria e
  auditoria de acessibilidade; regenerar baseline exige o Chromium do
  `browser-lock.json`, não o Chromium local.
- A matriz completa de nove viewports não foi executada nesta revisão; a
  infraestrutura está pronta, a execução integral é etapa própria.

**Exceções justificadas**

As exceções de token (`receipt-print`, `far-field-board`) e de layout seguem
registradas em `operator-token-exceptions.json` e
`operator-layout-exceptions.json`, com app, caso de uso, limitação canônica,
alternativas rejeitadas, justificativa, dono e teste.
